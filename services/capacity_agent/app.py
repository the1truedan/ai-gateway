#!/usr/bin/env python3
"""Small authenticated capacity probe for orchestration hosts."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


HOST_ID = os.environ.get("CAPACITY_AGENT_HOST_ID", platform.node())
TOKEN = os.environ.get("CAPACITY_AGENT_TOKEN", "")
THRESHOLD = float(os.environ.get("CAPACITY_SATURATION_THRESHOLD", "0.90"))
MAX_INFLIGHT = int(os.environ.get("CAPACITY_MAX_INFLIGHT", "2"))
TEST_METRICS = json.loads(os.environ.get("CAPACITY_TEST_METRICS", "{}"))

if not TOKEN and os.environ.get("CAPACITY_AGENT_ALLOW_INSECURE") != "1":
    raise RuntimeError("CAPACITY_AGENT_TOKEN is required")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _load_ratio() -> float:
    try:
        one_minute = os.getloadavg()[0]
        return _clamp(one_minute / max(1, os.cpu_count() or 1))
    except OSError:
        return 0.0


def _linux_memory_ratio() -> float | None:
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0])
        return _clamp(1 - values["MemAvailable"] / values["MemTotal"])
    except (OSError, KeyError, ValueError):
        return None


def _mac_memory_ratio() -> float | None:
    try:
        output = subprocess.check_output(["vm_stat"], text=True, timeout=1)
        page_size = 4096
        first = output.splitlines()[0]
        if "page size of" in first:
            page_size = int(first.split("page size of", 1)[1].split("bytes", 1)[0])
        pages: dict[str, int] = {}
        for line in output.splitlines()[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            pages[key] = int(value.strip().rstrip("."))
        free = pages.get("Pages free", 0) + pages.get("Pages speculative", 0)
        total_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=1))
        return _clamp(1 - (free * page_size) / total_bytes)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _memory_ratio() -> float:
    value = _linux_memory_ratio()
    if value is None and platform.system() == "Darwin":
        value = _mac_memory_ratio()
    return 0.0 if value is None else value


def _nvidia_ratio() -> float:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=2,
        )
        ratios: list[float] = []
        for line in output.splitlines():
            util, used, total = (float(item.strip()) for item in line.split(","))
            ratios.append(max(util / 100.0, used / max(1.0, total)))
        return _clamp(max(ratios, default=0.0))
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def capacity() -> dict[str, Any]:
    if TEST_METRICS:
        metrics = dict(TEST_METRICS)
    else:
        metrics = {
            "load_ratio": _load_ratio(),
            "memory_ratio": _memory_ratio(),
            "accelerator_ratio": _nvidia_ratio(),
            "inflight": int(os.environ.get("CAPACITY_INFLIGHT", "0")),
        }
    load = _clamp(float(metrics.get("load_ratio", 0.0)))
    memory = _clamp(float(metrics.get("memory_ratio", 0.0)))
    accelerator = _clamp(float(metrics.get("accelerator_ratio", 0.0)))
    inflight = max(0, int(metrics.get("inflight", 0)))
    queue_ratio = _clamp(inflight / max(1, MAX_INFLIGHT))
    score = max(load, memory, accelerator, queue_ratio)
    return {
        "host": HOST_ID,
        "available": True,
        "saturated": score >= THRESHOLD,
        "score": round(score, 4),
        "metrics": {
            "load_ratio": round(load, 4),
            "memory_ratio": round(memory, 4),
            "accelerator_ratio": round(accelerator, 4),
            "inflight": inflight,
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "manager-capacity-agent/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("CAPACITY_AGENT_ACCESS_LOG") == "1":
            super().log_message(fmt, *args)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "host": HOST_ID})
            return
        if self.path != "/capacity":
            self._json(404, {"error": {"code": "not_found"}})
            return
        if TOKEN and self.headers.get("Authorization", "") != f"Bearer {TOKEN}":
            self._json(401, {"error": {"code": "unauthorized"}})
            return
        self._json(200, capacity())


def main() -> None:
    host = os.environ.get("CAPACITY_AGENT_HOST", "0.0.0.0")
    port = int(os.environ.get("CAPACITY_AGENT_PORT", "8794"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
