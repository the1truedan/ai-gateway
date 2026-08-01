FROM python:3.12-slim

WORKDIR /workspace
COPY services /workspace/services
COPY config/orchestrator /app/config

ENV PYTHONUNBUFFERED=1
ENV ORCHESTRATOR_CONFIG=/app/config/routes.json
EXPOSE 8790

CMD ["python", "-m", "services.orchestrator.app"]
