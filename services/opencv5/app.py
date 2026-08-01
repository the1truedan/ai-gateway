#!/usr/bin/env python3
"""Small OpenCV 5 feature/preprocessing API for the NAS-HOST P2000 node."""

from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile


app = FastAPI(title="manager-opencv5", version="0.1.0")


@app.get("/healthz")
def health() -> dict:
    return {
        "status": "ok",
        "service": "manager-opencv5",
        "opencv": cv2.__version__,
        "cuda_devices": cv2.cuda.getCudaEnabledDeviceCount() if hasattr(cv2, "cuda") else 0,
    }


@app.post("/v1/features")
async def features(file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="unsupported image")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    height, width = gray.shape
    return {
        "width": width,
        "height": height,
        "channels": int(image.shape[2]),
        "mean_bgr": [round(float(value), 4) for value in image.mean(axis=(0, 1))],
        "edge_ratio": round(float(np.count_nonzero(edges)) / edges.size, 6),
        "thumbnail_gray_png": base64.b64encode(
            cv2.imencode(".png", cv2.resize(gray, (64, 64)))[1].tobytes()
        ).decode(),
    }
