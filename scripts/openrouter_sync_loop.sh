#!/usr/bin/env bash
# 24h refresh loop for host or sidecar use.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
INTERVAL_SECONDS="${OPENROUTER_SYNC_INTERVAL_SECONDS:-86400}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

echo "OpenRouter free-model sync loop every ${INTERVAL_SECONDS}s"

while true; do
  if python3 "$ROOT/scripts/sync_openrouter_free_models.py" | tee /tmp/openrouter_sync.log; then
    if grep -q "config_changed=true" /tmp/openrouter_sync.log; then
      echo "Free-model catalog changed; restarting litellm"
      docker compose restart litellm || true
    fi
  else
    echo "Sync failed; keeping existing generated config" >&2
  fi
  sleep "$INTERVAL_SECONDS"
done