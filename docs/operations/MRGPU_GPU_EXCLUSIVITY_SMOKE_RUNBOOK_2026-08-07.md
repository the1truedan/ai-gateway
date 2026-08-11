# MRGPU GPU exclusivity + OOM taxonomy runbook

**Date:** 2026-08-07  
**SSOT home:** `~/ai-gateway/docs/operations/` (big-pic disclosure for orchestrators)  
**Hosts:** gpu-host `mrgpu` · RTX 4060 Ti **16 GB** · system RAM **~62 GiB** (~**48 GiB** available class)  
**Stack facts (live):** driver **580.173.02** · torch **2.6.0+cu124** · CUDA **12.4** · Comfy venv Python **3.12.3** · ComfyUI **0.30.2**  
**Related:** `HIPPO_CONTEXT_CONTINUITY_STANDARD_2026-08-04.md` · `grokcode/docs/operations/ORCHESTRATION_HANDOFF_STATUS.md` · `mok-tua` smoke provenance  
**Custody index:** `grokcode/data/catalog/johnny_chipper_chains_mrgpu_stage_stream_2026-08-07.json`  

Thin pointers only in other repos — do not fork conflicting full copies.

### Johnny / C.H.I.P.P.E.R. / C.H.A.I.N.S. (deduped model cognitive cache)

| Layer | Role in this stream |
|-------|---------------------|
| **Johnny Appleseed** | Classify remote URL + local pool path into envelopes (`IngestRequest` / model_weight) |
| **C.H.I.P.P.E.R.** | Hash path·size·sha256·Flux task id (no multi-GB body in skeleton) |
| **C.H.A.I.N.S.** | Append-only custody under `logs/chains/` + `work/catalog/johnny-chipper/receipts/` |
| **fast-models / ai-data** | Canonical weights SSOT; bees L3; hash ladder L2 for dedup |
| **Public conceptual** | `https://github.com/the1truedan/johnny-appleseed-chipper.git` (PRIVATE until Template F go) |

Promote path: FluxDown → `_dl` → `scripts/fluxdown_promote_to_models.py` (Johnny envelope + CHAINS).

---

## 0. Purpose

1. Never confuse **multi-tool VRAM saturation** with **model-class OOM**.  
2. Gate every generative smoke (video · image · audio · large local LLM) on a **clean-GPU** baseline.  
3. Map **storage roles** (NFS pool · host root · `/MCP_WIP` second-SSD role) so offload/scratch does not fight weights.  
4. Prioritize **FluxDown** pulls for Director’s Console styles/video gaps **before** speculative multi-GB spikes.
5. **Do not** overlap PMB's embed-queue drain/reindex with an exclusive video window — PMB's production embedder calls Ollama `bge-m3` directly on mrgpu (2026-08-10, see §3.5), a real GPU consumer not covered by the forbidden-PID list below.

---

## 1. OOM / skip history (mok-tua + control)

**Primary test origin:** `~/mok-tua` (motion matrix, model-pull recheck, HANDOFF/PROVENANCE, Comfy API pins under `workflows/`). Control-plane stamps live in `~/grokcode/data/catalog/`. Residual multi-tool VRAM (Frame-Pack / facefusion / maestro) is a **separate** class — do not collapse mok-tua model OOMs into “the other tools were running.”

### Confirmed generative OOM (mok-tua lab)

| Case | Evidence | Class |
|------|----------|-------|
| **Qwen Image Edit 2509 KSampler** | mok-tua `docs/operations/MODEL_PULL_RECHECK_VIDEO_ROBUST_2026-08-06.md` · `docs/assets/capabilities/manager-pivot/PROVENANCE.json` · HANDOFF · motion `M7` · SESSION_HANDOFF 0.5.10 | **`model_settings`** — fp8 edit + VL TE (+ LoRAs) peak exceeds 16 GB even with Comfy `--lowvram`, 256–768². **This is the main historical OOM stamp from mok-tua tests.** |
| **MiniMax H3 low-MP KSampler (2026-08-07)** | mok-tua pin `workflows/minimax_h3_t2v_low_mp.api.json` · stamp `grokcode/data/catalog/mok_tua_h3_low_mp_smoke_2026-08-07.json` | **`model_settings`** — **clean gate 540 MiB**, zero forbidden PIDs; loaders+cond OK; **OOM at KSampler** peak **~15913 MiB** (480² · 22f · 8 steps). Proves H3 footprint under exclusive gate, not multi-tool. |

