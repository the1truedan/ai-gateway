# Local ai-gateway stack captures (Chrome)

**Date:** 2026-08-03 · **Browser:** Google Chrome headless · **Scope:** localhost only

These PNGs are **ops archives**. The public README prefers **mermaid routing diagrams** and **upstream Headroom / hippo visuals** over health-JSON screenshots.

| File | URL | README use |
|------|-----|------------|
| `capture-ai-gateway-deck.png` | http://127.0.0.1:8765/ | Optional — ops board |
| `capture-ai-gateway-comfy-local.png` | http://127.0.0.1:8188/ | Optional — creative path |
| `capture-ai-gateway-litellm-swagger.png` | http://127.0.0.1:4000/ | Archive only |
| `capture-ai-gateway-litellm-ui.png` | http://127.0.0.1:4000/ui/ | Archive only (login wall) |
| `capture-ai-gateway-headroom-ready.png` | http://127.0.0.1:8787/readyz | Archive only — use upstream savings graphic + mermaid instead |
| `capture-ai-gateway-prompt-io.png` | http://127.0.0.1:5050/health | Archive only — use Prompt-I/O mermaid instead |

Manifest: `ai_gateway_local_captures.json` · Upstream credits: [`../upstream/README.md`](../upstream/README.md)

## Public README guidance

**Prefer:** mermaid for LiteLLM routing / Prompt-I/O; `docs/assets/upstream/headroom-savings.png`; `docs/assets/upstream/hippo-init.svg`.

**Avoid for public hero frames:** models-and-endpoints, raw `/readyz` or `/health` JSON, spend tables with keys.

Mac worker bus: `litellm_config.mac-worker.yaml` (`manager-worker-m4-*`).
