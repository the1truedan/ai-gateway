# NAS-HOST worker and manager rollback

This is a separate Unraid Compose project. It must never be combined with or
used to operate the `fast-models` storage project.

Services and host ports:

- Open WebUI: `3001`
- Headroom: `8787`
- Manager Orchestrator: `8790` (`rollback` profile only)
- LiteLLM proxy and Admin UI: `4000`
- Postgres: internal only
- NAS-HOST Ollama P2000 endpoint: `11435` (small models only)
- OpenCV 5 preprocessing: `8795`
- Capacity agent: `8794`

NAS-HOST's P2000 runs only small Ollama models for lightweight and vision jobs,
with OpenCV 5 providing CPU preprocessing. M4 LiteLLM calls this worker's raw,
authenticated `:4000` endpoint.

All user-facing clients connect to their host-local Headroom at
`http://localhost:8787/v1` and default to `role-auto`. NAS-HOST Headroom forwards
to the M4 manager at `<mac-client-ip>:8790`. M4 LiteLLM/Postgres is the central
request/token ledger. NAS-HOST's old orchestrator and database remain recoverable
during soak, but the orchestrator starts only with `--profile rollback`.

Persistent state is local Unraid appdata under
`/mnt/user/appdata/manager-orchestration`. The NFS model pool is not used for
SQLite, queues, or service databases.

Always capture the `fast-models` container ID, start time, restart count, and
health before deployment and compare them afterward. Use only:

```sh
docker compose -p manager-orchestration up -d --build
```

Never run a broad Compose command from `/mnt/user/appdata`.
