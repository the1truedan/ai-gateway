# Capacity Agent

Authenticated, read-only host telemetry for the Manager Orchestrator. It reports
normalized CPU load, memory pressure, NVIDIA utilization/VRAM when available,
and an optional in-flight count. It does not start, stop, or mutate model
servers.

Run natively so the readings describe the host rather than a container:

```sh
CAPACITY_AGENT_TOKEN=... CAPACITY_AGENT_HOST_ID=mac-client \
  python3 -m services.capacity_agent.app
```

The orchestrator reads `GET /capacity` on port `8794`; `GET /healthz` is
unauthenticated. Ports `8791` and `8793` remain reserved for vision and AIDA
form fill.
