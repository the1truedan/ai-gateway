# AgentsView — Tower standalone stack

Independent compose project for the 24/7 AgentsView session-index archive.
Deliberately **not** merged into `repo/docker-compose.yml` or
`deploy/tower-orchestration/docker-compose.yml` — Tower already runs those two
side by side, sharing the `manager-orchestration` Docker network/project name
without either depending on the other. This stack follows the same pattern:
its own file, own lifecycle, same shared network so it's reachable like every
other Tower service.

Services and host ports:

- `tower-agentsview` (AgentsView `pg serve`, read-only web UI/API): `42100`
- `tower-agentsview-db` (Postgres, dedicated — not shared with `litellm-db`): internal only

## Deploy / update

```sh
cd /mnt/user/appdata/manager-orchestration/repo/deploy/agentsview
docker compose -p manager-orchestration up -d --build
```

Never run a broad Compose command from `/mnt/user/appdata` — always `cd` into
this directory first, and this command only ever touches `tower-agentsview`
and `tower-agentsview-db` (it will attach to the existing `manager-orchestration`
network without recreating it).

## Teardown (fully reversible)

```sh
cd /mnt/user/appdata/manager-orchestration/repo/deploy/agentsview
docker compose -p manager-orchestration down
```

This does not touch the shared `manager-orchestration` network or any other
stack's containers.

## First boot

1. Copy `.env.example` to `.env` in this directory, fill in
   `AGENTSVIEW_DB_PASSWORD` with a fresh random value. Root-owned, mode `600`,
   matching the sibling `tower-orchestration/.env` convention. Never commit.
2. `docker compose -p manager-orchestration up -d --build`
3. Confirm both containers healthy: `docker ps --filter name=tower-agentsview`
4. Read the auto-generated API auth token (needed by browser/API clients, not
   by `pg push` edges): `docker exec tower-agentsview cat /data/config.toml`
5. Point m4rv and mrgpu's `agentsview` install at
   `AGENTSVIEW_PG_URL=postgresql://agentsview:<password>@192.168.1.2:5433/agentsview`
   (Postgres is published on host port `5433`, not the plain `5432` other
   Tower services avoid — password-auth only, LAN/VPN reach, never forwarded
   to the internet).
6. Browse `http://192.168.1.2:42100/` from any LAN host — day/week filters
   only, year view is still known to freeze the browser (unchanged upstream
   limitation, unrelated to this migration).

See `docs/operations/AGENTSVIEW_TOWER_POSTGRES_MIGRATION_2026-08-06.md` for
the full design and `docs/operations/LOCAL_INFRA.md` for the fleet's port map.
