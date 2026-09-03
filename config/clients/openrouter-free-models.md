# OpenRouter free models (via AI-Gateway)

_Auto-generated 2026-09-03T10:00:06.595364+00:00 by `scripts/sync_openrouter_free_models.py`. Do not edit the catalog table by hand — re-run the sync._

Source: [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0)

## How to call (always prefer LiteLLM)

```bash
export OPENAI_BASE_URL=http://localhost:4000/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
# Curated:
#   manager-openrouter-free / tier-free-cloud  → openrouter/free router
#   manager-big-context / manager-understand-audit → defined in litellm_config.yaml, not here
#   manager-audit-claude → poolside/laguna-xs-2.1:free
# Direct free alias: or-free-<slug>
```

Agents (pi, OpenCode, tau) should use **gateway model ids**, not raw OpenRouter URLs,
so Prometheus, retries, and fallbacks apply.

## Catalog

**18** free chat-candidate models → **20** LiteLLM aliases (includes curated names).

| OpenRouter id | LiteLLM alias(es) | Ctx | Modality | Role |
|---------------|-------------------|-----|----------|------|
| `thinkingmachines/inkling-small:free` | `or-free-thinkingmachines-inkling-small-free` | 1.0M | text+image+audio->text | 1M-ctx smaller Inkling (public_code only) |
| `thinkingmachines/inkling:free` | `or-free-thinkingmachines-inkling-free` | 1.0M | text+image+audio->text | 1M-ctx multimodal (public_code only) |
| `minimax/minimax-m3:free` | `or-free-minimax-minimax-m3-free` | 1.0M | text+image+video->text | 1M-ctx multimodal |
| `nvidia/nemotron-3.5-lightning:free` | `or-free-nvidia-nemotron-3-5-lightning-free` | 1M | text->text | 1M-ctx free reasoning / recon overflow |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | `or-free-nvidia-nemotron-3-ultra-550b-a55b-free` | 1M | text->text | Frontier reasoning / orchestration |
| `dots-studio/dots-3-note-preview:free` | `or-free-dots-studio-dots-3-note-preview-free` | 512k | text+image->text | General free chat |
| `inclusionai/ling-3.0-flash-fin:free` | `or-free-inclusionai-ling-3-0-flash-fin-free` | 262k | text->text | General free chat |
| `poolside/laguna-s-2.1:free` | `or-free-poolside-laguna-s-2-1-free` | 262k | text->text | Free coding agent (larger Laguna) |
| `poolside/laguna-xs-2.1:free` | `manager-audit-claude`, `or-free-poolside-laguna-xs-2-1-free` | 262k | text->text | Lighter coding agent (curated audit) |
| `google/gemma-4-26b-a4b-it:free` | `or-free-google-gemma-4-26b-a4b-it-free` | 262k | text+image+video->text | Free multimodal MoE VLM |
| `google/gemma-4-31b-it:free` | `or-free-google-gemma-4-31b-it-free` | 262k | text+image+video->text | Free multimodal VLM (image/video→text) |
| `nvidia/nemotron-3-super-120b-a12b:free` | `or-free-nvidia-nemotron-3-super-120b-a12b-free` | 262k | text->text | Strong general MoE, efficient active params |
| `cohere/north-mini-code:free` | `or-free-cohere-north-mini-code-free` | 256k | text->text | Agentic coding (North family) |
| `z-ai/glm-5.2:free` | `or-free-z-ai-glm-5-2-free` | 256k | text->text | General tools / chat |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | `or-free-nvidia-nemotron-3-nano-omni-30b-a3b-reasoning-free` | 256k | text+image+audio+video->text | Multimodal perception / sub-agent |
| `openrouter/free` | `manager-openrouter-free`, `or-free-openrouter-free` | 200k | text+image->text | Router: random free model (unpredictable) |
| `minimax/minimax-m2.7:free` | `or-free-minimax-minimax-m2-7-free` | 196k | text->text | General free chat |
| `liquid/lfm-2.5-2.6b:free` | `or-free-liquid-lfm-2-5-2-6b-free` | 65k | text->text | General free chat |

