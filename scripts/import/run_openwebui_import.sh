#!/usr/bin/env bash
# Import grokhistory (xAI export) and grokcode (Grok Build sessions) into Open WebUI.
set -euo pipefail

IMPORT_DIR="${OPENWEBUI_IMPORT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
ROOT="${OPENWEBUI_PROJECT_ROOT:-$(cd "$IMPORT_DIR/../.." && pwd)}"
DATA_DIR="${OPENWEBUI_IMPORT_DATA_DIR:-$ROOT/import-data}"
IMPORTER_IMAGE="${OPENWEBUI_IMPORTER_IMAGE:-ghcr.io/yetanotherchris/openwebui-importer:latest}"
VENDOR_DIR="$IMPORT_DIR/vendor"
# Native Python avoids amd64-only upstream image on Apple Silicon (default on host).
USE_DOCKER="${OPENWEBUI_IMPORT_USE_DOCKER:-auto}"

GROK_HISTORY_EXPORT="${GROK_HISTORY_EXPORT:-}"
GROK_SESSIONS_DIR="${GROK_SESSIONS_DIR:-$HOME/.grok/sessions}"
OPENWEBUI_USER_ID="${OPENWEBUI_USER_ID:-}"
OPENWEBUI_GROK_MODEL="${OPENWEBUI_GROK_MODEL:-xai/grok-code-fast-1}"
CWD_FILTER="${GROK_BUILD_CWD_FILTER:-$ROOT:$HOME/grokcode}"
INCLUDE_TOOLS="${GROK_BUILD_INCLUDE_TOOLS:-0}"
APPLY_SQL="${OPENWEBUI_APPLY_SQL:-0}"
WEBUI_DB_PATH="${OPENWEBUI_DB_PATH:-}"

usage() {
  cat <<'EOF'
Usage: run_openwebui_import.sh [--history] [--build] [--all] [--apply]

  --history   Import grokhistory from xAI prod-grok-backend.json export
  --build     Import grokcode / Grok Build sessions from ~/.grok/sessions
  --all       Run both imports (default when no flags given)
  --apply     Backup webui.db, apply generated SQL (host: docker volume; container: /webui-data)

Environment (or .env):
  OPENWEBUI_USER_ID          Required unless readable from webui.db
  GROK_HISTORY_EXPORT        Path to prod-grok-backend.json (auto-detected under ~/Downloads/ttl)
  GROK_SESSIONS_DIR          Grok Build sessions root (default: ~/.grok/sessions)
  GROK_BUILD_CWD_FILTER      Colon-separated cwd prefixes to import
  OPENWEBUI_IMPORT_DATA_DIR  Output workspace (default: ./import-data)
  OPENWEBUI_GROK_MODEL       Model id for imported chats (default: xai/grok-code-fast-1)
  OPENWEBUI_APPLY_SQL=1      Same as --apply
EOF
}

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

IN_CONTAINER=0
if [[ -f /.dockerenv || "${OPENWEBUI_IMPORT_IN_CONTAINER:-}" == "1" ]]; then
  IN_CONTAINER=1
fi

use_docker() {
  if [[ "$IN_CONTAINER" -eq 1 ]]; then
    return 1
  fi
  case "$USE_DOCKER" in
    1|true|yes) return 0 ;;
    0|false|no) return 1 ;;
    auto)
      # Upstream image is linux/amd64 only; prefer native on arm64 Macs.
      if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
        return 1
      fi
      return 0
      ;;
    *) return 1 ;;
  esac
}

if use_docker; then
  IMPORT_MODE=docker
else
  IMPORT_MODE=native
  if [[ ! -f "$VENDOR_DIR/convert_grok.py" || ! -f "$VENDOR_DIR/create_sql.py" ]]; then
    echo "Missing vendor scripts in $VENDOR_DIR (convert_grok.py, create_sql.py)" >&2
    exit 1
  fi
fi

if [[ "$IMPORT_MODE" == "native" && "$IN_CONTAINER" -eq 0 ]]; then
  echo "Using native Python import (no Docker — avoids amd64 platform warning on Apple Silicon)."
