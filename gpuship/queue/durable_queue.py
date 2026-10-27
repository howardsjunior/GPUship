"""
Durable Asynchronous Queue for GPUShip
Ensures zero dropped requests, idempotency deduplication, and wake signals for the reconciler.
"""
import asyncio
import uuid
import time
import logging
from typing import Optional, Dict, Any, Tuple

from ..models import Job, JobCreate, JobStatus
from ..db import database as db

logger = logging.getLogger("gpuship.queue")

class DurableQueue:
    def __init__(self):
        self._wake_events: Dict[str, asyncio.Event] = {}

    def get_wake_event(self, service_id: str) -> asyncio.Event:
        if service_id not in self._wake_events:
            self._wake_events[service_id] = asyncio.Event()
        return self._wake_events[service_id]

    async def enqueue(self, service_id: str, job_create: JobCreate) -> Tuple[Job, bool]:
        """
        Enqueues a job durably into SQLite.
        Returns (Job, is_new: bool).
        If idempotency key matches an existing job, returns existing job.
        """
        if job_create.idempotency_key:
            existing = db.get_job_by_idempotency_key(service_id, job_create.idempotency_key)
            if existing:
                logger.info(f"Idempotency hit for key={job_create.idempotency_key}, returning existing job={existing.id}")
                return existing, False

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = time.time()
        
        job = Job(
            id=job_id,
            service_id=service_id,
            idempotency_key=job_create.idempotency_key,
            status=JobStatus.QUEUED,
            input_payload=job_create.input,
            created_at=now,
            execution_attempts=0,
            cold_start_incurred=False
        )
        
        # Persist before acknowledging
        db.create_job(job)
        db.log_activity(
            service_id=service_id,
            event_type="JOB_ENQUEUED",
            level="INFO",
            message=f"Job {job_id} enqueued into durable queue.",
            metadata={"job_id": job_id, "idempotency_key": job_create.idempotency_key}
        )
        
        # Signal reconciler to check queue and provision if needed
        wake_event = self.get_wake_event(service_id)
        wake_event.set()
        
        return job, True

    def get_job(self, job_id: str) -> Optional[Job]:
        return db.get_job(job_id)

    def get_next_job(self, service_id: str) -> Optional[Job]:
        return db.get_next_queued_job(service_id)

    def mark_assigned(self, job_id: str, pod_id: str):
        db.update_job(job_id, {
            "status": JobStatus.ASSIGNED,
            "assigned_pod_id": pod_id
        })

    def mark_running(self, job_id: str, cold_start_incurred: bool = False):
        db.update_job(job_id, {
            "status": JobStatus.RUNNING,
            "started_at": time.time(),
            "cold_start_incurred": cold_start_incurred
        })

    def mark_completed(self, job_id: str, result_payload: Dict[str, Any], latency_ms: float, estimated_cost: float = 0.0):
        db.update_job(job_id, {
            "status": JobStatus.SUCCEEDED,
            "result_payload": result_payload,
            "completed_at": time.time(),
            "latency_ms": latency_ms,
            "estimated_cost": estimated_cost
        })
        job = db.get_job(job_id)
        if job:
            db.log_activity(
                service_id=job.service_id,
                event_type="JOB_SUCCEEDED",
                level="INFO",
                message=f"Job {job_id} completed successfully in {latency_ms:.1f}ms.",
                metadata={"job_id": job_id, "latency_ms": latency_ms, "cost": estimated_cost}
            )

    def mark_failed(self, job_id: str, error_message: str):
        job = db.get_job(job_id)
        attempts = (job.execution_attempts + 1) if job else 1
        
        if attempts < 3:
            # Recoverable retry
            db.update_job(job_id, {
                "status": JobStatus.QUEUED,
                "error_message": f"Attempt {attempts} failed: {error_message}",
                "execution_attempts": attempts,
                "assigned_pod_id": None
            })
            if job:
                db.log_activity(
                    service_id=job.service_id,
                    event_type="JOB_RETRY",
                    level="WARNING",
                    message=f"Job {job_id} failed attempt {attempts}, requeueing for retry.",
                    metadata={"error": error_message}
                )
        else:
            # Terminal failure
            db.update_job(job_id, {
                "status": JobStatus.FAILED,
                "error_message": f"Terminal failure after {attempts} attempts: {error_message}",
                "execution_attempts": attempts,
                "completed_at": time.time()
            })
            if job:
                db.log_activity(
                    service_id=job.service_id,
                    event_type="JOB_FAILED",
                    level="ERROR",
                    message=f"Job {job_id} suffered terminal failure.",
                    metadata={"error": error_message}
                )

