from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import time

class DeploymentStatus(str, Enum):
    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"

class DeploymentCreate(BaseModel):
    service_id: str
    commit_hash: Optional[str] = None
    commit_msg: Optional[str] = "Update inference worker"

class Deployment(BaseModel):
    id: str
    service_id: str
    commit_hash: str
    commit_msg: str
    image_tag: str
    status: DeploymentStatus = DeploymentStatus.BUILDING
    build_logs: str = ""
    created_at: float = Field(default_factory=time.time)

