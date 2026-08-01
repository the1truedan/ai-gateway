# Unraid migration prep (Open WebUI + Prometheus + Grafana + Hister)

**Status:** prep only — **no cutover** · **no split-brain**  
**Active writer (production):** **Mac** Open WebUI `http://127.0.0.1:8080`  
**Last full grok.com ingest:** 2026-07-16 (see `import-data/openwebui_import_receipt_2026-07-16.json`)

---

## Policy (until cutover day)

| Rule | Detail |
|------|--------|
| Single writer | Only Mac OWUI writes `webui.db` |
| Unraid | May stage empty compose / appdata dirs; **do not** start a second OWUI that mounts a live copy of Mac DB |
| Hister | Same rule — Mac `:4433` is production until cutover |
| NFS TTL stage | Optional later (`/Volumes/ai-data/work/ttl-exports/…`); not required for Mac ingest |
| Env pin | Optional `GROK_HISTORY_EXPORT=…/prod-grok-backend.json` when re-importing |

---

## Mac production (current)

| Service | Port | Volume |
|---------|------|--------|
| open-webui | 8080 | `ai-gateway_open-webui-data` |
| litellm | 4000 | config bind-mount |
| litellm-db | internal only | `ai-gateway_litellm-postgres-data` (Admin UI / virtual keys) |
| prometheus | 9090 | `ai-gateway_prometheus-data` |
| grafana | 3000 | `ai-gateway_grafana-data` |
| hister | 4433 | `hister-data` (profile `search`) |

### LiteLLM Postgres (Admin UI)

LiteLLM Admin UI login and virtual keys **require Postgres**. Mac uses in-stack `litellm-db` (not Community Apps on nas-host) until cutover — same single-writer policy as Open WebUI.

| Phase | Postgres |
|-------|----------|
| Mac (now) | Compose service `litellm-db` on `ai-gateway` network; `DATABASE_URL` injected |
| Unraid cutover (preferred) | Same `litellm-db` service in Unraid compose; optional `pg_dump` from Mac |
| Unraid alt | Community Apps PostgreSQL with dedicated `litellm` DB — only for Unraid LiteLLM after Mac is stopped |

Do **not** point Mac LiteLLM at nas-host Postgres for daily use (coupling + split-brain risk).

**Re-ingest grok.com export (Mac only):**

```bash
cd ~/ai-gateway
set -a && source .env && set +a
export GROK_HISTORY_EXPORT="$HOME/Downloads/ttl/30d/export_data/<export-id>/prod-grok-backend.json"
export GROK_BUILD_CWD_FILTER="$HOME/ai-gateway:$HOME/grokcode"
./scripts/import/run_openwebui_import.sh --all --apply
```

---

## Live-safe prep on Unraid (OK anytime)

These do **not** create split-brain:

1. Sync `~/ai-gateway` repo to Unraid appdata (git clone / rsync **code only**, not Mac docker volumes).
2. Create dirs: `/mnt/user/appdata/ai-gateway/{open-webui,prometheus,grafana,hister}` (empty).
3. Copy `.env.example` → Unraid `.env`; set `OLLAMA_HOST_IP`, new or shared `LITELLM_MASTER_KEY` (document which).
4. `AI_GATEWAY_HOST_PROFILE=linux` + `docker-compose.linux.yml` dry-run parse.
5. Pull images: litellm, open-webui, prometheus, grafana, hister.
6. Optional: run LiteLLM-only stack on Unraid for LAN inference **without** starting OWUI (if desired).

**Do not yet:**

- Start Open WebUI on Unraid with a restored Mac DB while Mac OWUI still runs  
- Point browsers at both Mac and Unraid OWUI for daily use  
- Dual Prometheus scrape of the same app with two Grafana writers expecting one TSDB

---

## Cutover checklist (future — single maintenance window)

1. Final Mac import: `run_openwebui_import.sh --all --apply`  
2. Stop Mac: `open-webui` (+ optionally prometheus/grafana/hister)  
3. Backup Mac volumes → tarball → Unraid appdata  
4. Start Unraid stack with restored data  
5. Validate `:8080` / `:3000` / `:9090` / `:4433`  
6. Point clients (browser, pi, OpenCode, MCP `LITELLM_API_BASE`) at Unraid LAN IP  
7. Leave Mac OWUI **stopped** (or delete stack) — sole writer = Unraid  

Details: session plan `plan.md` Phase 2; earmarks `unraid-deploy`, `otel-litellm-dashboards`.

---

## Receipt

| Field | Value |
|-------|--------|
| Export | `~/Downloads/ttl/30d/export_data/<export-id>/prod-grok-backend.json` (size/count vary by export) |
| SQL | `import-data/sql/grokhistory.sql` + `grokcode.sql` (mtime 2026-07-16) |
| DB backup | `webui.db.bak-20260716-155216` (inside volume, at apply time) |
| Machine receipt | `import-data/openwebui_import_receipt_2026-07-16.json` |
