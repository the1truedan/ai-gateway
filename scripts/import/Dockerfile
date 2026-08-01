# Multi-host import image (arm64 Mac / amd64 Linux). Build: scripts/docker/build_importer.sh
FROM python:3.12-slim

WORKDIR /app

COPY vendor/convert_grok.py vendor/create_sql.py ./
COPY grok_build_parser.py convert_grok_build.py compose_import_entrypoint.sh run_openwebui_import.sh ./

RUN chmod +x compose_import_entrypoint.sh run_openwebui_import.sh

VOLUME ["/data", "/grok-sessions", "/grok-history", "/webui-data"]

ENV OPENWEBUI_IMPORT_IN_CONTAINER=1 \
    OPENWEBUI_IMPORT_DIR=/app \
    OPENWEBUI_PROJECT_ROOT=/app \
    OPENWEBUI_IMPORT_DATA_DIR=/data \
    PYTHONPATH=/app

ENTRYPOINT ["/bin/sh", "/app/compose_import_entrypoint.sh"]
CMD ["--all"]