fi

do_history=0
do_build=0
do_apply=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --history) do_history=1 ;;
    --build) do_build=1 ;;
    --all) do_history=1; do_build=1 ;;
    --apply) do_apply=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
  shift
done
if [[ "$do_history" -eq 0 && "$do_build" -eq 0 ]]; then
  do_history=1
  do_build=1
fi
if [[ "$APPLY_SQL" == "1" ]]; then
  do_apply=1
fi

mkdir -p "$DATA_DIR/output" "$DATA_DIR/sql"
export OPENWEBUI_GROK_MODEL PYTHONPATH="${PYTHONPATH:-}:$IMPORT_DIR"

resolve_user_id() {
  if [[ -n "$OPENWEBUI_USER_ID" ]]; then
    echo "$OPENWEBUI_USER_ID"
    return
  fi
  local db=""
  if [[ -n "$WEBUI_DB_PATH" && -f "$WEBUI_DB_PATH" ]]; then
    db="$WEBUI_DB_PATH"
  elif [[ -f /webui-data/webui.db ]]; then
    db="/webui-data/webui.db"
  elif [[ "$IN_CONTAINER" -eq 0 ]]; then
    uid="$("$IMPORT_DIR/get_webui_user_id.sh" 2>/dev/null || true)"
    if [[ -n "$uid" ]]; then
      echo "$uid"
      return
    fi
  fi
  if [[ -n "$db" && -f "$db" ]]; then
    python3 - "$db" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
row = con.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()
print(row[0] if row else "")
PY
    return
  fi
  echo ""
}

OPENWEBUI_USER_ID="$(resolve_user_id)"
if [[ -z "$OPENWEBUI_USER_ID" ]]; then
  echo "OPENWEBUI_USER_ID is required. Run: ./scripts/import/get_webui_user_id.sh" >&2
  exit 1
fi

find_grok_history_export() {
  if [[ -n "$GROK_HISTORY_EXPORT" && -f "$GROK_HISTORY_EXPORT" ]]; then
    echo "$GROK_HISTORY_EXPORT"
    return
  fi
  local hit
  hit="$(find "${GROK_HISTORY_EXPORT_DIR:-$HOME/Downloads/ttl}" -name 'prod-grok-backend.json' 2>/dev/null | head -1 || true)"
  if [[ -n "$hit" && -f "$hit" ]]; then
    echo "$hit"
  fi
}

grok_web_script() {
  if [[ -f "$IMPORT_DIR/convert_grok.py" ]]; then
    echo "$IMPORT_DIR/convert_grok.py"
  else
    echo "$VENDOR_DIR/convert_grok.py"
  fi
}

create_sql_script() {
  if [[ -f "$IMPORT_DIR/create_sql.py" ]]; then
    echo "$IMPORT_DIR/create_sql.py"
  else
    echo "$VENDOR_DIR/create_sql.py"
  fi
}

grok_build_script() {
  echo "$IMPORT_DIR/convert_grok_build.py"
}

run_convert_grok_web() {
  local export_path="$1"
  if [[ "$IMPORT_MODE" == "native" || "$IN_CONTAINER" -eq 1 ]]; then
    python3 "$(grok_web_script)" \
      --userid="$OPENWEBUI_USER_ID" \
      --output-dir="$DATA_DIR/output" \
      "$export_path"
  else
    docker run --rm \
      -v "$DATA_DIR:/data" \
      -v "$(dirname "$export_path"):/grok-export:ro" \
      "$IMPORTER_IMAGE" \
      python convert_grok.py \
        --userid="$OPENWEBUI_USER_ID" \
        --output-dir=/data/output \
        "/grok-export/$(basename "$export_path")"
  fi
}

