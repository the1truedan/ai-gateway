#!/usr/bin/env bash
# Ensure LM Studio Developer Server is running (OpenAI-compatible :1234).
set -euo pipefail

export PATH="${HOME}/.lmstudio/bin:${PATH}"
LMS_BIN="${LMS_BIN:-$(command -v lms || true)}"
PORT="${LMSTUDIO_PORT:-1234}"

if [[ -z "$LMS_BIN" || ! -x "$LMS_BIN" ]]; then
  echo "lms CLI not found. Install LM Studio and ensure ~/.lmstudio/bin/lms exists." >&2
  exit 1
fi

if "$LMS_BIN" server status 2>/dev/null | grep -qi "running"; then
  echo "LM Studio server already running on :${PORT}"
else
  echo "Starting LM Studio server on :${PORT}..."
  "$LMS_BIN" server start --port "$PORT"
fi

echo "  url:  http://127.0.0.1:${PORT}/v1"
echo "  auth: LM_API_TOKEN in ~/ai-gateway/.env"
echo "  load: ./scripts/load_lmstudio_model.sh mlx-fast|lms-local|lms-vision|<model-key>"
"$LMS_BIN" server status || true
