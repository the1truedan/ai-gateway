#!/usr/bin/env bash
# Wrapper: export Atuin → redacted markdown for OWUI KB + Hister.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$ROOT/scripts/history/export_atuin_for_kb.py" "$@"
