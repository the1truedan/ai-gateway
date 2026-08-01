FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

ENV PROMPT_IO_HOST=0.0.0.0
ENV PROMPT_IO_PORT=5050

EXPOSE 5050
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5050"]
