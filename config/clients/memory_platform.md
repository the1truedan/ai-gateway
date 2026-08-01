# Memory platform (ai-gateway)

## Decision (2026-07) — dual layer

| Layer | Choice | Role |
|-------|--------|------|
| **Personal / life memory SoR** | **botmem** (compose profile `memory`, `:12412`) | Connectors, people, cross-modal life events |
| **Agent / coding memory SoR** | **hippo-memory** (host, `.hippo/` per repo) | Lessons, errors, cross-session project memory |
| **Search index** | Hister (profile `search`) | History + local docs — not the same as memory |
| **Notes** | Obsidian + mcp-obsidian | Human-curated long-form |
| **Deferred** | distill, loreai, mem0, khoj as competing SoR | Don’t multi-install “one more memory of record” |

**Full intent matrix:** [`memory_map.md`](./memory_map.md).

Botmem ≠ hippo. One hole if you only run one; wrong-store queries if you run both without the map.

---

## Hippo (agent memory)

```bash
npm install -g hippo-memory   # Node 22.5+
cd ~/ai-gateway && hippo init
cd ~/grokcode && hippo init   # if present
# MCP: see hippo.mcp.snippet.json → ~/.config/mcp/mcp.json + OpenCode
```

- Storage: SQLite under `.hippo/` (git-friendly mirrors optional).
- Embeds: local `@xenova/transformers` by default — **do not** enable cloud embed keys unless intentional.
- Scope: coding agents (pi / OpenCode / Cursor / any MCP client).

---

## Botmem (personal memory)

```bash
cd ~/ai-gateway
# Required secrets in .env (production image rejects defaults):
#   BOTMEM_POSTGRES_PASSWORD, BOTMEM_APP_SECRET,
#   BOTMEM_JWT_ACCESS_SECRET, BOTMEM_JWT_REFRESH_SECRET, BOTMEM_OAUTH_JWT_SECRET
./scripts/docker/compose.sh --profile memory up -d
# UI: http://localhost:12412
```

### Local-only pins

```bash
BOTMEM_OLLAMA_BASE_URL=http://host.docker.internal:11434
BOTMEM_OLLAMA_EMBED_MODEL=nomic-embed-text-v2-moe:latest
BOTMEM_OLLAMA_TEXT_MODEL=qwen3.5:9b
# AI_BACKEND=ollama forced in compose for botmem-api
```

### First login (self-hosted)

- **Email/password only** — `authProvider: local`. Do **not** use Google SSO (Firebase = managed botmem.xyz).
- Stock `app-latest` is a **managed SPA** (baked `app.botmem.xyz` + Firebase + PostHog).
  ai-gateway rewrites via `config/botmem/entrypoint.sh` → same-origin `/api` + local auth default.
- If Brave hangs on SIGNING IN: clear **site data** for `localhost:12412` (cookies + cache + SW), then hard reload. Prefer `http://localhost:12412`.
- Save the **recovery key** shown once at register.

### Cloud?

| Path | Default here | Cloud? |
|------|--------------|--------|
| Auth (local JWT) | yes | No |
| Postgres memories | Docker volume | No |
| AI embed/enrich | Ollama | No |
| OpenRouter/Gemini | off unless set | Yes if enabled |
| Connectors (Gmail…) | off until connected | OAuth to that provider when you connect |
| Managed SPA without rewrite | — | Yes (wrong image) |
| PostHog in managed bundle | residual risk | Telemetry host unless self-built UI |

Long-term: rebuild web from `~/GitHub/botmem` with Dockerfile `VITE_AUTH_PROVIDER=local` instead of sed rewrite.

### Agent access

```bash
npx botmem search "query" --json
npx botmem ask "question"
# MCP: POST http://localhost:12412/mcp (after login / API key)
```

### Connectors (phased)

1. **Phase A:** local-safe (filesystem notes, optional iMessage).
2. **Phase B:** Gmail/Slack after OAuth + retention policy.

---

## Distill (still deferred)

Deterministic agent context remember/dedupe/compress — optional third layer, not a third SoR for life data. Path: `~/GitHub/distill`.

## Related (not memory SoR)

| Tool | Role |
|------|------|
| jCodeMunch | Code **symbols** (token-efficient retrieval) |
| Headroom | In-flight context compression |
| LiteLLM | Inference bus + spend |
