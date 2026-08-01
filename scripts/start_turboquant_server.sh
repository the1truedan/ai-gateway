#!/usr/bin/env bash
# Start TurboQuant+ llama-server on the M4 host (parallel to Ollama).
# CLI/export overrides beat turboquant.env (same pattern as TURBOQUANT_PROFILE).
set -euo pipefail

ENV_FILE="${TURBOQUANT_ENV:-/Volumes/models/turboquant/turboquant.env}"

# Capture overrides before sourcing env (env file must not clobber explicit exports)
CLI_PROFILE="${TURBOQUANT_PROFILE:-}"
CLI_CTX="${TURBOQUANT_CTX_SIZE:-}"
CLI_MODEL="${TURBOQUANT_MODEL:-}"
CLI_ALIAS="${TURBOQUANT_ALIAS:-}"
CLI_PARALLEL="${TURBOQUANT_PARALLEL:-}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi
[[ -n "$CLI_PROFILE" ]] && TURBOQUANT_PROFILE="$CLI_PROFILE"
[[ -n "$CLI_CTX" ]] && TURBOQUANT_CTX_SIZE="$CLI_CTX"
[[ -n "$CLI_MODEL" ]] && TURBOQUANT_MODEL="$CLI_MODEL"
[[ -n "$CLI_ALIAS" ]] && TURBOQUANT_ALIAS="$CLI_ALIAS"
[[ -n "$CLI_PARALLEL" ]] && TURBOQUANT_PARALLEL="$CLI_PARALLEL"

# Keep HF pulls on external models volume (turboquant.env sets these; export for -hf loads too)
export HF_HOME="${HF_HOME:-${TURBOQUANT_HF_CACHE:-/Volumes/models/turboquant/hf-cache}}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"

BIN="${TURBOQUANT_ROOT:?}/llama-server"
MODELS="${TURBOQUANT_MODELS:?}"
LOGS="${TURBOQUANT_LOGS:-/Volumes/models/turboquant/logs}"
RUN="${TURBOQUANT_RUN:-/Volumes/models/turboquant/run}"
PORT="${TURBOQUANT_PORT:-8081}"
HOST="${TURBOQUANT_HOST:-127.0.0.1}"
PROFILE="${TURBOQUANT_PROFILE:-reasoning}"
# M4 24GB: 16K is safer default than 65K×multi-slot (Metal OOM → Compute error)
CTX="${TURBOQUANT_CTX_SIZE:-16384}"
CTK="${TURBOQUANT_CACHE_TYPE_K:-q8_0}"
CTV="${TURBOQUANT_CACHE_TYPE_V:-turbo3}"
# Single slot on Mini — 4× parallel slots multiplies KV RAM
PARALLEL="${TURBOQUANT_PARALLEL:-1}"

mkdir -p "$LOGS" "$RUN"

case "$PROFILE" in
  reasoning)
    MODEL="${TURBOQUANT_MODEL:-${TURBOQUANT_MODEL_REASONING:-$MODELS/gemma4-26b-iq4.gguf}}"
    ALIAS="${TURBOQUANT_ALIAS:-${TURBOQUANT_ALIAS_REASONING:-gemma4-orchestrator}}"
    PORT="${TURBOQUANT_PORT:-8081}"
    ;;
  coder)
    MODEL="${TURBOQUANT_MODEL:-${TURBOQUANT_MODEL_CODER:-$MODELS/qwen3.5-9b-q4_k_s.gguf}}"
    ALIAS="${TURBOQUANT_ALIAS:-${TURBOQUANT_ALIAS_CODER:-qwen35-agent}}"
    PORT="${TURBOQUANT_PORT_CODER:-${TURBOQUANT_PORT:-8082}}"
    ;;
  *)
    echo "Unknown TURBOQUANT_PROFILE='$PROFILE' (use reasoning or coder)" >&2
    exit 1
    ;;
esac

if [[ ! -x "$BIN" ]]; then
  echo "TurboQuant binary not found: $BIN" >&2
  exit 1
fi
if [[ ! -f "$MODEL" ]]; then
  echo "Model not found: $MODEL" >&2
  exit 1
fi

PIDFILE="$RUN/llama-server-${PROFILE}.pid"
LOGFILE="$LOGS/llama-server-${PROFILE}.log"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "TurboQuant ($PROFILE) already running on :$PORT (pid $(cat "$PIDFILE"))"
  exit 0
fi

cd "$(dirname "$BIN")"
export DYLD_LIBRARY_PATH="$(dirname "$BIN"):${DYLD_LIBRARY_PATH:-}"

nohup "$BIN" \
  --model "$MODEL" \
  --alias "$ALIAS" \
  --host "$HOST" \
  --port "$PORT" \
  --ctx-size "$CTX" \
  --parallel "$PARALLEL" \
  --cache-type-k "$CTK" \
  --cache-type-v "$CTV" \
  --flash-attn auto \
  >>"$LOGFILE" 2>&1 &

echo $! >"$PIDFILE"
echo "Started TurboQuant ($PROFILE) pid $(cat "$PIDFILE")"
echo "  model: $MODEL"
echo "  alias: $ALIAS"
echo "  ctx:   $CTX  parallel: $PARALLEL"
echo "  url:   http://${HOST}:${PORT}/v1"
echo "  log:   $LOGFILE"