## Compare & contrast (use cases)

| Job | Prefer | Why | Watch out |
|-----|--------|-----|-----------|
| Day-to-day **coding agent** | `poolside/laguna-xs-2.1:free`, `laguna-s-2.1:free`, `cohere/north-mini-code:free`, `z-ai/glm-5.2:free` | Built for agentic coding / tools | Free queueing; tool quality varies by provider. `qwen3-coder:free` is **off** the 08-29 list |
| **Huge codebase audit** / long logs | `thinkingmachines/inkling:free` (1M), `nvidia/nemotron-3.5-lightning:free` / `ultra*:free` (1M) | Million-token context | Latency + free rate limits; still leaves host |
| **Multimodal** free (image/video→text) | `google/gemma-4-*:free`, `nvidia/nemotron-*-vl*:free`, `nemotron-3-nano-omni*:free` | Free VLM path | **Never PHI**; prefer `manager-vision-local` / Gemini for controlled cloud |
| Quick free fallback | `openrouter/free` → `manager-openrouter-free` / `tier-free-cloud` | Zero config router | **Random** free model — quality and tools are unpredictable |
| General chat / summarization | Llama 3.3 70B, Hermes 405B, Qwen3-Next | Broad instruction following | Not specialized for coding agents |
| Tiny / cheap experiments | Llama 3.2 3B, Nemotron Nano 9B, gpt-oss-20b | Low cost compute on provider side | Weak on hard coding / long agents |
| Uncensored sandbox | Dolphin / Venice edition | Fewer refusals | **Avoid** for compliance, PHI, caregiving |

### Vs local gateway tiers

| | Local (`tier-local-fast` / turbo) | Gemini (`tier-gemini`) | Free OpenRouter | Paid Grok (`tier-paid-cloud`) |
|--|-------------------------------|------------------------|-----------------|--------------------------------|
| Privacy | Best (stays on host) | Leaves host (AI Studio) | Leaves host (OR + upstream) | Leaves host (xAI) |
| Cost | Electricity only | Google One quota | $0 (rate-limited) | Paid |
| Context | Model-bound (local VRAM) | Large | Up to **1M** free | Large |
| Reliability | Your hardware | Good SLA-ish | Best-effort free tier | Paid SLA-ish |
| Best for | PHI, default coding | Multimodal cloud, tools | Burst audits, overflow | Hard coding when free fails |

## Limitations & other considerations

1. **Privacy / PHI** — Free OpenRouter always leaves the Mac. Default M.A.N.A.G.E.R. path is `tier-local-fast` / `manager-fast-turbo`. Do not default free OR for caregiver data.
2. **Churn** — Free list changes. Re-run `python3 scripts/sync_openrouter_free_models.py` (or the `openrouter-sync` compose profile). Stale `or-free-*` ids fail until re-sync.
3. **Rate limits & queues** — Free endpoints throttle; expect 429s and long TTFT under load.
4. **No SLA / tool-calling** — Agentic CLIs may break on models with weak tools; prefer Laguna / Qwen coder / North Mini for agents.
5. **Router opacity** — `openrouter/free` does not guarantee a coding model; pin an id for audits.
6. **Fallback graph** — Gateway already falls local → Gemini → free OR → Grok for many aliases; use tier names so that chain stays intact.
7. **Modality mismatches** — VL models are not drop-in for pure text agent loops; use vision tiers.

## Curated gateway aliases

| Alias | Upstream |
|-------|----------|
| `manager-audit-claude` | `poolside/laguna-xs-2.1:free` |
| `manager-openrouter-free` | `openrouter/free` |

## Refresh

```bash
cd ~/ai-gateway
set -a && source .env && set +a
python3 scripts/sync_openrouter_free_models.py
# if config_changed=true:
./scripts/docker/compose.sh restart litellm
```
