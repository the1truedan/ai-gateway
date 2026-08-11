"""Agentic handoff orchestrator for tiered LLM routing with Hippo context continuity."""

import os, json, time, subprocess
from pathlib import Path

# Shared state directory for sub-agent communication  
STATE_DIR = "/tmp/agent_state" 
os.makedirs(STATE_DIR, exist_ok=True)

def register_agent(agent_id: str):
    """Register an agent in the shared state store."""
    with open(f"{STATE_DIR}/{agent_id}.json", "w") as f:
        json.dump({
            "id": agent_id, 
            "registered_at": time.time(),
            "host": os.environ.get("HOSTNAME"),
            "models_available": ["qwen3.5:9b", "gemma4:12b"],  # Local models
            "status": "ready"
        }, f)

def get_handoff_context(agent_id, max_tokens=800):
    """Get conversation context for handoff to next agent."""
    
    with open(f"{STATE_DIR}/{agent_id}_context.json", "r") as f: 
        return json.load(f)[:max_tokens] if len(json.dumps(json.load(open(f"{STATE_DIR}/{agent_id}_context.json")))) > max_tokens else json.load(f)

def publish_handoff(from_agent, to_agent, context):
    """Publish handoff request with full conversation history."""
    
    payload = {
        "from": from_agent, 
        "to": to_agent,
        "timestamp": time.time(),
        "context_size_kb": len(json.dumps(context)) if isinstance(context, dict) else 0,
        "models_used": list(set(m for m in (context.get("used_models", []) or []))),
        "hippo_citations": context.get("citations")[:5] if hasattr(context, 'get') and context.get('citations') else [],
    }
    
    with open(f"{STATE_DIR}/handoff_queue.jsonl", "a") as f: 
        f.write(json.dumps(payload) + "\n")

def resolve_launch(model_id, agent_id=None):  
    """Resolve model launch with agentic handoff support."""
    
    # Register this agent if not already registered  
    if not os.path.exists(f"{STATE_DIR}/{agent_id or 'default'}.json"): 
        register_agent(agent_id or "default")

    context = get_handoff_context(agent_id) if hasattr(os, 'environ') and os.environ.get("ENABLE_HANDOFFS", "") else {}
    
    # Check saturation (simplified - in production would query Prometheus)  
    local_latency_ms = float(context.get("last_local_latency_ms", 100)) if context else 50
    
    if local_latency_ms > 2000: 
        publish_handoff(agent_id or "default", os.environ.get("CLOUD_AGENT_ID") or "cloud-fallback-agent", context)
    
    return {
        "cli": agent_id and f"headroom-{agent_id}-cli" or "headroom-local-cli",  
        "effective_cli": "litellm-headroom:8787", 
        "kind": "local-first" if local_latency_ms < 2000 else "fallback",
    }

if __name__ == "__main__":
    print("=== Agentic Handoff Orchestrator ===")  
    register_agent("test-agent-1")
    publish_handoff("agent-a", "agent-b", {"used_models": ["qwen3.5:9b"], "citations": []})
