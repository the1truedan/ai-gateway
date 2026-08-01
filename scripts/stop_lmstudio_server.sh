#!/usr/bin/env bash
# Stop LM Studio Developer Server (does not delete models).
set -euo pipefail

export PATH="${HOME}/.lmstudio/bin:${PATH}"
LMS_BIN="${LMS_BIN:-$(command -v lms || true)}"

if [[ -z "$LMS_BIN" || ! -x "$LMS_BIN" ]]; then
  echo "lms CLI not found." >&2
  exit 1
fi

if "$LMS_BIN" server status 2>/dev/null | grep -qi "running"; then
  "$LMS_BIN" server stop
  echo "LM Studio server stopped."
else
  echo "LM Studio server was not running."
fi
