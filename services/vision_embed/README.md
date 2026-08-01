# manager-vision-embed

Small **FastAPI** vision **feature** service for ai-gateway.

- **LiteLLM alias:** `manager-vision-embed` → `openai/` + `http://host.docker.internal:8791/v1`
- Chat facade returns **feature JSON**, not VLM captions — use `manager-vision-local` / `manager-gemini-vision` for that.
- OCR stays on `manager-ocr-local`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness + backend |
| GET | `/v1/models` | Lists `manager-vision-embed` (kind=vision_feature_encoder) |
| POST | `/v1/chat/completions` | OpenAI-compatible facade for LiteLLM (image data-URL → feature JSON) |
| POST | `/v1/features` | multipart `file` or form `image_b64` → CLS (+ optional patches) |
| POST | `/v1/features/json` | JSON `{ "image_b64": "..." }` |
| POST | `/v1/pca` | PNG spatial preview |

Default listen: `http://127.0.0.1:8791`

## Backends

| `VISION_EMBED_BACKEND` | Behavior |
|------------------------|----------|
| `numpy` (default) | Patch mean/std/edge/quantile features (10-D CLS) — no torch/MLX |
| `stub` | Hash-stable random unit vector (CI) |
| `external` | 501 until a LingBot/CoreML worker URL is implemented |

LingBot ViT-L MLX ([HF](https://huggingface.co/mnmly/lingbot-vision-vit-large-mlx)) is **Swift/MLX** — wire later as an external worker, not inside this Python process.

## Run (host — preferred on M4)

```bash
cd ~/ai-gateway
python3 -m venv services/vision_embed/.venv
source services/vision_embed/.venv/bin/activate
pip install -r services/vision_embed/requirements.txt
./scripts/start_vision_embed.sh
```

Smoke:

```bash
# solid color PNG
python3 - <<'PY'
from PIL import Image
Image.new("RGB", (64, 64), (30, 120, 200)).save("/tmp/ve-test.png")
PY

curl -sS http://127.0.0.1:8791/health
curl -sS -F "file=@/tmp/ve-test.png" http://127.0.0.1:8791/v1/features | python3 -m json.tool
```

## Env

| Variable | Default | Meaning |
|----------|---------|---------|
| `VISION_EMBED_HOST` | `127.0.0.1` | Bind address |
| `VISION_EMBED_PORT` | `8791` | Port |
| `VISION_EMBED_BACKEND` | `numpy` | `numpy` \| `stub` \| `external` |
| `VISION_EMBED_SIZE` | `224` | Input side (must be ÷ patch) |
| `VISION_EMBED_PATCH` | `16` | Patch size |
| `VISION_EMBED_INCLUDE_PATCHES` | `0` | Default include full patch matrix |

## Compose (optional profile)

```bash
./scripts/docker/compose.sh --profile vision up -d vision-embed
```

## MCP sketch (agents)

Agents call HTTP tools, not LiteLLM model ids:

```text
POST http://127.0.0.1:8791/v1/features  (multipart image)
→ { cls: [...], dim, patch_grid, backend }
```
