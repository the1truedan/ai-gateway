<!-- Public sanitized copy for ai-gateway. LAN IPs → NAS_HOST; absolute home paths redacted. Process content preserved. -->

# ai-data / bees: Grafana dashboard + overnight cron

**Deployed:** 2026-08-01 on the NAS host (`NAS_HOST`)  
**Grafana:** `http://NAS_HOST:3002` → dashboard **ai-data / bees dedupe** (`uid: ai-data-bees-dedupe`)  
**Prometheus:** `http://NAS_HOST:9090` (scrapes `nas-node-exporter` textfile collector)

**Hash sizing:** production table is **4 G** (1 G→2 G morning 2026-08-01 at 100%; 2 G→4 G evening when re-crawl hit 99%).  
See `docs/HOWTO_BEES_HASH_SIZING.md` and incident
`docs/operations/BEES_HASH_SIZE_INCIDENT_2026-08-01.md`. Optional **4 G** only
if 2 G fills again after a full re-crawl on this 32 GiB / no-swap host.

## What runs on a schedule

| When | Script | Purpose |
|------|--------|---------|
| `*/15 * * * *` | `ai_data_stats_exporter.sh` | Write Prometheus textfile metrics (audit + bees + btrfs) |
| `30 2 * * *` | `ai_data_dedup_audit_cron.sh` | Overnight **report-only** content-hash re-scan of `/ai-data` |
| `15 3 * * *` | `bees_health_cron.sh` | Daily bees liveness + `btrfs fi df` log + heartbeat |

All live under:
```
/mnt/user/appdata/manager-orchestration/exporters/
```

Logs:
```
/mnt/user/appdata/fast-models/logs/bees-health.log
/mnt/user/appdata/fast-models/logs/dedup-audit-nightly.log
```

Heartbeats (for Grafana “cron age” panels):
```
.../node-exporter-textfile/bees_health_last_ok_timestamp.value
.../node-exporter-textfile/dedup_audit_last_ok_timestamp.value
.../node-exporter-textfile/dedup_audit_last_duration_seconds.value
```

## Metrics (textfile → node-exporter → Prometheus)

| Metric | Source |
|--------|--------|
| `bees_up`, `bees_uptime_seconds` | live process |
| `bees_hash_table_occupancy_ratio` | `beesstats.txt` (fixed: 100% → 1.0 not 0.1) |
| `bees_extent_ref_ok_total` | bees counter (not bytes saved) |
| `btrfs_ai_data_{used,total}_bytes` | `btrfs fi df -b` inside container |
| `ai_data_mount_{size,used,avail}_bytes` | host `df` on `/mnt/ai-data` |
| `ai_data_dedup_{total,reclaimable}_gb` | overnight audit JSON |
| `ai_data_dedup_audit_age_seconds` | staleness of audit JSON |
| `bees_health_last_ok_timestamp` | daily health cron |
| `dedup_audit_last_*` | overnight audit cron |

## Two different “savings” numbers

1. **Block/extent (bees + zstd):** compare logical size vs `btrfs_ai_data_used_bytes` — real physical reclaim on the pool.  
2. **Content-hash audit:** `ai_data_dedup_reclaimable_gb` — *candidates* for human merge/symlink; not automatic.

Do not treat (2) as bees savings.

## Repo sources (copy to NAS host)

| Repo path | NAS host path |
|-----------|------------|
| `deploy/unraid-fast-models/exporters/*.sh` (or local ops tree) | `/mnt/user/appdata/manager-orchestration/exporters/` |
| `config/observability/ai-data-bees-dashboard.json` | Grafana import (uid `ai-data-bees-dedupe`) |
| `scripts/deepscan_ai_data_dedup.py` + `scripts/lib/dedup_engine.py` | `/root/dedup-tool/` (sync engine fix before audit) |
| `config/ai_data_dedup_buckets.json` | `/root/dedup-tool/config/` |

## Install / re-install crontab

```bash
ssh operator@nas-host '/mnt/user/appdata/manager-orchestration/exporters/install_dedup_cron.sh'
```

Managed block is delimited by:
```
# BEGIN manager-ai-data-dedup
...
# END manager-ai-data-dedup
```

## Manual smoke

```bash
# refresh metrics now
ssh operator@nas-host /mnt/user/appdata/manager-orchestration/exporters/ai_data_stats_exporter.sh
curl -sS http://NAS_HOST:9100/metrics | grep -E '^(bees_|ai_data_|btrfs_ai_)'

# health cron
ssh operator@nas-host /mnt/user/appdata/manager-orchestration/exporters/bees_health_cron.sh

# full overnight audit (IO-heavy; prefer overnight)
ssh operator@nas-host /mnt/user/appdata/manager-orchestration/exporters/ai_data_dedup_audit_cron.sh
```

## Hash table size (ops note)

If `bees_hash_table_occupancy_ratio` stays ~1.0, bees is thrashing/evicting and may under-dedupe.

### 2026-08-01: 1G → 2G (done carefully)

| Item | Value |
|------|--------|
| Method | Stopped **bees process only** (container + host `/mnt/ai-data` NFS stayed up) |
| New table | Fresh empty `beeshash.dat` **2.0G** (do **not** truncate-in-place a structured 1G table) |
| Crawl | Reset (`beescrawl.dat` renamed) so re-crawl re-seats fingerprints |
| `.env` | `BEES_HASH_SIZE=2G` (ALLOW_FORMAT/FORCE_FORMAT left at 0) |
| Post-check | `bees_up=1`, occupancy ~0 (expected), VmRSS ~2.0 GiB |
| Log | `/mnt/user/appdata/fast-models/logs/bees-hash-resize-2g.log` |
| Backups | `beeshash.dat.1G.pre-2g-*`, `beescrawl.dat.pre-2g-*` under appdata `bees/` — delete after ~1 stable day |

**Do not** jump to 4G unless 2G fills again after a full crawl window. Host is 32 GiB with **no swap**.

## Guardrails

- Overnight audit is **report-only** (no delete/symlink/merge).  
- Scans must stay **host-local on the NAS host** (`/ai-data` inside `fast-models`), never NFS client from Mac workstation / GPU worker.  
- Do not commit Grafana admin passwords; import uses NAS-local `.env` only.
