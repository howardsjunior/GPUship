# GPUShip 🚀

> **Scale-to-Zero GPU Deployment Platform for Lium**  
> Connect a GitHub repository, deploy an AI worker to [Lium](https://lium.io), and receive a permanent stable HTTPS API. Compute scales down to **$0.00/hour** when idle and boots on-demand with zero dropped requests.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688.svg)](https://fastapi.tiangolo.com)
[![Compute Backend](https://img.shields.io/badge/Backend-Lium%20Cloud-indigo.svg)](https://docs.lium.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

---

## ⚡ The Decisive Demo (Sleep / Wake Lifecycle)

As specified in the product brief (§8.5):

$$\text{Git Push} \longrightarrow \text{Pinned Build} \longrightarrow \text{Live API} \longrightarrow \text{Idle Timeout} \longrightarrow \text{GPU Released (\$0/hr)} \longrightarrow \text{New Job} \longrightarrow \text{Replacement GPU} \longrightarrow \text{Response Completed at Same URL}$$

You can run this demo end-to-end with a single command:

```bash
./demo.sh
```

Or trigger it visually with live telemetry in the interactive web dashboard at `http://localhost:8000`.

---

## 🎯 The Problem

Developers deploying custom AI inference (transcription, audio, image generation, custom fine-tuned LLMs) face a painful dilemma:

1. **Always-On Dedicated GPUs**: Renting an RTX 4090 (\$0.45/hr) or H100 (\$2.49/hr) 24/7 costs **\$324 to \$1,792/month**, even if traffic only arrives a few hours a day. Over 80% of compute spend is wasted on idle time.
2. **Proprietary Serverless Lock-in**: Services like Modal or RunPod require rewiring your codebase with proprietary Python decorators (`@stub.function`), making migration difficult.
3. **Fragile Self-Hosting**: Writing bespoke bash scripts or cron jobs to rent and teardown GPU VMs causes dropped HTTP requests during cold starts, race conditions, and abandoned billable instances.

---

## 💡 The GPUShip Solution

GPUShip is an open deployment and scale-to-zero control plane designed for developers' own **Lium** accounts:

- **Bring Your Own Lium Account**: Direct integration with Lium's per-second billing, custom images, and scoped API keys.
- **Ordinary Docker & FastAPI Applications**: Deploy standard containers without vendor-specific decorators.
- **Permanent Stable CPU Gateway**: Inexpensive CPU gateway stays online 24/7 to accept requests, maintain durable queues, and hold leases.
- **Scale-to-Zero on Idle**: An empty queue and an idle countdown timer automatically release the GPU pod back to Lium's capacity pool (\$0.00/hr).
- **Zero Dropped Requests**: Cold requests enter a durable queue; replacement GPU boots, verifies readiness via `/health`, and drains work.
- **Transparent Cold-Start Observability**: Deconstructs cold starts into clear stages: **Node Provisioning** $\rightarrow$ **Docker Container Boot** $\rightarrow$ **Model VRAM Allocation** $\rightarrow$ **Inference Execution**.
- **GitHub Lifecycle & Rollback**: Automatic commit hashing, build log streams, and 1-click instant version rollback.

---

## 🏛️ System Architecture

```
[ Client / Webhook ]
        │
        ▼  POST /api/v1/services/{id}/jobs  (Stable HTTPS Endpoint)
┌─────────────────────────────────────────────────────────────┐
│                   Stable CPU Gateway                        │
│   - Idempotency Deduplication (X-Idempotency-Key)           │
│   - Immediate SQLite Persistence (202 Accepted)             │
│   - Cost & Latency Metrics Engine                           │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Durable Async Queue                      │
│   - Recoverable Job Leases & Retry Budget                   │
│   - Wakeup Signals for Controller                           │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             Autonomous Reconciler Engine                    │
│   - Watchdog: Provisions Lium GPU when Queue > 0            │
│   - Idle Countdown: Releases Pod when Queue == 0 (Timeout)  │
│   - Race Prevention: Incoming jobs abort shutdown           │
│   - Orphaned Pod Detector: Prevents billable leaks          │
└──────────────────────────────┬──────────────────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│   Lium GPU Pod (RTX 4090)   │ │    Lium GPU Pod (H100)      │
│   - PyTorch / CUDA Runtime  │ │   - Large Model Inference   │
│   - App Container (Port 8000│ │   - vLLM / High Concurrency │
└─────────────────────────────┘ └─────────────────────────────┘
```

---

## 📊 Economics & Cost Comparison

Tested on intermittent traffic (150 requests/day, 4.5 seconds average GPU active time per request):

| Deployment Model | GPU Type | Daily Compute Billed | Daily Cost | Monthly Cost | Cost Reduction |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Always-On Baseline** | RTX 4090 (24GB) | 24.0 hours | \$10.80 | \$324.00 | Baseline |
| **GPUShip Scale-to-Zero** | RTX 4090 (24GB) | **1.85 hours** (Active + Grace) | **\$0.83** | **\$24.90** | **92.3% Saved** |
| **Always-On Baseline** | H100 PCIe (80GB) | 24.0 hours | \$59.76 | \$1,792.80 | Baseline |
| **GPUShip Scale-to-Zero** | H100 PCIe (80GB) | **2.10 hours** (Active + Grace) | **\$5.22** | **\$156.60** | **91.2% Saved** |

---

## 🚀 Quickstart

### 1. Launch the Platform
Start the CPU Gateway and Presentation Dashboard:

```bash
./run.sh
```

Open your browser to **`http://localhost:8000`**.

### 2. Run the Verification Decisive Demo
Run the automated test suite demonstrating the full sleep/wake cycle:

```bash
./demo.sh
```

### 3. Run Test Suite
GPUShip includes automated unit and integration tests:

```bash
python3 -m unittest discover -s tests
```

---

## 📡 API Reference

### 1. Submit an Inference Job (Asynchronous)
```bash
curl -X POST "http://localhost:8000/api/v1/services/svc_whisper_default/jobs" \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: req_abc123" \
  -d '{
    "input": {
      "text": "GPUShip automatically releases idle GPUs back to Lium."
    }
  }'
```

**Response (HTTP 202 Accepted)**:
```json
{
  "job_id": "job_8f29d10e82",
  "service_id": "svc_whisper_default",
  "status": "QUEUED",
  "is_deduplicated": false,
  "pod_state": "OFFLINE",
  "estimated_cold_start_sec": 7.0,
  "status_url": "http://localhost:8000/api/v1/services/svc_whisper_default/jobs/job_8f29d10e82",
  "created_at": 1729904200.12
}
```

### 2. Poll Job Status & Output
```bash
curl "http://localhost:8000/api/v1/services/svc_whisper_default/jobs/job_8f29d10e82"
```

**Response**:
```json
{
  "job_id": "job_8f29d10e82",
  "service_id": "svc_whisper_default",
  "status": "SUCCEEDED",
  "created_at": 1729904200.12,
  "started_at": 1729904206.82,
  "completed_at": 1729904207.25,
  "latency_ms": 432.1,
  "pod_state": "READY",
  "result": {
    "workload": "whisper-large-v3-turbo",
    "transcription": "Transcribed speech from input: 'GPUShip automatically releases idle GPUs back to Lium.'",
    "confidence": 0.984
  }
}
```

### 3. Synchronous Convenience Endpoint
Holds the connection until the GPU boots and responds:
```bash
curl -X POST "http://localhost:8000/api/v1/services/svc_whisper_default/inference" \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Analyze market trends"}}'
```

---

## 📦 Ready-to-Deploy Worker Templates

Located in `gpuship/templates/`:

1. **Faster-Whisper Transcription** (`templates/whisper/`): High-throughput audio transcription with VAD and timestamps.
2. **Stable Diffusion XL Turbo** (`templates/stable_diffusion/`): 4-step real-time latent image diffusion.
3. **vLLM Llama 3.1** (`templates/vllm_llm/`): PagedAttention-powered high-concurrency LLM inference.

---

## 🛡️ Reliability & Safety Mechanisms

- **Idempotent Operations**: All pod rental and termination calls to Lium use unique lease tokens to prevent double-billing.
- **Race Condition Prevention**: Newly admitted jobs immediately cancel pending idle countdowns.
- **Orphaned Pod Watchdog**: Continuous reconciliation detects and terminates abandoned pods across controller restarts.
- **Price Ceiling Guards**: Prevents provisioning if current spot/on-demand rates exceed the service's configured hourly budget.

---

## 📄 License

Apache License 2.0. Built for developers building on [Lium Cloud](https://lium.io).

