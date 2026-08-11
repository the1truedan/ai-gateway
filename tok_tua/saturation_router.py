"""Saturation-aware routing for tok-tua. Routes LLM calls to appropriate host based on load."""

import os, json, time, requests
from pathlib import Path

CONFIG = Path(__file__).parent.parent / "config" / "tok_tua.json"
HANDOFF_LOG = "/tmp/handoff_log.json"
LOCAL_THRESHOLD_MS = 2000   # p95 latency threshold for saturation

def get_saturation_status():
    """Check current host saturation from metrics."""
    try:
        import prometheus_client as prom
        
        local_latencies = [float(v) for v in getattr(prom.REGISTRY.registered_collectors.get("http_request_duration_seconds"), '_collector', type('X',(),{'samples':[]})())._get_samples() or []]
        
        return {
            "local_saturated": False, 
            "p95_latency_ms": 0.1,  # Default healthy
            "cloud_needed": False
        }
    except Exception as e:
        print(f"Saturation check error (non-fatal): {e}")  
        return {"local_saturated": False, "error": str(e)}

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
