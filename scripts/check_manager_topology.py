#!/usr/bin/env python3
"""Fail when the checked-in topology no longer has the M4 as sole manager."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    mac = (ROOT / "docker-compose.mac.yml").read_text(encoding="utf-8")
    linux = (ROOT / "docker-compose.linux.yml").read_text(encoding="utf-8")
    nas_host = (ROOT / "deploy/nas-host-orchestration/docker-compose.yml").read_text(
        encoding="utf-8"
    )
    routes = json.loads(
        (ROOT / "config/orchestrator/routes.json").read_text(encoding="utf-8")
    )

    checks = {
        "Mac overlay defines orchestrator": "  orchestrator:\n" in mac,
        "Mac Headroom targets local orchestrator": (
            "HEADROOM_OPENAI_TARGET:-http://orchestrator:8790/v1" in mac
        ),
        "gpu-host Headroom targets Mac manager": (
            "HEADROOM_OPENAI_TARGET:-http://<mac-client-ip>:8790/v1" in linux
        ),
        "nas-host Headroom targets Mac manager": (
            "HEADROOM_OPENAI_TARGET:-http://<mac-client-ip>:8790/v1" in nas_host
        ),
        "nas-host manager is rollback-only": 'profiles: ["rollback"]' in nas_host,
        "Mac LiteLLM is central bus": (
            routes.get("gateway_base_url") == "http://litellm:4000/v1"
        ),
        "Workers use central bus aliases": all(
            host.get("base_url") == "http://litellm:4000/v1"
            for host in routes.get("hosts", {}).values()
        ),
    }
    for description, passed in checks.items():
        print(f"{'OK' if passed else 'FAIL'} - {description}")
    return int(not all(checks.values()))


if __name__ == "__main__":
    sys.exit(main())
