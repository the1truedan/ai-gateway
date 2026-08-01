#!/bin/sh
# Source this file to use the shared NFS download cache with host-local envs.

case "$(uname -s)" in
  Darwin) uv_shared_root=/Volumes/ai-data/uv-cache/mac-client ;;
  *) uv_shared_root=/mnt/ai-data/uv-cache/$(hostname | tr '[:upper:]' '[:lower:]') ;;
esac

if mkdir -p "$uv_shared_root" 2>/dev/null && test_file="$uv_shared_root/.manager-write-test" \
  && : >"$test_file" 2>/dev/null && rm -f "$test_file"; then
  export UV_CACHE_DIR=$uv_shared_root
else
  export UV_CACHE_DIR=${TMPDIR:-/tmp}/manager-uv-cache
  echo "warning: shared uv cache unavailable; using $UV_CACHE_DIR" >&2
fi

# Virtual environments and installed tools stay local; concurrent NFS venvs are unsafe.
export UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-.venv}
