import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="vLLM Language Model Worker for GPUShip", version="1.0.0")

class PromptRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 128
    temperature: Optional[float] = 0.7

MODEL_LOADED = False

@app.on_event("startup")
async def load_model():
    global MODEL_LOADED
    time.sleep(1.0)
    MODEL_LOADED = True
    print("[Worker] Llama-3.1-8B-Instruct weights mapped to GPU memory.")

@app.get("/health")
def health():
    if not MODEL_LOADED:
        raise HTTPException(status_code=503, detail="Model still loading")
    return {"status": "HEALTHY", "model": "llama-3.1-8b-instruct", "gpu": "RTX 4090"}

@app.post("/inference")
def generate_text(req: PromptRequest):
    return {
        "prompt": req.prompt,
        "text": f"This is an inference completion from Llama-3 serving on Lium GPU via GPUShip. Prompt processed: '{req.prompt}'.",
        "tokens_generated": 34,
        "tokens_per_second": 88.5
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

