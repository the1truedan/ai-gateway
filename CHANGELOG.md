# Changelog

All notable changes to **ai-gateway** are documented here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/). Dates are local lab (America/New_York context).

Commits before this file existed predate versioning and aren't individually
back-filled here — `git log` is authoritative for that history. This starts
the tracked record going forward.

## [0.1.0] — 2026-08-11

First versioned release.

### Added

- **PMB** documented alongside hippo-memory in the architecture README:
  per-project semantic memory via local code/doc indexing + embedding
  (`docs/PMB_AGENT_MEMORY_AND_MODEL_STAGING.md`), including the
  workspace-isolation gotcha (a saved global default silently outranks
  cwd-based auto-detection unless a project pins itself explicitly).
- Model-staging lessons doc: FluxDown container bind-mount path gotcha,
  Civitai `?token=` vs `&token=` gotcha, don't-trust-secondary-source-model-names,
  in `docs/PMB_AGENT_MEMORY_AND_MODEL_STAGING.md`.
- `manager-worker-mrgpu-deepseek-reason` and `manager-test-*` opt-in local
  model tiers documented in `config/clients/RUNBOOK.md`.
- New local model aliases in `litellm_config.yaml`: `manager-codex-paid`,
  `manager-openai-paid`, `manager-openai-mini-paid`, `manager-claude-paid`,
  `manager-claude-opus-paid`, `manager-claude-haiku-paid`,
  `manager-openrouter-hc`.
- `deploy/agentsview/` compose profile, `services/agentsview/` service.
- `tok_tua/agentic_handoff.py`, `tok_tua/saturation_router.py`.
- `docs/PROVIDER_CREDIT_STATUS.md`, `docs/operations/MRGPU_GPU_EXCLUSIVITY_SMOKE_RUNBOOK_2026-08-07.md`.
- CI smoke workflow + `docs/PUBLIC_SECURITY_AND_SMOKE.md` (merged from upstream).

### Changed

- **hippo-memory diagram** made explicit: Claude Code, Codex, Grok Build, and
  Cursor all read/write the *same* per-repo `.hippo/` store — that sharing
  is the cross-agent handoff, previously implicit rather than diagrammed.
- **Prompt-I/O**: added an honest gap note. It's telemetry only today — scan
  results (injection/PII flags) don't yet feed back into routing decisions.
  Documented as real future work, not implied as already closed.
- **Storage plane**: added FluxDown, the rsync promote step, and Johnny
  Appleseed/CHIPPER/CHAINS (model-pool cataloging + dedup-job scheduling +
  custody receipts — generic infra role only) alongside bees, which stays
  the underlying physical (L3) dedup layer.
- Coding-pin routing (`services/orchestrator/app.py`): coding/execute/review/
  plan roles now prefer `gpu-host` first with no score-based shuffle, closing
  a gap where a dipping GPU score could silently place coding work on
  `mac-client` and risk loading an oversized Ollama tag there.
- `.env.example`: split `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` from new
  `OPENAI_CLOUD_API_KEY`/`ANTHROPIC_CLOUD_API_KEY` so a client's
  `OPENAI_API_KEY` can stay pointed at the local LiteLLM master key without
  colliding with the real paid cloud key.

### Fixed

- `.mcp.json` untracked in favor of a sanitized `.mcp.json.example` — the
  tracked file had picked up a live local PMB bearer token in its working-tree
  diff. Confirmed via full git history search (`git log -S`, all branches,
  local + both remotes) that the token was never actually committed or
  pushed anywhere before this fix landed.

### Docs

- `docs/UPDATE_SUMMARY.md` — OpenRouter free-model catalog sync + provider
  credit availability check summary.
- AgentsView added to the Optional profiles table in the README.
