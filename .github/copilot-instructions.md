# Copilot Instructions for raspberry-pi-docker (AI agents)

## What this is
- Raspberry Pi home automation + monitoring stack orchestrated by `docker-compose.yml`; services live under `grafana/`, `prometheus/`, `nginx-proxy-manager/`, `mosquitto/`, `homeassistant/`, `cloudflared/`, `influxdb/`, and new `influxdb3-core` + `influxdb3-explorer` services.
- Core data flow: ESP8266/ESP32 sensors → InfluxDB 2.7 (8086) and/or InfluxDB 3 Core (8181) → Grafana dashboards (3000); Prometheus/Loki/Promtail/cAdvisor/Node Exporter for system metrics; Nginx Proxy Manager + Cloudflare Tunnel for remote access.

## Non-negotiables
- Use `docker compose` (no hyphen) for all commands. Validate with `docker compose config -q` before applying.
- **Never commit `.env`**; it is gitignored. Use `.env.example` for placeholders; secrets are local only. Pre-commit hooks block `.env` commits.
- Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`). Run `./scripts/setup-git-hooks.sh` if hooks missing.

## Key files & locations
- Orchestration: `docker-compose.yml` (all services), `.env` (local secrets), `.env.example` (template).
- Grafana dashboards: `grafana/dashboards/*.json` (export/import via scripts; avoid manual edits when possible).
- Prometheus/Loki/Promtail configs: `prometheus/*.yml`.
- Nginx Proxy Manager hosts: `nginx-proxy-manager/data/nginx/proxy_host/*.conf` (numbered files, tracked in git).
- Docs: `docs/SETUP_GUIDE.md`, `docs/OPERATIONS_GUIDE.md`, `docs/INFLUXDB3_SETUP.md` (auth-required API usage), `MAKING_PUBLIC_CHECKLIST.md`.
- Scripts: `scripts/*.sh` (export/import/backup dashboards, validate secrets, status, update-all).

## InfluxDB specifics
- InfluxDB 2.7: init via env vars in compose using `.env` values. API on 8086.
- InfluxDB 3 Core (8181): **authentication required**. Create admin token inside container: `docker compose exec influxdb3-core influxdb3 create token --admin`; store in local `.env` as `INFLUXDB3_ADMIN_TOKEN` (do not commit). Explorer UI on 8888 (`MODE=admin`).
- **Telegraf bridge** (new): MQTT → InfluxDB 3 via `telegraf/telegraf.conf`; subscribes `homeassistant/sensor/+/state`, transforms JSON, writes to `homeassistant` bucket. Enable with `INFLUXDB3_ADMIN_TOKEN` in `.env` and `docker compose up -d telegraf`.
- Grafana datasource for v3: use FlightSQL, URL `http://influxdb3-core:8181`; bearer token if accessed externally.

## Workflows / common commands
- Start/stop: `docker compose up -d [services]`, `docker compose down`.
- Logs: `docker compose logs -f <service>`; status: `./scripts/status.sh` or `docker compose ps`.
- Dashboards: export/import via `./scripts/export_grafana_dashboards.sh` / `./scripts/import_grafana_dashboards.sh`; backup via `./scripts/backup_grafana_dashboards.sh`.
- Secrets check: `./scripts/validate_secrets.sh` (requires `.env`).
- Service restart examples: `docker compose restart grafana`, `docker compose restart influxdb3-core`.

## Nginx Proxy Manager pattern
- Host configs live in `nginx-proxy-manager/data/nginx/proxy_host/*.conf`; each file = one host; numbered sequentially. Add/modify, then reload: `docker compose exec -T nginx-proxy-manager nginx -s reload`. Test with `curl -H "Host: domain" http://localhost:8080/`. Commit the numbered file (force-add if needed).

## Conventions / style
- Shell: `#!/bin/bash`, `set -e` (or `set -euo pipefail`), 2-space YAML, keep JSON dashboards as exported (avoid reformatting).
- Network: all services on `monitoring` bridge unless otherwise noted; refer to services by container name (`http://influxdb:8086`, `http://influxdb3-core:8181`, etc.).
- Avoid embedding real tokens in docs; use placeholders like `apiv3_EXAMPLE_TOKEN...`.

## Pitfalls to avoid
- Do not use `docker-compose` binary; use `docker compose` v2.
- `.env` must stay local; ensure not staged. Pre-commit hooks will warn, but double-check.
- When editing dashboards JSON, preserve structure/ids; prefer exporting via Grafana scripts instead of hand edits.
- InfluxDB 3 API calls fail without bearer token; always include `Authorization: Bearer <token>`.

## Helpful references
- `docs/INFLUXDB3_SETUP.md` for tested auth + API examples.
- `docs/OPERATIONS_GUIDE.md` and `docs/SETUP_GUIDE.md` for end-to-end procedures.
- `MAKING_PUBLIC_CHECKLIST.md` for sanitization steps if sharing.
