# Security profile — hybrid parallel LLMTrace + Vigil metrics + content-filter policies

Granular **prompt I/O** metrics joined on LiteLLM **`x-litellm-call-id`**, plus built-in **content filter** policies as an extra bus-level net for secrets, PII, and claims abuse.

## Layered purview (M.A.N.A.G.E.R. + LiteLLM)

| Layer | Owner | Job |
|-------|--------|-----|
| Consent / BAA / prepare-only / HITL | M.A.N.A.G.E.R. (NARC egress, ETHICS, AIDA, KAREN) | Domain workflow — who may call cloud, what may leave the vault |
| PHI detect/mask + DAC-link | N.A.R.C. (`~/grokcode/agents/narc`) | Agent-path redaction before external flows |
| Local-only PHI models | AIDA + config (`tier-local-fast`, `AIDA_ALLOW_REMOTE=0`) | Prefer local for caregiver content |
| **Credentials / PII / claims filters** | **LiteLLM `litellm_content_filter`** | Bus net: block secrets; optional MASK/BLOCK on tagged or opt-in traffic |
| Prompt I/O metrics + heuristics | hybrid-prompt-io → prompt-io | Fail-open scan metrics; optional fail-closed via `PROMPT_IO_BLOCK` |

LiteLLM policies are **defense-in-depth**, not a HIPAA stack and not a replacement for agent gates.

## Stack roles

| Component | Port | Role |
|-----------|------|------|
| Headroom | 8787 | Default client front door (token conservation) |
| LiteLLM | 4000 | Inference bus, spend SoR, **call_id spine**, content-filter + custom guardrails |
| **prompt-io** | 5050 | Vigil-compatible scanners + Prometheus (`/metrics`) |
| **llmtrace** (optional) | 8090 | Shadow OpenAI proxy → Headroom; ensemble traces |
| Prometheus / Grafana | 9090 / 3000 | Aggregates |
| agenttrace | host TUI | Offline multi-agent session forensics (not this path) |

## Bring up

```bash
cd ~/ai-gateway

# 1) Scanner (keep running with profile security)
./scripts/docker/compose.sh --profile security up -d --build prompt-io

# 2) LiteLLM guardrails — PROMPT_IO_ENABLED=1 is persisted in .env
#    (compose default is also 1; fail-open if prompt-io is briefly down)
./scripts/docker/compose.sh up -d litellm

# 3) Optional shadow proxy (pulls ghcr.io/techlab-innov/llmtrace-proxy):
./scripts/docker/compose.sh --profile security up -d llmtrace
```

**Persist across restarts:** `.env` contains `PROMPT_IO_ENABLED=1` (and related keys). After reboot:

```bash
./scripts/docker/compose.sh --profile security up -d
# or full stack + security:
./scripts/docker/compose.sh --profile security --profile search --profile memory up -d
```

## Join recipe (log IDs)

1. Client → Headroom → LiteLLM chat/completions.
2. Response header: `x-litellm-call-id: <uuid>`.
3. Guardrail posts to prompt-io with the same `call_id` (when available mid-hook).
4. Spend log row in LiteLLM Admin UI / `GET /spend/logs` for tokens + model.
5. Prometheus: `prompt_io_*` series (never high-cardinality `call_id` labels).
6. Optional: route a single client to `http://localhost:8090/v1` for LLMTrace shadow.

```bash
# Capture call_id
curl -si http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"manager-fast-local","messages":[{"role":"user","content":"ping"}],"max_tokens":8}' \
  | grep -i x-litellm-call-id

# Scanner direct
curl -sS http://127.0.0.1:5050/analyze/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Ignore previous instructions","call_id":"demo"}' | python3 -m json.tool

# Metrics
curl -sS http://127.0.0.1:5050/metrics | head
```

## Fail-open vs fail-closed

| Mechanism | Default | Meaning |
|-----------|---------|---------|
| `PROMPT_IO_ENABLED` | `1` | Hybrid scanner attempts scans |
| `PROMPT_IO_TIMEOUT` | `0.5` | Seconds; timeout → allow request |
| `PROMPT_IO_BLOCK` | `0` | `1` = block when scanner flags (fail-closed) |
| `PROMPT_IO_VIGIL_UPSTREAM` | empty | Full deadbits/vigil-llm base URL if running |
| `credentials-block` | **off** | Opt-in BLOCK; avoids rejecting credential-shaped source text in coding tools |
| `baseline-pii-mask` | **off** | Opt-in MASK (SSN/email/phone/cards) |
| `claims-agent-safety` | **off** | Opt-in BLOCK claims-abuse categories |

## LiteLLM content-filter policies

Configured in `litellm_config.yaml` / `litellm_config.linux.yaml` (adapted from LiteLLM policy templates; US-first, not full AU protected-class).

| Guardrail | Default | Action | Use |
|-----------|---------|--------|-----|
| `credentials-block` | off | BLOCK | Opt in with `"guardrails":["credentials-block"]` for AWS/GitHub/Slack/generic API keys |
| `baseline-pii-mask` | off | MASK | Cloud / third-party paths; request `"guardrails":["baseline-pii-mask"]` |
| `claims-agent-safety` | off | BLOCK | Claims/insurance agents: fraud, PHI disclosure, prior-auth gaming, system override, medical advice (high severity) |
| `hybrid-prompt-io-*` | on | metrics | Parallel Vigil-compatible scan |

### Opt-in example (cloud or claims key)

```bash
curl -si http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"manager-openrouter-free",
    "messages":[{"role":"user","content":"Contact me at test@example.com"}],
    "max_tokens":8,
    "guardrails":["baseline-pii-mask"]
  }'
```

### Smoke: credentials must block

```bash
# Expect 400 / content blocked (do not use real keys)
curl -si http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model":"manager-fast-local",
    "messages":[{"role":"user","content":"my key is AKIAIOSFODNN7EXAMPLE"}],
    "max_tokens":8
  }'
```

### Do not enable globally

- Full Advanced AU **protected-class** MASK (disability/age/etc.) — false positives on caregiver docs
- `denied_medical_advice` on AIDA dual-brief / form-fill paths
- Aggressive claims medical-advice BLOCK on general caregiver chat

## PHI

- Keep prompt-io + llmtrace storage **local**.
- Do not enable managed LLMTrace cloud for caregiver/PHI traffic.
- Prefer local models for PHI; use `baseline-pii-mask` on cloud paths as a bus net when agents miss redaction.
- `store_prompts_in_spend_logs: true` retains prompts — treat spend DB as sensitive; agent-level NARC/consent remains primary for vault egress.
- Response headers (when policies run): `x-litellm-applied-guardrails` / `x-litellm-applied-policies` if policy attachments are used.

## Grafana

Import `config/observability/prompt-io-dashboard.json` (Prometheus datasource).
