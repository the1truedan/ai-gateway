#!/usr/bin/env python3
"""Saturation monitor for tiered LLM routing. Tracks local vs cloud saturation and triggers handoffs."""

import json, time, requests, os

METRICS_PATH = "/metrics"
LOCAL_THRESHOLD_MS = 2000   # avg latency > 2s = saturated
CLOUD_THRESHOLD_MS = 100    # Cloud is always fallback-only
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://192.168.1.2:9090")

# Real metric, confirmed live 2026-08-11. Headroom is the single front door
# for all traffic (local + cloud) - there is no per-host label to filter on,
# so the previous host='local-ollama' query never matched anything real (nor
# did the metric name http_request_duration_seconds_bucket exist). Also
# fixed: this was querying localhost instead of Tower, where Prometheus
# actually runs.
def get_latency_stats():
    """Get recent avg request latency from Headroom's Prometheus metrics."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": "rate(headroom_latency_ms_sum[5m]) / rate(headroom_latency_ms_count[5m])"},
            timeout=5,
        )
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        return float(result[0]["value"][1]) if result else None
    except Exception:
        return None

def check_saturation():
    """Check saturation and log handoff decisions."""
    avg_lat = get_latency_stats()

    if avg_lat is not None and avg_lat > LOCAL_THRESHOLD_MS:
        print(f"⚠️  Local saturated at avg={avg_lat:.0f}ms → triggering cloud fallback handoff")

        # Log to Hippo for context continuity
        hippo_log = {
            "event": "saturation_handoff",
            "timestamp": time.time(),
            "from_host": "local",
            "to_host": "cloud-fallback",
            "reason": f"avg latency exceeded threshold ({LOCAL_THRESHOLD_MS}ms)",
            "context_size_kb": os.path.getsize("/tmp/agent_context.json") if os.path.exists("/tmp/agent_context.json") else 0,
            "handoff_id": time.time(),
        }

        # Save handoff context for Hippo continuity
        with open("/tmp/handoff_log.json", "a") as f:
            f.write(json.dumps(hippo_log) + "\n")

if __name__ == "__main__":
    check_saturation()
