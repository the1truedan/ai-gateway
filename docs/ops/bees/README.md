# bees + ai-data dedupe (public ops notes)

What we learned running a shared **AI file pool** (Btrfs + bees + NFS) next to
an OpenAI-compatible gateway stack.

## Why this lives next to ai-gateway

The gateway is only useful if models and caches are somewhere durable.
**fast-models** (Unraid Docker stack) is that storage plane. bees is the
online block-level dedupe agent on the pool. Content-hash dual scans are a
*different* layer — see the ladder doc.

## Docs in this folder

| File | Topic |
|------|--------|
| [HOWTO_BEES_HASH_SIZING.md](./HOWTO_BEES_HASH_SIZING.md) | How to size / grow `BEES_HASH_SIZE` safely |
| [BEES_HASH_SIZE_INCIDENT_2026-08-01.md](./BEES_HASH_SIZE_INCIDENT_2026-08-01.md) | Real incident: 1 G table full → 2 G → **4 G** |
| [AI_DATA_BEES_GRAFANA_CRON.md](./AI_DATA_BEES_GRAFANA_CRON.md) | Metrics exporter + overnight cron shape |
| [AI_DATA_DEDUP_LADDER.md](./AI_DATA_DEDUP_LADDER.md) | L1 structure / L2 content-hash / L3 bees |

## Dashboard

Import Grafana JSON:

`config/observability/ai-data-bees-dashboard.json`

Point panels at your Prometheus datasource (default uid in file: `prometheus`).
Replace host placeholders if any remain.

## 4 G considerations (short)

- Sticky RSS ≈ table size. On a **~32 GiB, no-swap** NAS host, 4 G is workable
  but not free — leave headroom for containers and NFS.
- Grow only when occupancy stays ≳ 0.90–0.95 **after a full re-crawl** on the
  previous size. Do not pre-size to 4 G “just in case” while also loading large
  local LLMs on the same box.
- Resize = stop bees process → rename old `beeshash.dat` → fresh empty file →
  set `BEES_HASH_SIZE` → restart. Never flip format-allow flags for a resize.

## Status of this publish

Sanitized for GitHub: LAN IPs → `NAS_HOST` / role names, home absolute paths
redacted. Process steps and the 2026-08-01 history are intentionally kept so
others can avoid the same undersized-hash thrash.