**Law:** do **not** hammer Qwen Edit full sampling on mrgpu until a proven lower-VRAM pack or larger GPU.  
**H3:** next try `--lowvram` exclusive Comfy restart + CPU TE / tinier canvas; do not reclassify as multi-tool.

### Not OOM — version / nodes / pins / inventory (mostly mok-tua motion matrix)

| Case | Result | Cause |
|------|--------|-------|
| **MiniMax H3** motion `M6` | `SKIP_COMFY_LT_0.30` | Comfy **0.29** lacked native `MiniMaxH3*`; weights missing pre–FluxDown; API pin may still be absent |
| **WAN 2.2 generative** `M2` | inventory pass only | Weights present; Lightning/dual-noise **API pin** pending |
| Wan Gradio ports | skip | ports down |
| InstantID / FaceID | residual | incomplete models |

### Passed (modest VRAM) — mok-tua smokes that did fit 16 GB

| Case | Notes |
|------|-------|
| AnimateDiff sizzle | ~3.3–3.5 GiB · Comfy 0.29 |
| DreamShaper stills | ~2.5–3.5 GiB |
| FramePack CEO I2V | ~11–13 GiB peak · receipt under mok-tua `docs/assets/receipts/` |
| comfy robust 2026-08-02 | fail=0 on 0.29 |

### Multi-tool saturation (precondition risk — not mok-tua model OOM)

| Event | Evidence |
|-------|----------|
| Stage director cleanup | **3357 → 766 MiB** after stop Frame-Pack / facefusion / maestro + Comfy `POST /free` |
| Live clean baseline (2026-08-07 session) | ~**540 MiB** used · Contenders stopped |
| Post-H3 residual | ~**8 GiB** still held after `/free` — Comfy restart recommended before WAN/InfiniteTalk |

**How to read “OOM history”**  
- **mok-tua tests** produced the real generative OOMs (Qwen Edit; later H3 under clean gate) and most SKIP taxonomy (Comfy version / pins / inventory).  
- Older Comfy **blocked H3** (skip), did not fake an H3 OOM.  
- Concurrent tools can inflate VRAM and **mis-label** a later run as model OOM — always gate.  
- Residual after mok-tua/Comfy jobs can also look like “history of OOM” until restart.

---

## 2. `oom_class` taxonomy (required on every smoke stamp)

| Value | Meaning |
|-------|---------|
| `none` | Success under gate |
| `model_settings` | Clean GPU pre-submit; peak still OOMs (MP/frames/quant) |
| `multi_tool_saturation` | Pre-submit VRAM high or forbidden PIDs present |
| `version_or_missing_nodes` | Comfy/nodes too old or missing (e.g. H3 on 0.29) |
| `missing_weights` | Pool file absent |
| `unknown` | Cannot classify |

Stamp fields: `gpu_mib_before_submit` · `gpu_mib_peak_during` · `gpu_mib_after_free` · `forbidden_pids_*` · `oom_class`.

---

## 3. Clean-GPU gate (hard)

### 3.1 Targets

| Metric | Prefer | Hard abort |
|--------|--------|------------|
| `nvidia-smi memory.used` | ≤ **800 MiB** | > **2048 MiB** |
| Forbidden PIDs | zero | Frame-Pack · facefusion · `demo_gradio` · Maestro heavy · **PMB embed-queue drain / `pmb reindex`** (see §3.5) |
| Comfy queue | empty | other jobs running |
| Models | unloaded | skip `/free` before submit |

### 3.2 Preflight (mrgpu)

