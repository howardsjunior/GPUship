from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum
import time

class PodState(str, Enum):
    OFFLINE = "OFFLINE"
    PROVISIONING = "PROVISIONING"         # Renting VM from Lium
    BOOTING = "BOOTING"                   # Pulling image & starting container
    LOADING_MODEL = "LOADING_MODEL"       # Loading weights into GPU VRAM
    READY = "READY"                       # Health check passed, ready for inference
    PROCESSING = "PROCESSING"             # Actively executing an inference request
    IDLE_COOLING = "IDLE_COOLING"         # Queue is empty, waiting out idle countdown
    TERMINATING = "TERMINATING"           # Cleaning up & releasing back to Lium
    TERMINATED = "TERMINATED"

class ColdStartBreakdown(BaseModel):
    provision_seconds: float = 0.0
    container_boot_seconds: float = 0.0
    model_load_seconds: float = 0.0
    total_cold_start_seconds: float = 0.0

class Pod(BaseModel):
    id: str
    service_id: str
    deployment_id: Optional[str] = None
    provider: str = "lium"
    lium_pod_id: Optional[str] = None
    gpu_type: str = "rtx4090"
    ip_address: Optional[str] = None
    port: int = 8000
    state: PodState = PodState.OFFLINE
    rented_at: Optional[float] = None
    released_at: Optional[float] = None
    total_billed_seconds: float = 0.0
    hourly_rate: float = 0.45
    cold_start: ColdStartBreakdown = Field(default_factory=ColdStartBreakdown)
    last_heartbeat: float = Field(default_factory=time.time)
    current_job_id: Optional[str] = None
    idle_started_at: Optional[float] = None

