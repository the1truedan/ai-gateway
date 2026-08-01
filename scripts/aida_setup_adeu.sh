#!/usr/bin/env bash
# Install adeu (MIT) DOCX redline tooling into A.I.D.A. venv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${AIDA_VENV:-$ROOT/services/aida/.venv}"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip
pip install -U "adeu>=1.21.0" "python-docx>=1.1.0"

adeu -v 2>&1 | head -3 || true
python - <<'PY'
from adeu import RedlineEngine, ModifyText
print("adeu SDK OK")
from docx import Document
print("python-docx OK")
PY

echo
echo "OK. A.I.D.A. endpoints: GET /v1/adeu/health, POST /v1/adeu/{extract,apply,sanitize,from-brief}"
echo "Local only — no Adeu Cloud. Prepare-only + HITL before distribution."
