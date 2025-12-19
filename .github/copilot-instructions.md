# Copilot Instructions for raspberry-pi-docker (AI agents)

## What this is
- Raspberry Pi monitoring stack orchestrated by `docker-compose.yml`; services live under `prometheus/`, `nginx-proxy-manager/`, `mosquitto/`, `cloudflared/`, `influxdb3-core`, and `telegraf/`.
- Core data flow: ESP8266/ESP32 sensors → MQTT (1883) → Telegraf → InfluxDB 3 Core (8181) → **Grafana Cloud** (via pdc-agent); Prometheus/cAdvisor/Node Exporter for system metrics; Nginx Proxy Manager + Cloudflare Tunnel for remote access.
- **Note**: Using **InfluxDB 3 Core** (not v2) for time-series storage. Local Grafana container has been **removed**; all visualization via Grafana Cloud using `pdc-agent` (Private Data Center agent) for public dashboard sharing and alerting.

## Non-negotiables
- Use `docker compose` (no hyphen) for all commands. Validate with `docker compose config -q` before applying.
- **Never commit `.env`**; it is gitignored. Use `.env.example` for placeholders; secrets are local only. Pre-commit hooks block `.env` commits.
- Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`). Run `./scripts/setup-git-hooks.sh` if hooks missing.

## Key files & locations
- Orchestration: `docker-compose.yml` (all services), `.env` (local secrets), `.env.example` (template).
- Grafana dashboards: `grafana/dashboards/*.json` (legacy local Grafana exports; now using Grafana Cloud).
- Prometheus configs: `prometheus/prometheus.yml`.
- Telegraf config: `telegraf/telegraf.conf` (MQTT → InfluxDB 3 bridge).
- Nginx Proxy Manager hosts: `nginx-proxy-manager/data/nginx/proxy_host/*.conf` (numbered files, tracked in git).
- Backup: `scripts/backup_to_nas.sh` (automated daily at 3 AM), `scripts/restore_from_nas.sh`; NAS persistently mounted at `/mnt/nas-backup`.
- Docs: `docs/SETUP_GUIDE.md`, `docs/OPERATIONS_GUIDE.md`, `docs/INFLUXDB3_SETUP.md`, `docs/BACKUP_GUIDE.md` (complete backup/restore procedures), `MAKING_PUBLIC_CHECKLIST.md`.
- Scripts: `scripts/*.sh` (backup/restore, validate secrets, status, update-all).

## InfluxDB 3 Core specifics
- **Authentication required**: Create admin token inside container: `docker compose exec influxdb3-core influxdb3 create token --admin`; store in local `.env` as `INFLUXDB3_ADMIN_TOKEN` (do not commit).
- **API endpoint**: Port 8181 (HTTP); metrics at `/metrics` (for Prometheus scraping with bearer auth).
- **Telegraf bridge**: MQTT → InfluxDB 3 via `telegraf/telegraf.conf`; subscribes `homeassistant/sensor/+/state`, transforms JSON, writes to `homeassistant` bucket. Enable with `INFLUXDB3_ADMIN_TOKEN` in `.env` and `docker compose up -d telegraf`.
- **Grafana datasource**: Use FlightSQL plugin, URL `http://influxdb3-core:8181`; requires bearer token for external access.
- **Networking**: Must be on `monitoring` bridge network (not host mode) for DNS resolution from other containers.

## Workflows / common commands
- Start/stop: `docker compose up -d [services]`, `docker compose down`.
- Logs: `docker compose logs -f <service>`; status: `./scripts/status.sh` or `docker compose ps`.
- Dashboards: Managed in Grafana Cloud (dashboards.grafana.com). Upload via `./scripts/create_grafana_dashboard.sh <json-file> [folder]`; uses `GRAFANA_CLOUD_API_KEY` from `.env`. Legacy local exports in `grafana/dashboards/*.json`.
- Backup/restore: `sudo bash ./scripts/backup_to_nas.sh` (manual), automated daily at 3 AM via systemd; restore: `sudo bash ./scripts/restore_from_nas.sh`. See `docs/BACKUP_GUIDE.md`.
- Secrets check: `./scripts/validate_secrets.sh` (requires `.env`).
- Service restart examples: `docker compose restart pdc-agent`, `docker compose restart influxdb3-core`, `docker compose restart telegraf`.

## Tool discovery philosophy
- **Always check `scripts/` directory first** before manually implementing tasks; many operations have dedicated scripts with proper error handling and correct environment variables.
- When user asks for an operation (e.g., "upload dashboard", "backup data"), search for existing scripts before writing manual commands.
- Existing scripts often use the correct API keys/tokens from `.env`; manual curl commands may use wrong/deprecated variables.
- Common mistake: Using `GRAFANA_API_KEY` or `GRAFANA_ADMIN_API_KEY` instead of the correct `GRAFANA_CLOUD_API_KEY` that scripts actually use.

## Environment Variables (Canonical)
- Grafana Cloud
	- `GRAFANA_CLOUD_URL`: Base URL of the instance, e.g. https://aachten.grafana.net
	- `GRAFANA_CLOUD_API_KEY`: Service Account token used by scripts (minimum: dashboard write via API). Used by `scripts/create_grafana_dashboard.sh` for folders and dashboard upserts.
	- `GRAFANA_PDC_TOKEN`, `GRAFANA_PDC_CLUSTER`, `GRAFANA_PDC_GCLOUD_HOSTED_GRAFANA_ID`: Required by `pdc-agent` to ship Prometheus metrics to Grafana Cloud.

- InfluxDB 3 Core
	- `INFLUXDB3_ADMIN_TOKEN`: Required for Telegraf writes and authenticated metrics scraping; generated inside the container. Do not commit.

- AI Monitor / Prometheus (selected)
	- `PROMETHEUS_URL` (default `http://prometheus:9090`) for `ai-monitor`.
	- `AI_MONITOR_*` knobs for cadence, execution, allowlist, etc. (see `ai-monitor/monitor.py`).
	- `AI_MONITOR_HTTP_CHECKS`: Synthetic HTTP checks for app-level monitoring. Format: semicolon-separated list of checks. Each check: `url|expected_status_code[|Header=value]`. Example: `http://nginx-proxy-manager:81|200;http://app:8080|200|Authorization=Bearer%20token`. Results published as Prometheus metrics `ai_http_check_ok{target="..."}` (0=fail, 1=pass) and `ai_http_check_latency_ms{target="..."}`. LLM triage triggered on state changes (OK→FAIL).

### Deprecated/Do Not Use
- `GRAFANA_API_KEY`, `GRAFANA_ADMIN_API_KEY`, `GRAFANA_TOKEN` — not used by any current scripts. Use `GRAFANA_CLOUD_API_KEY` instead.

### Required patterns
- Dashboard uploads: always use `./scripts/create_grafana_dashboard.sh <json> [folder]` which reads `GRAFANA_CLOUD_API_KEY` and wraps payloads correctly for `/api/dashboards/db`.
- Never put secrets in repo; `.env` is local-only and ignored. Use `.env.example` placeholders if documenting.

## Nginx Proxy Manager pattern
- Host configs live in `nginx-proxy-manager/data/nginx/proxy_host/*.conf`; each file = one host; numbered sequentially. Add/modify, then reload: `docker compose exec -T nginx-proxy-manager nginx -s reload`. Test with `curl -H "Host: domain" http://localhost:8080/`. Commit the numbered file (force-add if needed).

## Conventions / style
- Shell: `#!/bin/bash`, `set -e` (or `set -euo pipefail`), 2-space YAML, keep JSON dashboards as exported (avoid reformatting).
- Network: all services on `monitoring` bridge unless otherwise noted; refer to services by container name (`http://influxdb3-core:8181`, `http://prometheus:9090`, etc.).
- Avoid embedding real tokens in docs; use placeholders like `INFLUXDB3_TOKEN_PLACEHOLDER...`.
- **Git branches**: Use `feature/` or `feat/` prefix for feature branches (e.g., `feature/mqtt-bridge`, `feat/dashboard-redesign`). Branch names trigger secrets workflow and pre-commit hooks for validation.

## Pitfalls to avoid
- Do not use `docker-compose` binary; use `docker compose` v2.
- `.env` must stay local; ensure not staged. Pre-commit hooks will warn, but double-check.
- When editing dashboards JSON, preserve structure/ids; prefer exporting via Grafana scripts instead of hand edits.
- InfluxDB 3 API calls fail without bearer token; always include `Authorization: Bearer <token>`.

## Grafana + InfluxDB 3 FlightSQL queries: best practices
- **Panel format**: Use `rawSql: true`, `rawQuery: true`, `editorMode: "builder"` for FlightSQL queries in targets.
- **Time macros**: Use `$__timeFrom` and `$__timeTo` in WHERE clauses; Grafana converts to milliseconds for InfluxDB 3.
- **Legend display**: Use field overrides with `displayName: "${__field.labels.deviceField}"` syntax for dimension-based naming. Use `"color": { "mode": "thresholds" }` for value-based line coloring.
- **Transformations**: For multi-series timeseries, apply `filterFieldsByName` (to keep time/dimensions/values) + `organize` (to reorder columns and ensure proper grouping).
- **Threshold colors**: Use `"mode": "absolute"` with value steps; e.g., `{ "value": 25, "color": "orange" }, { "value": 31, "color": "red" }` for temperature banding.
- **Panel transparency**: Set `"transparent": true` on panels for cleaner dark theme integration.
- **Gauge panels**: Match thresholds to timeseries thresholds for visual consistency; use `reduceOptions.calcs: ["lastNotNull"]` to always show latest value.
- **Legend tables**: Set `displayMode: "table"`, add `calcs: ["min", "max", "median", "last"]`, and include in `values` array for multi-column legend display.
- **Device grouping**: When selecting time, device, and value fields from FlightSQL, device becomes a natural dimension; hide it with `custom.hideFrom: { legend: true }` to avoid legend pollution.

## Backup system
- **Automated backups**: Daily at 3:00 AM via systemd timer (`docker-backup.timer`).
- **NAS mount**: Persistent via `/etc/fstab` at `/mnt/nas-backup` (//192.168.0.1/G).
- **What's backed up**: Docker volumes (Grafana-legacy, Prometheus, InfluxDB3, Portainer, Mosquitto), bind-mounted directories (Home Assistant, Nginx Proxy Manager), repository configs, `.env` file.
- **What's NOT backed up**: Docker images (pulled fresh), containers (rebuilt from compose), networks (from compose definition).
- **Retention**: 30 days automatic cleanup.
- **Scripts**: `scripts/backup_to_nas.sh`, `scripts/restore_from_nas.sh`.
- **Docs**: `docs/BACKUP_GUIDE.md` (complete backup/restore/disaster-recovery guide).

## Raspberry Pi Topology (Current)
- **Pi 1 (raspberrypi.local @ 192.168.0.167)**: Monitoring stack (Prometheus, InfluxDB 3 Core, Telegraf, Mosquitto), Nginx Proxy Manager, Cloudflare Tunnel, PDC agent.
- **Pi 2 (raspberrypi2.local @ 192.168.0.147)**: Camera Dashboard stack (PostgreSQL, Node.js API, Web UI, SFTP, Mediamtx). Volumes at `/storage`; NAS mounted at `/mnt/nas-backup`.
- **Pi 3 (raspberrypi3.local @ 192.168.0.248)**: Idle/standby for scaling.
- **All**: Cabled to router; `/mnt/nas-backup` Samba mount for shared backups and surveillance captures.

## SSH & User Conventions
- **Username**: `aachten` (SSH equivalence configured on all Pis).
- **Reference /etc/hosts** for hostname → IP mappings when connecting remotely.
- **Storage on Pi 2**: Use `/storage` for volumes (e.g., camera-dashboard at `/storage/camera-dashboard`).

## Camera Dashboard Integration
- **Plan**: See `docs/SURVEILLANCE_DASHBOARD_PLAN.md` in raspberry-pi-docker for complete phased rollout (Phases 0–10).
- **Repo**: `camera-dashboard` (https://github.com/aachtenberg/camera-dashboard.git) cloned to `/storage/camera-dashboard/` on Pi 2.
- **Services**: PostgreSQL, Express API (`/api`), web UI (`/`), SFTP (port 2222), Mediamtx (HLS/WebRTC on port 8888).
- **NPM vhost**: Pi 1's Nginx Proxy Manager proxies `/`, `/api`, `/streams/*` to Pi 2 stack.
- **MQTT → Telegraf → InfluxDB 3**: Camera motion events flow to Grafana Cloud analytics.
- **Image storage**: `/mnt/nas-backup/surveillance/captures/{device}/` shared across Pis via Samba.

## Grafana Cloud architecture
- **Local Grafana container removed**; all visualization via Grafana Cloud.
- Using **Grafana Cloud** for dashboards and alerting (reason: InfluxDB 3 Core requires FlightSQL datasource which works better with Grafana Cloud for public dashboard sharing).
- **pdc-agent** (Grafana Private Data Center agent) ships local Prometheus metrics to Grafana Cloud.
- PDC agent config: `GRAFANA_PDC_TOKEN`, `GRAFANA_PDC_CLUSTER`, `GRAFANA_PDC_GCLOUD_HOSTED_GRAFANA_ID` in `.env`.
- Dashboards managed at: https://aachten.grafana.net (your Grafana Cloud instance).
- Upload dashboards: `./scripts/create_grafana_dashboard.sh <json-file> [folder]` using `GRAFANA_CLOUD_API_KEY` from `.env`.

## Helpful references
- `docs/INFLUXDB3_SETUP.md` for tested auth + API examples.
- `docs/OPERATIONS_GUIDE.md` and `docs/SETUP_GUIDE.md` for end-to-end procedures.
- `docs/BACKUP_GUIDE.md` for complete backup/restore/disaster recovery procedures.
- `docs/SURVEILLANCE_DASHBOARD_PLAN.md` for camera dashboard phased implementation plan.
- `docs/influxv3-sql-example.json` for working temperature dashboard panel JSON reference (legacy local Grafana).
- `MAKING_PUBLIC_CHECKLIST.md` for sanitization steps if sharing.
