#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  PYTHON=""
fi

if [[ -n "$PYTHON" ]]; then
  "$PYTHON" "$ROOT/scripts/sync_openrouter_free_models.py" || {
    echo "OpenRouter free-model sync failed; starting LiteLLM with last generated config" >&2
  }
else
  echo "Python not found in container; skipping OpenRouter sync" >&2
fi

exec litellm --config /app/config.yaml --port 4000 --host 0.0.0.0