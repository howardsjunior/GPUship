// GPUShip Frontend Dashboard Logic

let currentServiceId = null;
let eventSource = null;
let services = [];

// Initialize Lucide icons
function refreshIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadServices();
  setSamplePayload('transcribe');
  refreshIcons();
});

// Load services list
async function loadServices() {
  try {
    const res = await fetch("/api/v1/services");
    services = await res.json();
    
    // If no services yet, create default Whisper service
    if (services.length === 0) {
      const defaultRes = await fetch("/api/v1/services", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "Whisper Audio Transcription Worker",
          repo_url: "https://github.com/gpuship-templates/whisper-fastapi",
          branch: "main",
          dockerfile_path: "Dockerfile",
          health_endpoint: "/health",
          gpu_spec: "rtx4090",
          price_ceiling_hr: 1.50,
          idle_timeout_seconds: 30,
          keep_warm_count: 0
        })
      });
      const created = await defaultRes.json();
      services = [created];
    }

    const selector = document.getElementById("service-selector");
    selector.innerHTML = "";
    services.forEach(svc => {
      const opt = document.createElement("option");
      opt.value = svc.id;
      opt.textContent = `${svc.name} (${svc.gpu_spec.toUpperCase()})`;
      selector.appendChild(opt);
    });

    if (!currentServiceId || !services.find(s => s.id === currentServiceId)) {
      currentServiceId = services[0].id;
    }
    selector.value = currentServiceId;
    
    await updateServiceView();
    startSSEStream();
  } catch (err) {
    console.error("Failed to load services:", err);
  }
}

// Service selector change
async function onServiceChanged() {
  const selector = document.getElementById("service-selector");
  currentServiceId = selector.value;
  await updateServiceView();
  startSSEStream();
}

// Update UI elements for selected service
async function updateServiceView() {
  const svc = services.find(s => s.id === currentServiceId);
  if (!svc) return;

  document.getElementById("service-repo-desc").textContent = `${svc.repo_url} (branch: ${svc.branch})`;
  document.getElementById("stat-gpu-spec").textContent = `${svc.gpu_spec.toUpperCase()} (24GB)`;
  document.getElementById("stat-idle-timeout").textContent = `${svc.idle_timeout_seconds}s`;
  
  const gatewayUrl = `${window.location.origin}/api/v1/services/${svc.id}/jobs`;
  document.getElementById("stable-gateway-url").textContent = gatewayUrl;

  await loadDeployments();
  await loadMetrics();
  refreshIcons();
}

// Load deployments list
async function loadDeployments() {
  if (!currentServiceId) return;
  try {
    const res = await fetch(`/api/v1/services/${currentServiceId}/deployments`);
    const deployments = await res.json();
    const svc = services.find(s => s.id === currentServiceId);
    const container = document.getElementById("deployments-list");
    container.innerHTML = "";

    deployments.forEach((dep, idx) => {
      const isActive = (dep.id === svc.active_deployment_id);
      const item = document.createElement("div");
      item.className = `p-3 rounded-xl border transition ${
        isActive 
          ? "border-emerald-500/40 bg-emerald-950/20 shadow-md" 
          : "border-slate-800 bg-slate-900/40 hover:bg-slate-800/40"
      }`;

      item.innerHTML = `
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="font-mono text-xs font-bold text-slate-200">#${dep.commit_hash}</span>
            ${isActive 
              ? '<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30">ACTIVE</span>' 
              : ''}
          </div>
          <span class="text-[10px] text-slate-400 font-mono">${new Date(dep.created_at * 1000).toLocaleTimeString()}</span>
        </div>
        <p class="text-xs text-slate-300 mt-1 line-clamp-1">${dep.commit_msg}</p>
        <div class="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/60 text-[11px] font-mono">
          <span class="text-slate-400 truncate max-w-[200px]">${dep.image_tag}</span>
          ${!isActive ? `
            <button onclick="rollbackTo('${dep.id}')" class="text-indigo-400 hover:text-indigo-300 font-semibold">
              Rollback
            </button>
          ` : '<span class="text-emerald-400">Deployed</span>'}
        </div>
      `;
      container.appendChild(item);
    });
    refreshIcons();
  } catch (err) {
    console.error("Failed to load deployments:", err);
  }
}

