# Changelog

All notable changes to **ai-gateway** are documented here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/). Dates are local lab (America/New_York context).

Commits before this file existed predate versioning and aren't individually
back-filled here — `git log` is authoritative for that history. This starts
the tracked record going forward.

## [0.2.4] — 2026-08-16

### Added

- Pages: **AgentsView**, Open WebUI, Hister, botmem, orchestrator, grok-tua/tok-tua
  as a second “around the door” row. AgentsView is a standalone stack so the
  session index can stay up when the chat bus is down.

## [0.2.3] — 2026-08-16

### Added

- Pages one-pager now credits **hippo-memory** (per-repo agent recall) and
  **PMB** (per-project indexed memory). Both were already in the stack map.

## [0.2.2] — 2026-08-16

### Added

- **GitHub Pages** one-pager (`docs/index.html`): gateway-themed sibling to
  mok-tua / fast-models. Headroom, LiteLLM, OpenRouter, and Grok get the
  credit they earned. Origin story in plain language.
  Live: [the1truedan.github.io/ai-gateway](https://the1truedan.github.io/ai-gateway/)

### Fixed

- Unraid fast-models persist hook docs: `/boot/config/go` must invoke
  `host-nfs-export.sh` with `bash`. FAT32 has no execute bits; a bare path
  prints Permission denied and leaves host nfsd down.

## [0.2.1] — 2026-08-12

### Fixed

- **Hister corpus-push automation** (`launchd com.manager.hister-corpus-push`,
  every 6h): had been silently failing since 2026-08-01 — the public-release
  sanitization commit (`abeca24`) stripped
  `scripts/history/push_hister_corpus_to_tower.sh` and its two dependencies
  (`collect_browser_corpus.py`, `enrich_browser_corpus_md.py`) from HEAD
  without disabling the job. Recovered all three from git history
  (`43c3dca`), restored locally as gitignored files (not re-committed —
  same intent as the original sanitization). Backfilled the ~10-day gap:
  36,867 browser records (incl. 1,538 PasteBar links), 1,886 shell history
  rows, 80 Grok CLI session summaries.
- **`pyproject.toml` version** was still `0.1.0` despite `VERSION` and this
  file already reading `0.2.0` — synced to `0.2.1`.

### Added

- **`tower-hister`** brought back up on Tower via the existing
  `deploy/tower-orchestration/docker-compose.yml` service definition (its
  index data was intact — 1,474+ English-index documents alone — only the
  container itself was gone). Verified live via its MCP search endpoint.
- **`tower-open-webui`** brought up the same way. Imported grok.com history
  (512 conversations from the xAI `prod-grok-backend.json` export) and Grok
  Build CLI sessions (106 sessions from `~/.grok/sessions`) via
  `scripts/import/run_openwebui_import.sh --history --build`, applied
  natively against the live `webui.db` (stop → backup → `sqlite3` apply →
  restart, backups preserved on Tower).

## [0.2.0] — 2026-08-11

### Added

- **NeMo Switchyard staged and smoke-tested**: `config/switchyard/manager-code.escalation.yaml`
  (fully local escalation-router config, zero cloud keys) + `docs/SWITCHYARD_STAGING_2026-08-11.md`
  documenting the real packaging gaps found (`nemo-switchyard[cli]` per the
  upstream README is missing `pyyaml`/`uvicorn`/`fastapi` — `[cli,server]` is
  the actual working install) and a verified end-to-end smoke test (real
  chat completion, correctly routed to the weak tier). Not wired into
  production routing — a deliberate follow-up decision, not done here.
- `ccusage` (MIT, upstream) installed globally for local CLI-agent token/cost
  tracking across Claude Code, Codex, OpenCode, Grok Build, and others — reads
  existing on-disk logs only, no upload.

### Fixed

- `tok_tua/saturation_router.py` / `scripts/saturation_monitor.py`: both were
  non-functional as committed in 0.1.0. `get_saturation_status()` called
  `prometheus_client` internals that don't exist in the real API and always
  silently fell through to a hardcoded "never saturated" result;
  `check_saturation()` had a `dict + dict` line that would raise `TypeError`
  the moment it actually triggered; the monitor queried `localhost` instead
  of the Tower host where Prometheus runs, against a metric name and a
  `host=` label that were never real. Rewritten against
  `headroom_latency_ms_sum`/`_count` (confirmed live via direct Prometheus
  query — Headroom is the single front door for all traffic, so there's no
  per-host label to filter on, which is also why the original design's
  premise didn't hold). Both scripts now run clean and were verified against
  real generated traffic (7.84ms measured, not a stub value).

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
