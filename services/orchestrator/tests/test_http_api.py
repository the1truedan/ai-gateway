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


class OrchestratorHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "ORCHESTRATOR_PORT": str(cls.port),
                "ORCHESTRATOR_CONFIG": str(
                    Path(__file__).with_name("fixtures") / "routes.json"
                ),
                "ORCHESTRATOR_TEST_CAPACITY": json.dumps(
                    {
                        "gpu-host": {"saturated": False, "score": 0.1},
                        "mac-client": {"saturated": False, "score": 0.2},
                        "nas-host": {"saturated": False, "score": 0.8},
                    }
                ),
                "ORCHESTRATOR_ALLOW_INSECURE": "1",
            }
        )
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "services.orchestrator.app"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{cls.port}/healthz", timeout=0.25
                ) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.05)
        stderr = cls.process.stderr.read() if cls.process.stderr else ""
        raise RuntimeError(f"orchestrator did not start: {stderr}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.process.terminate()
        cls.process.wait(timeout=5)
        if cls.process.stderr:
            cls.process.stderr.close()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict, dict[str, str]]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            f"http://localhost:{self.port}{path}",
            method=method,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return (
                    response.status,
                    json.load(response),
                    {key.lower(): value for key, value in response.headers.items()},
                )
        except urllib.error.HTTPError as error:
            try:
                return (
                    error.code,
                    json.load(error),
                    {key.lower(): value for key, value in error.headers.items()},
                )
            finally:
                error.close()

    def decision(
        self,
        prompt: str,
        *,
        model: str = "manager-auto",
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        status, payload, _ = self.request(
            "/v1/router/decision",
            method="POST",
            body={"model": model, "messages": [{"role": "user", "content": prompt}]},
            headers=headers,
        )
        return status, payload

    def test_model_catalog_exposes_auto_and_compatibility_roles(self) -> None:
        status, payload, _ = self.request("/v1/models")
        self.assertEqual(status, 200)
        ids = {entry["id"] for entry in payload["data"]}
        self.assertTrue(
            {
                "manager-auto",
                "manager-plan",
                "manager-research",
                "manager-code",
                "manager-reason",
                "manager-phi-local",
                "manager-review",
                "manager-codex-paid",
                "manager-claude-paid",
                "manager-mimo-paid",
                "manager-grok-paid",
            }.issubset(ids)
        )

    def test_cuda_coding_job_prefers_gpu_host_execution(self) -> None:
        status, payload = self.decision(
            "Implement and benchmark this CUDA kernel on the NVIDIA GPU"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "gpu-host")
        self.assertEqual(payload["selected_model"], "manager-code")
        self.assertEqual(payload["tier"], "local")

    def test_explicit_nvidia_tier_pins_gpu_host_without_prompt_hint(self) -> None:
        status, payload = self.decision("Explain this code", model="manager-code")
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "gpu-host")
        self.assertEqual(payload["selected_model"], "manager-code")
        self.assertEqual(payload["tier"], "local")

    def test_explicit_nvidia_tier_stays_on_gpu_host_with_sensitive_context(self) -> None:
        status, payload = self.decision(
            "Review this caregiver code that handles patient medication data",
            model="manager-code",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "gpu-host")
        self.assertEqual(payload["selected_model"], "manager-phi-local")
        self.assertEqual(payload["tier"], "local")

    def test_explicit_nvidia_agent_fallback_pins_gpu_host(self) -> None:
        status, payload = self.decision(
            "Use tools to review this caregiver application",
            model="manager-code",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "gpu-host")
        self.assertEqual(payload["selected_model"], "manager-phi-local")
        self.assertEqual(payload["tier"], "local")

    def test_apple_job_prefers_mac_client_execution(self) -> None:
        status, payload = self.decision(
            "Profile this Metal and CoreML pipeline on macOS"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "mac-client")
        self.assertEqual(payload["selected_model"], "manager-code")

    def test_opencv_job_prefers_nas_host_vision_model(self) -> None:
        status, payload = self.decision("Extract image edges with OpenCV")
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "nas-host")
        self.assertEqual(payload["selected_model"], "manager-vision")

    def test_lightweight_job_uses_nas_host_small_model(self) -> None:
        status, payload = self.decision("Give me a quick lightweight summary")
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "nas-host")
        self.assertEqual(payload["selected_model"], "manager-code")

    def test_automatic_planning_stays_on_local_reasoning(self) -> None:
        status, payload = self.decision(
            "Plan and architect a complex distributed system"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["tier"], "local")
        self.assertEqual(payload["selected_model"], "manager-reason")

    def test_phi_is_confined_to_local_models(self) -> None:
        status, payload = self.decision(
            "Summarize this patient's diagnosis and medication list"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_model"], "manager-phi-local")
        self.assertEqual(payload["tier"], "local")
        self.assertFalse(payload["cloud_allowed"])

    def test_explicit_privacy_header_forces_local(self) -> None:
        status, payload = self.decision(
            "Plan a complex case",
            headers={"X-Manager-Privacy": "phi"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_model"], "manager-phi-local")

    def test_responses_api_input_is_classified(self) -> None:
        status, payload, _ = self.request(
            "/v1/router/decision",
            method="POST",
            body={
                "model": "manager-auto",
                "input": "Analyze this CoreML implementation on macOS",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_host"], "mac-client")
        self.assertEqual(payload["selected_model"], "manager-code")

    def test_cloud_is_never_selected_automatically(self) -> None:
        status, payload = self.decision(
            "Design a complex distributed system with a detailed implementation plan",
            headers={"X-Manager-Test-Capacity": "all-saturated"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "cloud_consent_required")
        self.assertEqual(
            payload["error"]["allowed_models"],
            [
                "manager-openrouter-free",
                "manager-codex-paid",
                "manager-claude-paid",
                "manager-gemini-paid",
                "manager-grok-paid",
                "manager-mimo-paid",
                "manager-hf-paid",
            ],
        )

    def test_explicit_free_alias_is_also_a_consent_signal(self) -> None:
        status, payload = self.decision(
            "Research current approaches", model="manager-openrouter-free"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["tier"], "free-cloud")
        self.assertTrue(payload["cloud_allowed"])

    def test_explicit_paid_alias_is_the_approval_signal(self) -> None:
        status, payload = self.decision(
            "Produce a coding plan", model="manager-codex-paid"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["selected_model"], "manager-codex-paid")
        self.assertEqual(payload["tier"], "paid-cloud")
        self.assertTrue(payload["paid_approved"])

    def test_phi_cannot_use_explicit_paid_alias(self) -> None:
        status, payload = self.decision(
            "Review the patient's medical record", model="manager-mimo-paid"
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "sensitive_cloud_blocked")
        self.assertEqual(payload["error"]["recommended_model"], "manager-phi-local")


if __name__ == "__main__":
    unittest.main()
