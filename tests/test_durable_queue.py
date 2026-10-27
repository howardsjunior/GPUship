import unittest
import asyncio
import uuid
import os
import tempfile
from gpuship.db import database as db
from gpuship.models import JobCreate, JobStatus, Service
from gpuship.queue.durable_queue import DurableQueue

class TestDurableQueue(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        db.init_db()
        self.queue = DurableQueue()
        self.service_id = f"test_svc_{uuid.uuid4().hex[:6]}"
        db.create_service(Service(
            id=self.service_id,
            name="Test Service",
            repo_url="https://github.com/example/repo",
            branch="main",
            dockerfile_path="Dockerfile",
            health_endpoint="/health",
            gpu_spec="rtx4090",
            price_ceiling_hr=1.5,
            idle_timeout_seconds=30,
            keep_warm_count=0
        ))

    async def test_enqueue_and_retrieve(self):
        job, is_new = await self.queue.enqueue(
            self.service_id,
            JobCreate(input={"prompt": "test prompt 1"})
        )
        self.assertTrue(is_new)
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.service_id, self.service_id)

        # Retrieve next job
        next_job = self.queue.get_next_job(self.service_id)
        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.id, job.id)

    async def test_idempotency_deduplication(self):
        key = f"idemp_{uuid.uuid4().hex}"
        job1, is_new1 = await self.queue.enqueue(
            self.service_id,
            JobCreate(input={"prompt": "dedup test"}, idempotency_key=key)
        )
        self.assertTrue(is_new1)

        # Re-submitting with identical key must return existing job
        job2, is_new2 = await self.queue.enqueue(
            self.service_id,
            JobCreate(input={"prompt": "dedup test different payload"}, idempotency_key=key)
        )
        self.assertFalse(is_new2)
        self.assertEqual(job1.id, job2.id)

    async def test_job_completion_lifecycle(self):
        job, _ = await self.queue.enqueue(
            self.service_id,
            JobCreate(input={"text": "audio transcription"})
        )
        self.queue.mark_assigned(job.id, "pod_123")
        self.queue.mark_running(job.id, cold_start_incurred=True)
        self.queue.mark_completed(
            job.id,
            result_payload={"transcription": "hello"},
            latency_ms=350.0,
            estimated_cost=0.00004
        )

        completed = self.queue.get_job(job.id)
        self.assertEqual(completed.status, JobStatus.SUCCEEDED)
        self.assertEqual(completed.result_payload["transcription"], "hello")
        self.assertEqual(completed.latency_ms, 350.0)

if __name__ == "__main__":
    unittest.main()

