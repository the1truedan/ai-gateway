#!/usr/bin/env python3
"""manager-vision-embed — small FastAPI feature API (not LiteLLM chat).

Exposes image → CLS / patch vectors (+ optional PCA preview).
Default backend is a lightweight numpy spatial encoder (no torch/MLX).
Swap VISION_EMBED_BACKEND later for CoreML ONNX or an external LingBot MLX worker.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
import uuid
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field

APP_NAME = "manager-vision-embed"
DEFAULT_PORT = int(os.environ.get("VISION_EMBED_PORT", "8791"))
BACKEND = os.environ.get("VISION_EMBED_BACKEND", "numpy").lower()
DEFAULT_SIZE = int(os.environ.get("VISION_EMBED_SIZE", "224"))
PATCH = int(os.environ.get("VISION_EMBED_PATCH", "16"))
INCLUDE_PATCHES_DEFAULT = os.environ.get("VISION_EMBED_INCLUDE_PATCHES", "0") == "1"

app = FastAPI(
    title=APP_NAME,
    description=(
        "Vision FEATURE API for spatial embeds / patch tokens. "
        "Not an OpenAI chat model — do not register in LiteLLM model_list."
    ),
    version="0.1.0",
)


class FeatureResponse(BaseModel):
    model: str = APP_NAME
    backend: str
    dim: int
    size: int
    patch: int
    cls: list[float]
    patches: list[list[float]] | None = None
    patch_grid: list[int] | None = None
    image_sha256: str
    elapsed_ms: float
    note: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model: str = APP_NAME
    backend: str
    size: int
    patch: int


class Base64Request(BaseModel):
    image_b64: str = Field(..., description="Raw base64 or data URL")
    size: int | None = None
    include_patches: bool | None = None


def _decode_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        return img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid image: {exc}") from exc


def _load_from_b64(image_b64: str) -> bytes:
    s = image_b64.strip()
    if "," in s and s.lower().startswith("data:"):
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid base64: {exc}") from exc


def _resize(img: Image.Image, size: int) -> np.ndarray:
    """Return float32 HWC array in [0, 1], size×size."""
    resized = img.resize((size, size), Image.Resampling.BILINEAR)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    return arr


def _l2_normalize(v: np.ndarray, axis: int = -1) -> np.ndarray:
    norms = np.linalg.norm(v, axis=axis, keepdims=True)
    norms = np.maximum(norms, 1e-9)
    return v / norms


def extract_numpy_features(
    img: Image.Image,
    *,
    size: int,
    patch: int,
    include_patches: bool,
) -> dict[str, Any]:
    """Lightweight spatial features: patch mean/std/edge stats + CLS aggregate.

    Not LingBot weights — deterministic, M4-cheap, useful for wiring MCP/RAG smoke.
    """
    if size % patch != 0:
        raise HTTPException(status_code=400, detail=f"size {size} must be divisible by patch {patch}")

    arr = _resize(img, size)
    gh = gw = size // patch
    # patches: (gh, gw, patch, patch, 3)
    patches = arr.reshape(gh, patch, gw, patch, 3).transpose(0, 2, 1, 3, 4)
    flat = patches.reshape(gh * gw, patch * patch, 3)

    means = flat.mean(axis=1)  # (N, 3)
    stds = flat.std(axis=1)
    # simple edge energy via neighbor diff inside patch
    dx = np.abs(np.diff(flat, axis=1)).mean(axis=(1, 2))  # (N,)
    # luminance histogram moments (4 bins mean)
    lum = (0.299 * flat[:, :, 0] + 0.587 * flat[:, :, 1] + 0.114 * flat[:, :, 2])
    q = np.quantile(lum, [0.25, 0.5, 0.75], axis=1).T  # (N, 3)

    # feature dim = 3+3+1+3 = 10
    feats = np.concatenate(
        [means, stds, dx[:, None], q],
        axis=1,
    ).astype(np.float32)
    feats = _l2_normalize(feats, axis=1)

    cls = _l2_normalize(feats.mean(axis=0, keepdims=True), axis=1)[0]

    out: dict[str, Any] = {
        "dim": int(cls.shape[0]),
        "cls": cls.tolist(),
        "patch_grid": [gh, gw],
        "note": (
            "numpy spatial backend (patch stats). "
            "For LingBot ViT-L MLX weights use VISION_EMBED_BACKEND=external "
            "and a worker; see services/vision_embed/README.md"
        ),
    }
    if include_patches:
        out["patches"] = feats.tolist()
    else:
        out["patches"] = None
    return out


def extract_stub_features(
    img: Image.Image,
    *,
    size: int,
    include_patches: bool,
) -> dict[str, Any]:
    """Hash-stable unit vector for CI / dependency-free smoke."""
    raw = np.asarray(img.resize((size, size)), dtype=np.uint8).tobytes()
    digest = hashlib.sha256(raw).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
    dim = 10
    cls = _l2_normalize(rng.standard_normal(dim).astype(np.float32))
    out: dict[str, Any] = {
        "dim": dim,
        "cls": cls.tolist(),
        "patch_grid": None,
        "note": "stub backend — set VISION_EMBED_BACKEND=numpy for real patch stats",
    }
    if include_patches:
        n = (size // PATCH) ** 2
        patches = _l2_normalize(rng.standard_normal((n, dim)).astype(np.float32), axis=1)
        out["patches"] = patches.tolist()
        out["patch_grid"] = [size // PATCH, size // PATCH]
    else:
        out["patches"] = None
    return out


def extract_features(
    img: Image.Image,
    *,
    size: int | None = None,
    include_patches: bool | None = None,
) -> dict[str, Any]:
    size = size or DEFAULT_SIZE
    include_patches = INCLUDE_PATCHES_DEFAULT if include_patches is None else include_patches
    backend = BACKEND
    if backend in ("numpy", "spatial"):
        feat = extract_numpy_features(img, size=size, patch=PATCH, include_patches=include_patches)
    elif backend == "stub":
        feat = extract_stub_features(img, size=size, include_patches=include_patches)
    elif backend == "external":
        raise HTTPException(
            status_code=501,
            detail=(
                "VISION_EMBED_BACKEND=external: point VISION_EMBED_EXTERNAL_URL at a "
                "LingBot/CoreML worker or implement services/vision_embed backends."
            ),
        )
    else:
        raise HTTPException(status_code=500, detail=f"unknown backend: {backend}")
    feat["backend"] = backend
    feat["size"] = size
    feat["patch"] = PATCH
    return feat


def pca_preview_png(img: Image.Image, size: int = 512) -> bytes:
    """Map patch mean RGB (already 3D) to a simple spatial preview PNG."""
    arr = _resize(img, size)
    # center and scale per-channel for contrast
    flat = arr.reshape(-1, 3)
    mu = flat.mean(axis=0)
    centered = flat - mu
    # project onto first 3 PCs via SVD of covariance (cheap for 3 ch already)
    # use channel-wise zscore as pseudo-PCA RGB
    std = centered.std(axis=0)
    std = np.maximum(std, 1e-6)
    z = (centered / std).reshape(size, size, 3)
    z = (z - z.min()) / max(float(z.max() - z.min()), 1e-6)
    out = (z * 255.0).clip(0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out, mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


@app.get("/health", response_model=HealthResponse)
@app.get("/health/liveliness", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", backend=BACKEND, size=DEFAULT_SIZE, patch=PATCH)


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": APP_NAME,
                "object": "model",
                "owned_by": "ai-gateway",
                "backend": BACKEND,
                "kind": "vision_feature_encoder",
                "chat_completions": True,
                "note": "chat returns feature JSON; not a general VLM",
            }
        ],
    }


def _image_bytes_from_data_url(url: str) -> bytes | None:
    if not url:
        return None
    if url.startswith("data:") and "," in url:
        return _load_from_b64(url)
    # http(s) fetch is intentionally unsupported in the small host service
    return None


def _first_image_from_messages(messages: list[Any]) -> tuple[Image.Image | None, str]:
    """Extract first image from OpenAI-style chat messages; return (img, user_text)."""
    texts: list[str] = []
    img: Image.Image | None = None
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text" and part.get("text"):
                texts.append(str(part["text"]))
            elif ptype in ("image_url", "image"):
                image_url = part.get("image_url")
                if isinstance(image_url, dict):
                    url = image_url.get("url") or ""
                else:
                    url = str(image_url or part.get("url") or "")
                raw = _image_bytes_from_data_url(url)
                if raw and img is None:
                    img = _decode_image(raw)
            elif ptype == "input_image":
                # some clients use input_image + image_url string
                url = str(part.get("image_url") or part.get("url") or "")
                raw = _image_bytes_from_data_url(url)
                if raw and img is None:
                    img = _decode_image(raw)
    return img, " ".join(texts).strip()


class ChatCompletionsRequest(BaseModel):
    model: str = APP_NAME
    messages: list[Any] = Field(default_factory=list)
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool | None = False
    # passthrough / ignore extra LiteLLM params
    model_config = {"extra": "allow"}


@app.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionsRequest) -> dict[str, Any]:
    """OpenAI-compatible facade for LiteLLM.

    Accepts multimodal messages with data-URL images, returns feature JSON as
    assistant text (not a general vision-language caption model).
    """
    if body.stream:
        raise HTTPException(status_code=400, detail="stream not supported")

    t0 = time.perf_counter()
    img, user_text = _first_image_from_messages(body.messages)
    if img is None:
        # allow text-only probe: return model card so LiteLLM health-style pings work
        payload = {
            "error": "no_image",
            "hint": "send an image as content part type image_url with a data: URL",
            "model": APP_NAME,
            "backend": BACKEND,
            "user_text": user_text or None,
        }
        content = json.dumps(payload)
    else:
        raw_preview = io.BytesIO()
        img.save(raw_preview, format="PNG")
        sha = hashlib.sha256(raw_preview.getvalue()).hexdigest()
        include_patches = "patches" in (user_text or "").lower()
        feat = extract_features(img, include_patches=include_patches)
        payload = {
            "model": APP_NAME,
            "backend": feat["backend"],
            "dim": feat["dim"],
            "size": feat["size"],
            "patch": feat["patch"],
            "cls": feat["cls"],
            "patch_grid": feat.get("patch_grid"),
            "patches": feat.get("patches"),
            "image_sha256": sha,
            "user_text": user_text or None,
            "note": feat.get("note", ""),
            "kind": "vision_feature_encoder",
        }
        content = json.dumps(payload)

    elapsed = (time.perf_counter() - t0) * 1000.0
    created = int(time.time())
    return {
        "id": f"chatcmpl-ve-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": created,
        "model": body.model or APP_NAME,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": max(1, len(content) // 4),
            "total_tokens": max(1, len(content) // 4),
        },
        "manager_vision_embed": {
            "elapsed_ms": round(elapsed, 2),
            "backend": BACKEND,
        },
    }


async def _read_upload(file: UploadFile | None, image_b64: str | None) -> tuple[bytes, str]:
    if file is not None:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty file")
        return data, hashlib.sha256(data).hexdigest()
    if image_b64:
        data = _load_from_b64(image_b64)
        return data, hashlib.sha256(data).hexdigest()
    raise HTTPException(status_code=400, detail="provide file or image_b64")


@app.post("/v1/features", response_model=FeatureResponse)
async def features(
    file: UploadFile | None = File(None),
    image_b64: str | None = Form(None),
    size: int | None = Form(None),
    include_patches: bool | None = Form(None),
) -> FeatureResponse:
    t0 = time.perf_counter()
    data, sha = await _read_upload(file, image_b64)
    img = _decode_image(data)
    feat = extract_features(img, size=size, include_patches=include_patches)
    elapsed = (time.perf_counter() - t0) * 1000.0
    return FeatureResponse(
        backend=feat["backend"],
        dim=feat["dim"],
        size=feat["size"],
        patch=feat["patch"],
        cls=feat["cls"],
        patches=feat.get("patches"),
        patch_grid=feat.get("patch_grid"),
        image_sha256=sha,
        elapsed_ms=round(elapsed, 2),
        note=feat.get("note", ""),
    )


@app.post("/v1/features/json", response_model=FeatureResponse)
async def features_json(body: Base64Request) -> FeatureResponse:
    t0 = time.perf_counter()
    data = _load_from_b64(body.image_b64)
    sha = hashlib.sha256(data).hexdigest()
    img = _decode_image(data)
    feat = extract_features(img, size=body.size, include_patches=body.include_patches)
    elapsed = (time.perf_counter() - t0) * 1000.0
    return FeatureResponse(
        backend=feat["backend"],
        dim=feat["dim"],
        size=feat["size"],
        patch=feat["patch"],
        cls=feat["cls"],
        patches=feat.get("patches"),
        patch_grid=feat.get("patch_grid"),
        image_sha256=sha,
        elapsed_ms=round(elapsed, 2),
        note=feat.get("note", ""),
    )


@app.post("/v1/pca")
async def pca(
    file: UploadFile | None = File(None),
    image_b64: str | None = Form(None),
    size: int = Form(512),
) -> Response:
    data, _sha = await _read_upload(file, image_b64)
    img = _decode_image(data)
    png = pca_preview_png(img, size=size)
    return Response(content=png, media_type="image/png")


def main() -> None:
    import uvicorn

    host = os.environ.get("VISION_EMBED_HOST", "127.0.0.1")
    port = int(os.environ.get("VISION_EMBED_PORT", str(DEFAULT_PORT)))
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        factory=False,
        log_level=os.environ.get("VISION_EMBED_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
