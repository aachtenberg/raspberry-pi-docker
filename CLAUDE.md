# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Raspberry Pi home automation infrastructure that receives, stores, and visualizes temperature data from multiple ESP8266/ESP32 devices. All services are orchestrated through a unified Docker Compose stack.

**Architecture**: ESP Devices (4) → MQTT/HTTP → InfluxDB 2.7 (8086) & InfluxDB 3 Core (8181) → Grafana/Home Assistant → Prometheus → Cloudflare Tunnel

## Project Structure

- **`~/docker/`** - Main infrastructure project (this repository)
- **`~/homeassistant/`** - Home Assistant configuration directory (external mount)
- **`~/docker/install/`** - TypeScript MCP (Model Context Protocol) server
- **Key files**:
  - `docker-compose.yml` - All service definitions
  - `.env` - Local secrets (gitignored, never commit)
  - `.env.example` - Template for environment variables
  - `grafana/dashboards/*.json` - Exported dashboard definitions
  - `nginx-proxy-manager/data/nginx/proxy_host/*.conf` - Numbered host config files

## Common Development Commands

### Docker Stack Management

All commands from `~/docker/`:

```bash
# Start/stop services
docker compose up -d [services]
docker compose down

# View status and logs
docker compose ps
docker compose logs -f [service-name]
./scripts/status.sh

# Restart specific service
docker compose restart [service-name]

# Update and restart
docker compose pull
docker compose up -d

# Validate config before applying
docker compose config -q
```

### Configuration Scripts

```bash
# Secrets and validation
./scripts/validate_secrets.sh

# Grafana dashboard management
./scripts/export_grafana_dashboards.sh
./scripts/import_grafana_dashboards.sh
./scripts/backup_grafana_dashboards.sh

# System maintenance
./scripts/update-all.sh
./scripts/backup.sh

# Git hooks
./scripts/setup-git-hooks.sh
```

### MCP Server Development

For TypeScript MCP server in `~/docker/install/`:

```bash
cd ~/docker/install
npm install
npm run build
npm run watch      # Auto-rebuild on changes
npm run inspector  # Debug with MCP Inspector
```

### InfluxDB 3 Core Token Management

```bash
# Create admin token for InfluxDB 3 Core
docker compose exec influxdb3-core influxdb3 create token --admin

# Store token in .env as INFLUXDB3_ADMIN_TOKEN
```

## Key Architecture Details

### Service Communication

Services use the `monitoring` bridge network (except those with `network_mode: host`). Communicate using container names:
- `http://influxdb:8086` (InfluxDB 2.7)
- `http://influxdb3-core:8181` (InfluxDB 3 Core - **requires authentication**)
- `http://grafana:3000`
- `http://prometheus:9090`

### InfluxDB Dual-Stack Architecture

**InfluxDB 2.7** (port 8086):
- Initialized via environment variables from `.env`
- Legacy database, stable and production-ready
- API access without mandatory authentication

**InfluxDB 3 Core** (port 8181):
- Next-generation time-series database
- **Authentication required** for all API calls
- Token generation: `docker compose exec influxdb3-core influxdb3 create token --admin`
- Store token in `.env` as `INFLUXDB3_ADMIN_TOKEN`
- Explorer UI on port 8888 (`MODE=admin`)

**Telegraf Bridge**:
- Bridges MQTT messages to InfluxDB 3 Core
- Config: `telegraf/telegraf.conf`
- Subscribes to `homeassistant/sensor/+/state` and `surveillance/+`
- Transforms JSON payloads to line protocol
- Requires `INFLUXDB3_ADMIN_TOKEN` in `.env`

### Services and Ports

| Service | Port(s) | Purpose |
|---------|---------|---------|
| InfluxDB 2.7 | 8086 | Time-series database for ESP sensor data |
| InfluxDB 3 Core | 8181 | Next-gen time-series database (evaluation/migration) |
| InfluxDB 3 Explorer | 8888 | Web UI for InfluxDB 3 Core |
| Grafana | 3000 | Dashboards and visualization |
| Prometheus | 9090 | Metrics collection |
| Node Exporter | 9100 | System metrics |
| cAdvisor | 8081 | Container metrics |
| Home Assistant | 8123 | Home automation |
| Mosquitto | 1883, 9001 | MQTT broker |
| Nginx Proxy Manager | 81, 8080, 8443 | Reverse proxy & SSL |
| Portainer | 9000, 9443 | Docker management UI |

### Environment Variables

All secrets stored in `~/docker/.env` (gitignored). Key variables:
- `CLOUDFLARE_TUNNEL_TOKEN` - Tunnel authentication
- `INFLUXDB_ADMIN_PASSWORD`, `INFLUXDB_ADMIN_TOKEN` - InfluxDB 2.7 credentials
- `INFLUXDB3_ADMIN_TOKEN` - InfluxDB 3 Core API token (required for auth)
- `INFLUXDB3_UI_SESSION_KEY` - UI session persistence
- `GRAFANA_API_KEY`, `GRAFANA_ADMIN_API_KEY` - Dashboard export/import

