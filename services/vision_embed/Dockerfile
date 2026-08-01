FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

ENV VISION_EMBED_HOST=0.0.0.0
ENV VISION_EMBED_PORT=8791
ENV VISION_EMBED_BACKEND=numpy

EXPOSE 8791
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8791"]
