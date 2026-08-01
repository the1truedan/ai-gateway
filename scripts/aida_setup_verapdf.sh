#!/usr/bin/env bash
# Install host veraPDF CLI for A.I.D.A. (faster than Docker on M4).
set -euo pipefail

if command -v verapdf >/dev/null 2>&1; then
  echo "verapdf already on PATH: $(command -v verapdf)"
  verapdf --version 2>&1 | head -3 || true
  exit 0
fi

if command -v brew >/dev/null 2>&1; then
  echo "Installing verapdf via Homebrew…"
  brew install verapdf
  echo "OK: $(command -v verapdf)"
  exit 0
fi

echo "Homebrew not found. Options:"
echo "  1) Install Homebrew, then: brew install verapdf"
echo "  2) Download from https://verapdf.org/software/ and set VERAPDF_CMD=/path/to/verapdf"
echo "  3) Rely on Docker fallback: docker pull verapdf/cli:latest"
echo "     (A.I.D.A. copies NFS PDFs to local temp before docker run)"
exit 1