// Rollback to specific deployment
async function rollbackTo(deploymentId) {
  if (!confirm(`Are you sure you want to rollback to deployment ${deploymentId}?`)) return;
  try {
    const res = await fetch(`/api/v1/services/${currentServiceId}/rollback?target_deployment_id=${deploymentId}`, {
      method: "POST"
    });
    if (res.ok) {
      await loadServices();
    }
  } catch (err) {
    console.error("Rollback failed:", err);
  }
}

// Trigger simulated new commit push & build
async function triggerNewCommitDeploy() {
  const commit = Math.random().toString(36).substring(2, 9);
  try {
    await fetch(`/api/v1/services/${currentServiceId}/deploy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        commit_hash: commit,
        commit_msg: `Optimized inference batching & reduced cold start`
      })
    });
    setTimeout(async () => {
      await loadDeployments();
    }, 1800);
  } catch (err) {
    console.error("Deploy trigger failed:", err);
  }
}

// Load service metrics
async function loadMetrics() {
  if (!currentServiceId) return;
  try {
    const res = await fetch(`/api/v1/services/${currentServiceId}/metrics`);
    const metrics = await res.json();
    
    document.getElementById("metric-actual-cost").textContent = `$${metrics.actual_gpuship_cost_usd.toFixed(4)}`;
    document.getElementById("metric-always-on-cost").textContent = `$${metrics.always_on_cost_usd.toFixed(4)}`;
    document.getElementById("metric-savings-badge").textContent = `${metrics.savings_percentage}% SAVED`;
    document.getElementById("metric-billed-seconds").textContent = `${metrics.billed_gpu_seconds}s (${metrics.billed_gpu_hours.toFixed(4)}h)`;
    
    const pct = Math.min(100, Math.max(10, metrics.savings_percentage));
    document.getElementById("cost-progress-bar").style.width = `${pct}%`;
  } catch (err) {
    console.error("Failed to load metrics:", err);
  }
}

// Real-time Server-Sent Events (SSE) Stream
function startSSEStream() {
  if (eventSource) {
    eventSource.close();
  }
  if (!currentServiceId) return;

  eventSource = new EventSource(`/api/v1/services/${currentServiceId}/events`);
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.error) return;

      updateLivePipeline(data);
      if (data.metrics) {
        document.getElementById("metric-actual-cost").textContent = `$${data.metrics.actual_gpuship_cost_usd.toFixed(4)}`;
        document.getElementById("metric-always-on-cost").textContent = `$${data.metrics.always_on_cost_usd.toFixed(4)}`;
        document.getElementById("metric-savings-badge").textContent = `${data.metrics.savings_percentage}% SAVED`;
        document.getElementById("metric-billed-seconds").textContent = `${data.metrics.billed_gpu_seconds}s`;
      }
      if (data.recent_logs) {
        renderActivityLogs(data.recent_logs);
      }
    } catch (err) {
      console.error("SSE parse error:", err);
    }
  };
}

// Update live pipeline visual nodes
function updateLivePipeline(data) {
  const pod = data.active_pod;
  const queued = data.queued_jobs || 0;
  
  // Pipeline Step 2: Durable Queue depth
  document.getElementById("pipe-queue-depth").textContent = `${queued} Jobs Pending`;
  const step2 = document.getElementById("pipe-step-2");
  if (queued > 0) {
    step2.classList.add("active-stage-glow");
  } else {
    step2.classList.remove("active-stage-glow");
  }

  // Pipeline Step 3: Reconciler
  const reconcilerState = document.getElementById("pipe-reconciler-state");
  if (queued > 0 && (!pod || pod.state === "TERMINATED")) {
    reconcilerState.textContent = "Demanding Capacity!";
  } else if (pod && pod.state === "IDLE_COOLING") {
    reconcilerState.textContent = "Idle Watchdog (Cooling)";
  } else {
    reconcilerState.textContent = "Autonomous Watchdog";
  }

  // Pipeline Step 4: Lium Pod state
  const podStateElem = document.getElementById("pipe-gpu-state");
  const step4 = document.getElementById("pipe-step-4");
  const clusterCard = document.getElementById("cluster-status-card");
  const activeStateText = document.getElementById("active-state-text");

  if (!pod || pod.state === "TERMINATED" || pod.state === "OFFLINE") {
    podStateElem.textContent = "Scaled to Zero ($0.00/hr)";
    podStateElem.className = "text-[11px] text-slate-400 mt-1";
    step4.classList.remove("active-stage-glow");

    clusterCard.className = "flex items-center space-x-2.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono";
    activeStateText.textContent = "COMPUTE: $0.00/hr (SCALED TO ZERO)";
  } else if (pod.state === "PROVISIONING" || pod.state === "BOOTING" || pod.state === "LOADING_MODEL") {
    podStateElem.textContent = `Cold Start: ${pod.state}`;
    podStateElem.className = "text-[11px] text-yellow-400 font-semibold mt-1 animate-pulse";
    step4.classList.add("active-stage-glow");

    clusterCard.className = "flex items-center space-x-2.5 px-3 py-1.5 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-xs font-mono";
    activeStateText.textContent = `LIUM: ${pod.state.replace("_", " ")}...`;
  } else if (pod.state === "PROCESSING") {
    podStateElem.textContent = "Processing Inference Request";
    podStateElem.className = "text-[11px] text-cyan-400 font-semibold mt-1";
    step4.classList.add("active-stage-glow");

    clusterCard.className = "flex items-center space-x-2.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-mono";
    activeStateText.textContent = `ACTIVE: RTX 4090 @ $0.45/hr (COMPUTING)`;
  } else if (pod.state === "READY") {
    let idleInfo = "";
    if (pod.idle_started_at) {
      const elapsed = Math.round(Date.now() / 1000 - pod.idle_started_at);
      idleInfo = ` (Idle: ${elapsed}s)`;
    }
    podStateElem.textContent = `Pod Ready${idleInfo}`;
    podStateElem.className = "text-[11px] text-emerald-400 mt-1";
    step4.classList.remove("active-stage-glow");

    clusterCard.className = "flex items-center space-x-2.5 px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-mono";
    activeStateText.textContent = `READY: RTX 4090 @ $0.45/hr${idleInfo}`;
  }

  // Cold start telemetry breakdown
  if (pod && pod.cold_start) {
    document.getElementById("cs-vm-sec").textContent = `${pod.cold_start.provision_seconds}s`;
    document.getElementById("cs-boot-sec").textContent = `${pod.cold_start.container_boot_seconds}s`;
    document.getElementById("cs-vram-sec").textContent = `${pod.cold_start.model_load_seconds}s`;
    document.getElementById("cold-start-total-badge").textContent = `Total Cold Start: ${pod.cold_start.total_cold_start_seconds}s`;
  }
}

// Render real-time activity stream
function renderActivityLogs(logs) {
  const container = document.getElementById("activity-log-container");
  container.innerHTML = "";
  
  logs.forEach(log => {
    const timeStr = new Date(log.timestamp * 1000).toLocaleTimeString();
    const line = document.createElement("div");
    line.className = "flex items-start space-x-2";
    
    let levelBadge = '<span class="text-slate-400">[INFO]</span>';
    if (log.level === "WARNING") levelBadge = '<span class="text-yellow-400">[WARN]</span>';
    if (log.level === "ERROR") levelBadge = '<span class="text-red-400">[ERR]</span>';

    line.innerHTML = `
      <span class="text-slate-500">${timeStr}</span>
      ${levelBadge}
      <span class="text-slate-300">${log.message}</span>
    `;
    container.appendChild(line);
  });
}

// Preset payload samples
function setSamplePayload(type) {
  const textarea = document.getElementById("inference-input-json");
  if (type === 'transcribe') {
    textarea.value = JSON.stringify({
      "text": "GPUShip automatically scales GPU capacity down to zero when idle.",
      "language": "en"
    }, null, 2);
  } else if (type === 'image') {
    textarea.value = JSON.stringify({
      "prompt": "Futuristic aerospace laboratory with quantum supercomputers, 8k cinematic",
      "steps": 4,
      "guidance_scale": 7.5
    }, null, 2);
  } else if (type === 'llm') {
    textarea.value = JSON.stringify({
      "prompt": "Explain the difference between cold starts and warm idle GPU spend in 2 sentences.",
      "max_tokens": 64,
      "temperature": 0.7
    }, null, 2);
  }
}

// Submit Inference Request
async function sendInferenceJob() {
  const btn = document.getElementById("btn-submit-job");
  const outputBox = document.getElementById("inference-output-box");
  const timingBadge = document.getElementById("response-timing-badge");
  const syncMode = document.getElementById("check-sync-mode").checked;
  const inputVal = document.getElementById("inference-input-json").value;

  let parsedInput = {};
  try {
    parsedInput = JSON.parse(inputVal);
  } catch (e) {
    alert("Invalid JSON in input box");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<span class="animate-spin inline-block mr-2">⟳</span> Submitting...`;
  outputBox.textContent = "Request accepted into durable queue. Awaiting GPU worker...";
  timingBadge.textContent = "Connecting...";

  const startTime = performance.now();

  try {
    if (syncMode) {
      // Synchronous inference
      const res = await fetch(`/api/v1/services/${currentServiceId}/inference`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: parsedInput })
      });
      const data = await res.json();
      const duration = Math.round(performance.now() - startTime);
      timingBadge.textContent = `Total E2E: ${duration}ms | Exec: ${data.latency_ms?.toFixed(1) || '--'}ms`;
      outputBox.textContent = JSON.stringify(data, null, 2);
    } else {
      // Asynchronous Job API (POST /jobs -> GET /jobs/{id})
      const postRes = await fetch(`/api/v1/services/${currentServiceId}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: parsedInput })
      });
      const accepted = await postRes.json();
      outputBox.textContent = `Job Enqueued: ${accepted.job_id}\nInitial Pod State: ${accepted.pod_state}\nEstimated Cold Start: ${accepted.estimated_cold_start_sec}s\nPolling for completion...\n`;

      // Poll until succeeded
      const pollInterval = setInterval(async () => {
        const checkRes = await fetch(`/api/v1/services/${currentServiceId}/jobs/${accepted.job_id}`);
        const job = await checkRes.json();

        if (job.status === "SUCCEEDED") {
          clearInterval(pollInterval);
          const duration = Math.round(performance.now() - startTime);
          timingBadge.textContent = `Total E2E: ${duration}ms | Exec: ${job.latency_ms?.toFixed(1) || '--'}ms`;
          outputBox.textContent = JSON.stringify(job, null, 2);
          btn.disabled = false;
          btn.innerHTML = `<i data-lucide="send" class="w-3.5 h-3.5 mr-1"></i> Submit to Queue`;
          refreshIcons();
        } else if (job.status === "FAILED") {
          clearInterval(pollInterval);
          outputBox.textContent = `Job Failed: ${job.error}`;
          btn.disabled = false;
          btn.innerHTML = `<i data-lucide="send" class="w-3.5 h-3.5 mr-1"></i> Submit to Queue`;
          refreshIcons();
        } else {
          outputBox.textContent = `Job ID: ${accepted.job_id}\nStatus: ${job.status}\nWorker State: ${job.pod_state}\nWaiting for completion...`;
        }
      }, 500);
      return;
    }
  } catch (err) {
    outputBox.textContent = `Error: ${err.message}`;
  } finally {
    if (syncMode) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="send" class="w-3.5 h-3.5 mr-1"></i> Submit to Queue`;
      refreshIcons();
    }
  }
}

