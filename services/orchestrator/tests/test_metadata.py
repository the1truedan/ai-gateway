from __future__ import annotations

import os
import unittest
from pathlib import Path


os.environ.setdefault(
    "ORCHESTRATOR_CONFIG", str(Path(__file__).with_name("fixtures") / "routes.json")
)
os.environ.setdefault("ORCHESTRATOR_ALLOW_INSECURE", "1")

from services.orchestrator.app import Decision, _stamp_manager_metadata  # noqa: E402


class ManagerMetadataTest(unittest.TestCase):
    def test_routing_fields_merge_with_caller_metadata(self) -> None:
        payload = {"metadata": {"caller_trace_id": "trace-123"}}
        decision = Decision("gpu-host", "role-execute", "local", "test")

        _stamp_manager_metadata(payload, decision, "route-456")

        self.assertEqual(payload["metadata"]["caller_trace_id"], "trace-123")
        self.assertEqual(payload["metadata"]["manager_route_id"], "route-456")
        self.assertEqual(payload["metadata"]["manager_selected_host"], "gpu-host")
        self.assertEqual(payload["metadata"]["manager_selected_model"], "role-execute")
        self.assertEqual(payload["metadata"]["manager_tier"], "local")
        self.assertEqual(
            payload["metadata"]["spend_logs_metadata"]["manager_route_id"],
            "route-456",
        )

    def test_manager_fields_cannot_be_spoofed_by_caller(self) -> None:
        payload = {"metadata": {"manager_route_id": "caller-value"}}
        decision = Decision("nas-host", "tier-local-vision", "local", "test")

        _stamp_manager_metadata(payload, decision, "trusted-route")

        self.assertEqual(payload["metadata"]["manager_route_id"], "trusted-route")


if __name__ == "__main__":
    unittest.main()
