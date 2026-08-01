#!/usr/bin/env bash
# Start A.I.D.A. document pipeline FastAPI on the host (M4-friendly).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/services/aida"
VENV="${AIDA_VENV:-$APP_DIR/.venv}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export AIDA_HOST="${AIDA_HOST:-localhost}"
export AIDA_PORT="${AIDA_PORT:-8792}"
export AIDA_INGEST_ROOT="${AIDA_INGEST_ROOT:-${MANAGER_INGEST_ROOT:-/Volumes/ai-data/work/ingest}}"
export AIDA_LITELLM_BASE="${AIDA_LITELLM_BASE:-http://localhost:4000}"
export AIDA_MODEL="${AIDA_MODEL:-role-phi-local}"
export AIDA_ALLOW_REMOTE="${AIDA_ALLOW_REMOTE:-0}"

# Prefer Homebrew OpenJDK 17 for OpenDataLoader (system java may still be 8)
if [[ -z "${JAVA_HOME:-}" || ! -x "${JAVA_HOME}/bin/java" ]]; then
  for _jhome in \
    "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" \
    "/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" \
    "/opt/homebrew/opt/openjdk@17" \
    "/usr/local/opt/openjdk@17"
  do
    if [[ -x "${_jhome}/bin/java" ]]; then
      export JAVA_HOME="${_jhome}"
      break
    fi
  done
fi
if [[ -n "${JAVA_HOME:-}" && -x "${JAVA_HOME}/bin/java" ]]; then
  export PATH="${JAVA_HOME}/bin:${PATH}"
  export AIDA_JAVA_HOME="${AIDA_JAVA_HOME:-$JAVA_HOME}"
fi

if [[ -n "${LITELLM_MASTER_KEY:-}" && -z "${AIDA_LITELLM_KEY:-}" ]]; then
  export AIDA_LITELLM_KEY="$LITELLM_MASTER_KEY"
fi

cd "$APP_DIR"

if [[ -x "$VENV/bin/python" ]]; then
  PY="$VENV/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "python3 not found; create venv: python3 -m venv $VENV && $VENV/bin/pip install -r $APP_DIR/requirements.txt" >&2
  exit 1
fi

if ! "$PY" -c "import fastapi, uvicorn, httpx, pypdf" 2>/dev/null; then
  if [[ ! -x "$VENV/bin/pip" ]]; then
    python3 -m venv "$VENV"
    PY="$VENV/bin/python"
  fi
  "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
  PY="$VENV/bin/python"
fi

echo "manager-aida  model=$AIDA_MODEL  ingest=$AIDA_INGEST_ROOT  http://${AIDA_HOST}:${AIDA_PORT}"
exec "$PY" -m uvicorn app:app --host "$AIDA_HOST" --port "$AIDA_PORT"
