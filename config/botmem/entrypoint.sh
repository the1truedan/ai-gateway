#!/bin/sh
# botmem:app-latest ships a managed SPA baked to https://app.botmem.xyz + Firebase.
# For self-host we rewrite JS/HTML so the UI talks to this origin's /api and defaults
# to local auth (AUTH_PROVIDER=local on the API).
set -eu

SRC="${BOTMEM_WEB_SRC:-/srv}"
DST="${BOTMEM_WEB_DST:-/tmp/webroot}"

rm -rf "$DST"
cp -a "$SRC" "$DST"

# Managed image bakes absolute cloud URLs as JS template literals, e.g.:
#   var v=`https://app.botmem.xyz`,y=`https://app.botmem.xyz`; ... S=`https://app.botmem.xyz/api`
#   var D=!0   // isFirebaseMode default true
# Replace with same-origin expressions (no backticks around the expression).
find "$DST" -type f \( -name '*.js' -o -name '*.html' -o -name '*.css' -o -name '*.json' -o -name '*.map' \) -print0 |
  while IFS= read -r -d '' f; do
    sed -i \
      -e 's|`https://app\.botmem\.xyz/api`|(window.location.origin+"/api")|g' \
      -e 's|`https://api\.botmem\.xyz`|window.location.origin|g' \
      -e 's|`https://app\.botmem\.xyz`|window.location.origin|g' \
      -e 's|"https://app\.botmem\.xyz/api"|(window.location.origin+"/api")|g' \
      -e 's|"https://app\.botmem\.xyz"|window.location.origin|g' \
      -e "s|'https://app\.botmem\.xyz/api'|(window.location.origin+\"/api\")|g" \
      -e "s|'https://app\.botmem\.xyz'|window.location.origin|g" \
      -e 's|var D=!0|var D=!1|g' \
      -e 's|var D = !0|var D=!1|g' \
      "$f" 2>/dev/null || true
  done

# Sanity: must not leave the cloud host as a live string in bootstrap
if grep -R -l 'https://app\.botmem\.xyz' "$DST/assets" 2>/dev/null | head -1 | grep -q .; then
  echo "[botmem-app] warning: some app.botmem.xyz references remain (check assets)" >&2
  grep -R -n 'https://app\.botmem\.xyz' "$DST/assets" 2>/dev/null | head -5 >&2 || true
else
  echo "[botmem-app] rewrote app.botmem.xyz → window.location.origin; Firebase default off"
fi

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
