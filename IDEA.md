# ai-gateway — mental model

One front door for local and cloud models at home: route chat and tools to the
right machine, keep sensitive work local when it must be, and watch spend
without bolting five different UIs together by hand.

This repository is **orchestration glue**. The intelligence and UIs come from
upstream projects — see the stack table in [README.md](./README.md).

## What is in the stack

- **Docker Compose** variants for Mac, Linux, and Unraid.
- **[LiteLLM](https://github.com/BerriAI/litellm)** as the common API; **[Open WebUI](https://github.com/open-webui/open-webui)** for chat.
- **[Headroom](https://github.com/chopratejas/headroom)** in front (`:8787`) so clients default to a thrifty path; raw LiteLLM stays on `:4000` when you intentionally bypass.
- Local backends: **[Ollama](https://github.com/ollama/ollama)** and TurboQuant-backed host servers (`:8081`/`:8082`).
- Coding agents aimed at the door: **[Pi](https://github.com/badlogic/pi-mono)**, **[Oh My Pi](https://github.com/acidsugarx/oh-my-pi)**, **[OpenCode](https://github.com/anomalyco/opencode)**, plus Claude Code / Codex / Cursor / Grok Build.
- Optional pieces (profiles): search (**[Hister](https://github.com/asciimoo/hister)**), personal memory (**[botmem](https://github.com/botmem/botmem)**), agent memory (**[hippo-memory](https://github.com/kitfunso/hippo-memory)**), vision, document OCR (AIDA), import/sync helpers.
- Storage plane: **[fast-models](https://github.com/the1truedan/fast-models)** + **[bees](https://github.com/Zygo/bees)** for the shared **ai-data** pool.

## Routing ideas

Work is meant to flow by **role**: plan on a strong cloud model, recon on free
or local scouts, execute locally when you can, and keep care/PHI routes hard
local. Smoke: `./scripts/smoke_role_tiers.sh` (full tree).

## Operator notes

- Spend and usage: LiteLLM admin UI; snapshots via `scripts/usage_snapshot.sh`.
- Optional prompt/response metrics under the security profile.
- MCP wiring for tools lives under `config/clients/` — hippo / Hister / Obsidian
  connectors when enabled.

This repo is the **sanitized public shape** of a living home lab gateway, not
a turnkey SaaS product.
