#!/usr/bin/env bash
# Install matching Chrome for Testing + ChromeDriver for A.I.D.A. axe-core runs.
set -euo pipefail

echo "Installing Chrome for Testing + ChromeDriver via browser-driver-manager…"
npx --yes browser-driver-manager install chrome

DRIVER="$(find "$HOME/.browser-driver-manager/chromedriver" -type f -name chromedriver 2>/dev/null | head -1 || true)"
CHROME="$(find "$HOME/.browser-driver-manager/chrome" -type f -path '*/Google Chrome for Testing' 2>/dev/null | head -1 || true)"
# mac app path
if [[ -z "${CHROME}" ]]; then
  CHROME="$(find "$HOME/.browser-driver-manager/chrome" -type f -path '*/MacOS/Google Chrome for Testing' 2>/dev/null | head -1 || true)"
fi

echo "CHROMEDRIVER_TEST_PATH=${DRIVER}"
echo "CHROME_TEST_PATH=${CHROME}"
echo ""
echo "Optional shell exports for this session:"
echo "  export AIDA_CHROMEDRIVER_PATH=\"${DRIVER}\""
echo "  export AIDA_CHROME_PATH=\"${CHROME}\""
echo ""
echo "A.I.D.A. auto-discovers ~/.browser-driver-manager when env is unset."
echo "Smoke:  ./scripts/aida_drop_once.py --health | python3 -m json.tool | grep -A6 axe"
