#!/usr/bin/env sh
# Source from an gpu-host Herdr pane before launching pi/omp/OpenCode/Codex.
set -a
. $HOME/ai-gateway/.env
set +a
export OPENAI_BASE_URL=http://localhost:8787/v1
export OPENAI_API_BASE="$OPENAI_BASE_URL"
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
export LITELLM_BASE_URL="$OPENAI_BASE_URL"
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
