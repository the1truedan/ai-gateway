# Runbook: point agents at AI-Gateway

## CLI / TUI Headroom routing inventory

Default conservation path: **`http://localhost:8787/v1`** (Headroom → M4
orchestrator → M4 LiteLLM → selected local worker).
Bypass / admin: **`http://localhost:4000/v1`** (raw LiteLLM).

| Client | Installed | Headroom path | How configured |
|--------|-----------|---------------|----------------|
| **Open WebUI** | yes | yes | Compose env + `webui.db` `openai.api_base_urls` → `headroom:8787/v1` |
| **pi** | yes | yes | `~/.pi/agent/models.json` → `ai-gateway.baseUrl` `:8787` |
| **omp** (Oh My Pi, brew) | yes | yes | `~/.omp/agent/models.yml` providers `litellm` + `ai-gateway` → `:8787` + discovery; needs `LITELLM_MASTER_KEY` in env |
| **OpenCode** | yes | yes | `~/.config/opencode/opencode.json` → `baseURL` `:8787` |

Coding clients should default to `role-auto`. The orchestrator automatically
chooses among gpu-host, mac-client, and NAS-HOST local models. If all suitable local hosts
are unavailable it returns `cloud_consent_required`; select a cloud alias
explicitly in this order: `tier-codex-cloud`, `tier-gemini-free`,
`tier-free-cloud`, `tier-mimo-cloud`, `tier-grok-cloud`. `role-phi-local` can
never cross the LAN boundary.
| **tau** | yes | yes | `~/.tau/providers.json` → `:8787` |
| **turnstone** | host config | yes | `~/.config/turnstone/config.toml` → `:8787` |
| **Herdr** | yes | yes (panes) | `config/herdr/layout.json` exports `OPENAI_BASE_URL=:8787`; usage pane = CLI spend tock |
| **aider** | yes | yes | `~/.aider.conf.yml` `openai-api-base: :8787` + `OPENAI_API_KEY` |
| **nono** | yes | sandbox ports | Profile opens **8787** + 4000 (not an LLM client itself) |
| **hermes** | yes | **yes** (local default) | `custom:ai-gateway` → `:8787`; `~/.hermes/.env` has `LITELLM_MASTER_KEY`; default `manager-fast-turbo` |
| **grok** (Grok Build) | yes | **env-only** | xAI default; Herdr **grok** pane sets `OPENAI_*` → Headroom when you use OpenAI-compatible mode |
| **cursor** | yes (CLI) | **not wired** | No project OpenAI base in Cursor User settings; configure custom OpenAI-compatible base to `:8787` in Cursor Settings if desired |
| **codex** | **not installed** | n/a | Install `@openai/codex` then point OpenAI base / provider at `:8787` |
| **claude** (Claude Code) | **not on PATH** | n/a | Optional: `ANTHROPIC_BASE_URL` only if using an Anthropic-fronted proxy (not this stack’s OpenAI path) |
| **agenttrace** | yes (`brew`) | n/a | Herdr **trace** pane; multi-agent session cost offline (not an inference router) |
| **gollama / collie** | earmarked / partial | n/a | Host TUIs; not inference routers |
| **jcodemunch-mcp** | yes (`uvx`) | n/a | MCP in OpenCode + `~/.config/mcp/mcp.json` (pi/omp) |
| **hister MCP** | profile `search` | n/a | Remote MCP `http://127.0.0.1:4433/mcp` (semantic on) |

### omp (Oh My Pi) quick use

```bash
set -a && source ~/ai-gateway/.env && set +a
export LITELLM_MASTER_KEY   # models.yml resolves this env name
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
export LITELLM_BASE_URL=http://localhost:8787/v1   # optional; models.yml overrides built-in :4000
omp models refresh
omp models ai-gateway          # should list manager-* / tier-*
omp --model ai-gateway/manager-fast-turbo
# or: omp --model litellm/manager-gemini-fast
```

Config file: `~/.omp/agent/models.yml` (repo-agnostic; re-run refresh after stack model changes).

### Shell env for any env-based CLI (Herdr panes already set this)

```bash
set -a && source ~/ai-gateway/.env && set +a
export OPENAI_BASE_URL=http://localhost:8787/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
export OPENAI_API_BASE="$OPENAI_BASE_URL"
export LITELLM_BASE_URL="$OPENAI_BASE_URL"
export LITELLM_API_KEY="$LITELLM_MASTER_KEY"
```

---

## Dual-head architecture

