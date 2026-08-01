# ai-gateway

One front door for local and cloud models at home: route chat and tools to the
right machine, keep sensitive work local when it must be, and watch spend
without bolting five different UIs together by hand.

## What is in the stack

- **Docker Compose** variants for Mac, Linux, and Unraid.
- **LiteLLM** as the common API for models; **Open WebUI** for chat.
- **Headroom** in front (`:8787`) so clients default to a thrifty path; raw
  LiteLLM stays on `:4000` when you intentionally bypass.
- Optional pieces (profiles): search (Hister), personal memory (botmem),
  vision, document OCR (AIDA), import/sync helpers.
- Host-side agent memory (hippo `.hippo/` per repo) is separate from botmem.

## Routing ideas

Work is meant to flow by **role**: plan on a strong cloud model, recon on free
or local scouts, execute locally when you can, and keep care/PHI routes hard
local. Smoke: `./scripts/smoke_role_tiers.sh`.

## Operator notes

- Spend and usage: LiteLLM admin UI; snapshots via `scripts/usage_snapshot.sh`.
- Optional prompt/response metrics under the security profile.
- MCP wiring for tools lives under `config/clients/` — see memory map docs
  there if you enable hippo / Hister / Obsidian connectors.

This repo is the **sanitized public shape** of a living home lab gateway, not
a turnkey SaaS product.
