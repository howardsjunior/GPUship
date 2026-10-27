from pydantic import BaseModel, Field
from typing import Optional, List
import time

class ServiceCreate(BaseModel):
    name: str = Field(..., description="Service display name")
    repo_url: str = Field(..., description="Git repository URL")
    branch: str = Field(default="main", description="Target branch")
    dockerfile_path: str = Field(default="Dockerfile", description="Path to Dockerfile")
    health_endpoint: str = Field(default="/health", description="Health check endpoint path")
    gpu_spec: str = Field(default="rtx4090", description="Target GPU identifier (e.g. rtx4090, h100_pcie)")
    price_ceiling_hr: float = Field(default=1.50, description="Max hourly price allowed")
    idle_timeout_seconds: int = Field(default=30, description="Seconds of zero jobs before scale to zero")
    keep_warm_count: int = Field(default=0, description="0 = scale to zero, 1 = warm standby")

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    branch: Optional[str] = None
    gpu_spec: Optional[str] = None
    price_ceiling_hr: Optional[float] = None
    idle_timeout_seconds: Optional[int] = None
    keep_warm_count: Optional[int] = None

class Service(BaseModel):
    id: str
    name: str
    repo_url: str
    branch: str = "main"
    dockerfile_path: str = "Dockerfile"
    health_endpoint: str = "/health"
    gpu_spec: str = "rtx4090"
    price_ceiling_hr: float = 1.50
    idle_timeout_seconds: int = 30
    keep_warm_count: int = 0
    active_deployment_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