| Layer | Component | Where |
|-------|-----------|--------|
| **Agent head** | [Herdr](https://herdr.dev) | Host binary (`herdr status`) — multiplexes agent PTYs |
| **Token conservation** | Headroom | Docker `headroom-proxy` `:8787` (always-on) |
| **Inference head** | LiteLLM | Docker `litellm-proxy` `:4000` (bus + Admin UI) |
| **Chat surface** | Open WebUI | Docker `:8080` → Headroom → LiteLLM |
| **Spend / credits** | LiteLLM Admin UI | `http://localhost:4000/ui/login/` |
| **Mobile herd UI** | Collie | Host/Bun + Tailscale (optional) |

Herdr does **not** replace LiteLLM. Default path for agents and Open WebUI is **Headroom → LiteLLM**:

```bash
export OPENAI_BASE_URL=http://localhost:8787/v1   # Headroom (token conservation)
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"       # from ~/ai-gateway/.env
# Prefer: tier-local-fast | manager-fast-turbo | manager-fast-local
#          tier-local-reason | manager-reasoning-turbo | manager-reasoning-local
#          tier-gemini | manager-gemini-fast | manager-gemini-agent
#          manager-grok-coding | manager-openrouter-free | manager-embed
```

**Bypass** Headroom when you need raw LiteLLM (admin, embeddings, debug):

```bash
export OPENAI_BASE_URL=http://localhost:4000/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
```

## Prerequisites

- Docker stack healthy: `docker ps | grep litellm-proxy`
- **Shell** has master key: `set -a && source ~/ai-gateway/.env && set +a`  
  (Compose injects `.env` into containers only — not into your terminal. Empty `$LITELLM_MASTER_KEY` causes `401 Malformed API Key` / “Bearer prefix”.)
- Optional backends: Ollama `:11434`, TurboQuant coder `:8082`
- Agent head: `herdr status` → server running

### LiteLLM Admin UI (spend / request logs)

- Login: [http://127.0.0.1:4000/ui/login](http://127.0.0.1:4000/ui/login) (or `/ui/`)
- Username: `admin`
- Password: `$LITELLM_MASTER_KEY` (from `.env` — not Grafana’s password)
- After login, use the sidebar (SPA routes vary slightly by LiteLLM version):
  - **Logs** — per-request tokens / model / key / success·error ([UI Logs docs](https://docs.litellm.ai/docs/proxy/ui_logs))
  - **Usage / New Usage** — spend aggregates
  - **Virtual Keys** — key-level spend
- Optional API: `GET /spend/logs?limit=20` with `Authorization: Bearer $LITELLM_MASTER_KEY`
- Requires in-stack Postgres (`litellm-db`). Readiness should show DB connected:

```bash
curl -sS http://localhost:4000/health/readiness
# expect db connected (not "Not connected")
```

**Local models often show `$0.00` spend** (no price map) even when token counts are real — check **prompt/completion tokens** on Logs, not only dollars.

### call_id spine (prompt I/O join key)

Every LiteLLM completion gets a stable **`x-litellm-call-id`**. Use it to join:

| Store | What |
|-------|------|
| Response header `x-litellm-call-id` | Immediate client-side correlation |
| Admin UI **Logs** / `GET /spend/logs` | Tokens, model, spend, stored prompts |
| prompt-io scans (`metadata.hybrid_prompt_io`) | Security / entropy / PII heuristic hits |
| LLMTrace shadow (opt-in `:8090`) | Ensemble proxy traces |

```bash
set -a && source ~/ai-gateway/.env && set +a
curl -si http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"manager-fast-local","messages":[{"role":"user","content":"ping"}],"max_tokens":8}' \
  | grep -i x-litellm-call-id
```

### Hybrid parallel prompt I/O (Vigil + LLMTrace)

Granular prompt/response metrics without putting a second hard proxy on the default path.

```bash
# 1) Scanner + metrics
./scripts/docker/compose.sh --profile security up -d --build prompt-io

# 2) Enable guardrail HTTP from LiteLLM (fail-open, 0.5s timeout)
#    Add to .env:  PROMPT_IO_ENABLED=1
./scripts/docker/compose.sh up -d litellm

# 3) Optional LLMTrace shadow lane (NOT default for OWUI/agents)
./scripts/docker/compose.sh --profile security up -d llmtrace
# Client opt-in: OPENAI_BASE_URL=http://localhost:8090/v1

# 4) Prometheus scrapes prompt-io; import Grafana JSON:
#    config/observability/prompt-io-dashboard.json
```

| Port | Service |
|------|---------|
| 5050 | prompt-io (Vigil-compatible `/analyze/prompt` + `/metrics`) |
| 8090 | llmtrace-proxy shadow → Headroom |

- Full notes: `config/security/README.md`
- Guardrail code: `scripts/guardrails/hybrid_prompt_io.py`
- Full Vigil forward (optional): `PROMPT_IO_VIGIL_UPSTREAM=http://host:5000`
- Fail-closed only if needed: `PROMPT_IO_BLOCK=1`
- PHI: keep scanners/storage local; do not use managed LLMTrace cloud for caregiver data

### Open WebUI must use Headroom (DB overrides env)

Compose sets `OPENAI_API_BASE_URL=http://headroom:8787/v1`, but Open WebUI **persists** Admin → Connections settings in `webui.db`. If that row still points at `http://litellm:4000/v1`, chats **bypass Headroom**.

Check / fix:

```bash
docker exec open-webui python3 -c "import sqlite3; print(sqlite3.connect('/app/backend/data/webui.db').execute(\"select value from config where key='openai.api_base_urls'\").fetchone())"
# expect: ["http://headroom:8787/v1"]
```

Or in UI: **Admin → Settings → Connections → OpenAI API** → base URL `http://headroom:8787/v1` (key = `LITELLM_MASTER_KEY`).

### Headroom savings verification

```bash
curl -sS http://127.0.0.1:8787/readyz
curl -sS http://127.0.0.1:8787/stats | python3 -m json.tool | head -60
open http://127.0.0.1:8787/dashboard   # Headroom savings UI
# Response headers on chat/completions include:
#   x-headroom-tokens-before / x-headroom-tokens-after / x-headroom-tokens-saved
#   x-litellm-call-id  (proves request reached LiteLLM)
```

**Upstream must be LiteLLM, not Anthropic cloud.** Headroom keeps *separate* targets:

| Env | Protocol | Local-first value |
|-----|----------|-------------------|
| `OPENAI_TARGET_API_URL` | OpenAI `/v1/chat/completions` | `http://litellm:4000/v1` |
| `ANTHROPIC_TARGET_API_URL` | Anthropic `/v1/messages` | `http://litellm:4000` |
| `HEADROOM_NO_SUBSCRIPTION_TRACKING` | OAuth poller | `1` (disables `api.anthropic.com/api/oauth/usage`) |

If `/readyz` shows `"url": "https://api.anthropic.com"`, the Anthropic target was left at Headroom’s default (Claude Code path). That does **not** mean OpenAI clients were routed to Anthropic — but it *does* cause Anthropic-related health/log noise. Compose sets both targets to LiteLLM and disables the subscription poller.

```bash
# Prove OpenAI path → LiteLLM (look for x-litellm-call-id + x-headroom-tokens-*)
curl -si http://127.0.0.1:8787/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"manager-fast-local","messages":[{"role":"user","content":"ping"}],"max_tokens":4}' \
  | grep -iE 'x-litellm-call-id|x-headroom|x-litellm-model-api-base'
```

Compose wrapper (Mac/Linux overlays):

```bash
cd ~/ai-gateway
./scripts/docker/compose.sh up -d                       # LiteLLM + Headroom + Open WebUI
./scripts/docker/compose.sh --profile search up -d      # Hister :4433
./scripts/docker/compose.sh --profile memory up -d      # Botmem :12412
./scripts/docker/compose.sh --profile security up -d --build prompt-io  # prompt I/O metrics
./scripts/docker/compose.sh --profile import run --rm openwebui-importer --all
```

## 0. Herdr (agent head)

```bash
herdr status
herdr   # attach TUI

# Workspace cwd: ~/ai-gateway
# Layout + docs: config/herdr/
#   herdr.json   — workspace metadata
#   layout.json  — stack / usage / health / agent / grok panes
#   README.md    — dual-head notes + Collie security
```

Canonical env inside every agent pane (layout’s agent + grok panes set this):

```bash
set -a && source ~/ai-gateway/.env && set +a
export OPENAI_BASE_URL=http://localhost:8787/v1   # Headroom → LiteLLM
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
```

CLI spend/health (Herdr **usage** pane):

```bash
./scripts/usage_snapshot.sh
# USAGE_SNAPSHOT_INTERVAL=30 ./scripts/usage_snapshot.sh   # loop
```

Collie (phone UI): `~/GitHub/collie` — Tailscale **serve** only, never funnel. See Collie README.

## 1. Turnstone

```bash
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
mkdir -p ~/.config/turnstone
cp ~/ai-gateway/config/clients/turnstone.toml ~/.config/turnstone/config.toml
chmod 600 ~/.config/turnstone/config.toml

# CLI (from turnstone venv)
~/GitHub/turnstone/.venv/bin/turnstone \
  --base-url http://localhost:4000/v1 \
  --model manager-fast-turbo \
  --api-key "$LITELLM_MASTER_KEY" \
  --skip-permissions
```

Compose: set `LLM_BASE_URL=http://host.docker.internal:4000/v1`, dashboard `https://localhost:8443`.  
Avoid host `:8080` (Open WebUI) and remap SearxNG if `:8081` is TurboQuant orch.

## 2. Hister

```bash
# Preferred: join ai-gateway network with semantic search env
cd ~/ai-gateway
# If a standalone hister container already exists, stop it first:
#   docker stop hister && docker rm hister
./scripts/docker/compose.sh --profile search up -d
# UI: http://localhost:4433

# Or standalone from the pull:
#   cd ~/GitHub/hister && docker compose up -d
```

Semantic search defaults use LiteLLM `manager-embed`, which routes directly to
MRGPU Ollama nomic (768d). Headroom remains the chat/completions ingress and does
not proxy `/v1/embeddings`. To override the defaults explicitly, set:

```bash
export HISTER_EMBEDDING_ENDPOINT=http://litellm:4000/v1/embeddings
export HISTER_EMBEDDING_MODEL=manager-embed
export HISTER_EMBEDDING_API_KEY="$LITELLM_MASTER_KEY"
```

Snippet reference: `config/clients/hister.semantic_search.snippet.yaml`.  
MCP client snippets: `config/clients/hister.mcp.snippet.json` (OpenCode remote + shared `mcpServers`).

```bash
# MCP smoke (semanticSearchEnabled should be true in initialize result)
curl -sS -X POST http://127.0.0.1:4433/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
curl -sS -X POST http://127.0.0.1:4433/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

Registered on this Mac: OpenCode `mcp.hister` + user-global `~/.config/mcp/mcp.json` (pi-mcp-adapter).

**Shell history corpus (Atuin → markdown → Hister + OWUI KB):**

```bash
# Host capture (once): brew install atuin; eval "$(atuin init zsh)"; atuin import zsh
./scripts/history/export_atuin_for_kb.sh
# Hister mounts import-data/staging/dev-history (see config/hister/)
# OWUI: Workspace → Knowledge → dev-shell-history → Sync Directory → that folder
```

See `config/hister/README.md` and `config/clients/memory_map.md`.

## 3. Nono

```bash
brew install nono   # if needed
mkdir -p ~/.config/nono/profiles
cp ~/ai-gateway/config/nono/ai-gateway-agent.json ~/.config/nono/profiles/
nono run --profile ai-gateway-agent -- curl -sS http://127.0.0.1:4000/health/liveliness
```

## 4. Tau

```bash
# Merge ai-gateway provider (script or manual edit of ~/.tau/providers.json)
# Then:
export LITELLM_MASTER_KEY=...
tau   # select provider ai-gateway / model manager-fast-turbo
```

## 4b. Pi

Host config (already on this Mac):

- `~/.pi/agent/models.json` — provider `ai-gateway` → `http://localhost:4000/v1`
- `~/.pi/agent/settings.json` — `defaultProvider=ai-gateway`, `defaultModel=tier-local-fast` (or `manager-fast-turbo`)

Picker includes stable tiers (`tier-local-fast`, `tier-local-reason`, `tier-gemini`, `tier-free-cloud`, …), MLX/LMS, vision, Gemini, and high-value `or-free-*` aliases. Prefer gateway ids over direct Ollama when you want fallbacks + metrics.

**TurboQuant primary path:** `tier-local-fast` / `manager-fast-turbo` → host `:8082`; `tier-local-reason` / `manager-reasoning-turbo` → `:8081`. Start with `TURBOQUANT_PROFILE=coder|reasoning ./scripts/start_turboquant_server.sh` if you want the primary local-turbo backend. When Turbo is down, LiteLLM should fail over via `router_settings.fallbacks` (not a top-level `fallbacks:` key — ignored by LiteLLM 1.92+) to Ollama → Gemini → OpenRouter/xAI.

```bash
# apiKey in models.json must match LITELLM_MASTER_KEY from ~/ai-gateway/.env
pi   # model picker → ai-gateway / manager-fast-turbo or tier-local-fast
```

## 4c. OpenCode

```bash
# 1) Merge provider from repo snippet into ~/.config/opencode/opencode.json
#    (preserve existing mcp blocks)
#    config/clients/opencode.ai-gateway.snippet.json

# 2) Auth — store LiteLLM master key (do not commit):
#    ~/.local/share/opencode/auth.json
#    { "ai-gateway": { "type": "api", "key": "<LITELLM_MASTER_KEY>" } }
#    or use /connect in the TUI

# 3) Default model is ai-gateway/manager-fast-turbo
opencode models ai-gateway
opencode   # /models → AI Gateway (LiteLLM)
```

Direct OpenRouter / xAI / Ollama credentials can remain as escape hatches; default traffic should hit the gateway so fallovers and Prometheus apply.

Free OpenRouter compare guide: `config/clients/openrouter-free-models.md` (refreshed by `scripts/sync_openrouter_free_models.py`).

## 5. OpenWiki

If brew `openwiki` fails with missing `better-sqlite3` bindings:

```bash
cd /opt/homebrew/lib/node_modules/openwiki && npm rebuild better-sqlite3
```

`OPENAI_BASE_URL` must be set **in the shell** (it is ignored inside `~/.openwiki/.env`):

```bash
export OPENAI_BASE_URL=http://localhost:4000/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
export OPENWIKI_PROVIDER=openai
export OPENWIKI_MODEL_ID=manager-fast-local
export LANGSMITH_API_KEY=sk-local-disabled
export LANGCHAIN_TRACING_V2=false
openwiki -p "Summarize what you can do"
```

Optional: add a first-class `ai-gateway` provider via
`config/clients/openwiki.ai-gateway.provider.ts.snippet`.

## 6. Headroom (always-on token conservation)

Headroom starts with the core stack (`compose up -d`). Open WebUI uses `http://headroom:8787/v1` on the compose network.

```bash
# Host agents / Grok Build / pi:
export OPENAI_BASE_URL=http://localhost:8787/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
curl -sf http://127.0.0.1:8787/readyz
```

- Proxy-only (no qdrant/neo4j) — light on M4 24GB.
- Override OWUI base if needed: `OPENWEBUI_OPENAI_BASE=http://litellm:4000/v1` in `.env` then recreate open-webui.
- Spend/credits: LiteLLM Admin UI (Headroom shows compression savings, not $).

## 7. Memory layers (botmem + hippo)

**Dual SoR** — not either/or. Full map: `config/clients/memory_map.md`.

| Layer | SoR | Access |
|-------|-----|--------|
| Personal / life | **botmem** (profile `memory`) | UI `:12412`, CLI, optional MCP |
| Agent / coding | **hippo-memory** (host `.hippo/`) | `hippo` CLI + MCP |
| Search index | Hister | MCP `:4433/mcp` |
| Notes | Obsidian | mcp-obsidian when enabled |

### 7a. Botmem (personal memory — profile `memory`)

```bash
./scripts/docker/compose.sh --profile memory up -d
# UI: http://localhost:12412
# Postgres/Redis are internal to the compose network (not bound on host :5432/:6379)
```

Uses host Ollama for embed/text by default. Default embed model is aligned with stack nomic-v2-moe 768d (`BOTMEM_OLLAMA_EMBED_MODEL`). Change `BOTMEM_OLLAMA_*` / secrets in `.env` before real ingest.

```bash
npx botmem search "query" --json
npx botmem ask "question"
```

**Login:** email/password only (`authProvider: local`). Clear Brave site data for `localhost:12412` if SIGNING IN hangs. Stock `app-latest` is managed SPA; rewrite via `config/botmem/entrypoint.sh`.

### 7b. Hippo (agent memory)

```bash
npm install -g hippo-memory   # → often ~/.local/bin/hippo
cd ~/ai-gateway && hippo init
cd ~/grokcode && hippo init   # optional
hippo remember "lesson text" --tag architecture --pin
hippo recall "query" --json
# MCP stdio: hippo mcp  (OpenCode + ~/.config/mcp/mcp.json)
```

Snippet: `config/clients/hippo.mcp.snippet.json`. Local embeds by default — do not enable cloud embed keys unless intentional.

## 7c. jCodeMunch MCP (code symbols)

```bash
# Install is uvx-ephemeral; first call downloads wheel
uvx jcodemunch-mcp config --init   # ~/.code-index/config.jsonc
cd ~/ai-gateway && uvx jcodemunch-mcp index .
# Optional: cd ~/grokcode && uvx jcodemunch-mcp index .
uvx jcodemunch-mcp list-repos
```

Clients: OpenCode `mcp.jcodemunch`; shared `~/.config/mcp/mcp.json` for **pi** / **omp** (pi-mcp-adapter). Snippet: `config/clients/jcodemunch.mcp.snippet.json`.

## 7d. agenttrace (Herdr usage sibling)

```bash
brew install luoyuctl/tap/agenttrace
agenttrace -doctor
agenttrace   # TUI; Herdr layout pane label: trace
```

## 7e. mcp-obsidian (vault; optional)

Requires Obsidian **Local REST API** plugin + `OBSIDIAN_API_KEY`. Snippet: `config/clients/mcp-obsidian.snippet.json`. OpenCode entry exists with `enabled: false` until the key is set. Catalog split pattern (index notes + wikilinks) documented there and in `.agents/skills/obsidian-vault`.

## Tiered orchestration (plan vs execute)

**One-line rule:** *Local plans and executes by default; cloud requires explicit model selection; PHI never leaves local.*

**Recommended for new coding/tool sessions:** explicitly select `role-execute`.
Existing `manager-fast-turbo` / `tier-local-fast` defaults remain unchanged for compatibility.

Source: [Agentic Coding with Cloud Planning and Local LLM](https://grok.com/share/c2hhcmQtNA_d07d2ee7-9ae1-4418-820d-7ea7a41e17b4) (ACL sprint).
This is **role routing**, not only availability failover (`router_settings.fallbacks`).

| Role | Model id | Primary backend | Fallback policy |
|------|----------|-----------------|-----------------|
| **Plan** (architecture / design) | `role-plan` | local reasoning model | local only |
| **Recon** (research / analysis) | `role-recon` | local reasoning model | local only |
| **Execute** (coding / tools) | `role-execute` / `tier-execute-local` | TurboQuant coder `:8082` | local Ollama qwen |
| **Reason** (local orchestrate) | `role-reason` | TurboQuant gemma4 `:8081` | local Ollama gemma4 |
| **PHI / caregiver** | `role-phi-local` | Ollama qwen3.5:9b | **local only** (no cloud) |
| **Audit** (second opinion) | `role-audit` | local reasoning model | local only |

### Dual-call workflow (manual, zero new services)

```bash
cd ~/ai-gateway
set -a && source .env && set +a
export OPENAI_BASE_URL=http://localhost:8787/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"

# 1) Plan locally (select tier-codex-cloud explicitly only with consent)
curl -sS "$OPENAI_BASE_URL/chat/completions" \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"role-plan","messages":[{"role":"user","content":"Outline steps to add X"}],"max_tokens":512}'

# 2) Execute on local (implementation / tool loops)
curl -sS "$OPENAI_BASE_URL/chat/completions" \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"role-execute","messages":[{"role":"user","content":"Implement step 1 of the plan…"}],"max_tokens":1024}'
```

Smoke local-first roles (`role-phi-local`, then `role-execute`): `./scripts/smoke_role_tiers.sh`.
After verifying cloud credentials and accepting token use, add the cloud roles with
`INCLUDE_CLOUD_ROLES=1 ./scripts/smoke_role_tiers.sh`.

### Client recipes

| Pattern | What to pick |
|---------|----------------|
| Single-model agent (default) | Keep `manager-fast-turbo` / `tier-local-fast` (same as execute backend) |
| Explicit dual-role | Plan chat → `role-plan`; implement loop → `role-execute` |
| Caregiver / forms / AIDA | `role-phi-local` or `tier-local-fast` — **never** `role-plan` |
| Free recon / compare | `role-recon` or `manager-openrouter-free` |
| Second opinion (non-PHI) | `role-audit` / `manager-understand-audit` |

**Planner prompt (cloud):** Output a structured plan only; no file writes; strip PHI; ask for confirmation before execute.

**Executor prompt (local):** Implement approved plan steps with tools; prefer local context; refuse cloud escalate when content is caregiver/PHI.

### Policy matrix

| Content class | Plan step | Execute step |
|---------------|-----------|--------------|
| Engineering / non-PHI | `role-plan` local; explicit cloud alias optional | `role-execute` preferred |
| Caregiver / PHI / forms | **local only** (`role-phi-local`) | **local only** |
| Recon / research | `role-recon` local; explicit free-cloud alias optional | local summarize |

AIDA stays pinned to `AIDA_MODEL=role-phi-local`. Do not set AIDA to cloud roles.

### gpu-host NVIDIA + Codex cloud option

LAN clients can add `http://<gpu-host-ip>:8787/v1` as a second
OpenAI-compatible provider. On gpu-host, `role-execute` / `tier-nvidia-fast`
prefer the installed Qwen coder 14B on the RTX 4060 Ti, while
`role-reason` / `tier-nvidia-reason` prefer DeepSeek R1 14B. The optional
`tier-codex-cloud` route uses OpenAI GPT-5.6 Terra and requires
`OPENAI_API_KEY`; it is for non-PHI work only. Requests still pass through
Headroom and LiteLLM, so compression and LiteLLM usage logging remain visible.

For Codex CLI on gpu-host, keep the default provider unchanged and add a profile:

```toml
[model_providers.gpu_host_headroom]
name = "gpu-host Headroom → LiteLLM"
base_url = "http://localhost:8787/v1"
env_key = "LITELLM_MASTER_KEY"

[profiles.gpu-host]
model_provider = "gpu_host_headroom"
model = "role-execute"
```

Launch with `codex --profile gpu-host`. This compatibility path uses Chat
Completions; Codex documentation notes that Chat Completions provider support
is deprecated, so revisit it when Headroom supports the Responses API end to end.

---

## Preferred model roles

| Function | Model id | Backend |
|----------|----------|---------|
| **Plan (cloud)** | `role-plan` / `tier-plan-cloud` | Gemini 3.5 Flash |
| **Recon (free cloud)** | `role-recon` | OpenRouter free |
| **Execute (local)** | `role-execute` / `tier-execute-local` | TurboQuant `:8082` |
| **PHI local only** | `role-phi-local` | Ollama qwen (no cloud fallback) |
| **Audit (free)** | `role-audit` | Laguna / OpenRouter free |
| Fast coding (default agent) | `tier-local-fast` / `manager-fast-turbo` | TurboQuant `:8082` (Qwen) |
| Local only coding | `manager-fast-local` | Ollama `qwen3.5:9b` |
| Reasoning / orchestrator | `tier-local-reason` / `manager-reasoning-turbo` | TurboQuant `:8081` (Gemma4 12B) |
| Local reasoning | `manager-reasoning-local` | Ollama `gemma4:12b` |
| mrgpu deepseek reasoning (thinking model) | `manager-worker-mrgpu-deepseek-reason` | Ollama `deepseek-r1:14b`, mrgpu (2026-08-10) |
| mrgpu load-testing (opt-in, never a fallback target) | `manager-test-gpt-oss-20b` / `manager-test-qwen3-5-27b` / `manager-test-qwen3-coder-30b` / `manager-test-embed-bge-m3` / `manager-test-law-model` | Ollama, mrgpu — pulled-but-unproven models, added 2026-08-10; see `CLI_AGENT_STATUS_CONSOLIDATED_2026-08-10.md` |
| MLX fast (opt-in) | `tier-local-mlx` / `manager-mlx-fast` | LM Studio `:1234` `google/gemma-3n-e4b` |
| LMS general (opt-in) | `manager-lms-local` | LM Studio `:1234` `qwen/qwen3.5-9b` |
| LMS vision small (opt-in) | `manager-lms-vision` | LM Studio `:1234` `google/gemma-4-e4b` |
| Vision + tools (VLM chat) | `manager-vision-local` / `tier-local-vision` | Ollama `gemma4:12b` |
| Vision features (spatial CLS) | `manager-vision-embed` | FastAPI `:8791` (numpy/LingBot later) |
| Cloud vision (VLM) | `manager-gemini-vision` | Gemini 3.5 Flash multimodal |
| OCR | `manager-ocr-local` | Ollama `glm-ocr` |
| Greek translate | `manager-translate-el` | Ollama `translategemma:4b` |
| Llama A/B baseline | `manager-llama-local` | Ollama `llama3.1:8b` (optional pull) |
| Cloud chat / multimodal | `tier-gemini` / `manager-gemini-fast` | Google AI Studio **Gemini 3.5 Flash** (not 2.5 — blocked for new keys) |
| Cloud agentic tools | `manager-gemini-agent` | Gemini 3.5 Flash (tool-calling; stable agentic) |
| Cloud coding (paid) | `manager-grok-coding` / `tier-paid-cloud` | xAI Grok Code |
| Free remote | `manager-openrouter-free` / `tier-free-cloud` | OpenRouter free router |
| Long context free | `manager-big-context` | OpenRouter free Qwen coder (`or-free-qwen-qwen3-coder-free`) |
| Free audit / coding agent | `manager-audit-claude` / `or-free-poolside-laguna-*` | OpenRouter Laguna free |
| Free catalog guide | see `openrouter-free-models.md` | Synced free list + compare |
| Embeddings (text) | `manager-embed` | Ollama nomic-v2-moe |
| Vision **features** (not chat) | HTTP `:8791` — **not** LiteLLM | `services/vision_embed` FastAPI |

### Vision layers (do not conflate)

| Layer | Route / surface | Role |
|-------|-----------------|------|
| VLM chat + image | `manager-vision-local`, `tier-local-vision`, `manager-gemini-vision` | Image → text / tools (LiteLLM chat) |
| OCR / docs | `manager-ocr-local` | Layout → text; pair with OpenCV MCP preprocess |
| Text embeds | `manager-embed` | nomic (Hister / RAG) |
| **Vision embed / spatial** | `manager-vision-embed` (LiteLLM → `:8791`) | Image → feature JSON via chat facade or native `/v1/features` |

### manager-vision-embed (wired FastAPI)

Host (preferred on M4):

```bash
cd ~/ai-gateway
python3 -m venv services/vision_embed/.venv
source services/vision_embed/.venv/bin/activate
pip install -r services/vision_embed/requirements.txt
./scripts/start_vision_embed.sh
# stop: ./scripts/stop_vision_embed.sh
```

Optional compose: `./scripts/docker/compose.sh --profile vision up -d`

Smoke:

```bash
curl -sS http://localhost:8791/health
curl -sS -F "file=@/path/to.jpg" http://localhost:8791/v1/features
```

Default backend is **numpy** spatial patch stats (no LingBot weights). LingBot MLX / CoreML remain optional upgrades (`VISION_EMBED_BACKEND=external`).

**Via LiteLLM** (same OpenAI base as other models — use data-URL images):

```bash
set -a && source ~/ai-gateway/.env && set +a
# start vision-embed first: ./scripts/start_vision_embed.sh
curl -sS http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"manager-vision-embed","messages":[{"role":"user","content":"ping"}],"max_tokens":64}'
```

Assistant content is **JSON features** (CLS vector), not a natural-language caption — use `manager-vision-local` / `manager-gemini-vision` for VLM chat. Native feature API still at `http://localhost:8791/v1/features`. Docs: `services/vision_embed/README.md`.

### LM Studio / MLX (Mac host — opt-in)

```bash
cd ~/ai-gateway
set -a && source .env && set +a   # needs LM_API_TOKEN
./scripts/start_lmstudio_server.sh
./scripts/load_lmstudio_model.sh mlx-fast    # google/gemma-3n-e4b (~5 GB)
# or: lms-local | lms-vision | google/gemma-4-e2b

curl -sS http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"manager-mlx-fast","messages":[{"role":"user","content":"ping"}],"max_tokens":32}'
```

Weights live under `/Volumes/models/lmstudio/models`. Do **not** default-load 27B/30B/35B LMS models on the Mini for agent loops.

### Runtime rules (M4 24 GB)

1. **One large local model at a time** (do not run heavy TQ `:8081` + `:8082` + LMS + long context together).
2. Embedders (~2 GB) may stay resident.
3. Fallback order: **local → Gemini → free OpenRouter → paid xAI**.
4. **PHI / caregiver content:** keep on local models; Gemini is opt-in cloud (Google One / AI Studio), not the default for sensitive data.
5. Rejected on 24 GB for agent loops: `llama3.3:70b`, `qwen3-coder:30b`, `qwen3.5:27b`, official `gemma4:26b`, LMS 27B/30B/35B MoEs.

### Gemini (Google One — `you@example.com`)

1. Create key at https://aistudio.google.com/apikey (restrict to Gemini API only).
2. Put `GEMINI_API_KEY=...` in `~/ai-gateway/.env` (never commit).
3. Restart LiteLLM: `./scripts/docker/compose.sh up -d litellm`
4. Smoke (always load `.env` into the shell first — Compose does not export vars for you):

```bash
cd ~/ai-gateway
set -a && source .env && set +a
# Empty $LITELLM_MASTER_KEY → 401 "Malformed API Key" / "Ensure Key has Bearer prefix"
echo "key len=${#LITELLM_MASTER_KEY}"   # must be > 0

curl -sS http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"manager-gemini-fast","messages":[{"role":"user","content":"ping"}],"max_tokens":32}'
```

## Ranked next tools (from `~/GitHub`)

See `config/integration_earmarks.json` → `integration_ranking`. Short list:

| Tier | Tool | Role |
|------|------|------|
| S | Headroom | Always-on context compression (`:8787` → LiteLLM) |
| S | Herdr + Collie | Agent head + phone UI; usage/grok panes for CLI insight |
| S | Hister | Local search (profile `search`) |
| S | gollama | Host Ollama TUI (no docker) |
| A | Botmem | **Personal/life memory SoR** (profile `memory`) |
| A | hippo-memory | **Agent/coding memory SoR** (host MCP — wired) |
| A | agenttrace, jcodemunch-mcp | Session cost TUI / token-efficient code MCP (**wired**) |
| A | prompt-io + LLMTrace shadow | Hybrid parallel prompt I/O metrics (profile `security`) |
| A | mcp-obsidian | Vault MCP (snippet ready; enable after Local REST API key) |
| A | Understand-Anything | On-demand graphs for ai-gateway + grokcode (capacity cost) |
| A | token-optimizer | Agent harness (after Headroom) |
| A | hermes-agent | Peer agent in a Herdr pane → Headroom → LiteLLM |
| B | distill / mem0 / loreai | Deferred — optional layers, not extra SoRs |
| B | cognee / khoj / anything-llm / ragflow | Heavy; pick only if Open WebUI RAG is not enough |
| C | Domain MCP one-offs | On demand, not always-on stack |

## Canonical multi-host orchestration

The M4 Mac is the sole manager; gpu-host and NAS-HOST are workers:

```text
Open WebUI / Pi / OMP / OpenCode / Herdr / Codex profile
  → local Headroom :8787
  → M4 Manager Orchestrator :8790 (authenticated, internal dispatch)
  → M4 LiteLLM :4000 (central metadata ledger)
  → selected local backend or raw worker LiteLLM :4000
```

Use `role-auto` for semantic placement. Use `role-execute` when explicitly
requesting local coding/tool execution and `role-phi-local` for sensitive data.
`tier-codex-cloud` and `tier-mimo-cloud` are paid approval signals and are never
selected by `role-auto`. `tier-gemini-free` requires a separate AI Studio
project with billing disabled.

Local escape hatches remain available on each workstation:

```bash
export OPENAI_BASE_URL=http://localhost:8787/v1  # local Headroom
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
```

`:8787` is the only client inference ingress. `:8790` is authenticated manager
dispatch, and `:4000` is raw/admin access only. Manager failure is fail-closed;
there is no automatic NAS-HOST takeover. The capacity agent listens on `:8794`;
`:8791` remains reserved for vision and
`:8793` for the optional AIDA form-fill service.
The dispatcher classifies prompts locally and logs route metadata plus a short
hash, never full sensitive prompt bodies.

### Node parity and Python cache

```bash
cd ~/ai-gateway
source scripts/uv_env.sh
uv sync
uv run python scripts/check_manager_topology.py
uv run python scripts/check_litellm_routes.py
uv run python scripts/check_node_parity.py --static-only
# after deployment:
uv run python scripts/check_node_parity.py
```

The `uv` download cache is shared at `/Volumes/ai-data/uv-cache` on Mac and
`/mnt/ai-data/uv-cache` on Linux. Virtual environments, Git worktrees, SQLite,
Postgres, and service queues stay host-local. See
`config/INTEGRATION_MATRIX.md` for AIDA, memory, security, and observability
completion gates.

### Worker deployment and rollback

Deploy NAS-HOST only from `deploy/nas-host-orchestration`; never combine it with the
protected `fast-models` project. Its orchestrator has the `rollback` profile and
must stay stopped during normal operation. For rollback, start that profile and
explicitly repoint Headroom upstream variables; never delete either LiteLLM
database or Open WebUI volume.

gpu-host must deploy from a Forgejo-backed Git checkout. Before switching an
unmanaged directory, preserve its `.env`, record `git rev-parse HEAD` in the
deployment log, retain the old directory with a UTC timestamp, validate Compose
in the fresh checkout, and recreate only `litellm`, `headroom`, and the affected
support services. Install `deploy/capacity-agent/manager-capacity-agent.service`
on the host and confirm `nvidia-smi` telemetry before removing the Docker
capacity container. Manual edits to deployed configuration are prohibited.