```bash
ssh -o BatchMode=yes mrgpu 'bash -s' <<'EOF'
set -euo pipefail
pkill -f 'demo_gradio|Frame-Pack|facefusion' 2>/dev/null || true
curl -sS -X POST http://127.0.0.1:8188/free \
  -H 'Content-Type: application/json' \
  -d '{"unload_models":true,"free_memory":true}' || true
sleep 2
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
pgrep -af 'Frame-Pack|facefusion|demo_gradio|maestro' || echo no_forbidden_pids
pgrep -af 'pmb.*(reindex|watch|consolidate)|embed_queue' || echo no_pmb_embed_drain
free -h | head -2
curl -sS http://127.0.0.1:8188/system_stats | python3 -c \
  'import sys,json;d=json.load(sys.stdin);dev=d["devices"][0];print("comfy",d["system"].get("comfyui_version"),"vram_free",dev.get("vram_free"))'
EOF
```

### 3.3 Keep vs stop during exclusive window

| Keep | Stop |
|------|------|
| Comfy `:8188` (single job) | Frame-Pack Gradio |
| Headroom `:8787` · LiteLLM `:4000` (no heavy gen) | facefusion |
| Ollama **9b coding pin only** or unloaded | Maestro · concurrent second video · Qwen Edit full |
| Directors Console **if not loading models** | Any second Comfy queue |
| PMB keyword search / normal MCP reads | **PMB embed-queue drain, `pmb reindex`, `pmb watch --once`** (see §3.5) |

### 3.4 Between families

`POST /free` → re-check gate → next family (H3 → WAN Lightning → InfiniteTalk).

### 3.5 PMB embed-queue interlock (added 2026-08-10)

PMB's production embedder is **not** behind LiteLLM/Headroom — it calls Ollama `bge-m3`
directly on mrgpu (`embedding.ollama_model`, switched from `nomic-embed-text-v2-moe`
2026-08-10; see `grokcode/docs/operations/CLI_AGENT_STATUS_CONSOLIDATED_2026-08-10.md`).
The durable embed queue (`pmb/core/embed_queue.py`) drains pending rows via a background
worker thread making one HTTP embed call per event — at the observed **~240ms/event**
rate a large backlog (the 2026-08-10 pass left ~115K events unembedded) is a **multi-hour**
job that will contend for mrgpu GPU/VRAM exactly like a second generative job would.

**Rule:** treat an active PMB embed-queue drain or `pmb reindex` the same as Frame-Pack/
facefusion — it must be stopped (or simply not started) before declaring the gate clean,
and must not be kicked off (manually, via `pmb watch`, or via a scheduled consolidate)
during an exclusive video window. Check with the `pgrep` line added to §3.2 before every
submit; if it hits, stop the drain, `sleep 2`, re-run the gate.

---

## 4. Storage plane — avoid OOM via multi-path (not multi-tool)

| Mount / path | Role | Use for | Do not |
|--------------|------|---------|--------|
| **`/mnt/ai-data`** (NFS · Tower SSOT · ~3.7 TiB) | Canonical **weights** · workflows · work outputs | Comfy models · promote destination · shared smokes | unbounded `find`; Mac multi-GB HF write |
| **`/` host SSD** (`/dev/sda3` · ~431 G · ~170 G free class) | OS · services · small scratch | Comfy venv already on ai-data envs preferred | dump multi-GB weights here |
| **`/MCP_WIP`** (local SSD role · same host disk class / reclaim target) | **Runtime cache · LLM offload · UV/HF scratch · Ollama local cache** | `OLLAMA_MODELS` overflow · HF cache when NFS laggy · Pinokio-runtime · comfy runtime scratch | treat empty `Models/` stubs as pool; permanent weight SSOT |
| **`/mnt/ai-data/hf-cache`** · **`uv-cache/mrgpu`** | Preferred pool-adjacent caches | Downloads that promote into models/ | Pinokio app-local multi-GB trees |

### 4.1 48 GiB RAM + 16 GB VRAM orchestration rules

- **Video gen:** exclusive GPU; TE/block-swap/offload to **system RAM** then spill sequential to **local SSD** (`/MCP_WIP/scratch` or ai-data work) — never concurrent Frame-Pack.  
- **Image gen:** same gate; Qwen Edit full remains **PAUSED**.  
- **Audio / lipsync:** LivePortrait/wav2vec after video unload.  
- **Local LLM:** coding pin `qwen3.5:9b` OK light concurrent; **14B+** only when video idle; **27B/30B never default**.  
- **Bleeding-edge LLM pulls:** stage blobs on **`/MCP_WIP`** or host-local first if NFS write contention; promote GGUF into `/mnt/ai-data/models/llms/…` when stable; Ollama `num_gpu` / layer offload + `num_ctx` caps for 48 GiB available RAM.

