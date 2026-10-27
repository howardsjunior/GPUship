import unittest
from starlette.testclient import TestClient
from gpuship.main import app
from gpuship.db import database as db

class TestGatewayAPI(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.client = TestClient(app)

    def test_health_check(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "HEALTHY")
        self.assertEqual(data["platform"], "GPUShip")

    def test_list_and_create_service(self):
        # List services
        res = self.client.get("/api/v1/services")
        self.assertEqual(res.status_code, 200)
        initial_count = len(res.json())

        # Create new service
        create_res = self.client.post("/api/v1/services", json={
            "name": "Integration Test SDXL API",
            "repo_url": "https://github.com/example/sdxl",
            "branch": "main",
            "dockerfile_path": "Dockerfile",
            "health_endpoint": "/health",
            "gpu_spec": "rtx4090",
            "price_ceiling_hr": 2.0,
            "idle_timeout_seconds": 45,
            "keep_warm_count": 0
        })
        self.assertEqual(create_res.status_code, 200)
        svc = create_res.json()
        self.assertEqual(svc["name"], "Integration Test SDXL API")
        self.assertIsNotNone(svc["active_deployment_id"])

    def test_job_enqueue_and_status(self):
        # Create service
        create_res = self.client.post("/api/v1/services", json={
            "name": "Job API Service",
            "repo_url": "https://github.com/example/api",
            "gpu_spec": "rtx4090",
            "price_ceiling_hr": 1.5,
            "idle_timeout_seconds": 30,
            "keep_warm_count": 0
        })
        svc_id = create_res.json()["id"]

        # Enqueue job via stable gateway
        job_res = self.client.post(
            f"/api/v1/services/{svc_id}/jobs",
            json={"input": {"prompt": "Hello test"}}
        )
        self.assertEqual(job_res.status_code, 202)
        job_data = job_res.json()
        self.assertEqual(job_data["status"], "QUEUED")
        job_id = job_data["job_id"]

        # Fetch status
        status_res = self.client.get(f"/api/v1/services/{svc_id}/jobs/{job_id}")
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()
        self.assertEqual(status_data["job_id"], job_id)

    def test_metrics_endpoint(self):
        services = self.client.get("/api/v1/services").json()
        if services:
            svc_id = services[0]["id"]
            metrics_res = self.client.get(f"/api/v1/services/{svc_id}/metrics")
            self.assertEqual(metrics_res.status_code, 200)
            metrics = metrics_res.json()
            self.assertIn("savings_percentage", metrics)
            self.assertIn("actual_gpuship_cost_usd", metrics)
            self.assertIn("always_on_cost_usd", metrics)

if __name__ == "__main__":
    unittest.main()

