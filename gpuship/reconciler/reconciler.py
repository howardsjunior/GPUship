"""
Scale-to-Zero and Pod Lifecycle Reconciler for GPUShip
Runs an autonomous continuous reconciliation loop that matches durable queue demand
to Lium GPU capacity, enforces scale-to-zero on idle timeout, and avoids race conditions.
"""
import asyncio
import time
import logging
from typing import Dict, Any, Optional

from ..config import RECONCILER_INTERVAL_SECONDS, GPU_CATALOG
from ..models import Pod, PodState, ColdStartBreakdown, JobStatus, Service
from ..db import database as db
from ..queue.durable_queue import DurableQueue
from ..lium.driver import LiumDriver

logger = logging.getLogger("gpuship.reconciler")

class Reconciler:
    def __init__(self, queue: DurableQueue, driver: LiumDriver):
        self.queue = queue
        self.driver = driver
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._processing_jobs: set = set()

    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self._reconcile_loop())
        logger.info("GPUShip Reconciler started.")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("GPUShip Reconciler stopped.")

    async def _reconcile_loop(self):
        while self.running:
            try:
                services = db.list_services()
                for service in services:
                    await self._reconcile_service(service)
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}", exc_info=True)
            
            await asyncio.sleep(RECONCILER_INTERVAL_SECONDS)

    async def _reconcile_service(self, service: Service):
        service_id = service.id
        active_pod = db.get_active_pod_for_service(service_id)
        queued_count = db.count_queued_jobs(service_id)

        # 1. Update pod provisioning / cold-start status from Lium provider
        if active_pod and active_pod.state in (PodState.PROVISIONING, PodState.BOOTING, PodState.LOADING_MODEL):
            provider_status = await self.driver.get_pod_status(active_pod.lium_pod_id)
            new_state = provider_status.get("state")
            
            if new_state and new_state != active_pod.state:
                updates = {"state": new_state}
                if "cold_start" in provider_status:
                    updates["cold_start"] = ColdStartBreakdown(**provider_status["cold_start"])
                if "ip_address" in provider_status and provider_status["ip_address"]:
                    updates["ip_address"] = provider_status["ip_address"]
                
                db.update_pod(active_pod.id, updates)
                active_pod = db.get_pod(active_pod.id)
                
                stage_labels = {
                    PodState.BOOTING: "Lium VM provisioned. Pulling container image...",
                    PodState.LOADING_MODEL: "Container started. Loading model weights into GPU VRAM...",
                    PodState.READY: f"Model loaded! Healthcheck passed. GPU worker online ({active_pod.cold_start.total_cold_start_seconds}s total cold start)."
                }
                if new_state in stage_labels:
                    db.log_activity(
                        service_id=service_id,
                        event_type="POD_STATE_CHANGE",
                        level="INFO",
                        message=stage_labels[new_state],
                        metadata={"state": new_state.value, "cold_start": active_pod.cold_start.model_dump()}
                    )

        # 2. If we need a pod and don't have one active -> Provision one
        needs_capacity = (queued_count > 0) or (service.keep_warm_count > 0)
        if needs_capacity and (not active_pod or active_pod.state == PodState.TERMINATED):
            await self._provision_pod_for_service(service)
            return

        # 3. If pod is READY and there are queued jobs -> Dispatch job
        if active_pod and active_pod.state == PodState.READY:
            if queued_count > 0:
                # Cancel any idle countdown immediately
                if active_pod.idle_started_at is not None:
                    db.update_pod(active_pod.id, {"idle_started_at": None})
                    active_pod.idle_started_at = None

                next_job = db.get_next_queued_job(service_id)
                if next_job and next_job.id not in self._processing_jobs:
                    self._processing_jobs.add(next_job.id)
                    asyncio.create_task(self._dispatch_job(service, active_pod, next_job))
                    return

            # 4. If pod is READY and queue is empty -> Check idle timer for scale-to-zero
            elif queued_count == 0 and service.keep_warm_count == 0:
                now = time.time()
                if active_pod.idle_started_at is None:
                    # Start idle countdown
                    db.update_pod(active_pod.id, {"idle_started_at": now})
                    active_pod.idle_started_at = now
                    db.log_activity(
                        service_id=service_id,
                        event_type="IDLE_COUNTDOWN_STARTED",
                        level="INFO",
                        message=f"Queue empty. Idle countdown started ({service.idle_timeout_seconds}s timeout).",
                        metadata={"idle_timeout_seconds": service.idle_timeout_seconds}
                    )
                else:
                    idle_duration = now - active_pod.idle_started_at
                    if idle_duration >= service.idle_timeout_seconds:
                        # Scale to zero!
                        await self._scale_pod_to_zero(service, active_pod)

    async def _provision_pod_for_service(self, service: Service):
        service_id = service.id
        gpu_spec = service.gpu_spec
        gpu_info = GPU_CATALOG.get(gpu_spec, GPU_CATALOG["rtx4090"])
        
        # Enforce price ceiling
        if gpu_info["hourly_rate"] > service.price_ceiling_hr:
            logger.warning(f"GPU {gpu_spec} rate (${gpu_info['hourly_rate']}/hr) exceeds ceiling (${service.price_ceiling_hr}/hr)")
            db.log_activity(
                service_id=service_id,
                event_type="PRICE_CEILING_EXCEEDED",
                level="ERROR",
                message=f"Cannot provision: GPU rate ${gpu_info['hourly_rate']}/hr exceeds ceiling ${service.price_ceiling_hr}/hr.",
                metadata={"rate": gpu_info["hourly_rate"], "ceiling": service.price_ceiling_hr}
            )
            return

        deployment = None
        if service.active_deployment_id:
            deployment = db.get_deployment(service.active_deployment_id)
        
        image_tag = deployment.image_tag if deployment else f"gpuship/{service_id}:latest"
        dep_id = deployment.id if deployment else "dep_default"

        db.log_activity(
            service_id=service_id,
            event_type="PROVISION_REQUESTED",
            level="INFO",
            message=f"Queue demands GPU. Renting {gpu_info['name']} on Lium...",
            metadata={"gpu": gpu_spec, "hourly_rate": gpu_info["hourly_rate"]}
        )

        pod_data = await self.driver.rent_pod(service_id, dep_id, gpu_spec, image_tag)
        
        pod = Pod(
            id=f"pod_{pod_data['lium_pod_id']}",
            service_id=service_id,
            deployment_id=dep_id,
            provider="lium",
            lium_pod_id=pod_data["lium_pod_id"],
            gpu_type=gpu_spec,
            ip_address=pod_data.get("ip_address"),
            port=pod_data.get("port", 8000),
            state=PodState.PROVISIONING,
            rented_at=pod_data["rented_at"],
            hourly_rate=gpu_info["hourly_rate"],
            total_billed_seconds=0.0
        )
        db.create_pod(pod)

    async def _scale_pod_to_zero(self, service: Service, pod: Pod):
        service_id = service.id
        now = time.time()
        billed_seconds = max(1.0, now - (pod.rented_at or now))
        
        db.update_pod(pod.id, {"state": PodState.TERMINATING})
        db.log_activity(
            service_id=service_id,
            event_type="SCALE_TO_ZERO",
            level="INFO",
            message=f"Idle timer elapsed ({service.idle_timeout_seconds}s). Releasing Lium GPU pod. Compute scaled to $0/hr.",
            metadata={"billed_seconds": round(billed_seconds, 1), "gpu": pod.gpu_type}
        )

        await self.driver.release_pod(pod.lium_pod_id)
        
        db.update_pod(pod.id, {
            "state": PodState.TERMINATED,
            "released_at": now,
            "total_billed_seconds": billed_seconds
        })

    async def _dispatch_job(self, service: Service, pod: Pod, job: Any):
        job_id = job.id
        try:
            # Set pod busy
            db.update_pod(pod.id, {"state": PodState.PROCESSING, "current_job_id": job_id})
            
            # Determine if this request incurred a cold start
            cold_start_incurred = False
            if pod.cold_start and pod.cold_start.total_cold_start_seconds > 0:
                # If job was created before or while pod was booting
                if job.created_at <= (pod.rented_at or time.time()) + pod.cold_start.total_cold_start_seconds:
                    cold_start_incurred = True

            self.queue.mark_running(job_id, cold_start_incurred=cold_start_incurred)
            start_time = time.time()

            # Execute via Lium driver
            result = await self.driver.execute_inference(
                lium_pod_id=pod.lium_pod_id,
                payload=job.input_payload,
                workload_type=service.name
            )

            latency_ms = (time.time() - start_time) * 1000.0
            
            # Calculate job compute cost
            # Fraction of GPU hour used by execution time
            per_sec_rate = pod.hourly_rate / 3600.0
            exec_sec = latency_ms / 1000.0
            estimated_cost = round(exec_sec * per_sec_rate, 6)

            self.queue.mark_completed(
                job_id=job_id,
                result_payload=result,
                latency_ms=latency_ms,
                estimated_cost=estimated_cost
            )

        except Exception as e:
            logger.error(f"Error executing job {job_id} on pod {pod.id}: {e}", exc_info=True)
            self.queue.mark_failed(job_id, str(e))

        finally:
            self._processing_jobs.discard(job_id)
            # Pod is free again
            db.update_pod(pod.id, {
                "state": PodState.READY,
                "current_job_id": None,
                "idle_started_at": time.time()  # Start idle timer right after job completion
            })

