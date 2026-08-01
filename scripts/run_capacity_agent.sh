#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f "$HOME/.config/manager-capacity-agent.env" ]; then
  set -a
  . "$HOME/.config/manager-capacity-agent.env"
  set +a
fi
. "$REPO_ROOT/scripts/uv_env.sh"
exec uv run --project "$REPO_ROOT" python -m services.capacity_agent.app
