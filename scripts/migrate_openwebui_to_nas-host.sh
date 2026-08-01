#!/bin/sh
set -eu

# Safe single-writer migration. Dry-run unless --apply is supplied.
MODE=${1:-dry-run}
NAS_HOST_SSH=${NAS_HOST_SSH:-root@<nas-host-ip>}
SOURCE_CONTAINER=${SOURCE_CONTAINER:-open-webui}
SOURCE_VOLUME=${SOURCE_VOLUME:-ai-gateway_open-webui-data}
NAS_HOST_APPDATA=${NAS_HOST_APPDATA:-/mnt/user/appdata/manager-orchestration/open-webui}
EXPECTED_CHATS=${EXPECTED_CHATS:-515}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="open-webui-mac-${STAMP}.tar.gz"
LOCAL_STAGE=${LOCAL_STAGE:-/private/tmp/manager-openwebui-migration}
SOURCE_STOPPED=0
CUTOVER_STAGED=0

restore_on_failure() {
  exit_code=$?
  trap - EXIT HUP INT TERM
  if [ "$SOURCE_STOPPED" -eq 1 ] && [ "$CUTOVER_STAGED" -eq 0 ]; then
    echo "Migration failed; restarting Mac Open WebUI" >&2
    docker start "$SOURCE_CONTAINER" >/dev/null || true
  fi
  exit "$exit_code"
}
trap restore_on_failure EXIT HUP INT TERM

count_source() {
  docker exec "$SOURCE_CONTAINER" python3 -c '
import sqlite3
c=sqlite3.connect("file:/app/backend/data/webui.db?mode=ro", uri=True)
print("integrity=" + c.execute("pragma integrity_check").fetchone()[0])
print("chats=" + str(c.execute("select count(*) from chat").fetchone()[0]))
print("users=" + str(c.execute("select count(*) from user").fetchone()[0]))
'
}

echo "source_container=$SOURCE_CONTAINER source_volume=$SOURCE_VOLUME"
count_source
ssh "$NAS_HOST_SSH" "docker inspect fast-models --format 'fast_models_id={{.Id}} started={{.State.StartedAt}} restart={{.RestartCount}} health={{.State.Health.Status}}'"

if [ "$MODE" != "--apply" ]; then
  echo "dry-run only; re-run with --apply for the single-writer cutover"
  exit 0
fi

mkdir -p "$LOCAL_STAGE"
docker stop "$SOURCE_CONTAINER"
SOURCE_STOPPED=1
docker run --rm \
  -v "$SOURCE_VOLUME:/source:ro" \
  -v "$LOCAL_STAGE:/backup" \
  alpine:3.22 tar -C /source -czf "/backup/$ARCHIVE" .

ssh "$NAS_HOST_SSH" "mkdir -p /mnt/user/appdata/manager-orchestration/migration '$NAS_HOST_APPDATA'; test ! -e '$NAS_HOST_APPDATA/webui.db'"
scp "$LOCAL_STAGE/$ARCHIVE" "$NAS_HOST_SSH:/mnt/user/appdata/manager-orchestration/migration/$ARCHIVE"
ssh "$NAS_HOST_SSH" "tar -C '$NAS_HOST_APPDATA' -xzf '/mnt/user/appdata/manager-orchestration/migration/$ARCHIVE'"

ssh "$NAS_HOST_SSH" "docker run --rm -v '$NAS_HOST_APPDATA:/data:ro' python:3.12-slim python -c 'import sqlite3; c=sqlite3.connect(\"file:/data/webui.db?mode=ro&immutable=1\",uri=True); integrity=c.execute(\"pragma integrity_check\").fetchone()[0]; chats=c.execute(\"select count(*) from chat\").fetchone()[0]; users=c.execute(\"select count(*) from user\").fetchone()[0]; print(f\"integrity={integrity} chats={chats} users={users}\"); raise SystemExit(integrity != \"ok\" or chats != $EXPECTED_CHATS or users < 1)'"
ssh "$NAS_HOST_SSH" "docker inspect fast-models --format 'fast_models_id={{.Id}} started={{.State.StartedAt}} restart={{.RestartCount}} health={{.State.Health.Status}}'"

CUTOVER_STAGED=1
trap - EXIT HUP INT TERM
echo "Migration staged. Mac Open WebUI remains stopped. Start only the NAS-HOST canonical instance after verifying counts."
echo "Rollback: stop NAS-HOST Open WebUI, then start $SOURCE_CONTAINER on the Mac; never run both copied databases as writers."
