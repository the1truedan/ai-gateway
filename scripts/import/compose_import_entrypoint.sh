#!/usr/bin/env bash
# Docker Compose entrypoint for the openwebui-importer profile service.
set -euo pipefail

IMPORT_ROOT="${OPENWEBUI_IMPORT_ROOT:-/app}"
export OPENWEBUI_IMPORT_IN_CONTAINER=1
export OPENWEBUI_IMPORT_DATA_DIR="${OPENWEBUI_IMPORT_DATA_DIR:-/data}"
export GROK_SESSIONS_DIR="${GROK_SESSIONS_DIR:-/grok-sessions}"
export GROK_HISTORY_EXPORT_DIR="${GROK_HISTORY_EXPORT_DIR:-/grok-history}"
export WEBUI_DB_PATH="${WEBUI_DB_PATH:-/webui-data/webui.db}"
export PYTHONPATH="${IMPORT_ROOT}:${PYTHONPATH:-}"

if [[ -z "${GROK_HISTORY_EXPORT:-}" ]]; then
  hit="$(find /grok-history -name 'prod-grok-backend.json' 2>/dev/null | head -1 || true)"
  if [[ -n "$hit" ]]; then
    export GROK_HISTORY_EXPORT="$hit"
  fi
fi

if [[ $# -eq 0 ]]; then
  set -- --all
fi

exec "$IMPORT_ROOT/run_openwebui_import.sh" "$@"