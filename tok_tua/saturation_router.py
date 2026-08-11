"""Saturation-aware routing for tok-tua. Routes LLM calls to appropriate host based on load."""

import os, json, time, requests
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config" / "tok_tua.json"
HANDOFF_LOG = "/tmp/handoff_log.json"
LOCAL_THRESHOLD_MS = 2000   # avg latency threshold for saturation
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://192.168.1.2:9090")

# Real metric, confirmed live 2026-08-11 via direct Prometheus query. Headroom
# is the single front door for all traffic (local + cloud), so there is no
# per-host label to filter on - `host="local-ollama"` (the previous version
# of this function) never existed in the real metric set, which is why
# get_saturation_status() always silently fell through to its hardcoded
# "never saturated" except-branch. litellm_* request-latency metrics were
# checked too but currently return zero live samples (not actively populated
# right now) - avg latency over Headroom's own counters is the only metric
# with real data today.
def get_saturation_status():
    """Check current avg request latency from Headroom's Prometheus metrics."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": "rate(headroom_latency_ms_sum[5m]) / rate(headroom_latency_ms_count[5m])"},
            timeout=5,
        )
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        if not result:
            return {"local_saturated": False, "p95_latency_ms": None, "cloud_needed": False,
                     "note": "no recent traffic to measure"}
        avg_latency_ms = float(result[0]["value"][1])
        if avg_latency_ms != avg_latency_ms:  # NaN: rate() over an idle window (0/0), not an error
            return {"local_saturated": False, "p95_latency_ms": None, "cloud_needed": False,
                     "note": "no recent traffic to measure"}
        saturated = avg_latency_ms > LOCAL_THRESHOLD_MS
        return {
            "local_saturated": saturated,
            "p95_latency_ms": avg_latency_ms,  # actually avg, not p95 - Headroom doesn't expose a latency histogram, only sum/count
            "cloud_needed": saturated,
        }
    except Exception as e:
        print(f"Saturation check error (non-fatal): {e}")
        return {"local_saturated": False, "p95_latency_ms": None, "cloud_needed": False, "error": str(e)}

def resolve_launch(model_id, context=None):
    """Resolve model launch with saturation-aware routing."""
    
    status = get_saturation_status()
    
    # If local is saturated and we have a full conversation history  
    if status["cloud_needed"] and context: 
        print(f"🔄 Handoff triggered: p95={status['p95_latency_ms']}ms → cloud fallback")

    return {
        "cli": os.environ.get("LOCAL_LITELLM_CLI", "headroom-local-cli"),  
        "effective_cli": "litellm-headroom:8787", 
        "kind": status["cloud_needed"] and "fallback" or "local-first", 
        "model": model_id,
    }

if __name__ == "__main__":
    print("=== Saturation Router Test ===")  
    status = get_saturation_status()
    print(json.dumps(status, indent=2))
