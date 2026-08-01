#!/usr/bin/env bash
# Start manager-vision-embed FastAPI on the host (M4-friendly; not LiteLLM).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/services/vision_embed"
VENV="${VISION_EMBED_VENV:-$APP_DIR/.venv}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export VISION_EMBED_HOST="${VISION_EMBED_HOST:-127.0.0.1}"
export VISION_EMBED_PORT="${VISION_EMBED_PORT:-8791}"
export VISION_EMBED_BACKEND="${VISION_EMBED_BACKEND:-numpy}"

cd "$APP_DIR"

if [[ -x "$VENV/bin/python" ]]; then
  PY="$VENV/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "python3 not found; create venv: python3 -m venv $VENV && $VENV/bin/pip install -r $APP_DIR/requirements.txt" >&2
  exit 1
fi

# Ensure deps if venv exists but fastapi missing
if ! "$PY" -c "import fastapi, uvicorn, PIL, numpy" 2>/dev/null; then
  if [[ -x "$VENV/bin/pip" ]]; then
    "$VENV/bin/pip" install -q -r "$APP_DIR/requirements.txt"
  else
    echo "Missing deps. Run: python3 -m venv $VENV && $VENV/bin/pip install -r $APP_DIR/requirements.txt" >&2
    exit 1
  fi
fi

echo "manager-vision-embed  backend=$VISION_EMBED_BACKEND  http://${VISION_EMBED_HOST}:${VISION_EMBED_PORT}"
exec "$PY" -m uvicorn app:app --host "$VISION_EMBED_HOST" --port "$VISION_EMBED_PORT"