// Copy cURL command to clipboard
function copyStableUrl() {
  const url = document.getElementById("stable-gateway-url").textContent;
  const curlCmd = `curl -X POST "${url}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"input": {"text": "Inference request"}}'`;
  navigator.clipboard.writeText(curlCmd);
  alert("Copied cURL command to clipboard!");
}

// Trigger Decisive Demo Runner
async function triggerDecisiveDemo() {
  const card = document.getElementById("decisive-demo-card");
  const terminal = document.getElementById("demo-terminal-box");
  card.classList.remove("hidden");
  terminal.innerHTML = "";

  const logDemo = (msg, color = "text-slate-300") => {
    const line = document.createElement("div");
    line.className = color;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
  };

  logDemo("Starting Decisive Demo execution (§8.5)...", "text-cyan-400 font-bold");
  document.getElementById("demo-step-1-status").textContent = "Building image...";
  document.getElementById("demo-step-1-status").className = "text-[10px] text-yellow-400 animate-pulse";

  try {
    logDemo("Step 1: Git push -> Triggering pinned Docker image build...");
    const res = await fetch(`/api/v1/demo/run-decisive?service_id=${currentServiceId}`, {
      method: "POST"
    });
    const result = await res.json();

    document.getElementById("demo-step-1-status").textContent = "✓ Image Pinned";
    document.getElementById("demo-step-1-status").className = "text-[10px] text-emerald-400 font-bold";

    document.getElementById("demo-step-2-status").textContent = "✓ Succeeded";
    document.getElementById("demo-step-2-status").className = "text-[10px] text-emerald-400 font-bold";

    document.getElementById("demo-step-3-status").textContent = "✓ Scaled to Zero";
    document.getElementById("demo-step-3-status").className = "text-[10px] text-emerald-400 font-bold";

    document.getElementById("demo-step-4-status").textContent = "✓ Completed";
    document.getElementById("demo-step-4-status").className = "text-[10px] text-emerald-400 font-bold";

    logDemo("Decisive demo completed successfully!", "text-emerald-400 font-bold");
    logDemo(`Trace summary: ${result.summary.demo_outcome}`);
    logDemo(`Savings achieved: ${result.summary.savings_vs_always_on}`);
    
    await loadMetrics();
    await loadDeployments();
  } catch (err) {
    logDemo(`Demo execution error: ${err.message}`, "text-red-400");
  }
}

