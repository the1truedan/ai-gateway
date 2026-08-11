# NeMo Switchyard — staged, smoke-tested, not wired into production

**Status:** proven working standalone. Not load-bearing for any live traffic yet — see "Next step, not done here" below.

## What this is

[NVIDIA-NeMo/Switchyard](https://github.com/NVIDIA-NeMo/Switchyard) (Apache 2.0, pre-alpha) is a model-routing layer with dynamic escalation: every conversation starts on a cheap "weak" tier, an LLM judge watches the trajectory each turn, and on a clear pattern of trouble it latches the conversation to a "strong" tier for the rest of the task. This is genuinely new capability for this stack — confirmed by reading `services/orchestrator/app.py` directly: `decide()` today is a static alias→host mapping with zero retry/escalation logic.

Full recon + verification: `../grokcode/docs/roadmap/MANAGER_SWITCHYARD_MODEL_RECON_REVIEW_2026-08-11.md`.

## Install (the README's documented command is incomplete)

```bash
uv tool install --python 3.12 --with pyyaml --with uvicorn --with fastapi "nemo-switchyard[cli,server]"
```

NVIDIA's own README says `uv tool install --python 3.12 "nemo-switchyard[cli]"` — that installs the CLI but not the `serve` subcommand's actual runtime. Confirmed by hitting it live: `serve` failed three times in a row with `ModuleNotFoundError` (`yaml`, then `uvicorn`, then `fastapi`) before `[cli,server]` (an extra not mentioned in the README) pulled in the real dependency set (`fastapi`, `starlette`, `sse-starlette`, `uvloop`, `websockets`, `python-dotenv`). Consistent with the project's own "pre-alpha, expect rough edges" framing — not a dealbreaker, just don't copy the README command verbatim.

## Config: `config/switchyard/manager-code.escalation.yaml`

Fully local, zero cloud keys — proves the mechanism works before any cost/cloud-routing question comes up:

```yaml
routes:
  manager-code:
    type: escalation_router
    weak:
      model: qwen3.5:9b          # mrgpu, existing daily coding pin
    strong:
      model: qwen2.5-coder:14b   # mrgpu, existing local model
    judge:
      model: qwen2.5-coder:14b   # non-thinking judge — see gotcha below
    fallback_target_on_evict: weak
```

## Smoke test — real, not just "it started"

```bash
switchyard serve -c config/switchyard/manager-code.escalation.yaml --host 127.0.0.1 --port 4321 --inbound openai
curl -s http://127.0.0.1:4321/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"manager-code","messages":[{"role":"user","content":"hi"}],"max_tokens":20}'
```

`GET /health` → `{"status":"ok"}`. A real chat completion round-tripped and correctly landed on `qwen3.5:9b` — the weak tier, exactly right for a fresh conversation before the judge has had a turn to evaluate anything.

**Gotcha caught live:** that first response had empty `content` with a `reasoning` field and `finish_reason: length` — the already-documented hybrid-reasoning completion-budget bug (`qwen3.5:9b` burns a small `max_tokens` ceiling on its internal thinking preamble). Not a Switchyard bug; it's the same gotcha already on file for PMB's local-LLM calls. Means any real weak-tier config using a thinking model needs either a larger `max_tokens` or the `think:false` passthrough, same as everywhere else this project talks to thinking models.

## Next step, not done here

This config is proven correct in isolation. Wiring it in for real means deciding **whether it replaces `tok_tua/saturation_router.py` / `scripts/saturation_monitor.py`** (both fixed to work today, but doing a much simpler job — a static latency threshold, not judge-based escalation) — that's a real architectural call about production routing behavior, made deliberately, not as a side effect of a staging pass.
