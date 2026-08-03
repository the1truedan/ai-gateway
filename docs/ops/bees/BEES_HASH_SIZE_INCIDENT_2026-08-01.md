<!-- Public sanitized copy for ai-gateway. LAN IPs → NAS_HOST; absolute home paths redacted. Process content preserved. -->

# Incident: bees hash table undersized (1 G full on ~1.6 TiB pool) — 2026-08-01

## Summary

The online Btrfs dedupe agent **bees** (inside the `fast-models` container on
NAS host) had been running with a **1 G** fingerprint hash table
(`BEES_HASH_SIZE=1G`). On a pool with roughly **1.57 TiB** of Btrfs Data used,
that table hit **100% occupancy**. bees kept running, but it had to **evict**
old fingerprints, so it spent more time re-hashing and missed dedupe
opportunities. This was **not** caused by Unraid parity, broken cron, or a
full disk — it was a **capacity misconfiguration** relative to pool size and
host RAM.

**Fixed the same day:** hash table grown carefully **1 G → 2 G** (morning),
then **2 G → 4 G** (evening) after 2 G re-filled to **99%** occupancy.
Each step: fresh empty table + crawl reset; container and NFS left up.
Grafana tracks occupancy and bees health. Logs on the NAS host:
`.../logs/bees-hash-resize-2g.log`, `.../logs/bees-hash-resize-4g.log`.

## What people might misread

| Symptom | Easy wrong conclusion | Actual |
|---------|----------------------|--------|
| Hash occupancy 100% | “Disk full” or “parity check filled it” | bees’ **in-memory fingerprint table** is full |
| bees CPU high | “Cron jobs broken” | bees still works; eviction thrash under load |
| Reclaimable GB huge in Grafana | “bees failed” | **Content-hash audit** ≠ bees block savings |
| Parity running on Unraid | “That’s why occupancy is 100%” | Different disks / different subsystem |

## Root cause

1. **Default was too small for this pool.**  
   `BEES_HASH_SIZE=1G` is a reasonable starter for small pools, not for
   multi-terabyte model/cache trees with heavy near-duplicate content.
2. **No early warning until metrics existed.**  
   Occupancy lived only in `beesstats.txt` until the 2026-08-01 textfile
   exporter + Grafana board (`ai-data / bees dedupe`).
3. **Entrypoint does not resize an existing table.**  
   If `beeshash.dat` already exists, changing `.env` alone does nothing —
   operators must replace the file while bees is stopped.

## Impact

- bees process: **up** the whole time (not a crash).
- Dedupe **quality**: reduced while table was full (evictions).
- Host RAM: ~1 GiB sticky RSS for the 1 G table; after fix ~2 GiB for 2 G.
- NFS `/mnt/ai-data`, pool data, and Unraid array: **not rewritten**.
- Overnight content-hash audit / bees-health cron: **unaffected** (they do
  not use the bees hash mmap).

## Fix applied (2026-08-01) — careful path

**Principle:** stop **only bees**, keep `fast-models` container and host
`/mnt/ai-data` NFS mount alive. Never touch `ALLOW_FORMAT` / `FORCE_FORMAT`.

1. Confirmed `ALLOW_FORMAT=0`, `FORCE_FORMAT=0`, host + container mounts OK,
   MemAvailable ≳ 20 GiB.
2. Set `BEES_HASH_SIZE=2G` in stack `.env` (backup of previous `.env` kept).
3. `SIGTERM` bees inside the container; verified process down.
4. **Did not** truncate the old 1 G structured table in place (cell layout
   depends on size). Renamed backups, then created a **fresh empty 2 G**
   `beeshash.dat`.
5. Renamed `beescrawl.dat` so a re-crawl re-seats fingerprints into the new
   table.
6. Restarted bees (1 thread, scan-mode 4, nice/ionice).
7. Verified: process up, file **2.0 G**, RSS ~2 GiB, occupancy ~0 (expected
   until re-crawl fills it), pool still mounted, marker file present.

Log on the NAS host:
`/mnt/user/appdata/fast-models/logs/bees-hash-resize-2g.log`

Backups (delete after a stable day):
```
.../bees/beeshash.dat.1G.pre-2g-*
.../bees/beescrawl.dat.pre-2g-*
```

## 4 G step (done 2026-08-01 evening)

| | 2 G | 4 G (production now) |
|--|-----|----------------------|
| Extra sticky RAM vs 1 G | +~1 GiB | +~3 GiB |
| When | Morning (1 G at 100%) | Evening (2 G re-filled to 99% after re-crawl) |
| Host fit (31 GiB, **no swap**) | Comfortable | OK with MemAvailable ≳ 20 GiB at resize; watch if large local LLMs park on the NAS host |
| Procedure | Fresh empty table, crawl reset, bees-only restart | Same |

**Do not** grow past 4 G without another full re-crawl + occupancy ≳ 0.95
and explicit RAM budget. Prefer more host RAM before 8 G.

## Prevention / best practices

See also: `docs/HOWTO_BEES_HASH_SIZING.md`,
`docs/operations/AI_DATA_BEES_GRAFANA_CRON.md`.

1. Watch Grafana **hash table occupancy** (alert ≳ 0.85 yellow, ≳ 0.95 red).
2. Size hash for **pool + host RAM**, not “whatever the sample `.env` said.”
3. Grow with a **fresh table + crawl reset**; never in-place truncate of a
   live structured hash.
4. Keep `BEES_THREADS=1` on ~32 GiB Unraid boxes.
5. Remember: **parity ≠ bees hash**; **content-hash reclaimable GB ≠ bees
   bytes saved**.

## Related

- Grafana: `http://NAS_HOST:3002/d/ai-data-bees-dedupe`
- Stack: `fast-models` on the NAS host; GitHub mirror `the1truedan/fast-models`
- NAS disk incident context (separate; private ops notes, not in this tree)
