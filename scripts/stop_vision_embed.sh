#!/usr/bin/env bash
# Stop host vision-embed if started via start_vision_embed.sh (port match).
set -euo pipefail

PORT="${VISION_EMBED_PORT:-8791}"
if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    echo "stopped listeners on :$PORT ($pids)"
  else
    echo "no listener on :$PORT"
  fi
else
  echo "lsof not available; kill uvicorn manually" >&2
  exit 1
fi
