#!/usr/bin/env bash
# CLI usage / health snapshot for Herdr "usage" pane and operators.
# LiteLLM Admin UI remains the system of record: http://localhost:4000/ui/login/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

KEY="${LITELLM_MASTER_KEY:-}"
LITELLM_BASE="${LITELLM_BASE:-http://localhost:4000}"
HEADROOM_BASE="${HEADROOM_BASE:-http://localhost:8787}"
LOOP_SEC="${USAGE_SNAPSHOT_INTERVAL:-0}" # 0 = once; e.g. 30 for pane refresh loop

auth_hdr=()
if [[ -n "$KEY" ]]; then
  auth_hdr=(-H "Authorization: Bearer ${KEY}")
fi

snap() {
  echo "=== ai-gateway usage snapshot $(date '+%Y-%m-%d %H:%M:%S') ==="
  echo

  echo "-- LiteLLM liveliness --"
  if curl -sf --max-time 3 "${LITELLM_BASE}/health/liveliness" 2>/dev/null; then
    echo
  else
    echo "(unreachable: ${LITELLM_BASE})"
  fi

  echo
  echo "-- Headroom readyz --"
  if curl -sf --max-time 3 "${HEADROOM_BASE}/readyz" 2>/dev/null; then
    echo
  else
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "${HEADROOM_BASE}/readyz" 2>/dev/null || echo fail)"
    echo "(not ready or unreachable: ${HEADROOM_BASE} http=${code})"
  fi

  echo
  echo "-- Paths --"
  echo "  LiteLLM UI:  ${LITELLM_BASE}/ui/login/"
  echo "  Headroom:    ${HEADROOM_BASE}/v1  (conservation default)"
  echo "  Bypass:      ${LITELLM_BASE}/v1  (raw inference)"
  echo "  Open WebUI:  http://localhost:8080"
  echo "  Grafana:     http://localhost:3000"
  echo "  Prompt I/O:  http://localhost:5050  (profile security)"
  echo "  LLMTrace:    http://localhost:8090/v1  (shadow opt-in)"

  PROMPT_IO_BASE_SNAP="${PROMPT_IO_BASE_HOST:-http://localhost:5050}"
  echo
  echo "-- Prompt I/O scanner (hybrid Vigil metrics) --"
  if curl -sf --max-time 2 "${PROMPT_IO_BASE_SNAP}/health" 2>/dev/null; then
    echo
    curl -sf --max-time 2 "${PROMPT_IO_BASE_SNAP}/metrics" 2>/dev/null \
      | python3 -c '
import sys
from collections import defaultdict
want = ("prompt_io_scan_total", "prompt_io_injection_flag_total", "prompt_io_scanner_hits_total")
vals = defaultdict(float)
for line in sys.stdin:
    line=line.strip()
    if not line or line.startswith("#"):
        continue
    for p in want:
        if line.startswith(p):
            parts=line.rsplit(" ", 1)
            if len(parts)==2:
                try: vals[parts[0]] += float(parts[1])
                except ValueError: pass
if not vals:
    print("  (metrics endpoint up; no series yet)")
else:
    for k,v in sorted(vals.items())[:12]:
        print(f"  {k} = {v:g}")
' 2>/dev/null || echo "  (health ok; metrics parse skipped)"
  else
    echo "(down — enable: PROMPT_IO_ENABLED=1 + compose --profile security up -d --build prompt-io)"
  fi

  if [[ -z "$KEY" ]]; then
    echo
    echo "-- Spend --"
    echo "(set LITELLM_MASTER_KEY in .env for spend API probes)"
    return 0
  fi

  echo
  echo "-- LiteLLM spend/logs (latest slice; join on call_id) --"
  # Prefer v2 if present; fall back to v1. Never fail the snapshot.
  if ! curl -sf --max-time 5 "${auth_hdr[@]}" \
    "${LITELLM_BASE}/spend/logs?limit=5" 2>/dev/null \
    | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception as e:
    print("(could not parse spend/logs)", e); sys.exit(0)
rows=d if isinstance(d,list) else (d.get("data") or d.get("logs") or [])
if not rows:
    print(json.dumps(d, indent=2)[:1200] if isinstance(d,dict) else str(d)[:400])
    sys.exit(0)
for r in rows[:5]:
    model=r.get("model") or r.get("model_group") or "?"
    spend=r.get("spend", r.get("cost", "?"))
    pt=r.get("prompt_tokens", r.get("total_prompt_tokens", "?"))
    ct=r.get("completion_tokens", r.get("total_completion_tokens", "?"))
    call_id = (
        r.get("request_id")
        or r.get("call_id")
        or r.get("id")
        or r.get("litellm_call_id")
        or ""
    )
    start=r.get("startTime") or r.get("start_time") or ""
    print(f"  call_id={call_id}  {start}  model={model}  spend={spend}  prompt={pt}  completion={ct}")
' 2>/dev/null; then
    echo "(spend/logs unavailable — use LiteLLM UI for full history)"
  fi

  echo
  echo "-- call_id tip --"
  echo "  Response header x-litellm-call-id joins spend logs + prompt-io scans."
  echo "  See config/security/README.md"

  echo
  echo "-- Headroom tip --"
  echo "  Host CLI (if installed): headroom dashboard"
  echo "  Compression savings are local to Headroom; spend/credits live in LiteLLM UI."
  echo
}

if [[ "$LOOP_SEC" =~ ^[0-9]+$ ]] && [[ "$LOOP_SEC" -gt 0 ]]; then
  while true; do
    clear 2>/dev/null || true
    snap
    sleep "$LOOP_SEC"
  done
else
  snap
fi
