#!/bin/bash
# Start LiteLLM with tiered routing (MRGPU primary strategy)
# This script sets up local-first routing to avoid thermal throttling

set -e

CONFIG_DIR="/Users/dtm/ai-gateway/config"
STATE_DIR="/tmp/agent_state"
HANDOFF_LOG="$STATE_DIR/handoff_log.jsonl"

echo "=== Starting Tiered LLM Routing ===" 
echo "Priority: Local Ollama → TurboQuant → Cloud Fallback"

# Create state directory  
mkdir -p "$STATE_DIR"

# Initialize handoff log  
> "$HANDOFF_LOG"

# Start LiteLLM with tiered routing config
cd /Users/dtm/ai-gateway/deploy/unraid-fast-models || cd ~/grokcode && python3 -m litellm --host 0.0.0.0 \
    --port 4000 \
    --model-list-config "$CONFIG_DIR/litellm_config_tiered.yaml" \
    --saturation-threshold-ms 2000

echo "✅ Tiered routing started on port 4000" 
echo "Local models: qwen3.5:9b, gemma4:12b (Ollama)"  
echo "TurboQuant: http://host.docker.internal:8081/v1"
