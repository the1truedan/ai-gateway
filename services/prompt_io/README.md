# prompt-io-scanner

Vigil-compatible prompt/response scanner for **granular prompt I/O metrics**, joined on LiteLLM `x-litellm-call-id`.

## Role

| Layer | Job |
|-------|-----|
| LiteLLM | Spend SoR + `call_id` spine |
| This service (`:5050`) | Parallel scan + Prometheus metrics (heuristics; optional full Vigil forward) |
| LLMTrace (optional shadow) | Opt-in proxy lane for deeper ensemble traces |
| agenttrace | Offline multi-agent session forensics (unchanged) |

## Endpoints

- `GET /health`
- `GET /metrics` — Prometheus
- `POST /analyze/prompt` — body: `{ "prompt", "call_id?", "model?" }`
- `POST /analyze/response` — body: `{ "prompt", "response", "call_id?", "model?" }`
- `GET /settings`

## Compose

```bash
./scripts/docker/compose.sh --profile security up -d --build prompt-io
```

Optional full Vigil upstream:

```bash
export PROMPT_IO_VIGIL_UPSTREAM=http://host.docker.internal:5000
```

## PHI

Local-only. Do not point managed cloud sinks at this scanner. Fail-open by design for the LiteLLM guardrail.
