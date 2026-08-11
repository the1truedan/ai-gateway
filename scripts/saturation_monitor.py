#!/usr/bin/env python3
"""Saturation monitor for tiered LLM routing. Tracks local vs cloud saturation and triggers handoffs."""

import json, time, requests, os, prometheus_client as prom

METRICS_PATH = "/metrics"
LOCAL_THRESHOLD_MS = 2000   # p95 latency > 2s = saturated
CLOUD_THRESHOLD_MS = 100    # Cloud is always fallback-only

def get_latency_stats(host):
    """Get recent latencies from Prometheus metrics."""
    try:
        resp = requests.get(f"http://localhost:{os.environ.get('PROMETHEUS_PORT', '9090')}/api/v1/query", 
                           params={"query": f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{host='{host}'}}))[1m])"})
        return float(resp.json()["data"]["result"][0]["value"][1]) if resp.status_code == 200 else None
    except: 
        return None

def check_saturation():
    """Check saturation and log handoff decisions."""
    local_lat = get_latency_stats("local-ollama")
    
    if local_lat is not None and local_lat > LOCAL_THRESHOLD_MS:
        print(f"⚠️  Local Ollama saturated at p95={local_lat:.0f}ms → triggering cloud fallback handoff")
        
        # Log to Hippo for context continuity  
        hippo_log = {
            "event": "saturation_handoff", 
            "timestamp": time.time(),
            "from_host": "local-ollama",
            "to_host": "cloud-fallback",
            "reason": f"p95 latency exceeded threshold ({LOCAL_THRESHOLD_MS}ms)",
            "context_size_kb": os.path.getsize("/tmp/agent_context.json") if os.path.exists("/tmp/agent_context.json") else 0,
        }
        
        # Save handoff context for Hippo continuity  
        with open("/tmp/handoff_log.json", "a") as f: 
            json.dump(hippo_log + {"handoff_id": time.time()}, f)

if __name__ == "__main__":
    check_saturation()
