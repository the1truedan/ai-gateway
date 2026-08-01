# Client configs for AI-Gateway (LiteLLM)

**Dual head:** Herdr (host) = agent multiplexer · LiteLLM (docker `:4000`) = inference bus.  
See `config/herdr/README.md` and `RUNBOOK.md`.

For an emoji model catalog and copy/paste Pi, OMP, and OpenCode tests that
exercise Mac orchestration through the NVIDIA Ollama worker, see
[`ORCHESTRATOR_MODEL_OPTIONS.md`](ORCHESTRATOR_MODEL_OPTIONS.md).

Canonical OpenAI-compatible contract for any consumer (**token conservation default**):

```bash
export OPENAI_BASE_URL=http://localhost:8787/v1   # Headroom → LiteLLM
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"       # from ~/ai-gateway/.env
# Prefer: tier-local-fast | manager-fast-turbo | manager-fast-local
#          tier-local-reason | manager-reasoning-turbo
# Automatic: role-auto (NAS-HOST semantic dispatcher)
# Roles:  role-plan | role-execute | role-recon | role-phi-local | role-audit
#          tier-gemini | manager-gemini-fast | manager-gemini-agent
#          manager-grok-coding | manager-openrouter-free | manager-embed
# Bypass (raw LiteLLM): OPENAI_BASE_URL=http://localhost:4000/v1
# GEMINI_API_KEY from Google AI Studio (Google One); never default PHI to Gemini
# Orchestration: cloud plan (role-plan) → local execute (role-execute); see RUNBOOK
```

Docker containers on the same host: Headroom `http://host.docker.internal:8787/v1` or LiteLLM `:4000/v1`.
LAN clients (Unraid/PopOS gateway): `http://<gateway-lan-ip>:8787/v1` (or `:4000` bypass).

| File | Consumer |
|------|----------|
| `turnstone.toml` | Turnstone CLI / node bootstrap |
| `tau.providers.snippet.json` | Merge into `~/.tau/providers.json` |
| `opencode.ai-gateway.snippet.json` | Merge into `~/.config/opencode/opencode.json` (+ auth) |
| `opencode.nas-host.json` / `pi.nas-host.models.json` / `omp.nas-host.models.yml` | Canonical NAS-HOST `role-auto` profiles |
| `codex.nas-host.profile.toml` | Codex NAS-HOST Headroom profile |
| `openrouter-free-models.md` | Free OpenRouter catalog + compare (auto-synced) |
| `openwiki.env.example` | `~/.openwiki/.env` (+ shell `OPENAI_BASE_URL`) |
| `hister.semantic_search.snippet.yaml` | Hister semantic search overlay |
| `hister.mcp.snippet.json` | Hister MCP (OpenCode remote + shared mcpServers) |
| `jcodemunch.mcp.snippet.json` | jCodeMunch MCP (OpenCode + pi/omp shared) |
| `mcp-obsidian.snippet.json` | Obsidian Local REST API MCP (enable after key) |
| `memory_platform.md` | Dual SoR: botmem (life) + hippo (agent) |
| `memory_map.md` | Intent → store matrix for agents |
| `hippo.mcp.snippet.json` | hippo-memory MCP (OpenCode + shared mcpServers) |
| `../nono/ai-gateway-agent.json` | Nono sandbox profile |
| `../herdr/` | Herdr agent-head workspace layout |

**Pi** is wired at `~/.pi/agent/models.json` (`gpu-host-headroom` → Mac **`:8787` Headroom**, default `tier-nvidia-fast`; tiers + free OR aliases). Ollama provider remains direct `:11434` bypass.

**OpenCode** is wired at `~/.config/opencode/opencode.json` (`provider.gpu-host-headroom` → Mac **`:8787`**, default `gpu-host-headroom/tier-nvidia-fast`). Auth key in `~/.local/share/opencode/auth.json`. Snippet: `opencode.gpu-host.json`.

Core stack includes **Headroom** (`:8787`). Optional profiles: `search` (Hister), `memory` (Botmem), `vision` (manager-vision-embed FastAPI), `import`, `sync`.

Vision **features** (not chat): host `./scripts/start_vision_embed.sh` → `http://localhost:8791` — see `services/vision_embed/README.md`.

Smoke:

```bash
cd ~/ai-gateway
set -a && source .env && set +a   # required — empty $LITELLM_MASTER_KEY → 401 Malformed API Key
test -n "$LITELLM_MASTER_KEY" || { echo "LITELLM_MASTER_KEY missing"; exit 1; }

curl -sS http://localhost:4000/health/liveliness
curl -sS http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"manager-fast-local","messages":[{"role":"user","content":"ping"}],"max_tokens":64}'
```
