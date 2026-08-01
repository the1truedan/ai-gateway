#!/usr/bin/env bash
# Staged TurboQuant+ model acquisition for M4 24GB (does not auto-run).
# Full TQ4_1S utilization requires GGUF in TQ4_1S format, not Ollama IQ4/Q5 pulls.
set -euo pipefail

ENV_FILE="${TURBOQUANT_ENV:-/Volumes/models/turboquant/turboquant.env}"
# shellcheck disable=SC1090
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"

BIN="${TURBOQUANT_ROOT:?}/llama-server"
QUANT="${TURBOQUANT_ROOT}/llama-quantize"
MODELS="${TURBOQUANT_MODELS:-/Volumes/models/turboquant/models}"
HF_CACHE="${TURBOQUANT_HF_CACHE:-/Volumes/models/turboquant/hf-cache}"

export HF_HOME="${HF_HOME:-$HF_CACHE}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-${HF_HOME}/hub}"

usage() {
  cat <<'EOF'
Usage: pull_turboquant_models.sh <stage>

Stages (run one at a time; review disk + RAM before each):
  list     — show recommended picks for M4 24GB
  qwen35   — pull Qwen3.5-9B Q4_K_S via llama-server -hf (~5.0 GB) [best agent coder]
  gemma12  — pull Gemma4-12B Q4_K_M via llama-server -hf (~7.6 GB) [best turbo-native Gemma4]
  qwen38   — pull Qwen3-8B Q4_K_M via llama-server -hf (~5.2 GB) [lighter coder fallback]
  requant  — convert an existing GGUF to TQ4_1S (needs SOURCE_GGUF env)

Plan file: scripts/turboquant_staged_plan.json

Examples:
  ./scripts/pull_turboquant_models.sh list
  ./scripts/pull_turboquant_models.sh gemma12
  ./scripts/pull_turboquant_models.sh qwen38
  SOURCE_GGUF=models/qwen3.5-9b-q4_k_s.gguf ./scripts/pull_turboquant_models.sh requant
EOF
}

stage_list() {
  cat <<EOF
TurboQuant+ best picks — M4 Mac Mini 24 GB
HF cache: $HF_HOME

Current Ollama GGUFs (IQ4 / Q5_K_M):
  - Get turbo KV compression only (q8_0/turbo3) — NOT TQ4_1S fused Metal kernels
  - Fine for now; swap when you want full turboquant weight optimization

On disk (HF-native):
  - qwen3.5-9b Q4_K_S  ~5.0 GB  — linked; coder profile :8082

Staged next (see turboquant_staged_plan.json):
  1. gemma4-12b Q4_K_M  ~7.6 GB  — reasoning orchestrator :8081
  2. qwen3-8b Q4_K_M    ~5.2 GB  — lighter coder alt :8082

Optional requant (full TQ4_1S Metal kernels):
  llama-quantize model.gguf model.tq4_1s.gguf TQ4_1S

Keep on Ollama (not TurboQuant):
  glm-ocr, translategemma:4b, nomic-embed-text-v2-moe, bge-m3
EOF
}

link_model() {
  local dest_name="$1"
  local src_gguf="$2"
  local dest="$MODELS/$dest_name"
  [[ -f "$src_gguf" ]] || { echo "Downloaded GGUF not found: $src_gguf" >&2; exit 1; }
  ln -sf "$src_gguf" "$dest"
  echo "Linked: $dest -> $src_gguf"
}

find_hf_gguf() {
  local repo_slug="$1"
  local quant_pattern="$2"
  local hub_dir="${HUGGINGFACE_HUB_CACHE}/models--${repo_slug//\//--}"
  [[ -d "$hub_dir/snapshots" ]] || return 0
  find "$hub_dir/snapshots" \( -name "*${quant_pattern}*.gguf" \) \( -type f -o -type l \) 2>/dev/null | head -1
}

pull_hf() {
  local repo="$1" quant="$2" alias="$3" dest_name="$4"
  mkdir -p "$MODELS" "$HUGGINGFACE_HUB_CACHE"
  cd "$(dirname "$BIN")"
  export DYLD_LIBRARY_PATH="$(dirname "$BIN"):${DYLD_LIBRARY_PATH:-}"

  echo "Pulling ${repo}:${quant} into $HF_HOME ..."
  echo "  alias: $alias"
  # Start HF download in background; poll cache instead of waiting for full model load
  "$BIN" -hf "${repo}:${quant}" --alias "$alias" -c 512 --port 0 --timeout 600 >/dev/null 2>&1 &
  local pull_pid=$!

  local gguf="" waited=0
  while (( waited < 1800 )); do
    gguf="$(find_hf_gguf "$repo" "$quant")"
    if [[ -n "$gguf" && -f "$gguf" ]]; then
      kill "$pull_pid" 2>/dev/null || true
      wait "$pull_pid" 2>/dev/null || true
      break
    fi
    if ! kill -0 "$pull_pid" 2>/dev/null; then
      gguf="$(find_hf_gguf "$repo" "$quant")"
      break
    fi
    sleep 5
    waited=$((waited + 5))
    du -sh "${HUGGINGFACE_HUB_CACHE}/models--${repo//\//--}" 2>/dev/null | awk -v s="$waited" '{printf "\r  downloaded: %s (%ds)", $1, s}'
  done
  echo ""

  if [[ -z "$gguf" || ! -f "$gguf" ]]; then
    kill "$pull_pid" 2>/dev/null || true
    echo "Warning: could not locate downloaded GGUF under $HUGGINGFACE_HUB_CACHE" >&2
    echo "Re-run or check HF repo quant name matches: $quant" >&2
    exit 1
  fi

  link_model "$dest_name" "$gguf"
  echo ""
  echo "Update turboquant.env (then restart server):"
  echo "  TURBOQUANT_MODEL_<profile>=$MODELS/$dest_name"
  echo "  TURBOQUANT_ALIAS_<profile>=$alias"
}

requant_tq4() {
  local src="${SOURCE_GGUF:?Set SOURCE_GGUF to input GGUF}"
  local dst="${DEST_GGUF:-${src%.gguf}.tq4_1s.gguf}"
  [[ -x "$QUANT" ]] || { echo "llama-quantize not found: $QUANT" >&2; exit 1; }
  [[ -f "$src" ]] || { echo "Missing: $src" >&2; exit 1; }
  echo "Quantizing $src -> $dst (TQ4_1S) ..."
  "$QUANT" "$src" "$dst" TQ4_1S
  echo "Done: $dst"
}

case "${1:-list}" in
  list) stage_list ;;
  qwen35) pull_hf "unsloth/Qwen3.5-9B-GGUF" "Q4_K_S" "qwen35-agent" "qwen3.5-9b-q4_k_s.gguf" ;;
  gemma12) pull_hf "ggml-org/gemma-4-12B-it-GGUF" "Q4_K_M" "gemma4-orchestrator" "gemma4-12b-q4_k_m.gguf" ;;
  qwen38) pull_hf "unsloth/Qwen3-8B-GGUF" "Q4_K_M" "qwen-coder" "qwen3-8b-q4_k_m.gguf" ;;
  requant) requant_tq4 ;;
  *) usage; exit 1 ;;
esac