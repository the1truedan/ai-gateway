FROM python:3.12-slim

WORKDIR /workspace
COPY services /workspace/services

ENV PYTHONUNBUFFERED=1
EXPOSE 8794

CMD ["python", "-m", "services.capacity_agent.app"]
