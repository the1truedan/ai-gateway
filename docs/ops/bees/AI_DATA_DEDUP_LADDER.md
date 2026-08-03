<!-- Public sanitized copy for ai-gateway. LAN IPs → NAS_HOST; absolute home paths redacted. Process content preserved. -->

# ai-data Dedup Ladder + Gate + Receipt

**Single ops law** for content-hash duals, quarantine, bees, and Johnny/CHIPPER cataloging.  
**Related:** `docs/roadmap/AI_DATA_DEDUP_INDEXING_STAGING.md`, `docs/roadmap/JOHNNY_APPLESEED_CHIPPER_CHAINS.md`, `docs/HOWTO_BEES_HASH_SIZING.md`, `docs/operations/AI_DATA_BEES_GRAFANA_CRON.md`.

## Three layers (do not conflate)

| Layer | What | Metric / tool |
|-------|------|----------------|
| **L3 bees** | Btrfs extent physical sharing | Grafana occupancy, `beesstats` — not “reclaimable GB” |
| **L2 file hash** | size → sample → full SHA256 | `deepscan_*`, `dedup_engine`, dual-verify |
| **L1 structure** | dual install roots, husks, `.merged-away-*` | prune manifests, structure inventory |

Quarantine waves (e.g. `prune-2026-08-01`) are often **L1** until dual-verify promotes paths to **L2 proven_match**.

## Ladder (detect)

```text
exact size → sample_hash (4 MiB head/tail) → full SHA256 only on multi-member sample groups
```

| Confidence | Meaning | Execute (apply / purge)? |
|------------|---------|---------------------------|
| `basename_size` | Same name + size only | No (unless `--allow-basename`) |
| `sample` | Head/tail match | No (unless `--allow-sample`) — escalate first |
| **`sha256`** | Byte-identical | Yes, after verification-manifest |
| `dir_tree` | Same relative paths+sizes | Structure candidate only |

**Best practice:** `--escalate-full` (not legacy `--full-hash` whole tree). Cap with `--max-escalate-gb` on nightly jobs.

## Gate (act)

1. Report-only scan writes `data/catalog/_*.json`.  
2. `apply_models_dedup.py --execute` requires `--verification-manifest` with `verified=true` and `all_hosts_readable=true`.  
3. Default confidence gate: **sha256 only**.  
4. Prefer **quarantine** same-FS before permanent `rm`.  
5. Same-FS `mv` does **not** free space until `rm`; bees may already share extents.

## Dual-verify quarantine (CHIPPER-style job)

### Important: scripts are NOT on the ai-data pool

`/ai-data` (or `/mnt/ai-data`) has models/pinokio/… only. Repo tools live in
**``<manager monorepo>``** and must be synced to the NAS host **`/root/dedup-tool/`** (same layout
the overnight audit cron already expects). Inside the `fast-models` console you
only see pool mounts — `python3 scripts/...` will always fail until tools are
staged.

| Where | Path |
|-------|------|
| Mac repo | ``<manager monorepo>`/scripts/verify_quarantine_duals.py` |
| NAS host cache | `/root/dedup-tool/scripts/` + `lib/dedup_engine.py` |
| Inside container at run | `/tmp/dedup-tool-*/scripts/` (docker cp’d for the job) |
| Pool data root in container | **`/ai-data`** (not `/mnt/ai-data`) |
| Quarantine wave | `/ai-data/.dedup_quarantine/prune-2026-08-01/` (hidden — `ls -la`) |

### Sync + run (preferred)

```bash
# On operator workstation (SSH to NAS host)
cd `<manager monorepo>`
./scripts/sync_dedup_tool_to_nas.sh operator@nas-host

# On NAS host (Unraid root shell — not only docker console)
/root/dedup-tool/scripts/run_verify_quarantine_on_nas.sh
# optional: WAVE=prune-2026-08-01 COVERAGE=95 MAX_GB=50 ...
```

### Manual docker path (if you stay in console)

```bash
# On NAS HOST first (has /root/dedup-tool after sync):
docker cp /root/dedup-tool/scripts fast-models:/tmp/dedup-tool/scripts
docker cp /root/dedup-tool/config  fast-models:/tmp/dedup-tool/config   # optional
docker exec -it fast-models sh
# inside container:
cd /tmp/dedup-tool
ionice -c3 nice -n19 python3 scripts/verify_quarantine_duals.py \
  --ai-root /ai-data \
  --wave prune-2026-08-01 \
  --coverage-pct 95 \
  --write --johnny-chipper
```

- Largest files first until coverage target of logical bytes.  
- Join full SHA256 to live `models/`.  
- **Purge only `proven_match`.** Hold **orphans**.

## Host law

| Host | Full-pool hash / deepscan |
|------|---------------------------|
| **NAS host** | Yes — `/mnt/ai-data` local |
| Mac workstation / GPU worker | Local disks only; use catalog, not NFS deepwalk |
| Agents | Structure inventory / catalog only |

## Living catalog (Johnny)

Domain map: `config/ai_data_catalog_domains.json` (models, SM, pinokio, comfy, github, work, quarantine).

Near-term flat layout:

```text
work/catalog/johnny-chipper/
  domains/<domain>/latest.json
  duals/<date>/candidates.json
  quarantine/<wave>/verify.json
  jobs/<job_id>.json
```

`fast-models` / pool tops = **what exists**; Johnny indexes digests; CHIPPER schedules H/I/S jobs; bees stays L3 underneath.

## bees (L3)

- Resize hash table only if occupancy ≳ 0.90–0.95 **after a full re-crawl** (HOWTO).  
- Prefer L2 dual reduction when reclaimable sha256 duals dominate.  
- No auto-resize from cron.

## Tool map

| Script | Role |
|--------|------|
| `scripts/lib/dedup_engine.py` | Ladder core + escalate |
| `scripts/deepscan_models_dedup.py` | Models L2 audit (`--escalate-full`) |
| `scripts/deepscan_ai_data_dedup.py` | Non-model buckets |
| `scripts/verify_quarantine_duals.py` | Stratified quarantine vs live |
| `scripts/apply_models_dedup.py` | Gated symlink/quarantine (sha256) |
| `scripts/catalog_ai_data_models.py` | Sidecar catalog / `--johnny-chipper` |
| `scripts/ai_data_structure_inventory.py` | Safe L0 walk |

## Nightly (NAS host)

Existing: `ai_data_dedup_audit_cron.sh` (report-only). Prefer:

```bash
ionice -c3 nice -n 19 python3 scripts/deepscan_ai_data_dedup.py \
  --root /mnt/ai-data --write --escalate-full --max-escalate-gb 80
```

On new quarantine wave: run `verify_quarantine_duals.py` before any `rm -rf`.
