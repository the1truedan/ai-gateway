#!/bin/sh
export OPENAI_BASE_URL=http://<nas-host-ip>:8787/v1
export OPENAI_API_BASE=$OPENAI_BASE_URL
export OPENAI_API_KEY=${LITELLM_MASTER_KEY:-}
export MANAGER_DEFAULT_MODEL=role-auto
