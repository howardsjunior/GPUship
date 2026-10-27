"""
GPUShip Main Server & Gateway Entry Point
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import BASE_DIR, GATEWAY_HOST, GATEWAY_PORT
from .db import database as db
from .queue.durable_queue import DurableQueue
from .lium.driver import LiumDriver
from .reconciler.reconciler import Reconciler
from .gateway import routes

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("gpuship")

# Global subsystem singletons
queue = DurableQueue()
driver = LiumDriver()
reconciler = Reconciler(queue=queue, driver=driver)

# Inject singletons into routes module
routes.queue_instance = queue
routes.driver_instance = driver

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing GPUShip durable database...")
    db.init_db()

    # Seed flagship templates if not already present
    seed_templates = [
        {
            "id": "svc_whisper_default",
            "name": "Faster-Whisper Audio Transcription",
            "repo_url": "https://github.com/gpuship-templates/whisper-fastapi",
            "gpu_spec": "rtx4090",
            "rate": 0.45,
            "idle_timeout": 30,
            "commit": "c7f93a1",
            "msg": "Faster-Whisper large-v3 optimized for RTX 4090"
        },
        {
            "id": "svc_sdxl_default",
            "name": "Stable Diffusion XL Turbo",
            "repo_url": "https://github.com/gpuship-templates/sdxl-worker",
            "gpu_spec": "rtx4090",
            "rate": 0.45,
            "idle_timeout": 30,
            "commit": "8f20ad4",
            "msg": "SDXL Turbo 4-step real-time latent diffusion"
        },
        {
            "id": "svc_llama3_default",
            "name": "Llama 3.1 8B Instruct (vLLM)",
            "repo_url": "https://github.com/gpuship-templates/vllm-llama3",
            "gpu_spec": "h100_pcie",
            "rate": 2.49,
            "idle_timeout": 60,
            "commit": "d91a0c8",
            "msg": "vLLM PagedAttention inference server"
        }
    ]

    for tmpl in seed_templates:
        if not db.get_service(tmpl["id"]):
            logger.info(f"Seeding flagship template service: {tmpl['name']}...")
            s = db.create_service(
                routes.Service(
                    id=tmpl["id"],
                    name=tmpl["name"],
                    repo_url=tmpl["repo_url"],
                    branch="main",
                    dockerfile_path="Dockerfile",
                    health_endpoint="/health",
                    gpu_spec=tmpl["gpu_spec"],
                    price_ceiling_hr=tmpl["rate"] + 1.0,
                    idle_timeout_seconds=tmpl["idle_timeout"],
                    keep_warm_count=0
                )
            )
            dep = db.create_deployment(
                routes.Deployment(
                    id=f"dep_{tmpl['commit']}",
                    service_id=tmpl["id"],
                    commit_hash=tmpl["commit"],
                    commit_msg=tmpl["msg"],
                    image_tag=f"registry.lium.io/{tmpl['id']}:{tmpl['commit']}",
                    status=routes.DeploymentStatus.READY,
                    build_logs="[Builder] Image built and verified.",
                    created_at=s.created_at
                )
            )
            db.update_service(tmpl["id"], {"active_deployment_id": dep.id})

    logger.info("Starting Autonomous Scale-to-Zero Reconciler...")
    await reconciler.start()

    yield

    # Shutdown
    logger.info("Shutting down GPUShip Reconciler...")
    await reconciler.stop()

# FastAPI application instance
app = FastAPI(
    title="GPUShip — Scale-to-Zero GPU Deployment Platform for Lium",
    description="Connect Git repositories, build GPU workers, and scale to zero compute on Lium.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Platform & Gateway API router
app.include_router(routes.router)

# Mount Static Dashboard assets
static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", include_in_schema=False)
async def serve_dashboard():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "GPUShip Platform API Online"}

@app.get("/health")
async def health_check():
    return {
        "status": "HEALTHY",
        "platform": "GPUShip",
        "lium_engine": "ACTIVE",
        "reconciler_running": reconciler.running
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gpuship.main:app", host=GATEWAY_HOST, port=GATEWAY_PORT, reload=False)
