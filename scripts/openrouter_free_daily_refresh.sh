#!/usr/bin/env bash
# Daily OpenRouter free-model refresh: sync -> reconcile -> restart-if-changed
# -> commit+push the regenerated catalog doc, fully unattended.
#
# Install:
#   cp deploy/launchd/com.manager.openrouter-free-refresh.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.manager.openrouter-free-refresh.plist
#
# Safety: reconcile is the gate. If it reports a conflict (CURATED map drift,
# a model registered twice), this script stops BEFORE touching the live
# container or pushing anything — a human needs to look at it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

set -a
source .env
set +a

log "running openrouter free-model sync..."
SYNC_OUT="$(python3 scripts/sync_openrouter_free_models.py)"
echo "$SYNC_OUT"

log "re-rendering linux/gpu-host merged config (litellm_config.linux.merged.yaml)..."
python3 scripts/render_linux_litellm_config.py

log "reconciling CURATED map against the fresh catalog..."
if ! python3 ~/grokcode/scripts/manager-mcp/reconcile_openrouter_curated.py; then
  log "RECONCILE FAILED — CURATED map drift or duplicate registration. Not restarting, not pushing. Needs manual review (see litellm_config.yaml vs openrouter_free_models.generated.yaml)."
  exit 1
fi

if echo "$SYNC_OUT" | grep -q "config_changed=true"; then
  log "model set changed — restarting litellm-proxy"
  /usr/local/bin/docker restart litellm-proxy
  healthy=0
  for _ in 1 2 3 4 5 6; do
    sleep 5
    if curl -sf http://localhost:4000/health/liveliness > /dev/null; then
      healthy=1
      break
    fi
  done
  if [[ "$healthy" -ne 1 ]]; then
    log "POST-RESTART HEALTH CHECK FAILED — litellm-proxy did not come back healthy within 30s."
    exit 1
  fi
  log "litellm-proxy healthy post-restart"
else
  log "no model-set change, skipping restart"
fi

if ! git diff --quiet -- config/clients/openrouter-free-models.md; then
  log "catalog doc changed, committing + pushing"
  git add config/clients/openrouter-free-models.md
  git commit -m "chore: daily openrouter free-model catalog refresh ($(date -u +%F))"
  git push forgejo main
  git push github main
  log "pushed refreshed catalog doc to forgejo + github"
else
  log "catalog doc unchanged, nothing to commit"
fi

log "done"
