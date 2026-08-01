#!/usr/bin/env bash
# Load one M4-safe LM Studio model (unloads others first). Usage:
#   ./scripts/load_lmstudio_model.sh mlx-fast
#   ./scripts/load_lmstudio_model.sh lms-local
#   ./scripts/load_lmstudio_model.sh lms-vision
#   ./scripts/load_lmstudio_model.sh google/gemma-3n-e4b
set -euo pipefail

export PATH="${HOME}/.lmstudio/bin:${PATH}"
LMS_BIN="${LMS_BIN:-$(command -v lms || true)}"

if [[ -z "$LMS_BIN" || ! -x "$LMS_BIN" ]]; then
  echo "lms CLI not found. Install LM Studio and ensure ~/.lmstudio/bin/lms exists." >&2
  exit 1
fi

ALIAS="${1:-mlx-fast}"
case "$ALIAS" in
  mlx-fast|manager-mlx-fast|tier-local-mlx)
    MODEL_KEY="google/gemma-3n-e4b"
    ;;
  lms-local|manager-lms-local)
    MODEL_KEY="qwen/qwen3.5-9b"
    ;;
  lms-vision|manager-lms-vision)
    MODEL_KEY="google/gemma-4-e4b"
    ;;
  mlx-tiny|qwen17)
    MODEL_KEY="qwen3-1.7b-mlx-python-18k-alpaca"
    ;;
  *)
    MODEL_KEY="$ALIAS"
    ;;
esac

# Reject known agent-unfit defaults on 24 GB unless FORCE=1
case "$MODEL_KEY" in
  qwen3-coder-30b-a3b-moe|qwen3.5-27b-claude-4.6-opus-distilled-mlx|qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive|dolphin-mistral-glm-4.7-flash-24b-venice-edition-thinking-uncensored-i1)
    if [[ "${FORCE:-0}" != "1" ]]; then
      echo "Refusing to load '$MODEL_KEY' on M4 24GB agent profile (set FORCE=1 to override)." >&2
      exit 2
    fi
    ;;
esac

if ! "$LMS_BIN" server status 2>/dev/null | grep -qi "running"; then
  echo "Starting LM Studio server..."
  "$LMS_BIN" server start
fi

echo "Unloading any currently loaded models..."
"$LMS_BIN" unload --all 2>/dev/null || "$LMS_BIN" unload -a 2>/dev/null || true

echo "Loading $MODEL_KEY (alias=$ALIAS)..."
"$LMS_BIN" load "$MODEL_KEY" -y --ttl "${LMSTUDIO_TTL:-3600}"
echo "Loaded. LiteLLM aliases: manager-mlx-fast | manager-lms-local | manager-lms-vision | tier-local-mlx"
"$LMS_BIN" ps || true
