import sqlite3
import json
import time
import os
import threading
from typing import Optional, List, Dict, Any
from ..config import DB_PATH
from ..models import (
    Service, Deployment, DeploymentStatus,
    Pod, PodState, ColdStartBreakdown,
    Job, JobStatus
)

_lock = threading.Lock()
_initialized = False

def init_db():
    global _initialized
    with _lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        cursor = conn.cursor()
        
        # 1. Services table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            repo_url TEXT NOT NULL,
            branch TEXT NOT NULL,
            dockerfile_path TEXT NOT NULL,
            health_endpoint TEXT NOT NULL,
            gpu_spec TEXT NOT NULL,
            price_ceiling_hr REAL NOT NULL,
            idle_timeout_seconds INTEGER NOT NULL,
            keep_warm_count INTEGER NOT NULL,
            active_deployment_id TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """)
        
        # 2. Deployments table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS deployments (
            id TEXT PRIMARY KEY,
            service_id TEXT NOT NULL,
            commit_hash TEXT NOT NULL,
            commit_msg TEXT NOT NULL,
            image_tag TEXT NOT NULL,
            status TEXT NOT NULL,
            build_logs TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (service_id) REFERENCES services(id)
        )
        """)
        
        # 3. Pods table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pods (
            id TEXT PRIMARY KEY,
            service_id TEXT NOT NULL,
            deployment_id TEXT,
            provider TEXT NOT NULL,
            lium_pod_id TEXT,
            gpu_type TEXT NOT NULL,
            ip_address TEXT,
            port INTEGER NOT NULL,
            state TEXT NOT NULL,
            rented_at REAL,
            released_at REAL,
            total_billed_seconds REAL NOT NULL,
            hourly_rate REAL NOT NULL,
            cold_start_json TEXT NOT NULL,
            last_heartbeat REAL NOT NULL,
            current_job_id TEXT,
            idle_started_at REAL,
            FOREIGN KEY (service_id) REFERENCES services(id)
        )
        """)
        
        # 4. Jobs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            service_id TEXT NOT NULL,
            idempotency_key TEXT,
            status TEXT NOT NULL,
            input_payload TEXT NOT NULL,
            result_payload TEXT,
            error_message TEXT,
            assigned_pod_id TEXT,
            created_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL,
            latency_ms REAL,
            execution_attempts INTEGER NOT NULL,
            cold_start_incurred INTEGER NOT NULL,
            estimated_cost REAL NOT NULL,
            FOREIGN KEY (service_id) REFERENCES services(id)
        )
        """)
        
        # 5. Service activity events / logs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata_json TEXT,
            timestamp REAL NOT NULL
        )
        """)
        
        conn.commit()
        conn.close()
        _initialized = True

def get_connection() -> sqlite3.Connection:
    global _initialized
    if not _initialized:
        init_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20.0)
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn


# Service CRUD
def create_service(service: Service) -> Service:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO services (
            id, name, repo_url, branch, dockerfile_path, health_endpoint,
            gpu_spec, price_ceiling_hr, idle_timeout_seconds, keep_warm_count,
            active_deployment_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            service.id, service.name, service.repo_url, service.branch,
            service.dockerfile_path, service.health_endpoint, service.gpu_spec,
            service.price_ceiling_hr, service.idle_timeout_seconds, service.keep_warm_count,
            service.active_deployment_id, service.created_at, service.updated_at
        ))
        conn.commit()
        conn.close()
        return service

def get_service(service_id: str) -> Optional[Service]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM services WHERE id = ?", (service_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return Service(**dict(row))

def list_services() -> List[Service]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM services ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [Service(**dict(r)) for r in rows]

def update_service(service_id: str, updates: Dict[str, Any]) -> Optional[Service]:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        updates["updated_at"] = time.time()
        fields = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [service_id]
        cursor.execute(f"UPDATE services SET {fields} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return get_service(service_id)

# Deployment CRUD
def create_deployment(dep: Deployment) -> Deployment:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO deployments (
            id, service_id, commit_hash, commit_msg, image_tag,
            status, build_logs, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dep.id, dep.service_id, dep.commit_hash, dep.commit_msg,
            dep.image_tag, dep.status.value, dep.build_logs, dep.created_at
        ))
        conn.commit()
        conn.close()
        return dep

def get_deployment(dep_id: str) -> Optional[Deployment]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deployments WHERE id = ?", (dep_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["status"] = DeploymentStatus(data["status"])
    return Deployment(**data)

def list_deployments_for_service(service_id: str) -> List[Deployment]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deployments WHERE service_id = ? ORDER BY created_at DESC", (service_id,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["status"] = DeploymentStatus(d["status"])
        results.append(Deployment(**d))
    return results

def update_deployment(dep_id: str, updates: Dict[str, Any]):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        if "status" in updates and isinstance(updates["status"], DeploymentStatus):
            updates["status"] = updates["status"].value
        fields = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [dep_id]
        cursor.execute(f"UPDATE deployments SET {fields} WHERE id = ?", values)
        conn.commit()
        conn.close()

# Pod CRUD
def create_pod(pod: Pod) -> Pod:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO pods (
            id, service_id, deployment_id, provider, lium_pod_id,
            gpu_type, ip_address, port, state, rented_at, released_at,
            total_billed_seconds, hourly_rate, cold_start_json, last_heartbeat,
            current_job_id, idle_started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pod.id, pod.service_id, pod.deployment_id, pod.provider, pod.lium_pod_id,
            pod.gpu_type, pod.ip_address, pod.port, pod.state.value, pod.rented_at,
            pod.released_at, pod.total_billed_seconds, pod.hourly_rate,
            pod.cold_start.model_dump_json(), pod.last_heartbeat,
            pod.current_job_id, pod.idle_started_at
        ))
        conn.commit()
        conn.close()
        return pod

def get_pod(pod_id: str) -> Optional[Pod]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pods WHERE id = ?", (pod_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["state"] = PodState(d["state"])
    d["cold_start"] = ColdStartBreakdown(**json.loads(d["cold_start_json"]))
    del d["cold_start_json"]
    return Pod(**d)

def get_active_pod_for_service(service_id: str) -> Optional[Pod]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM pods 
    WHERE service_id = ? AND state != 'TERMINATED' 
    ORDER BY rented_at DESC LIMIT 1
    """, (service_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["state"] = PodState(d["state"])
    d["cold_start"] = ColdStartBreakdown(**json.loads(d["cold_start_json"]))
    del d["cold_start_json"]
    return Pod(**d)

def list_pods_for_service(service_id: str, limit: int = 20) -> List[Pod]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pods WHERE service_id = ? ORDER BY rented_at DESC LIMIT ?", (service_id, limit))
    rows = cursor.fetchall()
    conn.close()
    pods = []
    for r in rows:
        d = dict(r)
        d["state"] = PodState(d["state"])
        d["cold_start"] = ColdStartBreakdown(**json.loads(d["cold_start_json"]))
        del d["cold_start_json"]
        pods.append(Pod(**d))
    return pods

def list_all_unreleased_pods() -> List[Pod]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pods WHERE state != 'TERMINATED'")
    rows = cursor.fetchall()
    conn.close()
    pods = []
    for r in rows:
        d = dict(r)
        d["state"] = PodState(d["state"])
        d["cold_start"] = ColdStartBreakdown(**json.loads(d["cold_start_json"]))
        del d["cold_start_json"]
        pods.append(Pod(**d))
    return pods

def update_pod(pod_id: str, updates: Dict[str, Any]):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        if "state" in updates and isinstance(updates["state"], PodState):
            updates["state"] = updates["state"].value
        if "cold_start" in updates and isinstance(updates["cold_start"], ColdStartBreakdown):
            updates["cold_start_json"] = updates["cold_start"].model_dump_json()
            del updates["cold_start"]
        fields = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [pod_id]
        cursor.execute(f"UPDATE pods SET {fields} WHERE id = ?", values)
        conn.commit()
        conn.close()

# Job CRUD
def create_job(job: Job) -> Job:
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO jobs (
            id, service_id, idempotency_key, status, input_payload,
            result_payload, error_message, assigned_pod_id, created_at,
            started_at, completed_at, latency_ms, execution_attempts,
            cold_start_incurred, estimated_cost
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.id, job.service_id, job.idempotency_key, job.status.value,
            json.dumps(job.input_payload),
            json.dumps(job.result_payload) if job.result_payload else None,
            job.error_message, job.assigned_pod_id, job.created_at,
            job.started_at, job.completed_at, job.latency_ms,
            job.execution_attempts, 1 if job.cold_start_incurred else 0,
            job.estimated_cost
        ))
        conn.commit()
        conn.close()
        return job

