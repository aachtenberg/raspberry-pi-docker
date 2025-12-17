# Copilot Instructions for raspberry-pi-docker (AI agents)

## What this is
- Raspberry Pi monitoring stack orchestrated by `docker-compose.yml`; services live under `prometheus/`, `nginx-proxy-manager/`, `mosquitto/`, `cloudflared/`, `influxdb/`, `influxdb3-core`, `influxdb3-explorer`, and `telegraf/`.
- Core data flow: ESP8266/ESP32 sensors → MQTT (1883) → Telegraf → InfluxDB 3 Core (8181) → **Grafana Cloud** (via pdc-agent); Prometheus/cAdvisor/Node Exporter for system metrics; Nginx Proxy Manager + Cloudflare Tunnel for remote access.
- **Note**: Local Grafana container has been **removed**. All visualization via Grafana Cloud using `pdc-agent` (Private Data Center agent) to ship metrics for public dashboard sharing and alerting capabilities. InfluxDB 3 Core doesn't support public dashboard sharing with local Grafana.

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

## InfluxDB specifics
- InfluxDB 2.7: init via env vars in compose using `.env` values. API on 8086.
- InfluxDB 3 Core (8181): **authentication required**. Create admin token inside container: `docker compose exec influxdb3-core influxdb3 create token --admin`; store in local `.env` as `INFLUXDB3_ADMIN_TOKEN` (do not commit). Explorer UI on 8888 (`MODE=admin`).
- **Telegraf bridge** (new): MQTT → InfluxDB 3 via `telegraf/telegraf.conf`; subscribes `homeassistant/sensor/+/state`, transforms JSON, writes to `homeassistant` bucket. Enable with `INFLUXDB3_ADMIN_TOKEN` in `.env` and `docker compose up -d telegraf`.
- Grafana datasource for v3: use FlightSQL, URL `http://influxdb3-core:8181`; bearer token if accessed externally.

## Workflows / common commands
- Start/stop: `docker compose up -d [services]`, `docker compose down`.
- Logs: `docker compose logs -f <service>`; status: `./scripts/status.sh` or `docker compose ps`.
- Dashboards: Managed in Grafana Cloud (dashboards.grafana.com). Legacy local exports in `grafana/dashboards/*.json`.
- Backup/restore: `sudo bash ./scripts/backup_to_nas.sh` (manual), automated daily at 3 AM via systemd; restore: `sudo bash ./scripts/restore_from_nas.sh`. See `docs/BACKUP_GUIDE.md`.
- Secrets check: `./scripts/validate_secrets.sh` (requires `.env`).
- Service restart examples: `docker compose restart pdc-agent`, `docker compose restart influxdb3-core`, `docker compose restart telegraf`.

## Nginx Proxy Manager pattern
- Host configs live in `nginx-proxy-manager/data/nginx/proxy_host/*.conf`; each file = one host; numbered sequentially. Add/modify, then reload: `docker compose exec -T nginx-proxy-manager nginx -s reload`. Test with `curl -H "Host: domain" http://localhost:8080/`. Commit the numbered file (force-add if needed).

## Conventions / style
- Shell: `#!/bin/bash`, `set -e` (or `set -euo pipefail`), 2-space YAML, keep JSON dashboards as exported (avoid reformatting).
- Network: all services on `monitoring` bridge unless otherwise noted; refer to services by container name (`http://influxdb:8086`, `http://influxdb3-core:8181`, etc.).
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

## Grafana Cloud migration notes
- **Local Grafana container is deprecated** (still running but not primary visualization).
- Using **Grafana Cloud** for dashboards and alerting (reason: InfluxDB 3 Core + local Grafana doesn't support public dashboard sharing; didn't want to downgrade to InfluxDB 2).
- **pdc-agent** (Grafana Private Data Center agent) ships local metrics to Grafana Cloud.
- PDC agent config: `GRAFANA_PDC_TOKEN`, `GRAFANA_PDC_CLUSTER`, `GRAFANA_PDC_GCLOUD_HOSTED_GRAFANA_ID` in `.env`.
- Dashboards managed at: https://dashboards.grafana.com (or your Grafana Cloud instance).
- Future: Can leverage Grafana Cloud alerting capabilities.

## Helpful references
- `docs/INFLUXDB3_SETUP.md` for tested auth + API examples.
- `docs/OPERATIONS_GUIDE.md` and `docs/SETUP_GUIDE.md` for end-to-end procedures.
- `docs/BACKUP_GUIDE.md` for complete backup/restore/disaster recovery procedures.
- `docs/influxv3-sql-example.json` for working temperature dashboard panel JSON reference (legacy local Grafana).
- `MAKING_PUBLIC_CHECKLIST.md` for sanitization steps if sharing.
