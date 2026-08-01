#!/usr/bin/env bash
# Print the first Open WebUI user id from the docker volume (or OPENWEBUI_USER_ID).
set -euo pipefail

if [[ -n "${OPENWEBUI_USER_ID:-}" ]]; then
  echo "$OPENWEBUI_USER_ID"
  exit 0
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [[ -n "${OPENWEBUI_USER_ID:-}" ]]; then
  echo "$OPENWEBUI_USER_ID"
  exit 0
fi

VOLUME="${OPENWEBUI_DATA_VOLUME:-ai-gateway_open-webui-data}"

docker run --rm -v "${VOLUME}:/data" alpine:3.20 \
  sh -c "apk add --no-cache sqlite >/dev/null && sqlite3 /data/webui.db \"SELECT id FROM user ORDER BY created_at LIMIT 1;\"" 2>/dev/null