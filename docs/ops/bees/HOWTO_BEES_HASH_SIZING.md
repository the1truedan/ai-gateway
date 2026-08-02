<!-- Public sanitized copy for ai-gateway. LAN IPs → NAS_HOST; absolute home paths redacted. Process content preserved. -->

# HOWTO: Size and grow the bees hash table (ai-data / fast-models)

**Audience:** anyone operating the Tower `fast-models` pool.  
**Related incident:** `docs/operations/BEES_HASH_SIZE_INCIDENT_2026-08-01.md`  
**Metrics:** Grafana dashboard **ai-data / bees dedupe**

## Plain-language picture

bees keeps a **phone book of content fingerprints** on disk (`beeshash.dat`).
When two chunks of the pool look the same, it can share the physical copy on
Btrfs. That phone book has a fixed size:

- Too small → book fills up, bees forgets old entries, works harder, dedupes less well.  
- Too large → steals RAM from everything else on Tower (and this host has **no swap**).

The phone book size is **not** “how full the disk is.” A full hash table can
happen while you still have terabytes free.

## Current production defaults (Tower, after 2026-08-01)

| Setting | Value | Notes |
|---------|--------|--------|
| `BEES_HASH_SIZE` | **4G** | 1G→2G morning (100% full); 2G→4G evening (99% full after re-crawl) on ~1.5 TiB used |
| `BEES_THREADS` | **1** | Keep unless you have clear spare CPU/RAM |
| `BEES_SCAN_MODE` | **4** | Extent scan (good for model blobs) |
| Host RAM | ~31 GiB, **no swap** | Sticky hash RSS ≈ table size (~4 GiB at 4G) |

## Choosing a size

Rough guide for this fleet:

| Pool Data used (btrfs) | Host RAM | Start with | Grow if occupancy stays high |
|------------------------|----------|------------|------------------------------|
| &lt; ~500 GiB | 16–32 GiB | 1G | 2G |
| ~0.5–2 TiB | 32 GiB | **2G** | 4G only if needed |
| &gt; 2 TiB | 32 GiB | 2G–4G | Prefer more RAM or split workloads before 8G |

**4G plan:** only if, after a **full re-crawl** on 2G, Grafana still shows
occupancy ≳ **0.90–0.95**. Do not “pre-buy” 4G while also loading large local
LLMs on the same box.

## How to grow safely (runbook)

### Do

1. Confirm Grafana / `beesstats.txt` occupancy is truly high.  
2. Confirm `ALLOW_FORMAT=0` and `FORCE_FORMAT=0` in stack `.env`.  
3. Confirm host `/mnt/ai-data` and container `/ai-data` are mounted.  
4. Confirm `MemAvailable` leaves headroom (several GiB above the new table size).  
5. Stop **only the bees process** (leave the container and NFS up if possible).  
6. **Rename** old `beeshash.dat` and `beescrawl.dat` (backup).  
7. Create a **fresh empty** file: `truncate -s 2G beeshash.dat` (or 4G).  
8. Set `BEES_HASH_SIZE` in `.env` to match (for the next full container start).  
9. Start bees again (same flags as entrypoint: 1 thread, scan-mode 4, nice/ionice).  
10. Expect occupancy near **0**, then a slow climb. That is healthy.

### Don’t

- Don’t set `ALLOW_FORMAT=1` or `FORCE_FORMAT=1` for a hash resize.  
- Don’t truncate a **live** structured 1G table “up” to 2G in place.  
- Don’t blame Unraid **parity** for hash occupancy.  
- Don’t treat content-hash “reclaimable GB” as bees savings.  
- Don’t jump straight to 4G on a busy 32 GiB no-swap host without measuring.

## Verify

```bash
# process + size
docker exec fast-models pgrep -a bees
ls -lh /mnt/user/appdata/fast-models/bees/beeshash.dat

# occupancy (or Grafana)
docker exec fast-models sh -c 'grep -E "cells occupied|Uptime" /var/lib/bees/beesstats.txt'

# pool untouched
docker exec fast-models btrfs fi df /ai-data
findmnt /mnt/ai-data
```

## Where files live

| Path | Role |
|------|------|
| `/mnt/user/appdata/fast-models/stack/.env` | `BEES_HASH_SIZE`, format safety flags |
| `/mnt/user/appdata/fast-models/bees/beeshash.dat` | Hash table (appdata / array) |
| `/mnt/user/appdata/fast-models/bees/beescrawl.dat` | Crawl cursor (reset when replacing hash) |
| `/mnt/ai-data` | Host NFS export of the model pool (not the hash file) |

## See also

- Incident writeup: `docs/operations/BEES_HASH_SIZE_INCIDENT_2026-08-01.md`  
- Metrics + overnight jobs: `docs/operations/AI_DATA_BEES_GRAFANA_CRON.md`  
- Public stack docs: GitHub `the1truedan/fast-models`
