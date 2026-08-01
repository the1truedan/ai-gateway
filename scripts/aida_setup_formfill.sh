#!/usr/bin/env bash
# Start ai-pdf-autofiller sidecar for A.I.D.A. Phase 2 form fill (localhost only).
set -euo pipefail

PORT="${AIDA_FORMFILL_PORT:-8793}"
IMAGE="${AIDA_FORMFILL_IMAGE:-ghcr.io/lindseystead/ai-pdf-autofiller:latest}"
NAME="${AIDA_FORMFILL_CONTAINER:-aida-formfill}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Alternatives:"
  echo "  pip install pdf-autofiller   # if published to PyPI"
  echo "  git clone https://github.com/lindseystead/ai-pdf-autofiller && make run-api"
  exit 1
fi

# Already healthy?
if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "Form fill already healthy on :${PORT}"
  curl -sS "http://127.0.0.1:${PORT}/health" | head -c 400 || true
  echo
  exit 0
fi

# Reuse stopped container if present
if docker ps -a --format '{{.Names}}' | grep -qx "${NAME}"; then
  echo "Starting existing container ${NAME}..."
  docker start "${NAME}"
else
  echo "Pulling ${IMAGE}..."
  docker pull "${IMAGE}"
  echo "Running ${NAME} on 127.0.0.1:${PORT}..."
  # Image is linux/amd64; on Apple Silicon use emulation
  PLATFORM_ARGS=()
  if [[ "$(uname -m)" == "arm64" ]]; then
    PLATFORM_ARGS=(--platform linux/amd64)
  fi
  docker run -d --name "${NAME}" \
    "${PLATFORM_ARGS[@]}" \
    -p "127.0.0.1:${PORT}:8000" \
    -e API_AUTH_ENABLED=false \
    --restart unless-stopped \
    "${IMAGE}"
fi

echo "Waiting for health..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "OK: form fill at http://127.0.0.1:${PORT}"
    echo "AIDA_FORMFILL_URL=http://127.0.0.1:${PORT}"
    curl -sS "http://127.0.0.1:${PORT}/health" || true
    echo
    exit 0
  fi
  sleep 1
done

echo "Timed out waiting for health on :${PORT}"
docker logs "${NAME}" 2>&1 | tail -40 || true
exit 1
