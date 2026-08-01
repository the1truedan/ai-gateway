
#!/usr/bin/env bash
# webhook_listener: Listen for Karakeep add events → trigger immediate Hister indexing  
set -euo pipefail; trap 'echo "[!] Failed at step $LINENO" >&2' ERR

PORT="${LISTENER_PORT:-4086}" HOST_URL="http://localhost:$PORT" LOG_DIR="/logs/bookmarks_webhook.log"  

handle_add() { 
    URL=$1 && TITLE=${TITLE:-test}  # parse request body for url/title if JSON payload passed to API  
    echo "[*] Received webhook add event: $URL → indexing..." >> "$LOG_DIR"; \
        curl -sf "http://host.docker.internal:4433/api/bookmark/add?url=$URL&title=${TITLE:-${1}}" >/dev/null || true; 
}

handle_list() { list_urls_from_karaka_api "$HOST_URL" > /tmp/kara_bookmarks_$$(date +%Y%m%d).json }  

while read URL TITLE <<< <(curl -sf "http://localhost:4086/bookmark/list?cursor=1&limit=50"); do \
    curl -sf --max-time 30 "$HOST_URL/api/bookmark/add?url=$URL&title=${TITLE:-$}" >/dev/null || true; 
done

echo "[✓] Webhook listener running: listening on port $PORT (check logs for trigger events)" && tail -15 /var/log/syslog | grep bookmark_sync || true 

EOF  