def get_job(job_id: str) -> Optional[Job]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)

def get_job_by_idempotency_key(service_id: str, idempotency_key: str) -> Optional[Job]:
    if not idempotency_key:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE service_id = ? AND idempotency_key = ?", (service_id, idempotency_key))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)

def get_next_queued_job(service_id: str) -> Optional[Job]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM jobs 
    WHERE service_id = ? AND status = 'QUEUED' 
    ORDER BY created_at ASC LIMIT 1
    """, (service_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _parse_job_row(row)

def count_queued_jobs(service_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE service_id = ? AND status = 'QUEUED'", (service_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def list_jobs_for_service(service_id: str, limit: int = 50) -> List[Job]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE service_id = ? ORDER BY created_at DESC LIMIT ?", (service_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [_parse_job_row(r) for r in rows]

def update_job(job_id: str, updates: Dict[str, Any]):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        if "status" in updates and isinstance(updates["status"], JobStatus):
            updates["status"] = updates["status"].value
        if "input_payload" in updates and isinstance(updates["input_payload"], dict):
            updates["input_payload"] = json.dumps(updates["input_payload"])
        if "result_payload" in updates and isinstance(updates["result_payload"], dict):
            updates["result_payload"] = json.dumps(updates["result_payload"])
        if "cold_start_incurred" in updates and isinstance(updates["cold_start_incurred"], bool):
            updates["cold_start_incurred"] = 1 if updates["cold_start_incurred"] else 0
            
        fields = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [job_id]
        cursor.execute(f"UPDATE jobs SET {fields} WHERE id = ?", values)
        conn.commit()
        conn.close()

def _parse_job_row(row: sqlite3.Row) -> Job:
    d = dict(row)
    d["status"] = JobStatus(d["status"])
    d["input_payload"] = json.loads(d["input_payload"]) if d["input_payload"] else {}
    d["result_payload"] = json.loads(d["result_payload"]) if d["result_payload"] else None
    d["cold_start_incurred"] = bool(d["cold_start_incurred"])
    return Job(**d)

# Logging & Activity stream
def log_activity(service_id: str, event_type: str, level: str, message: str, metadata: Optional[Dict[str, Any]] = None):
    with _lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO activity_logs (service_id, event_type, level, message, metadata_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            service_id, event_type, level, message,
            json.dumps(metadata or {}), time.time()
        ))
        conn.commit()
        conn.close()

def get_activity_logs(service_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM activity_logs WHERE service_id = ? ORDER BY timestamp DESC LIMIT ?
    """, (service_id, limit))
    rows = cursor.fetchall()
    conn.close()
    logs = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json.loads(d["metadata_json"]) if d["metadata_json"] else {}
        del d["metadata_json"]
        logs.append(d)
    return logs

