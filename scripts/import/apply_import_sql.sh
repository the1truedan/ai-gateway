#!/usr/bin/env bash
# Apply generated import SQL files to the open-webui webui.db volume.
set -euo pipefail

SQL_DIR="${1:-}"
if [[ -z "$SQL_DIR" || ! -d "$SQL_DIR" ]]; then
  echo "Usage: apply_import_sql.sh <sql-directory>" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VOLUME="${OPENWEBUI_DATA_VOLUME:-ai-gateway_open-webui-data}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.yml}"

mapfile -t sql_files < <(find "$SQL_DIR" -maxdepth 1 -name '*.sql' -type f | sort)
if [[ ${#sql_files[@]} -eq 0 ]]; then
  echo "No .sql files in $SQL_DIR" >&2
  exit 1
fi

echo "Stopping open-webui..."
docker compose -f "$COMPOSE_FILE" stop open-webui 2>/dev/null || docker stop open-webui 2>/dev/null || true

stamp="$(date +%Y%m%d-%H%M%S)"
docker run --rm -v "${VOLUME}:/data" alpine:3.20 \
  sh -c "cp /data/webui.db /data/webui.db.bak-${stamp} && echo backup: webui.db.bak-${stamp}"

for sql in "${sql_files[@]}"; do
  echo "Applying $(basename "$sql")..."
  docker run --rm \
    -v "${VOLUME}:/data" \
    -v "$SQL_DIR:/sql:ro" \
    alpine:3.20 \
    sh -c "apk add --no-cache sqlite >/dev/null && sqlite3 /data/webui.db < /sql/$(basename "$sql")"
done

echo "Starting open-webui..."
docker compose -f "$COMPOSE_FILE" start open-webui 2>/dev/null || docker start open-webui 2>/dev/null || true
echo "Import applied."