### 4.2 Suggested env (mrgpu agent profile)

```bash
# weights SSOT
export COMFY_MODEL_ROOT=/mnt/ai-data/models
# local SSD leverage (LLM / cache / scratch)
export MCP_WIP_ROOT=/MCP_WIP
export HF_HOME=${HF_HOME:-/mnt/ai-data/hf-cache}
export UV_CACHE_DIR=${UV_CACHE_DIR:-/mnt/ai-data/uv-cache/mrgpu}
# optional local overflow (create dirs if reclaim complete)
# export OLLAMA_MODELS=/MCP_WIP/ollama/models   # only if intentionally host-local
# export TMPDIR=/MCP_WIP/scratch/tmp
```

Reclaim note: large `pinokio.local-bak-*` on `/MCP_WIP` is reclaim candidate after verify vs ai-data pinokio (see `grokcode/docs/operations/MCP_WIP_AND_SOVEREIGN_COMFY.md`).

---

## 5. FluxDown priority (video · LoRAs · DC styles · then LLM)

**Plane:** Tower FluxDown `:17800` · throttle **40 MiB/s** · `max_concurrent=1` · promote → `/mnt/ai-data/models/…`

| Pri | Class | Examples | Why first |
|-----|-------|----------|-----------|
| **P0** | Small DC style / face LoRAs + LivePortrait | `bfs_head_v5_*` · LivePortrait Kijai pack | Unblocks Director’s Console prefill / style grabs · minutes not hours |
| **P0** | Smoke-critical video already in pool | H3 core pack · WAN 2.2 · Lightning LoRAs · InfiniteTalk patch | **Check present** before re-queue |
| **P1** | MimicMotion body | MimicMotion fp16 pack | DC motion prefill |
| **P1** | H3 R2V (optional) | `minimax_h3_ref2va_*` | After T2V/I2V low-MP green |
| **P2** | FireRed edit · Qwen Edit 2511 | large fp8 | DC image edit — **sampling still 16 GB risk** |
| **P3** | Bleeding-edge **local** LLMs (MoE A3B / small high-ctx) | staged ollama plan · LMS GGUF | Only after video exclusive window free; prefer **MCP_WIP / host-local** then promote |
| **Never day-0 on 16 GB** | Inkling-Small / DeepSeek-V4-Flash full · 70B+ dense | high-RAM multi-GPU class | |

Always: **model check (ls + size + hash if custody)** before FluxDown re-download.

---

## 6. LiteLLM audit law (all orchestrators)

```text
CLI / mok-tua / tok-tua / grok-tua / Herdr / Turnstone
  → Headroom :8787
  → Orchestrator :8790 (when present)
  → worker LiteLLM :4000
```

- No direct Anthropic/OpenAI/OpenRouter base from agents for production traffic.  
- PHI: local only (`manager-phi-local`); paid cloud aliases **forbidden** for PHI.  
- Coding pin mrgpu: `qwen3.5:9b` — never silent fallback to 27B/30B.

---

## 7. Hippo / handoff citations

When compacting or starting a new chat, cite:

- this file (path above)  
- `mok-tua` HANDOFF + PROVENANCE for Qwen OOM  
- `grokcode/data/catalog/*smoke*` stamps for machine evidence  

Do **not** paste full burn transcripts. `HIPPO_CONTEXT_CITATIONS_ONLY=1` when appropriate.

---

## 8. Success for a smoke window

1. Pre-submit ≤ ~800 MiB · no forbidden PIDs · **no PMB embed-queue drain running** (§3.5).  
2. Single family job · stamp with `oom_class`.  
3. `/free` · idle again before next.  
4. FluxDown P0 style/LoRA checks done or queued with throttle.  
5. LLM spikes only after video window closed or on desk Metal path.
