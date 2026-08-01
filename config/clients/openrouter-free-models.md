# OpenRouter free models (via AI-Gateway)

_Auto-generated 2026-07-17T01:37:29.925164+00:00 by `scripts/sync_openrouter_free_models.py`. Do not edit the catalog table by hand — re-run the sync._

Source: [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0)

## How to call (always prefer LiteLLM)

```bash
export OPENAI_BASE_URL=http://localhost:4000/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
# Curated:
#   manager-openrouter-free / tier-free-cloud  → openrouter/free router
#   manager-big-context / manager-understand-audit → qwen/qwen3-coder:free
#   manager-audit-claude → poolside/laguna-xs-2.1:free
# Direct free alias: or-free-<slug>
```

Agents (pi, OpenCode, tau) should use **gateway model ids**, not raw OpenRouter URLs,
so Prometheus, retries, and fallbacks apply.

## Catalog

**20** free chat-candidate models → **24** LiteLLM aliases (includes curated names).

| OpenRouter id | LiteLLM alias(es) | Ctx | Modality | Role |
|---------------|-------------------|-----|----------|------|
| `qwen/qwen3-coder:free` | `manager-big-context`, `manager-understand-audit`, `or-free-qwen-qwen3-coder-free` | 1.0M | text->text | Best free coding + huge context audits |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | `or-free-nvidia-nemotron-3-ultra-550b-a55b-free` | 1M | text->text | Frontier reasoning / orchestration |
| `nvidia/nemotron-3-super-120b-a12b:free` | `or-free-nvidia-nemotron-3-super-120b-a12b-free` | 1M | text->text | Strong general MoE, efficient active params |
| `tencent/hy3:free` | `or-free-tencent-hy3-free` | 262k | text->text | Large MoE reasoning (Tencent) |
| `poolside/laguna-xs-2.1:free` | `manager-audit-claude`, `or-free-poolside-laguna-xs-2-1-free` | 262k | text->text | Lighter coding agent (curated audit) |
| `poolside/laguna-m.1:free` | `or-free-poolside-laguna-m-1-free` | 262k | text->text | Flagship free coding agent |
| `google/gemma-4-26b-a4b-it:free` | `or-free-google-gemma-4-26b-a4b-it-free` | 262k | text+image+video->text | Free multimodal MoE VLM |
| `google/gemma-4-31b-it:free` | `or-free-google-gemma-4-31b-it-free` | 262k | text+image+video->text | Free multimodal VLM (image/video→text) |
| `qwen/qwen3-next-80b-a3b-instruct:free` | `or-free-qwen-qwen3-next-80b-a3b-instruct-free` | 262k | text->text | Fast instruct chat |
| `cohere/north-mini-code:free` | `or-free-cohere-north-mini-code-free` | 256k | text->text | Agentic coding (North family) |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | `or-free-nvidia-nemotron-3-nano-omni-30b-a3b-reasoning-free` | 256k | text+image+audio+video->text | Multimodal perception / sub-agent |
| `nvidia/nemotron-3-nano-30b-a3b:free` | `or-free-nvidia-nemotron-3-nano-30b-a3b-free` | 256k | text->text | Efficient small MoE for agents |
| `openrouter/free` | `manager-openrouter-free`, `or-free-openrouter-free` | 200k | text+image->text | Router: random free model (unpredictable) |
| `openai/gpt-oss-20b:free` | `or-free-openai-gpt-oss-20b-free` | 131k | text->text | Small OSS baseline |
| `meta-llama/llama-3.3-70b-instruct:free` | `or-free-meta-llama-llama-3-3-70b-instruct-free` | 131k | text->text | General chat 70B |
| `meta-llama/llama-3.2-3b-instruct:free` | `or-free-meta-llama-llama-3-2-3b-instruct-free` | 131k | text->text | Tiny general chat |
| `nousresearch/hermes-3-llama-3.1-405b:free` | `or-free-nousresearch-hermes-3-llama-3-1-405b-free` | 131k | text->text | Large generalist / agentic |
| `nvidia/nemotron-nano-12b-v2-vl:free` | `or-free-nvidia-nemotron-nano-12b-v2-vl-free` | 128k | text+image+video->text | Video/image VL reasoning |
| `nvidia/nemotron-nano-9b-v2:free` | `or-free-nvidia-nemotron-nano-9b-v2-free` | 128k | text->text | Tiny efficient LLM |
| `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` | `or-free-cognitivecomputations-dolphin-mistral-24b-venice-edition-free` | 32k | text->text | Uncensored; avoid PHI |

## Compare & contrast (use cases)

| Job | Prefer | Why | Watch out |
|-----|--------|-----|-----------|
| Day-to-day **coding agent** | `poolside/laguna-m.1:free`, `laguna-xs-2.1:free`, `cohere/north-mini-code:free`, `qwen/qwen3-coder:free` | Built for agentic coding / tools | Free queueing; tool quality varies by provider |
| **Huge codebase audit** / long logs | `qwen/qwen3-coder:free` (1M), `nvidia/nemotron-3-ultra*:free` / `super*:free` (1M) | Million-token context | Latency + free rate limits; still leaves host |
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
| `manager-big-context` | `qwen/qwen3-coder:free` |
| `manager-audit-claude` | `poolside/laguna-xs-2.1:free` |
| `manager-understand-audit` | `qwen/qwen3-coder:free` |
| `manager-openrouter-free` | `openrouter/free` |

## Refresh

```bash
cd ~/ai-gateway
set -a && source .env && set +a
python3 scripts/sync_openrouter_free_models.py
# if config_changed=true:
./scripts/docker/compose.sh restart litellm
```