Always use `.env.example` as template for new variables.

### Nginx Proxy Manager Pattern

- Host configs in `nginx-proxy-manager/data/nginx/proxy_host/*.conf`
- Each file = one proxy host (numbered sequentially)
- Reload after changes: `docker compose exec -T nginx-proxy-manager nginx -s reload`
- Test with: `curl -H "Host: domain" http://localhost:8080/`
- Commit numbered config files (force-add if gitignored)

### Grafana Dashboard Development

**FlightSQL Query Best Practices** (for InfluxDB 3):
- Use `rawSql: true`, `rawQuery: true`, `editorMode: "builder"` in targets
- Time macros: `$__timeFrom` and `$__timeTo` (Grafana converts to milliseconds)
- Legend display: `displayName: "${__field.labels.deviceField}"` for dimension-based naming
- Color modes: `"color": { "mode": "thresholds" }` for value-based line coloring
- Transformations: `filterFieldsByName` + `organize` for multi-series timeseries
- Threshold colors: `"mode": "absolute"` with value steps
- Gauge panels: Match thresholds to timeseries, use `reduceOptions.calcs: ["lastNotNull"]`
- Legend tables: `displayMode: "table"`, add `calcs: ["min", "max", "median", "last"]`

**Dashboard Management**:
- Export via script (avoid manual edits): `./scripts/export_grafana_dashboards.sh`
- Import: `./scripts/import_grafana_dashboards.sh`
- Preserve structure/IDs when editing JSON
- Reference: `docs/influxv3-sql-example.json` for working panel examples

### Data Persistence

Docker volumes with pattern `docker_<service>-data`:
- `docker_influxdb-data` - InfluxDB 2.7 time-series data
- `docker_influxdb3-data` - InfluxDB 3 Core data
- `docker_grafana-data` - Dashboard configurations
- `docker_prometheus-data` - Metrics history

```bash
# Volume management
docker volume ls
docker volume inspect docker_influxdb-data

# Backup volume
docker run --rm -v docker_influxdb-data:/data -v ~/backups:/backup alpine tar czf /backup/influxdb-backup.tar.gz /data
```

## Development Workflows

### Git Conventions

- **Commits**: Conventional format (`feat:`, `fix:`, `docs:`, `chore:`)
- **Branch naming**: Use `feature/` or `feat/` prefix (e.g., `feat/mqtt-bridge`, `feature/dashboard-redesign`)
- **Pre-commit hooks**: Auto-installed via `./scripts/setup-git-hooks.sh`
- **Secrets protection**: Workflow validates no `.env` files committed; `.sql` files excluded from scan

### Docker Compose Best Practices

- Always use `docker compose` (v2, no hyphen) - never `docker-compose`
- Validate before applying: `docker compose config -q`
- Service naming convention: lowercase with hyphens
- Network: All services on `monitoring` bridge unless `network_mode: host` required

### Security Practices

- **Never commit `.env`** - gitignored and validated by pre-commit hooks
- Store all secrets in `.env`, use placeholders in `.env.example`
- No real tokens in docs - use format like `apiv3_EXAMPLE_TOKEN...`
- Repository designed to be safely shared publicly

## Troubleshooting

### Service Issues

```bash
# Check logs
docker compose logs [service-name]

# Restart service
docker compose restart [service-name]

# Recreate service
docker compose up -d --force-recreate [service-name]
```

### Port Conflicts

```bash
# Check port usage
sudo netstat -tulpn | grep :8086
sudo ss -tulpn | grep :8086
```

### InfluxDB 3 Authentication Errors

All InfluxDB 3 Core API calls require authentication:
```bash
# Verify token exists
echo $INFLUXDB3_ADMIN_TOKEN

# API call format
curl -H "Authorization: Bearer $INFLUXDB3_ADMIN_TOKEN" http://localhost:8181/api/v3/...
```

### Resource Cleanup

```bash
# Remove stopped containers
docker container prune

# Remove unused volumes (CAREFUL - data loss!)
docker volume prune
```

## Related Projects

- **ESP Temperature Sensors**: https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor
  - 4 deployed ESP8266/ESP32 devices sending data every 15 seconds
  - Separate PlatformIO project with own secrets management

## Documentation References

- `docs/SETUP_GUIDE.md` - Complete installation and configuration
- `docs/OPERATIONS_GUIDE.md` - Daily operations, monitoring, maintenance
- `docs/INFLUXDB3_SETUP.md` - InfluxDB 3 Core authentication and API usage
- `docs/SECRETS_SETUP.md` - Comprehensive secrets configuration
- `docs/influxv3-sql-example.json` - Working dashboard panel reference
- `MAKING_PUBLIC_CHECKLIST.md` - Sanitization steps for public sharing