run_convert_grok_build() {
  local sessions_root="$1"
  shift
  local -a extra=("$@")
  if [[ "$IMPORT_MODE" == "native" || "$IN_CONTAINER" -eq 1 ]]; then
    python3 "$(grok_build_script)" \
      --sessions-root="$sessions_root" \
      --userid="$OPENWEBUI_USER_ID" \
      --output-dir="$DATA_DIR/output" \
      "${extra[@]}"
  else
    docker run --rm \
      -v "$IMPORT_DIR:/custom:ro" \
      -v "$DATA_DIR:/data" \
      -v "$sessions_root:/grok-sessions:ro" \
      -e OPENWEBUI_GROK_MODEL="$OPENWEBUI_GROK_MODEL" \
      -e PYTHONPATH=/custom \
      "$IMPORTER_IMAGE" \
      python /custom/convert_grok_build.py \
        --sessions-root=/grok-sessions \
        --userid="$OPENWEBUI_USER_ID" \
        --output-dir=/data/output \
        "${extra[@]}"
  fi
}

run_create_sql() {
  local input_dir="$1"
  local tags="$2"
  local output="$3"
  if [[ "$IMPORT_MODE" == "native" || "$IN_CONTAINER" -eq 1 ]]; then
    python3 "$(create_sql_script)" \
      "$input_dir" \
      --tags="$tags" \
      --output="$output"
  else
    docker run --rm \
      -v "$DATA_DIR:/data" \
      "$IMPORTER_IMAGE" \
      python create_sql.py \
        "/data/${input_dir#$DATA_DIR/}" \
        --tags="$tags" \
        --output="/data/${output#$DATA_DIR/}"
  fi
}

split_cwd_filter() {
  local IFS=':'
  read -r -a _parts <<< "$1"
  for part in "${_parts[@]}"; do
    [[ -n "$part" ]] && printf '%s\0' "$part"
  done
}

if [[ "$do_history" -eq 1 ]]; then
  export_path="$(find_grok_history_export || true)"
  if [[ -z "$export_path" ]]; then
    echo "Skipping grokhistory: set GROK_HISTORY_EXPORT or place export under ~/Downloads/ttl" >&2
  else
    echo "==> grokhistory: $export_path"
    run_convert_grok_web "$export_path"
    run_create_sql "$DATA_DIR/output/grok" "imported-grok,grokhistory" "$DATA_DIR/sql/grokhistory.sql"
    echo "Wrote $DATA_DIR/sql/grokhistory.sql"
  fi
fi

if [[ "$do_build" -eq 1 ]]; then
  echo "==> grokcode: $GROK_SESSIONS_DIR"
  cwd_args=()
  while IFS= read -r -d '' part; do
    cwd_args+=(--cwd-filter "$part")
  done < <(split_cwd_filter "$CWD_FILTER")

  tool_flag=()
  if [[ "$INCLUDE_TOOLS" == "1" ]]; then
    tool_flag=(--include-tools)
  fi

  run_convert_grok_build "$GROK_SESSIONS_DIR" "${cwd_args[@]}" "${tool_flag[@]}"
  run_create_sql "$DATA_DIR/output/grok-build" "imported-grok,grokcode,grok-build" "$DATA_DIR/sql/grokcode.sql"
  echo "Wrote $DATA_DIR/sql/grokcode.sql"
fi

if [[ "$do_apply" -eq 1 ]]; then
  if [[ "$IN_CONTAINER" -eq 1 ]]; then
    if [[ ! -f /webui-data/webui.db ]]; then
      echo "--apply in container requires open-webui-data mounted at /webui-data" >&2
      exit 1
    fi
    stamp="$(date +%Y%m%d-%H%M%S)"
    cp /webui-data/webui.db "/webui-data/webui.db.bak-${stamp}"
    for sql in "$DATA_DIR"/sql/*.sql; do
      [[ -f "$sql" ]] || continue
      echo "Applying $(basename "$sql")..."
      python3 - "$sql" <<'PY'
import sqlite3, sys
db = "/webui-data/webui.db"
sql = open(sys.argv[1], encoding="utf-8").read()
sqlite3.connect(db).executescript(sql)
PY
    done
    echo "SQL applied to /webui-data/webui.db (backup: webui.db.bak-${stamp})"
  else
    "$IMPORT_DIR/apply_import_sql.sh" "$DATA_DIR/sql"
  fi
fi

echo "Done. JSON under $DATA_DIR/output — SQL under $DATA_DIR/sql"