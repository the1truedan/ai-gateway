# Herdr — agent head for ai-gateway

Herdr is the **agent multiplexer** (tmux for AI coding agents). It is **not** the model gateway.

| Layer | Owner | Port / path |
|-------|--------|-------------|
| Agent head | **Herdr** (host binary) | Unix socket `~/.config/herdr/herdr.sock` |
| Token conservation | **Headroom** (docker, always-on) | `http://localhost:8787/v1` |
| Inference head | **LiteLLM** (docker) | `http://localhost:4000/v1` (bypass + Admin UI) |
| Chat | Open WebUI | `:8080` → Headroom → LiteLLM |
| Spend / credits (system of record) | LiteLLM Admin UI | `http://localhost:4000/ui/login/` |
| CLI usage pane | `scripts/usage_snapshot.sh` | Herdr **usage** pane |
| Mobile herd UI | Collie (optional) | Tailscale serve → Collie bridge |

## Prerequisites

```bash
herdr status          # server running (0.7.x+)
herdr --version
# LiteLLM + Headroom up:
curl -sS http://localhost:4000/health/liveliness
curl -sf http://localhost:8787/readyz
```

## Canonical agent env (token conservation)

Every pane agent should use **Headroom** by default:

```bash
set -a && source ~/ai-gateway/.env && set +a
export OPENAI_BASE_URL=http://localhost:8787/v1
export OPENAI_API_KEY="$LITELLM_MASTER_KEY"
export OPENAI_API_BASE="$OPENAI_BASE_URL"
# preferred: manager-fast-turbo | manager-fast-local | manager-reasoning-local
```

For new coding/tool sessions, explicitly select **`role-execute`**. Existing
`manager-fast-turbo` defaults remain in place for compatibility. Use
`role-phi-local` for PHI; its fallback chain is local-only.

**Bypass** (raw LiteLLM — admin, embeddings, debug, or when compression is wrong for a call):

```bash
export OPENAI_BASE_URL=http://localhost:4000/v1
```

## Open workspace layout

Layout JSON is advisory for manual pane setup or grokcode-style adapters:

- `config/herdr/layout.json` — stack / usage / health / agent / grok panes
- `config/herdr/herdr.json` — workspace metadata

```bash
cd ~/ai-gateway
herdr   # attach TUI; create workspace with cwd ~/ai-gateway
# Split panes manually or apply layout via your adapter (see ~/grokcode/integrations/herdr)
```

Suggested panes:

1. **stack** — `./scripts/docker/compose.sh ps` / logs  
2. **usage** — `./scripts/usage_snapshot.sh` (LiteLLM spend + Headroom health loop)
3. **health** — curl liveliness + URL cheat sheet
4. **agent** — pi / tau / turnstone with **Headroom** env
5. **grok** — Grok Build (`grok`) with gateway env for spend transparency

Optional: hermes CLI, hister client, **agenttrace** (Herdr **trace** pane).

### CLI insight vs LiteLLM GUI

| Need | Where |
|------|--------|
| Keys, model spend, credit-style transparency | **LiteLLM Admin UI** `:4000/ui` |
| Quick health + last spend rows in terminal | Herdr **usage** pane (`scripts/usage_snapshot.sh`) |
| Compression savings | Headroom (`readyz`; host `headroom dashboard` if installed) |
| Multi-agent session $ offline | Herdr **trace** pane → `agenttrace` (`brew install luoyuctl/tap/agenttrace`) |

```bash
agenttrace --version
agenttrace -doctor    # detect pi / OpenCode / omp / hermes log dirs
agenttrace            # interactive TUI
```

Grok Build traffic appears in LiteLLM spend **only** when routed through Headroom/LiteLLM (this layout’s default). Direct xAI/Grok cloud bypass will not show there.

## Collie (phone UI)

Collie lives at `~/GitHub/collie`. It is **host-side** (Bun + Tailscale), not a compose service.

- Bind loopback only; use `tailscale serve` — **never** funnel  
- Requires Herdr ≥ 0.7.0  
- See Collie README security section before installing  

```bash
# From Collie docs once Tailscale is ready:
# herdr plugin install AltanS/collie
# herdr plugin action invoke start --plugin herdr.collie
```

## What not to do

- Do not point Herdr at cloud providers as the primary path if you want local-first — use LiteLLM model aliases via Headroom.
- Do not replace LiteLLM with Hermes/OpenHands as the shared bus.  
- Do not expose Collie beyond the tailnet.
- Do not put Herdr in Docker as a LiteLLM/Headroom replacement.
