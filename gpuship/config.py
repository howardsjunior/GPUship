"""
GPUShip Configuration and Constants
"""
import os
from typing import Dict, Any

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Database
DB_PATH = os.path.join(DATA_DIR, "gpuship.db")

# Lium Configuration
LIUM_API_KEY = os.getenv("LIUM_API_KEY", "")
LIUM_API_URL = os.getenv("LIUM_API_URL", "https://api.lium.io/v1")
LIUM_SIMULATION_MODE = os.getenv("LIUM_SIMULATION_MODE", "true").lower() in ("true", "1", "yes")

# Reconciler Settings
RECONCILER_INTERVAL_SECONDS = float(os.getenv("RECONCILER_INTERVAL_SECONDS", "1.0"))
DEFAULT_IDLE_TIMEOUT_SECONDS = int(os.getenv("DEFAULT_IDLE_TIMEOUT_SECONDS", "30"))
DEFAULT_PRICE_CEILING_HR = float(os.getenv("DEFAULT_PRICE_CEILING_HR", "1.50"))

# Hardware Catalog & Pricing (Per hour and per second)
GPU_CATALOG: Dict[str, Dict[str, Any]] = {
    "rtx4090": {
        "name": "NVIDIA GeForce RTX 4090 (24GB VRAM)",
        "vram_gb": 24,
        "hourly_rate": 0.45,
        "per_second_rate": 0.45 / 3600.0,
        "typical_boot_sec": 6.5,
        "typical_model_load_sec": 5.0,
        "supported_workloads": ["whisper", "sd15", "llama3-8b-q4"]
    },
    "h100_pcie": {
        "name": "NVIDIA H100 PCIe (80GB SXM/PCIe)",
        "vram_gb": 80,
        "hourly_rate": 2.49,
        "per_second_rate": 2.49 / 3600.0,
        "typical_boot_sec": 8.0,
        "typical_model_load_sec": 7.0,
        "supported_workloads": ["llama3-70b", "flux-dev", "whisper-large-v3", "qwen2.5-72b"]
    },
    "a100_sxm": {
        "name": "NVIDIA A100 SXM4 (80GB VRAM)",
        "vram_gb": 80,
        "hourly_rate": 1.89,
        "per_second_rate": 1.89 / 3600.0,
        "typical_boot_sec": 7.5,
        "typical_model_load_sec": 6.5,
        "supported_workloads": ["mistral-large", "sdxl", "deepseek-coder"]
    },
    "l40s": {
        "name": "NVIDIA L40S (48GB VRAM)",
        "vram_gb": 48,
        "hourly_rate": 0.95,
        "per_second_rate": 0.95 / 3600.0,
        "typical_boot_sec": 6.0,
        "typical_model_load_sec": 5.5,
        "supported_workloads": ["whisper-large-v3", "sdxl-turbo", "llama3-8b"]
    }
}

# Gateway Settings
GATEWAY_HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8000"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", f"http://localhost:{GATEWAY_PORT}")