# Metrics & Spend Analytics
def get_service_metrics(service_id: str) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total jobs
    cursor.execute("""
    SELECT 
        COUNT(*) as total_jobs,
        SUM(CASE WHEN status = 'SUCCEEDED' THEN 1 ELSE 0 END) as successful_jobs,
        SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_jobs,
        AVG(CASE WHEN status = 'SUCCEEDED' THEN latency_ms ELSE NULL END) as avg_latency_ms,
        SUM(CASE WHEN cold_start_incurred = 1 THEN 1 ELSE 0 END) as cold_start_count
    FROM jobs WHERE service_id = ?
    """, (service_id,))
    job_stats = dict(cursor.fetchone() or {})
    
    # Pod usage & spend
    cursor.execute("""
    SELECT 
        SUM(total_billed_seconds) as total_gpu_seconds,
        COUNT(*) as total_rentals
    FROM pods WHERE service_id = ?
    """, (service_id,))
    pod_stats = dict(cursor.fetchone() or {})
    
    # Service created time for counterfactual always-on
    cursor.execute("SELECT created_at, gpu_spec FROM services WHERE id = ?", (service_id,))
    svc_row = cursor.fetchone()
    
    conn.close()
    
    from ..config import GPU_CATALOG
    gpu_spec = svc_row["gpu_spec"] if svc_row else "rtx4090"
    rate_hr = GPU_CATALOG.get(gpu_spec, {}).get("hourly_rate", 0.45)
    rate_sec = rate_hr / 3600.0
    
    svc_created_at = svc_row["created_at"] if svc_row else time.time()
    elapsed_seconds = max(1.0, time.time() - svc_created_at)
    
    # Total billed GPU seconds (including currently active pod)
    active_pod = get_active_pod_for_service(service_id)
    additional_active_sec = 0.0
    if active_pod and active_pod.rented_at:
        additional_active_sec = max(0.0, time.time() - active_pod.rented_at)
        
    billed_gpu_seconds = (pod_stats.get("total_gpu_seconds") or 0.0) + additional_active_sec
    actual_gpuship_cost = billed_gpu_seconds * rate_sec
    
    # Counterfactual: what would an always-on GPU cost over the same duration?
    # For realism in fresh demos where service was created seconds ago, we also compute a normalized 24-hour projected baseline
    always_on_elapsed_cost = elapsed_seconds * rate_sec
    daily_always_on = rate_hr * 24.0
    
    # Projected daily cost with GPUShip (based on current hourly rate of consumption)
    projected_daily_gpuship = (actual_gpuship_cost / max(elapsed_seconds, 30.0)) * 86400.0
    
    savings_pct = 0.0
    if always_on_elapsed_cost > 0:
        savings_pct = max(0.0, min(99.0, ((always_on_elapsed_cost - actual_gpuship_cost) / always_on_elapsed_cost) * 100.0))
    elif total_jobs := job_stats.get("total_jobs", 0):
        savings_pct = 85.0  # standard theoretical intermittent saving

    return {
        "service_id": service_id,
        "total_jobs": job_stats.get("total_jobs", 0),
        "successful_jobs": job_stats.get("successful_jobs", 0),
        "failed_jobs": job_stats.get("failed_jobs", 0),
        "avg_latency_ms": round(job_stats.get("avg_latency_ms") or 0.0, 2),
        "cold_start_count": job_stats.get("cold_start_count", 0),
        "total_gpu_rentals": pod_stats.get("total_rentals", 0),
        "billed_gpu_seconds": round(billed_gpu_seconds, 1),
        "billed_gpu_hours": round(billed_gpu_seconds / 3600.0, 4),
        "actual_gpuship_cost_usd": round(actual_gpuship_cost, 4),
        "always_on_cost_usd": round(always_on_elapsed_cost, 4),
        "savings_percentage": round(savings_pct, 1),
        "daily_always_on_usd": round(daily_always_on, 2),
        "projected_daily_gpuship_usd": round(min(daily_always_on, projected_daily_gpuship), 2)
    }
