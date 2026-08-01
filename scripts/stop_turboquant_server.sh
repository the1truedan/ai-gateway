#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${TURBOQUANT_ENV:-/Volumes/models/turboquant/turboquant.env}"
RUN="${TURBOQUANT_RUN:-/Volumes/models/turboquant/run}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  RUN="${TURBOQUANT_RUN:-$RUN}"
fi

stopped=0
for profile in reasoning coder; do
  pidfile="$RUN/llama-server-${profile}.pid"
  if [[ -f "$pidfile" ]]; then
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      echo "Stopped TurboQuant ($profile) pid $pid"
      stopped=1
    fi
    rm -f "$pidfile"
  fi
done

if [[ "$stopped" -eq 0 ]]; then
  echo "No TurboQuant server was running."
fi