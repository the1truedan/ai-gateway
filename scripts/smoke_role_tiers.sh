#!/usr/bin/env bash
# Smoke tiered orchestration roles via Headroom → LiteLLM.
# Usage: ./scripts/smoke_role_tiers.sh
# Cloud/token-using roles are opt-in: INCLUDE_CLOUD_ROLES=1 ./scripts/smoke_role_tiers.sh
# Optional: BASE_URL=http://localhost:4000/v1 ./scripts/smoke_role_tiers.sh  # raw LiteLLM

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BASE_URL="${BASE_URL:-http://localhost:8787/v1}"
KEY="${LITELLM_MASTER_KEY:-}"
if [[ -z "$KEY" ]]; then
  echo "ERROR: LITELLM_MASTER_KEY empty. Run: set -a && source .env && set +a" >&2
  exit 1
fi

echo "BASE_URL=$BASE_URL"
echo "key len=${#KEY}"
echo

REQUIRED_ROLES=(role-plan role-recon role-execute role-reason role-phi-local role-audit)
ROLES=(role-phi-local role-execute)
if [[ "${INCLUDE_CLOUD_ROLES:-0}" == "1" ]]; then
  ROLES+=(role-plan role-recon role-audit)
fi

models="$(curl -fsS --max-time 20 "${BASE_URL}/models" \
  -H "Authorization: Bearer ${KEY}")"
for m in "${REQUIRED_ROLES[@]}"; do
  if ! python3 -c 'import json,sys; model=sys.argv[1]; data=json.load(sys.stdin); raise SystemExit(0 if model in {x.get("id") for x in data.get("data", [])} else 1)' "$m" <<<"$models"; then
    echo "ERROR: /v1/models does not expose $m" >&2
    exit 1
  fi
done
echo "Model inventory exposes all six role aliases."
echo "Smoke order: ${ROLES[*]}"
if [[ "${INCLUDE_CLOUD_ROLES:-0}" != "1" ]]; then
  echo "Cloud roles skipped; set INCLUDE_CLOUD_ROLES=1 only after checking credentials and accepting token use."
fi
echo

fail=0
for m in "${ROLES[@]}"; do
  echo "=== $m ==="
  # shellcheck disable=SC2086
  body="$(curl -sS --max-time 120 "${BASE_URL}/chat/completions" \
    -H "Authorization: Bearer ${KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${m}\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":16}" \
    || true)"
  if echo "$body" | grep -q '"choices"'; then
    echo "OK $(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model','?'), (d.get('choices') or [{}])[0].get('message',{}).get('content','')[:60])" 2>/dev/null || echo ok)"
  else
    echo "FAIL ${body:0:240}"
    fail=1
  fi
  echo
done

if [[ "$fail" -ne 0 ]]; then
  echo "Some roles failed (local backends may be down; cloud needs keys). PHI must never succeed only via cloud."
  exit 1
fi
echo "Selected role smokes returned choices."
