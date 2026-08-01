#!/usr/bin/env bash
# Install Docling (MIT) into A.I.D.A. venv. Optional GraniteDocling is runtime flag.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${AIDA_VENV:-$ROOT/services/aida/.venv}"

if [[ ! -x "$VENV/bin/pip" ]]; then
  python3 -m venv "$VENV"
fi

echo "Installing docling into $VENV …"
"$VENV/bin/pip" install -U 'docling>=2.50.0' 'PyYAML>=6.0'
"$VENV/bin/python" -c "from docling.document_converter import DocumentConverter; print('docling OK')"

cat <<'EOF'

Docling is MIT (free, local). Adobe is not used.

Standard pipeline (default):
  ./scripts/aida_drop_once.py /path/to.pdf --category medical --no-llm

Optional GraniteDocling VLM (Apache-2.0, free weights; large download):
  export AIDA_DOCLING_VLM=1
  # or: export AIDA_DOCLING_PIPELINE=vlm
  ./scripts/aida_drop_once.py /path/to.pdf --category medical --no-llm

Health:
  ./scripts/aida_drop_once.py --health | python3 -m json.tool | grep -A20 docling
EOF
