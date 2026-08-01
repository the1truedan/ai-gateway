#!/usr/bin/env bash
# Install ctx (if needed) and register the Grok Build history-source plugin.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLUGIN_SRC="$ROOT/scripts/ctx/grok-build"
EXPORTER="$PLUGIN_SRC/grok-build-to-ctx.py"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

CTX_DATA_ROOT="${CTX_DATA_ROOT:-$HOME/.local/share/ctx}"
GROK_SESSIONS_DIR="${GROK_SESSIONS_DIR:-$HOME/.grok/sessions}"
GROK_BUILD_CWD_FILTER="${GROK_BUILD_CWD_FILTER:-$ROOT:$HOME/grokcode}"

if ! command -v ctx >/dev/null 2>&1; then
  echo "Installing ctx..."
  curl -fsSL https://ctx.rs/install | sh
fi

PLUGIN_DIR="$CTX_DATA_ROOT/plugins/grok-build"
mkdir -p "$PLUGIN_DIR"
chmod +x "$EXPORTER"

python3 - "$PLUGIN_DIR/ctx-history-plugin.json" "$EXPORTER" "$GROK_SESSIONS_DIR" "$GROK_BUILD_CWD_FILTER" <<'PY'
import json
import sys
from pathlib import Path

out, exporter, sessions_dir, cwd_filter = sys.argv[1:5]
manifest = {
    "schema_version": 1,
    "name": "grok-build",
    "display_name": "Grok Build / Grok Code sessions",
    "version": "0.1.0",
    "history_sources": [
        {
            "id": "default",
            "provider_key": "grok-build",
            "source_id": "default",
            "source_format": "grok-build-updates-jsonl-v1",
            "enabled": True,
            "refresh": "auto",
            "command": ["python3", str(Path(exporter).resolve())],
            "timeout_seconds": 300,
            "env": {
                "GROK_SESSIONS_DIR": sessions_dir,
                "GROK_BUILD_CWD_FILTER": cwd_filter,
            },
        }
    ],
}
Path(out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {out}")
PY

echo "Running ctx setup (indexes native sources)..."
ctx setup

echo "Importing Grok Build history via plugin..."
ctx import --history-source grok-build/default

echo "ctx sources (grok-build should appear):"
ctx sources --json | python3 -c "
import json,sys
for row in json.load(sys.stdin):
    if 'grok' in str(row.get('provider','')).lower() or row.get('provider_key')=='grok-build':
        print(json.dumps(row, indent=2))
" 2>/dev/null || ctx sources

echo ""
echo "Search example:"
echo "  ctx search \"litellm\" --provider-key grok-build"
echo "MCP (optional): ctx mcp serve"