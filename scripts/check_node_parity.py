#!/usr/bin/env python3
"""Audit static and runtime parity for Mac, gpu-host, and NAS-HOST proxy paths."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMMON = {
    "role-plan",
    "role-recon",
    "role-execute",
    "role-reason",
    "role-phi-local",
    "role-audit",
    "tier-free-cloud",
    "tier-gemini-free",
    "tier-codex-cloud",
    "tier-mimo-cloud",
}
MODEL_RE = re.compile(r"^\s*-\s*model_name:\s*([^\s#]+)\s*$", re.M)


def static_models(path: Path) -> set[str]:
    return set(MODEL_RE.findall(path.read_text(encoding="utf-8")))


def fetch_json(url: str, key: str) -> dict:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--key", default=os.environ.get("LITELLM_MASTER_KEY", ""))
    parser.add_argument("--mac", default="http://localhost:8787")
    parser.add_argument("--gpu-host", default="http://<gpu-host-ip>:8787")
    parser.add_argument("--nas-host", default="http://<nas-host-ip>:8787")
    args = parser.parse_args()

    failed = False
    static = {
        "mac": static_models(ROOT / "litellm_config.yaml"),
        "gpu-host": static_models(ROOT / "litellm_config.linux.yaml"),
    }
    for name, models in static.items():
        missing = sorted(COMMON - models)
        print(f"static {name}: {len(models)} models; missing={missing}")
        failed |= bool(missing)
    if args.static_only:
        return int(failed)

    for name, base in (("mac", args.mac), ("gpu-host", args.gpu-host), ("nas-host", args.nas-host)):
        try:
            ready = fetch_json(f"{base}/readyz", args.key)
            models = fetch_json(f"{base}/v1/models", args.key)
            ids = {item.get("id") for item in models.get("data", [])}
            missing = sorted(COMMON - ids)
            upstream = json.dumps(ready, separators=(",", ":"))[:240]
            print(f"runtime {name}: models={len(ids)} missing={missing} ready={upstream}")
            failed |= bool(missing)
        except (OSError, ValueError, urllib.error.URLError) as error:
            print(f"runtime {name}: ERROR {error}")
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
