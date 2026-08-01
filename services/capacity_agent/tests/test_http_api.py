from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return int(sock.getsockname()[1])


class CapacityAgentHTTPTest(unittest.TestCase):
    def start_agent(self, metrics: dict, *, token: str = "test-token") -> tuple[subprocess.Popen, int]:
        port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "CAPACITY_AGENT_PORT": str(port),
                "CAPACITY_AGENT_TOKEN": token,
                "CAPACITY_TEST_METRICS": json.dumps(metrics),
                "CAPACITY_AGENT_HOST_ID": "fixture-host",
                "CAPACITY_AGENT_ALLOW_INSECURE": "0",
            }
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "services.capacity_agent.app"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=0.2):
                    return process, port
            except (OSError, urllib.error.URLError):
                time.sleep(0.05)
        stderr = process.stderr.read() if process.stderr else ""
        process.terminate()
        raise RuntimeError(f"capacity agent did not start: {stderr}")

    def get(self, port: int, path: str, *, token: str | None = None) -> tuple[int, dict]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        request = urllib.request.Request(f"http://localhost:{port}{path}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            finally:
                error.close()

    def test_capacity_reports_available_host(self) -> None:
        process, port = self.start_agent(
            {"load_ratio": 0.2, "memory_ratio": 0.3, "accelerator_ratio": 0.4, "inflight": 0}
        )
        try:
            status, payload = self.get(port, "/capacity", token="test-token")
            self.assertEqual(status, 200)
            self.assertEqual(payload["host"], "fixture-host")
            self.assertFalse(payload["saturated"])
            self.assertLess(payload["score"], 0.8)
        finally:
            process.terminate()
            process.wait(timeout=5)
            if process.stderr:
                process.stderr.close()

    def test_capacity_reports_saturation_when_accelerator_is_full(self) -> None:
        process, port = self.start_agent(
            {"load_ratio": 0.2, "memory_ratio": 0.5, "accelerator_ratio": 0.95, "inflight": 1}
        )
        try:
            status, payload = self.get(port, "/capacity", token="test-token")
            self.assertEqual(status, 200)
            self.assertTrue(payload["saturated"])
            self.assertGreaterEqual(payload["score"], 0.9)
        finally:
            process.terminate()
            process.wait(timeout=5)
            if process.stderr:
                process.stderr.close()

    def test_capacity_requires_bearer_token(self) -> None:
        process, port = self.start_agent(
            {"load_ratio": 0.1, "memory_ratio": 0.1, "accelerator_ratio": 0.1, "inflight": 0}
        )
        try:
            status, payload = self.get(port, "/capacity")
            self.assertEqual(status, 401)
            self.assertEqual(payload["error"]["code"], "unauthorized")
        finally:
            process.terminate()
            process.wait(timeout=5)
            if process.stderr:
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
