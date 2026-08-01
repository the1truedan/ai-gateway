# OpenCV 5 on NAS-HOST

Lightweight OpenCV 5 preprocessing and feature extraction for NAS-HOST. The PyPI
wheel is CPU-only; the P2000 remains available to Ollama and future explicitly
built CUDA/ONNX workloads. This avoids pretending the standard wheel provides
CUDA acceleration.

- `GET /healthz`
- `POST /v1/features` with multipart field `file`

Loopback smoke uses `http://localhost:8795`.
