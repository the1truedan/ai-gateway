FROM python:3.12-slim

# ocrmypdf + tesseract for in-container OCR (host preferred on M4)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ocrmypdf \
    tesseract-ocr \
    tesseract-ocr-eng \
    ghostscript \
    qpdf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py pipeline.py verapdf_runner.py .

ENV AIDA_HOST=0.0.0.0
ENV AIDA_PORT=8792
ENV AIDA_INGEST_ROOT=/ingest
ENV AIDA_LITELLM_BASE=http://litellm:4000
ENV AIDA_MODEL=role-phi-local
ENV VERAPDF_DISABLE_DOCKER=1

EXPOSE 8792
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8792"]
