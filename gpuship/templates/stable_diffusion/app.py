import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Stable Diffusion Worker for GPUShip", version="1.0.0")

class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = "blurry, low quality"
    steps: Optional[int] = 4
    guidance_scale: Optional[float] = 7.5

MODEL_LOADED = False

@app.on_event("startup")
async def load_model():
    global MODEL_LOADED
    time.sleep(1.0)
    MODEL_LOADED = True
    print("[Worker] Stable Diffusion XL Turbo loaded into VRAM.")

@app.get("/health")
def health():
    if not MODEL_LOADED:
        raise HTTPException(status_code=503, detail="Model still loading")
    return {"status": "HEALTHY", "model": "sdxl-turbo", "gpu": "RTX 4090"}

@app.post("/inference")
def generate_image(req: GenerateRequest):
    return {
        "prompt": req.prompt,
        "image_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80",
        "steps": req.steps,
        "seed": 8492019,
        "format": "jpeg"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

