# Hister + Atuin shell-history corpus

## What

Atuin captures shell history locally.
`scripts/history/export_atuin_for_kb.py` writes redacted day-chunked markdown to:

```text
import-data/staging/dev-history/shell/
```

That folder is:

1. **Open WebUI Knowledge Base** — Sync Directory → create KB `dev-shell-history`
2. **Hister** — mounted at `/data/dev-history` and listed under `indexer.directories` in `config.yml`

## Refresh export

```bash
./scripts/history/export_atuin_for_kb.sh
# optional: last 30 days only
./scripts/history/export_atuin_for_kb.sh --days 30
```

## Recreate Hister with file index

```bash
./scripts/docker/compose.sh --profile search up -d
# After first export, wait a few seconds then:
curl -sS -X POST http://127.0.0.1:4433/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search","arguments":{"query":"type:local docker compose","limit":5,"semantic":true}}}'
```

## Open WebUI KB (manual once)

1. Open http://localhost:8080 → Workspace → Knowledge → **New Knowledge** → `dev-shell-history`
2. Add Content → **Sync Directory** (or Upload Directory) →
   `$HOME/ai-gateway/import-data/staging/dev-history/shell`
3. Attach KB to a stack model, or use `#dev-shell-history` in chat
4. Prefer hybrid/grep for exact commands; focused RAG for “what did I run for X?”

## Grok history (not this folder)

Grok.com + Grok Build stay as **OWUI chats**:

```bash
./scripts/import/run_openwebui_import.sh --build --apply
./scripts/import/run_openwebui_import.sh --history --apply   # when you have a new xAI export
```

## Security

- Atuin is **local-only** (`auto_sync = false` in `~/.config/atuin/config.toml`).
- Export redacts common secret patterns; still review before sharing KB access.
- `import-data/` is gitignored — do not force-add shell history to git.
