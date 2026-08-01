# Memory map (ai-gateway)

Layered memory — **different jobs, different stores**. Agents must pick the right one; Headroom/LiteLLM hold **no** durable memory.

```
  Life events ──► botmem     (connectors, people, RAG ask)
  Coding sessions ──► hippo  (.hippo/ SQLite + MCP)
  Browsing/docs ──► hister   (local search index)
  Shell commands ──► Atuin → export → OWUI KB + Hister
  Grok chats/build ──► OWUI chats (import scripts; not shell KB)
  Deliberate notes ──► Obsidian (mcp-obsidian when enabled)
           │
           ▼
  Agent chooses via this map (not a single mega-DB)
```

## Intent → store

| Intent (example) | Store | Access |
|------------------|--------|--------|
| “What did we decide about X in this **repo**?” | **Hippo** | MCP `hippo` / `hippo` CLI |
| “What did Sarah **email** about the deadline?” | **Botmem** | UI `:12412` / `botmem search` / MCP `/mcp` when authed |
| “I **read a page** about Y last week” | **Hister** | MCP `http://127.0.0.1:4433/mcp` |
| “What **command** did I run when deploying X?” | **Atuin** (terminal) + **dev-shell-history** (OWUI KB / Hister export) | `atuin search`; OWUI `#dev-shell-history`; Hister `type:local` |
| “What did we discuss in **Grok Build** / grok.com?” | **Open WebUI chats** | `./scripts/import/run_openwebui_import.sh --build|--history` |
| “Our **vault note** on Z” | **Obsidian** | `mcp-obsidian` (Local REST API + key) |
| “Don’t re-learn this constraint next session” | **Hippo** (tag error/lesson) | MCP / CLI |
| “Compress this turn / dedupe context” | Distill (deferred) | Optional later |
| Chat completions | Headroom→LiteLLM | **Not memory** — inference bus only |

## Rules of thumb

1. **Code/project lessons → hippo**
2. **People / multimodal life events → botmem**
3. **Web/history/docs corpus → hister**
4. **Shell operational breadcrumbs → Atuin** (capture) → redacted export → OWUI KB + Hister (not a new SoR)
5. **Grok / Grok Build narrative → OWUI chats** (import), not the shell KB
6. **Curated long-form → Obsidian**
7. Never treat Headroom/LiteLLM as a memory store.

### Shell history pipeline

```bash
# Capture (host): brew install atuin; eval "$(atuin init zsh)"; atuin import zsh
# Export for RAG (gitignored under import-data/):
./scripts/history/export_atuin_for_kb.sh
# Details: config/hister/README.md
```

## Smoke commands

```bash
# Hippo (agent memory — host)
cd ~/ai-gateway && hippo --help
# after init: write/search via CLI or MCP tools

# Botmem (personal — compose profile memory)
curl -sS http://127.0.0.1:12412/api/version   # authProvider: local
# UI: http://localhost:12412  (clear Brave site data if login stuck; email/password only)

# Hister
curl -sS -X POST http://127.0.0.1:4433/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## MCP registration (this Mac)

| Server | Config |
|--------|--------|
| hippo | `~/.config/mcp/mcp.json` + OpenCode `mcp.hippo` |
| hister | remote `http://127.0.0.1:4433/mcp` |
| jcodemunch | code symbols (not episodic memory) |
| mcp-obsidian | enabled after `OBSIDIAN_API_KEY` |
| botmem `/mcp` | optional after local login works |

See also: `memory_platform.md`, `hippo.mcp.snippet.json`, `config/botmem/entrypoint.sh` (self-host SPA rewrite).
