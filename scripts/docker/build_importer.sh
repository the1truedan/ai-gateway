#!/usr/bin/env bash
# Build openwebui-importer for current host or multi-platform (buildx).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

IMAGE="${OPENWEBUI_IMPORTER_IMAGE:-ai-gateway-openwebui-importer:local}"
PLATFORMS="${BUILD_PLATFORMS:-}"

if [[ "${1:-}" == "--multi" ]]; then
  PLATFORMS="${2:-linux/amd64,linux/arm64}"
  echo "Building $IMAGE for $PLATFORMS (buildx)"
  docker buildx build \
    --platform "$PLATFORMS" \
    -t "$IMAGE" \
    -f scripts/import/Dockerfile \
    scripts/import \
    --load
  exit 0
fi

case "$(uname -m)" in
  arm64|aarch64) PLATFORM=linux/arm64 ;;
  *) PLATFORM=linux/amd64 ;;
esac

echo "Building $IMAGE ($PLATFORM)"
docker build \
  --platform "$PLATFORM" \
  -t "$IMAGE" \
  -f scripts/import/Dockerfile \
  scripts/import