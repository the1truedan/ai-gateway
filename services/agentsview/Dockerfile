FROM python:3.11-slim

# Pin the same version currently running on the desk Pinokio install
# (~/pinokio/api/agentsviewMAC.pinokio.git) so Tower behaves identically.
ARG AGENTSVIEW_VERSION=0.40.0

RUN pip install --no-cache-dir "agentsview==${AGENTSVIEW_VERSION}"

ENV PYTHONUNBUFFERED=1
EXPOSE 42100

# AGENTSVIEW_PG_URL supplied via compose environment (points at agentsview-db).
# --require-auth: this container is reachable on the LAN, not just localhost —
# on first boot it generates its own auth_token into AGENTSVIEW_DATA_DIR/config.toml
# (same as the desk Pinokio install did); read it back with
#   docker exec agentsview-serve cat /data/config.toml
# --no-sync: this container has no local CLI session dirs to scan — it only
# ever reads/writes Postgres. m4rv and mrgpu remain the writable sync edges.
CMD ["agentsview", "pg", "serve", "--host", "0.0.0.0", "--port", "42100", "--require-auth", "--no-sync"]
