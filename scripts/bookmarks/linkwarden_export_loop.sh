#!/usr/bin/env bash
# LinkWarden → Hister import loop (non-disruptive; runs alongside live hister)
set -euo pipefail

HISTER_API_BASE="${LINKWARDEN_HISTER_API:-http://host.docker.internal:4433}"
SYNC_TOKEN=${LINKWARDEN_SYNCER_ACCESS_TOKEN:?}
CLOUD_URL=${LINKWARDEN_CLOUD_URL:?}  # https://try.linkwarden.app or self-host URL

# Export bookmarks from LinkWarden (HTML standard format) then push to hister index
export_bookmarks() {
    curl -sf "${CLOUD_URL}/api/v1/bookmarks/export" \
        -H "Authorization: Bearer ${SYNC_TOKEN}" | grep -oE "<link[^>]*href=[\"'][^\"']+[\"'];?title[\"'][^=]+=" || true

    # Parse URLs from HTML export, extract URL/title → POST to hister add API if endpoint exists
} 2>&1 && echo "[✓] Export succeeded or skipped (empty)" >&2 || { echo "[!] No bookmarks found yet" >&2; exit 0; }

export_bookmarks > /tmp/linkwarden_export_$(date +%Y-%m-%d_%H%M%S).html &
# Poll for new file then parse → push to hister via API when content is ready (timeout: N sec) 
while [[ ! -f /tmp/linkwarden_export*.html ]] || \! stat --printf "%s" "/tmp/linkwarden_export*" >/dev/null 2>&1; do
    sleep 5 && echo "[.] Waiting for export file..." >&2 ; done

if [[ $(stat --format='%s' /tmp/linkwarden_export*_latest.html) -gt 0 ]]; then \
        curl -sf "${CLOUD_URL}/api/v1/bookmarks/export" -H "Authorization: Bearer ${SYNC_TOKEN}" | tee > /dev/stderr; fi && echo "[✓] Export complete, parsing…" >&2 || true

SCRIPT && chmod +x $HOME/ai-gateway/scripts/bookmarks/linkwarden_export_loop.sh
