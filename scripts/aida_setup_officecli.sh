#!/usr/bin/env bash
# Install + configure OfficeCLI for A.I.D.A. Phase 4 (External Mode → local LiteLLM).
# Hosted trial / online publish disabled by default (PHI / prepare-only policy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export PATH="${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"

if ! command -v officecli >/dev/null 2>&1; then
  if command -v npm >/dev/null 2>&1; then
    echo "Installing officecli via npm -g..."
    npm install -g officecli
  else
    echo "npm not found; trying curl installer..."
    curl -fsSL https://raw.githubusercontent.com/officecli/officecli-dist/main/scripts/install-officecli.sh | bash
  fi
fi

if ! command -v officecli >/dev/null 2>&1; then
  echo "officecli still not on PATH"
  exit 1
fi

echo "officecli: $(officecli --version 2>&1 | head -1)"

# External mode (non-interactive)
officecli config set-runtime external 2>/dev/null || true

BASE="${AIDA_LITELLM_BASE:-http://localhost:4000}"
KEY="${AIDA_LITELLM_KEY:-${LITELLM_MASTER_KEY:-sk-local}}"
MODEL="${AIDA_OFFICECLI_MODEL:-role-phi-local}"
if [[ "$BASE" != */v1 ]]; then
  BASE_V1="${BASE}/v1"
else
  BASE_V1="$BASE"
fi

CFG="${AIDA_OFFICECLI_CONFIG:-$HOME/Library/Application Support/officecli/config.json}"
mkdir -p "$(dirname "$CFG")"
python3 - <<PY
import json
from pathlib import Path
p = Path(r"""$CFG""")
cfg = {
  "defaults": {
    "output_dir": "./output",
    "mode": "fast",
    "publish": False,
    "pptx_style_preset": "tech-contrast",
  },
  "runtime": {"mode": "external"},
  "llm": {
    "provider": "openai",
    "base_url": r"""$BASE_V1""",
    "api_key": r"""$KEY""",
    "model": r"""$MODEL""",
    "image_model": r"""$MODEL""",
    "review_model": r"""$MODEL""",
    "timeout_sec": 180,
  },
  "license": {
    "base_url": "https://platform.officecli.io",
    "api_key": "",
    "enabled": False,
    "timeout_sec": 30,
  },
  "publish": {
    "provider": "http",
    "base_url": "https://platform.officecli.io",
    "api_key": "",
    "enabled": False,
    "timeout_sec": 60,
  },
}
p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
print("wrote", p)
print("runtime=external base_url=", cfg["llm"]["base_url"], "model=", cfg["llm"]["model"])
print("publish=false license.enabled=false")
PY

officecli config status 2>&1 || true
echo
echo "OK. A.I.D.A. endpoints: GET /v1/officecli/health, POST /v1/officecli/generate"
echo "Policy: External Mode + local LiteLLM; no publish; medical refuses hosted."
echo "Restart A.I.D.A. after first install if health still shows unavailable."
