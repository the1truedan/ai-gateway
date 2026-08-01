#!/usr/bin/env bash
# Hister Bookmark Sync: Export from LinkWarden → Index via API (safe for live stack)

set -euo pipefail; trap 'echo "[!] Failed at step $LINENO" >&2' ERR
HOST_URL="${LINKWARDEN_CLOUD_URL:-https://try.linkwarden.app}"  
API_TOKEN=${SYNCER_ACCESS_TOKEN:?require token}  

export_bookmarks() { 
    echo "[*] Exporting from LinkWarden..." && sleep 1 \
        curl -sf "$HOST_URL/api/v1/bookmarks/export" --max-time 60 | tee /tmp/linkwdn_$(date +%Y%m%d).html || true;
}

test_url="https://example.com/test_link"  
curl -s "$HISTER_API/add?url=$URL&title=test_title" >/dev/null && echo "[✓] Test indexed!" 