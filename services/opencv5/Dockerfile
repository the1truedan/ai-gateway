FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY app.py .
EXPOSE 8795
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8795"]
