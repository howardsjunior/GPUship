import unittest
import asyncio
from starlette.testclient import TestClient
from gpuship.main import app

class TestDecisiveDemo(unittest.TestCase):
    def test_decisive_demo_execution(self):
        client = TestClient(app)
        res = client.post("/api/v1/demo/run-decisive")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "DECISIVE_DEMO_PASSED")
        self.assertIn("trace", data)
        self.assertIn("summary", data)
        
        # Verify all 4 major stages in the trace
        steps = [e["step"] for e in data["trace"]]
        self.assertIn("1_GIT_PUSH_AND_BUILD", steps)
        self.assertIn("2_LIVE_API_REQUEST", steps)
        self.assertIn("3_IDLE_SCALE_TO_ZERO", steps)
        self.assertIn("4_NEW_REQUEST_SAME_URL", steps)

if __name__ == "__main__":
    unittest.main()

