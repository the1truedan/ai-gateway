#!/usr/bin/env bash
# Stage Mac project sources into Turnstone's NFS-backed gpu-host workspace.
# This is intentionally additive: it never uses rsync --delete and does not
# manage/restart the Unraid fast-models or NFS services.
set -euo pipefail

remote_host="${TURNSTONE_SYNC_HOST:-youruser@<gpu-host-ip>}"
remote_root="${TURNSTONE_WORKSPACE_ROOT:-/mnt/ai-data/work/turnstone}"

projects=(ai-gateway supafix grokcode)
source_root="${TURNSTONE_SOURCE_ROOT:-$HOME}"

exclude_args=(
  --include=.env.example
  --exclude=.env
  --exclude='.env.*'
  --exclude=.DS_Store
  --exclude=.venv/
  --exclude=node_modules/
  --exclude=target/
  --exclude=dist/
  --exclude=build/
  --exclude=__pycache__/
  --exclude='*.pyc'
  --exclude=logs/
  --exclude=litellm_data/
  --exclude='*.db'
  --exclude='*.sqlite'
  --exclude='*.sqlite3'
)

ssh -o BatchMode=yes "$remote_host" \
  "mkdir -p '$remote_root/ai-gateway' '$remote_root/supafix' '$remote_root/grokcode'"

for project in "${projects[@]}"; do
  source_dir="$source_root/$project"
  if [[ ! -d "$source_dir" ]]; then
    echo "missing source directory: $source_dir" >&2
    exit 1
  fi

  echo "syncing $source_dir/ -> $remote_host:$remote_root/$project/"
  rsync -a --human-readable --itemize-changes --partial \
    "${exclude_args[@]}" \
    -e "ssh -o BatchMode=yes" \
    "$source_dir/" "$remote_host:$remote_root/$project/"
done

ssh -o BatchMode=yes "$remote_host" \
  "find '$remote_root' -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort"
