# ai-gateway

One front door for the models and tools in a home AI lab — chat UIs, coding
agents, and scripts all aim at the same local gateway instead of five different
API bases and five different excuses when something is down.

## How this came to be

This did **not** start as a product pitch.

**22 March 2026** — earliest “vibecoding” on record: Grok chats about surplus
hardware and a homelab. No caregiving mission yet; just curiosity and spare
parts.

**13 April 2026** — the pivot. Real-world harm around my mother’s care made the
hobby stop being a hobby. Within a week I was in Gateway Technical College’s
AI/ML certificate program, the ACL caregiver prize path opened, and
**M.A.N.A.G.E.R. LLC** was formed (Delaware, 20 April 2026). The question became:
*how do you prepare for the care when we cannot be there?*

### Phase 1 — orchestration testing for M.A.N.A.G.E.R. core

`ai-gateway` began as **parallel infrastructure work** next to the main
caregiving monorepo (`grokcode`). The monorepo held agents, compliance, and
story. The gateway was where we tested:

- multi-host routing (**Mac mini M4, 24 GB** as the main desk machine — not a
  laptop — plus a GPU box and Unraid “Tower”)
- a single OpenAI-compatible door (LiteLLM) with a thrifty front door (Headroom)
- smoke checks so a coding agent could tell *before* a long session that the
  stack was alive

If core M.A.N.A.G.E.R. was the brain, this was the nervous system on the LAN.

### Phase 2 — local LLM code-agent framework

Once the routes worked, the same stack became the place **coding CLIs** lived:
Claude Code, Codex, Grok Build, Cursor, and friends all pointed at local
`manager-*` models or careful cloud tiers. Tools like **grok-tua** / **tok-tua**
grew up around that: launch a CLI, watch health and spend, refuse the wrong
tier for sensitive work.

### Phase 3 — cloud LLMs as co-workers under deadline

ACL Phase 1 had a hard clock (**31 July 2026**). One person cannot type every
line. So the pattern became honest multi-model collaboration:

- long design and “what should this even be?” sessions with **Grok**, **Claude**,
  and **ChatGPT**
- take the **best concrete step** from each session, not the prettiest paragraph
- keep a **local git repo** as the ground truth (no “the chat is the product”)
- only after the ACL package went out did the sanitized trees start landing as
  **public GitHub** releases

That is the arc: chitter-chatter → decisions → commits → public repos.

### Where **ai-data** fits

Models, Pinokio trees, git mirrors, and caches grew too large to duplicate on
every machine. **ai-data** is the shared pool on Tower (NVMe + Btrfs + bees +
NFS) so the gateway hosts pull weights and assets from one place. The
`fast-models` repo is that storage plane. Gateway without storage is a
doorbell with no house behind it.

## What you get here

- Compose files for Mac / Linux / Unraid-shaped layouts
- LiteLLM as the common API; Headroom as the default thrifty path
- Optional profiles: search, memory, vision, document helpers
- Operator notes for a small multi-machine fleet

This public tree is **sanitized** for release. Home secrets, private care
data, and raw LAN IPs stay off GitHub (roles like `gpu-host` / `nas-host`
instead).

## Shared AI pool, bees, and dashboards

The storage plane next to this gateway uses Btrfs + **bees** (block dedupe)
and a separate **content-hash** dual ladder (file-level candidates). Those are
easy to confuse — we published the runbooks and a Grafana board so others can
copy the pattern:

| Path | What |
|------|------|
| [`docs/ops/bees/`](./docs/ops/bees/) | Hash sizing HOWTO, **4 G** considerations, 2026-08-01 incident history, Grafana/cron shape, L1/L2/L3 ladder |
| [`config/observability/ai-data-bees-dashboard.json`](./config/observability/ai-data-bees-dashboard.json) | Importable Grafana dashboard (Prometheus) |
| [`deploy/unraid-fast-models/`](./deploy/unraid-fast-models/) | Sketch of the Unraid “fast-models” pool stack |

**4 G short version:** bees fingerprint table size is *not* disk fullness.
We grew **1 G → 2 G → 4 G** when occupancy hit ~100% on a ~1.5 TiB-used pool.
Sticky RAM ≈ table size; only grow after a full re-crawl still saturates the
table, and never enable format flags for a resize.

Related design repo: [johnny-appleseed-chipper](https://github.com/the1truedan/johnny-appleseed-chipper)
(process templates for inventory / dual-verify / public handoff).

## Quick start (sketch)

See Compose files in-repo and `IDEA.md` for the mental model. You will need
your own model backends (Ollama, vLLM, cloud keys, etc.) — nothing here claims
to be a turnkey hospital product.

```bash
# typical shape (adapt to your host)
cp .env.example .env   # if present
docker compose up -d
```

## Related public pieces

| Repo | Role |
|------|------|
| [fast-models](https://github.com/the1truedan/fast-models) | Shared NVMe pool (ai-data) |
| [grok-tua-tok-tua](https://github.com/the1truedan/grok-tua-tok-tua) | Coding-CLI launchers + status panes |
| [mok-tua](https://github.com/the1truedan/mok-tua) | Script → storyboard pipeline |
| [shreddit](https://github.com/the1truedan/shreddit) | Side utility — first public OSS release timed with ACL |

---

<p align="left">
  <a href="https://linktr.ee/the1truedan"><img src="https://img.shields.io/badge/Linktree-39E09B?style=for-the-badge&logo=linktree&logoColor=white" alt="Linktree"></a>
  <a href="https://ko-fi.com/the1truedan"><img src="https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
</p>

**© 2026 M.A.N.A.G.E.R. LLC** — *prepare for the care when we cannot be there*
