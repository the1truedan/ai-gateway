# Manager Orchestrator

Privacy-first OpenAI-compatible dispatcher running on mac-client for mac-client, gpu-host,
and NAS-HOST workers.

Public endpoints:

- `GET /healthz`, `GET /readyz`
- `GET /v1/models`
- `POST /v1/router/decision` (dry decision, no inference)
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /metrics`

`role-auto` classifies task type and selects a local host. Sensitive prompts are
rewritten to `role-phi-local` and cannot use cloud aliases. Selecting
Selecting `tier-codex-cloud`, `tier-mimo-cloud`, or `tier-grok-cloud` is an
explicit paid-use approval signal. Automatic routing stops with
`cloud_consent_required` after all suitable local hosts are unavailable. The
recommended escalation order is Codex, Gemini, OpenRouter free, MiMo, then
Grok; the orchestrator reports that order but never performs the cloud hop
automatically.

The service merges `manager_route_id`, selected host/model, and tier into caller
metadata so Mac LiteLLM spend rows can be joined to routing decisions. It logs
route metadata and a short request hash, never the prompt or response body.
