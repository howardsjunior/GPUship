import unittest
import asyncio
import uuid
import time
from gpuship.db import database as db
from gpuship.models import JobCreate, JobStatus, Service, PodState
from gpuship.queue.durable_queue import DurableQueue
from gpuship.lium.driver import LiumDriver
from gpuship.reconciler.reconciler import Reconciler

class TestReconcilerScaleToZero(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        db.init_db()
        self.queue = DurableQueue()
        self.driver = LiumDriver(simulation=True)
        self.driver.speed_multiplier = 0.05  # Ultra fast for unit tests
        self.reconciler = Reconciler(self.queue, self.driver)
        
        self.service_id = f"test_svc_{uuid.uuid4().hex[:6]}"
        self.service = db.create_service(Service(
            id=self.service_id,
            name="Test Scale to Zero Service",
            repo_url="https://github.com/example/whisper",
            branch="main",
            dockerfile_path="Dockerfile",
            health_endpoint="/health",
            gpu_spec="rtx4090",
            price_ceiling_hr=1.5,
            idle_timeout_seconds=1,  # 1s idle timeout for instant test
            keep_warm_count=0
        ))

    async def test_demand_triggers_cold_start_and_execution(self):
        # 1. Enqueue job
        job, _ = await self.queue.enqueue(
            self.service_id,
            JobCreate(input={"text": "Test input for cold start"})
        )
        
        # 2. Run reconciler step
        await self.reconciler._reconcile_service(self.service)
        
        # Pod should now be provisioned
        active_pod = db.get_active_pod_for_service(self.service_id)
        self.assertIsNotNone(active_pod)
        self.assertEqual(active_pod.state, PodState.PROVISIONING)

        # 3. Simulate passage of time for provisioning -> booting -> loading -> ready -> executed
        completed_job = None
        for _ in range(30):
            await asyncio.sleep(0.05)
            await self.reconciler._reconcile_service(self.service)
            current = db.get_job(job.id)
            if current and current.status == JobStatus.SUCCEEDED:
                completed_job = current
                break

        self.assertIsNotNone(completed_job)
        self.assertEqual(completed_job.status, JobStatus.SUCCEEDED)
        self.assertIsNotNone(completed_job.result_payload)

    async def test_scale_to_zero_after_idle_timeout(self):
        # Provision pod manually to READY state
        pod_data = await self.driver.rent_pod(self.service_id, "dep_1", "rtx4090", "image:latest")
        from gpuship.models import Pod
        pod = Pod(
            id=f"pod_{pod_data['lium_pod_id']}",
            service_id=self.service_id,
            deployment_id="dep_1",
            provider="lium",
            lium_pod_id=pod_data["lium_pod_id"],
            gpu_type="rtx4090",
            port=8000,
            state=PodState.READY,
            rented_at=time.time(),
            idle_started_at=time.time() - 2.0 # 2 seconds ago, exceeds 1s timeout
        )
        db.create_pod(pod)

        # Reconcile service: should detect idle timeout and release pod
        await self.reconciler._reconcile_service(self.service)
        
        updated_pod = db.get_pod(pod.id)
        self.assertEqual(updated_pod.state, PodState.TERMINATED)
        self.assertGreater(updated_pod.total_billed_seconds, 0)

    async def test_reconcile_orphaned_pods_recovery(self):
        # Insert a pod that exists locally in DB but is abandoned/missing on provider
        from gpuship.models import Pod
        stale_pod_id = f"stale_pod_{uuid.uuid4().hex[:6]}"
        db.create_pod(Pod(
            id=stale_pod_id,
            service_id=self.service_id,
            deployment_id="dep_stale",
            provider="lium",
            lium_pod_id="non_existent_on_provider",
            gpu_type="rtx4090",
            port=8000,
            state=PodState.READY,
            rented_at=time.time() - 100.0,
            idle_started_at=time.time() - 50.0
        ))

        # Run orphan reconciliation
        await self.reconciler.reconcile_orphaned_pods()

        # The stale pod must be cleanly marked TERMINATED
        recovered_pod = db.get_pod(stale_pod_id)
        self.assertEqual(recovered_pod.state, PodState.TERMINATED)

if __name__ == "__main__":
    unittest.main()

