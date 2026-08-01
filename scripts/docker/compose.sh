#!/usr/bin/env bash
# Multi-host docker compose wrapper (Mac arm64 / Linux amd64).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PROFILE="${AI_GATEWAY_HOST_PROFILE:-}"
if [[ -z "$PROFILE" ]]; then
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) PROFILE=mac ;;
    Linux-aarch64) PROFILE=mac ;;
    Linux-x86_64|Linux-amd64) PROFILE=linux ;;
    *) PROFILE=linux ;;
  esac
fi

HOST_ENV="$ROOT/config/hosts/${PROFILE}.env"
OVERLAY="$ROOT/docker-compose.${PROFILE}.yml"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [[ -f "$HOST_ENV" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOST_ENV"
  set +a
fi

export AI_GATEWAY_HOST_PROFILE="$PROFILE"
export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-}"

if [[ ! -f "$OVERLAY" ]]; then
  echo "Missing overlay: $OVERLAY" >&2
  exit 1
fi

echo "ai-gateway compose profile=$PROFILE platform=${DOCKER_DEFAULT_PLATFORM:-auto}"

exec docker compose -f docker-compose.yml -f "$OVERLAY" "$@"