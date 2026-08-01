# Gateway integration and completeness matrix

The M4 Mac is the sole manager. The canonical inference path is any local
client → local Headroom `:8787` → M4 Manager Orchestrator `:8790` → M4 LiteLLM
`:4000` → the selected raw worker LiteLLM `:4000`. Worker Headroom instances
point to the M4 manager; workers never dispatch through one another.

| Area | Current state | Canonical integration | Completion gate |
|---|---|---|---|
| LiteLLM Mac | Central bus and 90-day metadata-only Postgres ledger; local and raw worker aliases | Sole inference bus; mac-client target for Metal/macOS | Static routes, central call row, routing metadata, local role smoke |
| LiteLLM gpu-host | Local/NVIDIA worker aliases; cloud credentials blank; raw authenticated `:4000` | Primary CUDA execution/reasoning worker | RTX and PHI smokes; host capacity reports nonzero GPU load |
| NAS-HOST worker | Open WebUI/history retained; small/vision LiteLLM and P2000 Ollama retained | Lightweight/vision worker; old manager is rollback-only | P2000 smoke; Mac central row; no `fast-models` restart |
| Capacity | Authenticated `:8794` host agents | CPU/RAM/GPU saturation gates placement | All endpoints healthy; unavailable hosts fail closed; cloud requires explicit selection |
| AIDA | Implemented watch/OCR/remediation pipeline; NFS ingest; local-default model | Call host LiteLLM with `role-phi-local`; never route through automatic cloud | Health, one-document smoke, PHI failure test, veraPDF/HITL gaps documented |
| Memory | Botmem Compose profile plus Hippo/Hister client work is present but optional | Keep personal, agent, and search memory stores separate; inject retrieved context before Headroom | Health per enabled store; local embeddings; no cloud fallback for memory data |
| Security | Prompt I/O guardrail and optional LLMTrace profile are present | Privacy classification occurs before routing; LiteLLM guardrail remains defense-in-depth | PHI cloud-block test, prompt-injection smoke, redacted logs, fail-open/closed policy recorded |
| Observability | LiteLLM Postgres/Prometheus/Grafana and prompt-I/O dashboard scaffolding exist | Join dispatcher route ID with host LiteLLM call ID; store metadata, not sensitive bodies | Metrics scrape, spend row, route metadata, dashboard import, retention check |

## Python and NFS policy

- Use `uv` for locking, running tests, and installing host tools.
- Set `UV_CACHE_DIR` to `/Volumes/ai-data/uv-cache` on Mac and
  `/mnt/ai-data/uv-cache` on Linux.
- `scripts/uv_env.sh` assigns per-host subdirectories (`mac-client`, `gpu-host`,
  `nas-host`) beneath that shared cache root to avoid NFS ownership collisions.
- Keep `.venv`, tool installs, SQLite, Postgres, queues, and Git worktrees on
  host-local storage. The shared NFS directory is a download/build cache only.
- Linux Compose maps `uv-cache`, `models`, and `codebase-mirror` to stable
  `/shared/...` paths. Model/code mirrors are read-only except each host's
  dedicated Ollama subdirectory; NAS-HOST binds its local `/mnt/ai-data` path and
  does not loop back through NFS. mac-client host tools use `/Volumes/ai-data`, while
  Docker Desktop mounts the same export through Docker-managed NFSv3 volumes
  (the required Mac workaround) at the same `/shared/...` container paths.
- Source `scripts/uv_env.sh`, then use `uv run python ...` for repository tools.

Run `uv run python scripts/check_manager_topology.py` and
`uv run python scripts/check_node_parity.py --static-only` before a commit
and the runtime form after deployment. Loopback endpoints always use
`localhost`, never `127.0.0.1`.