function closeDecisiveDemo() {
  document.getElementById("decisive-demo-card").classList.add("hidden");
}

// Modal handlers
function openNewServiceModal() {
  document.getElementById("new-service-modal").classList.remove("hidden");
  applyTemplatePreset();
  refreshIcons();
}

function closeNewServiceModal() {
  document.getElementById("new-service-modal").classList.add("hidden");
}

function applyTemplatePreset() {
  const val = document.getElementById("modal-template-select").value;
  const nameInput = document.getElementById("modal-service-name");
  const repoInput = document.getElementById("modal-repo-url");
  const gpuSelect = document.getElementById("modal-gpu-spec");

  if (val === "whisper") {
    nameInput.value = "Faster-Whisper Transcription API";
    repoInput.value = "https://github.com/gpuship-templates/whisper-fastapi";
    gpuSelect.value = "rtx4090";
  } else if (val === "sdxl") {
    nameInput.value = "Stable Diffusion XL Turbo API";
    repoInput.value = "https://github.com/gpuship-templates/sdxl-worker";
    gpuSelect.value = "rtx4090";
  } else if (val === "llama3") {
    nameInput.value = "Llama-3.1 8B Instruct vLLM";
    repoInput.value = "https://github.com/gpuship-templates/vllm-llama3";
    gpuSelect.value = "h100_pcie";
  }
}

async function submitNewService(e) {
  e.preventDefault();
  const name = document.getElementById("modal-service-name").value;
  const repo_url = document.getElementById("modal-repo-url").value;
  const gpu_spec = document.getElementById("modal-gpu-spec").value;
  const idle_timeout = parseInt(document.getElementById("modal-idle-timeout").value, 10);

  try {
    const res = await fetch("/api/v1/services", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        repo_url,
        branch: "main",
        dockerfile_path: "Dockerfile",
        health_endpoint: "/health",
        gpu_spec,
        price_ceiling_hr: 3.00,
        idle_timeout_seconds: idle_timeout,
        keep_warm_count: 0
      })
    });
    const created = await res.json();
    closeNewServiceModal();
    await loadServices();
    currentServiceId = created.id;
    document.getElementById("service-selector").value = created.id;
    await updateServiceView();
  } catch (err) {
    alert(`Failed to create service: ${err.message}`);
  }
}

