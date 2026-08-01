#!/usr/bin/env bash
# Source this before running Claude Code against the local LiteLLM gateway.
# Usage: source ./setup-claude-code.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing $ROOT/.env — copy .env.example and fill in keys" >&2
  return 1 2>/dev/null || exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

export ANTHROPIC_BASE_URL="http://localhost:4000"
export ANTHROPIC_AUTH_TOKEN="${LITELLM_MASTER_KEY}"

# Route Claude Code defaults through local LiteLLM model aliases
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${ANTHROPIC_DEFAULT_HAIKU_MODEL:-claude-haiku-4-5-20251001}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-claude-sonnet-4-6}"
export ANTHROPIC_DEFAULT_OPUS_MODEL="${ANTHROPIC_DEFAULT_OPUS_MODEL:-claude-opus-4-7}"

echo "Claude Code → LiteLLM gateway configured"
echo "  ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL"
echo "  Default models: haiku=$ANTHROPIC_DEFAULT_HAIKU_MODEL sonnet=$ANTHROPIC_DEFAULT_SONNET_MODEL opus=$ANTHROPIC_DEFAULT_OPUS_MODEL"
echo ""
echo "Understand-Anything examples:"
echo "  claude --model manager-fast-local"
echo "  claude --model manager-understand-audit   # needs OPENROUTER_API_KEY"
echo "  /understand    # inside Claude Code with understand-anything plugin"