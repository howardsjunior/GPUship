from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum
import time

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class JobCreate(BaseModel):
    input: Dict[str, Any] = Field(default_factory=dict, description="Inference input payload")
    idempotency_key: Optional[str] = Field(None, description="Client idempotency key for deduplication")

class Job(BaseModel):
    id: str
    service_id: str
    idempotency_key: Optional[str] = None
    status: JobStatus = JobStatus.QUEUED
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    result_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    assigned_pod_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    latency_ms: Optional[float] = None
    execution_attempts: int = 0
    cold_start_incurred: bool = False
    estimated_cost: float = 0.0

class JobResponse(BaseModel):
    job_id: str
    service_id: str
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    latency_ms: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    pod_state: Optional[str] = None

