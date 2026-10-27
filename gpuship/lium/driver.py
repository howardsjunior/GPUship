"""
Lium Cloud Compute Driver & Emulator
Handles pod provisioning, lifecycle management, and scale-to-zero interactions with Lium.
Supports both live Lium API communication and high-fidelity realistic emulation for demonstrations.
"""
import asyncio
import time
import uuid
import logging
from typing import Dict, Any, Optional, List
import httpx

from ..config import LIUM_API_KEY, LIUM_API_URL, LIUM_SIMULATION_MODE, GPU_CATALOG
from ..models import PodState, ColdStartBreakdown

logger = logging.getLogger("gpuship.lium")

class LiumDriver:
    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None, simulation: bool = True):
        self.api_key = api_key or LIUM_API_KEY
        self.api_url = api_url or LIUM_API_URL
        self.simulation = simulation if self.api_key == "" else (LIUM_SIMULATION_MODE and not bool(api_key))
        # In-memory tracking for simulation mode
        self._simulated_pods: Dict[str, Dict[str, Any]] = {}
        # Demo speed multiplier: 1.0 = normal quick-demo (few seconds per stage), 0.2 = super fast
        self.speed_multiplier = 0.5

    async def rent_pod(self, service_id: str, deployment_id: str, gpu_spec: str, image_tag: str) -> Dict[str, Any]:
        """
        Rent a GPU pod on Lium for the specified service.
        Idempotent: generates a unique provider rental ID.
        """
        gpu_info = GPU_CATALOG.get(gpu_spec, GPU_CATALOG["rtx4090"])
        hourly_rate = gpu_info["hourly_rate"]
        
        if not self.simulation and self.api_key:
            return await self._live_rent_pod(service_id, deployment_id, gpu_spec, image_tag, hourly_rate)
        else:
            return await self._simulated_rent_pod(service_id, deployment_id, gpu_spec, image_tag, hourly_rate)

    async def release_pod(self, lium_pod_id: str) -> bool:
        """
        Idempotently release a rented pod back to Lium's capacity pool.
        """
        if not self.simulation and self.api_key:
            return await self._live_release_pod(lium_pod_id)
        else:
            return await self._simulated_release_pod(lium_pod_id)

    async def get_pod_status(self, lium_pod_id: str) -> Dict[str, Any]:
        """
        Poll the current status of a pod from Lium.
        """
        if not self.simulation and self.api_key:
            return await self._live_get_status(lium_pod_id)
        else:
            return await self._simulated_get_status(lium_pod_id)

    async def execute_inference(self, lium_pod_id: str, payload: Dict[str, Any], workload_type: str = "whisper") -> Dict[str, Any]:
        """
        Send an inference job to the worker running on the pod.
        """
        if not self.simulation and self.api_key:
            pod_info = await self.get_pod_status(lium_pod_id)
            ip = pod_info.get("ip_address")
            port = pod_info.get("port", 8000)
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"http://{ip}:{port}/inference", json=payload)
                res.raise_for_status()
                return res.json()
        else:
            return await self._simulated_execute_inference(lium_pod_id, payload, workload_type)

    # ---------------- SIMULATION IMPLEMENTATION ----------------
    async def _simulated_rent_pod(self, service_id: str, deployment_id: str, gpu_spec: str, image_tag: str, hourly_rate: float) -> Dict[str, Any]:
        pod_id = f"lium-node-{uuid.uuid4().hex[:8]}"
        now = time.time()
        
        pod_record = {
            "lium_pod_id": pod_id,
            "service_id": service_id,
            "deployment_id": deployment_id,
            "gpu_spec": gpu_spec,
            "image_tag": image_tag,
            "hourly_rate": hourly_rate,
            "ip_address": f"10.244.{hash(pod_id) % 250 + 1}.{hash(pod_id) % 254 + 1}",
            "port": 8000,
            "state": PodState.PROVISIONING,
            "created_at": now,
            "rented_at": now,
            "stage_started_at": now,
            "cold_start": {
                "provision_seconds": 0.0,
                "container_boot_seconds": 0.0,
                "model_load_seconds": 0.0,
                "total_cold_start_seconds": 0.0
            }
        }
        self._simulated_pods[pod_id] = pod_record
        logger.info(f"[Lium Emulator] Rented pod {pod_id} ({gpu_spec} @ ${hourly_rate}/hr)")
        return pod_record

    async def _simulated_release_pod(self, lium_pod_id: str) -> bool:
        if lium_pod_id in self._simulated_pods:
            self._simulated_pods[lium_pod_id]["state"] = PodState.TERMINATED
            self._simulated_pods[lium_pod_id]["released_at"] = time.time()
            logger.info(f"[Lium Emulator] Released pod {lium_pod_id} back to pool.")
            return True
        return False

    async def _simulated_get_status(self, lium_pod_id: str) -> Dict[str, Any]:
        pod = self._simulated_pods.get(lium_pod_id)
        if not pod:
            return {"state": PodState.TERMINATED}
        
        now = time.time()
        state = pod["state"]
        stage_duration = now - pod["stage_started_at"]
        
        # Timing constants (adjusted by speed multiplier for snappy interactive presentation)
        PROVISION_TIME = 2.0 * self.speed_multiplier
        BOOT_TIME = 2.5 * self.speed_multiplier
        MODEL_LOAD_TIME = 2.5 * self.speed_multiplier
        
        if state == PodState.PROVISIONING:
            if stage_duration >= PROVISION_TIME:
                pod["cold_start"]["provision_seconds"] = round(stage_duration, 2)
                pod["state"] = PodState.BOOTING
                pod["stage_started_at"] = now
                logger.info(f"[Lium Emulator] Pod {lium_pod_id} finished provisioning, starting container.")
                
        elif state == PodState.BOOTING:
            if stage_duration >= BOOT_TIME:
                pod["cold_start"]["container_boot_seconds"] = round(stage_duration, 2)
                pod["state"] = PodState.LOADING_MODEL
                pod["stage_started_at"] = now
                logger.info(f"[Lium Emulator] Pod {lium_pod_id} container up, loading model weights into VRAM.")
                
        elif state == PodState.LOADING_MODEL:
            if stage_duration >= MODEL_LOAD_TIME:
                pod["cold_start"]["model_load_seconds"] = round(stage_duration, 2)
                total = (
                    pod["cold_start"]["provision_seconds"] +
                    pod["cold_start"]["container_boot_seconds"] +
                    round(stage_duration, 2)
                )
                pod["cold_start"]["total_cold_start_seconds"] = round(total, 2)
                pod["state"] = PodState.READY
                pod["stage_started_at"] = now
                logger.info(f"[Lium Emulator] Pod {lium_pod_id} is READY! Total cold start: {total}s")
                
        return pod

    async def _simulated_execute_inference(self, lium_pod_id: str, payload: Dict[str, Any], workload_type: str) -> Dict[str, Any]:
        # Realistic inference simulation based on workload type
        # Simulate realistic GPU compute latency (e.g. 300ms - 800ms)
        compute_delay = 0.45 * self.speed_multiplier
        await asyncio.sleep(compute_delay)
        
        now_iso = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        prompt = payload.get("prompt") or payload.get("text") or payload.get("audio_url") or "standard test input"
        
        if "whisper" in workload_type.lower() or "audio" in workload_type.lower():
            return {
                "workload": "whisper-large-v3-turbo",
                "transcription": f"Transcribed speech from input: '{prompt}'. [Word count: 32, confidence: 0.984]",
                "language": "en",
                "duration_seconds": 4.2,
                "gpu_device": "NVIDIA RTX 4090 (Compute Cap 8.9)",
                "vram_allocated_mb": 4210,
                "completed_at": now_iso
            }
        elif "diffusion" in workload_type.lower() or "image" in workload_type.lower() or "sd" in workload_type.lower():
            return {
                "workload": "stable-diffusion-xl-turbo",
                "prompt": prompt,
                "image_url": f"https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80",
                "seed": 42910842,
                "steps": 4,
                "guidance_scale": 7.5,
                "vram_allocated_mb": 9150,
                "completed_at": now_iso
            }
        else: # LLM
            return {
                "workload": "llama-3.1-8b-instruct-vllm",
                "prompt": prompt,
                "completion": f"Response from GPUShip Llama-3 worker: Processing '{prompt}' on Lium GPU node. Scale-to-zero active with 0 idle overhead.",
                "tokens_generated": 68,
                "tokens_per_second": 94.2,
                "vram_allocated_mb": 15400,
                "completed_at": now_iso
            }

    # ---------------- LIVE LIUM API IMPLEMENTATION ----------------
    async def _live_rent_pod(self, service_id: str, deployment_id: str, gpu_spec: str, image_tag: str, hourly_rate: float) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "name": f"gpuship-{service_id[:8]}",
            "gpu_type": gpu_spec,
            "image": image_tag,
            "ports": [8000],
            "tags": {"project": "gpuship", "service_id": service_id, "deployment_id": deployment_id}
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{self.api_url}/pods", json=payload, headers=headers)
            res.raise_for_status()
            data = res.json()
            return {
                "lium_pod_id": data["id"],
                "service_id": service_id,
                "deployment_id": deployment_id,
                "gpu_spec": gpu_spec,
                "image_tag": image_tag,
                "hourly_rate": hourly_rate,
                "ip_address": data.get("ip_address"),
                "port": 8000,
                "state": PodState.PROVISIONING,
                "rented_at": time.time(),
                "cold_start": {"provision_seconds": 0, "container_boot_seconds": 0, "model_load_seconds": 0, "total_cold_start_seconds": 0}
            }

    async def _live_release_pod(self, lium_pod_id: str) -> bool:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.delete(f"{self.api_url}/pods/{lium_pod_id}", headers=headers)
            return res.status_code in (200, 204, 404)

    async def _live_get_status(self, lium_pod_id: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(f"{self.api_url}/pods/{lium_pod_id}", headers=headers)
            if res.status_code == 404:
                return {"state": PodState.TERMINATED}
            res.raise_for_status()
            data = res.json()
            # Map Lium status to PodState
            status_map = {
                "provisioning": PodState.PROVISIONING,
                "starting": PodState.BOOTING,
                "running": PodState.READY,
                "stopped": PodState.TERMINATED
            }
            return {
                "lium_pod_id": lium_pod_id,
                "state": status_map.get(data.get("status", "").lower(), PodState.READY),
                "ip_address": data.get("ip_address")
            }

