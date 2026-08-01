# Turnstone addition and Unraid observability migration

## Decision summary

- Grafana and Prometheus can be moved from the Mac Compose stack to Docker containers installed through Unraid Community Applications (CA). CA is a curated catalog of community-maintained containers, and Unraid stores container working files conventionally under the `appdata` share. The CA templates are not the data migration mechanism: install/configure the destination containers, stop writers, transfer the persistent data, then validate before removing the Mac instances. Sources: [Unraid Community Applications](https://docs.unraid.net/community-applications/), [Unraid shares](https://docs.unraid.net/unraid-os/using-unraid-to/manage-storage/shares/).
- The current stack persists Grafana at `/var/lib/grafana` in `grafana-data` and Prometheus at `/prometheus` in `prometheus-data`; `prometheus.yml` is a bind-mounted repository file. These are the assets that must move.
- Do not treat `ghcr.io/turnstonelabs/turnstone:stable` as a complete production service by itself. The image contains multiple executables, but Turnstone's official production topology uses PostgreSQL, console, Caddy, SearxNG, server, and optionally the channel gateway. A minimal gateway integration may run the `turnstone-server` role alone, but that omits the official shared-database console/discovery topology. Sources: [Turnstone Docker deployment](https://github.com/turnstonelabs/turnstone/blob/main/docs/docker.md), [official production Compose](https://raw.githubusercontent.com/turnstonelabs/turnstone/main/turnstone/deploy/compose.yaml), [official Dockerfile](https://raw.githubusercontent.com/turnstonelabs/turnstone/main/Dockerfile).

## Turnstone requirements relevant to ai-gateway

The stable release image is `ghcr.io/turnstonelabs/turnstone:stable`. Its default command starts `turnstone-server` on port 8080. Persist `/data`, mount the agent workspace at `/workspace`, and configure the bootstrap OpenAI-compatible backend with:

- `LLM_BASE_URL=http://headroom:8787/v1` when attached to the `ai-gateway` Docker network
- `OPENAI_API_KEY` set to the LiteLLM master key
- `MODEL=tier-nvidia-fast`
- `TURNSTONE_NODE_ID` and `TURNSTONE_ADVERTISE_URL` if joining the official console topology
- `TURNSTONE_SEARXNG_URL` if web search is wanted; the official stack supplies a private SearxNG service
- `SKIP_PERMISSIONS` only for explicitly trusted development use

The official production deployment requires strong `TURNSTONE_JWT_SECRET` and `POSTGRES_PASSWORD` values, shares the same PostgreSQL URL/JWT secret among roles, serves its console through Caddy at HTTPS port 8443, and recommends pinning the image tag. The user-requested `stable` tag is the documented production-grade release track, but a digest or numbered release is more reproducible. Sources: [Turnstone Docker deployment](https://github.com/turnstonelabs/turnstone/blob/main/docs/docker.md), [Turnstone PyPI release tracks](https://pypi.org/project/turnstone/).

## Unraid destination layout

Suggested CA template mappings on `<nas-host-ip>`:

| Container | Image | Host path | Container path | Port |
|---|---|---|---|---|
| Grafana | `grafana/grafana` | `/mnt/user/appdata/grafana` | `/var/lib/grafana` | `3000:3000` |
| Prometheus | `prom/prometheus` | `/mnt/user/appdata/prometheus/data` | `/prometheus` | `9090:9090` |
| Prometheus config | same | `/mnt/user/appdata/prometheus/config/prometheus.yml` | `/etc/prometheus/prometheus.yml` (read-only) | — |

Use a local cache/pool-backed filesystem for Prometheus data, not NFS: Prometheus explicitly does not support non-POSIX filesystems and advises against NFS for its local TSDB. Configure retention so it cannot consume the entire pool; Prometheus recommends a size limit no higher than roughly 80–85% of allocated disk. Source: [Prometheus storage](https://prometheus.io/docs/prometheus/latest/storage/).

The current scrape names (`litellm:4000`, `prompt-io:5050`, and `llmtrace:8080`) are Compose-network DNS names and will not resolve from independent Unraid containers. Replace them with reachable Mac addresses/ports, or attach exporters and Prometheus to a network where those names exist. Validate each target from the Unraid Prometheus container before cutover. After moving Grafana, change its Prometheus data-source URL to the Unraid Prometheus address/container name as appropriate.

## Low-risk migration sequence

1. Record the source and destination image versions. Avoid combining a host migration with an uncontrolled major-version upgrade; Prometheus 3 TSDB data cannot be read by versions older than 2.55. Source: [Prometheus 3 migration guide](https://prometheus.io/docs/prometheus/latest/migration/).
2. Install the CA Grafana and Prometheus templates but do not let empty destination data replace the source of truth. Configure the mappings above, matching environment variables and command flags from `docker-compose.yml`.
3. Copy `prometheus.yml` to the Unraid config path and rewrite/test the scrape targets for cross-host reachability.
4. Stop Grafana on the Mac before copying `grafana-data`. Grafana's default SQLite database is `/var/lib/grafana/grafana.db`, and Grafana requires shutdown for an integrity-safe SQLite backup. Copy all of `/var/lib/grafana`, including plugins, then ensure the Unraid bind mount is writable by the container user. Sources: [Grafana backup](https://grafana.com/docs/grafana/latest/administration/back-up-grafana/), [Grafana Docker persistence](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/).
5. For Prometheus, either stop the source container and copy the complete `/prometheus` directory, or enable the admin API temporarily and create/copy a TSDB snapshot. Prometheus recommends snapshots; ad-hoc live copies can lose recent head/WAL data. Source: [Prometheus storage](https://prometheus.io/docs/prometheus/latest/storage/), [Prometheus snapshot API](https://prometheus.io/docs/prometheus/latest/querying/api/#snapshot).
6. Start Unraid Prometheus first. Confirm `/api/v1/status/config`, Targets, historical queries, and current ingestion. Then start Grafana and confirm users, dashboards, data sources, plugins, and alert rules.
7. Keep the stopped Mac volumes as a rollback copy until the Unraid services have passed a retention-window-sized validation period. Only then disable/remove the Mac Compose services. Do not run both Prometheus instances against the same TSDB directory.

## Feasibility caveats

- CA listings are community templates with basic vetting, not first-party Grafana/Prometheus installers. Review the selected template's image, mappings, permissions, and support link before installation. Unraid preserves template settings in `/boot/config/plugins/dockerMan/templates-user`, but that does not back up application data. Source: [Unraid Community Applications](https://docs.unraid.net/community-applications/).
- Migration is operationally straightforward because both current services already use the official persistent container paths. The main work is safe data transfer, permissions, and changing network-dependent scrape/data-source URLs.
- No data was migrated by this document. Live migration should be done in a short maintenance window with backups and explicit post-copy validation.
