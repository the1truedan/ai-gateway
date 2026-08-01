#!/usr/bin/env bash
# Install OpenDataLoader PDF (Apache-2.0) + ensure OpenJDK 17 on PATH for A.I.D.A.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${AIDA_VENV:-$ROOT/services/aida/.venv}"

# Prefer brew openjdk@17
if command -v brew >/dev/null 2>&1; then
  if ! brew list openjdk@17 >/dev/null 2>&1; then
    echo "Installing openjdk@17 via Homebrew..."
    brew install openjdk@17
  fi
  J17="$(brew --prefix openjdk@17)"
  if [[ -x "${J17}/libexec/openjdk.jdk/Contents/Home/bin/java" ]]; then
    export JAVA_HOME="${J17}/libexec/openjdk.jdk/Contents/Home"
  elif [[ -x "${J17}/bin/java" ]]; then
    export JAVA_HOME="${J17}"
  fi
  if [[ -n "${JAVA_HOME:-}" ]]; then
    export PATH="${JAVA_HOME}/bin:${PATH}"
    export AIDA_JAVA_HOME="${JAVA_HOME}"
    echo "JAVA_HOME=${JAVA_HOME}"
  fi
fi

if ! command -v java >/dev/null 2>&1; then
  echo "Java not found (OpenDataLoader needs JDK 11+)."
  echo "  brew install openjdk@17"
  exit 1
fi

MAJOR="$(java -version 2>&1 | head -1 | sed -n 's/.*version \"\([0-9]*\).*/\1/p')"
if [[ "${MAJOR}" == "1" ]]; then
  MAJOR="$(java -version 2>&1 | head -1 | sed -n 's/.*version \"1\.\([0-9]*\).*/\1/p')"
fi
echo "Java: $(java -version 2>&1 | head -1) (major=${MAJOR:-?})"
if [[ -n "${MAJOR:-}" && "${MAJOR}" -lt 11 ]]; then
  echo "ERROR: need JDK 11+; got ${MAJOR}"
  exit 1
fi

if [[ ! -d "$VENV" ]]; then
  echo "Creating venv at $VENV"
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip
pip install -U "opendataloader-pdf"

python - <<'PY'
import opendataloader_pdf
print("opendataloader-pdf import OK:", getattr(opendataloader_pdf, "__file__", "?"))
PY

# Persist path hint for the user shell
PROFILE_HINT="${HOME}/.zprofile"
LINE='export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"'
LINE2='export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"'
if [[ -d /opt/homebrew/opt/openjdk@17 ]]; then
  if [[ -f "$PROFILE_HINT" ]] && grep -q 'openjdk@17' "$PROFILE_HINT" 2>/dev/null; then
    echo "zprofile already mentions openjdk@17"
  else
    echo ""
    echo "To put JDK 17 on PATH for all shells, add to ~/.zprofile:"
    echo "  ${LINE}"
    echo "  ${LINE2}"
    echo "(start_aida.sh already prefers brew openjdk@17 without editing your profile.)"
  fi
fi

echo
echo "OK. Restart A.I.D.A. so /health shows opendataloader.available=true."
echo "Disable with AIDA_OPENDATALOADER_DISABLE=1 if needed."
echo "Note: free path = Tagged PDF; full PDF/UA export is enterprise (we do not use it)."
