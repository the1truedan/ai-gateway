#!/usr/bin/env bash
# Source this before running Claude Code against the local LiteLLM gateway.
# Usage: source ./setup-claude-code.sh                      # local models (default)
#        CLAUDE_GATEWAY_MODE=paid source ./setup-claude-code.sh   # real Anthropic models (needs ANTHROPIC_API_KEY in .env)
#
# This file is sourced into your shell, so it does not use `set -euo pipefail`
# (that would change your interactive shell and can close it on the next error).
#
# Model names (updated 2026-10-03):
#   local mode: Claude Code sends Claude-style names; litellm_config.yaml maps them to LOCAL Ollama models
#               (haiku/sonnet → qwen3.5:9b, opus → gemma4:12b). No Anthropic call is made.
#   paid mode:  the manager-claude-*-paid routes call Anthropic: Haiku 4.5, Sonnet 5.5, Opus 5.5.
#               Fable 5.1 (the most capable) is `claude --model manager-claude-fable-paid`.

_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$_ROOT/.env" ]]; then
  echo "Missing $_ROOT/.env — copy .env.example and fill in keys" >&2
  return 1 2>/dev/null || exit 1
fi

set -a
# shellcheck disable=SC1091
source "$_ROOT/.env"
set +a

if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
  echo "LITELLM_MASTER_KEY is not set in $_ROOT/.env" >&2
  return 1 2>/dev/null || exit 1
fi

export ANTHROPIC_BASE_URL="http://localhost:4000"
export ANTHROPIC_AUTH_TOKEN="${LITELLM_MASTER_KEY}"

case "${CLAUDE_GATEWAY_MODE:-local}" in
  paid)
    _HAIKU=manager-claude-haiku-paid; _SONNET=manager-claude-paid; _OPUS=manager-claude-opus-paid ;;
  *)
    _HAIKU=claude-haiku-4-5-20251001; _SONNET=claude-sonnet-5-5; _OPUS=claude-opus-5-5 ;;
esac
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${ANTHROPIC_DEFAULT_HAIKU_MODEL:-$_HAIKU}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-$_SONNET}"
export ANTHROPIC_DEFAULT_OPUS_MODEL="${ANTHROPIC_DEFAULT_OPUS_MODEL:-$_OPUS}"

echo "Claude Code → LiteLLM gateway configured (mode: ${CLAUDE_GATEWAY_MODE:-local})"
echo "  ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL"
echo "  Default models: haiku=$ANTHROPIC_DEFAULT_HAIKU_MODEL sonnet=$ANTHROPIC_DEFAULT_SONNET_MODEL opus=$ANTHROPIC_DEFAULT_OPUS_MODEL"
echo ""
echo "Examples:"
echo "  claude --model manager-fast-local"
echo "  claude --model manager-claude-fable-paid      # Fable 5.1 via Anthropic (needs ANTHROPIC_API_KEY)"
echo "  claude --model manager-understand-audit       # needs OPENROUTER_API_KEY"
echo "  /understand    # inside Claude Code with the understand-anything plugin"
unset _ROOT _HAIKU _SONNET _OPUS
