# Copilot Instructions for raspberry-pi-docker

## Project Overview

This is a Raspberry Pi home automation and monitoring infrastructure using Docker Compose. It collects temperature data from 4 ESP8266/ESP32 devices and provides visualization, monitoring, and remote access.

## Architecture

```
ESP Devices (4) → InfluxDB → Grafana Dashboards
                      ↓
               Prometheus Stack → System Monitoring
                      ↓
              Cloudflare Tunnel → Remote Access
```

## Key Services

| Service | Port | Purpose |
|---------|------|---------|
| InfluxDB | 8086 | Time-series database for sensor data |
| Grafana | 3000 | Dashboards and visualization |
| Prometheus | 9090 | Metrics collection |
| Home Assistant | 8123 | Home automation |
| Mosquitto | 1883 | MQTT broker |

## Important Guidelines

### Docker Commands
- **Always use `docker compose`** (without hyphen), NOT `docker-compose`
- Example: `docker compose up -d`, `docker compose logs -f`

### Secrets Management
- **Never commit `.env` file** - it contains real credentials
- All secrets are in `.env` (gitignored)
- Use `.env.example` for templates with placeholder values
- Run `./scripts/validate_secrets.sh` to check configuration

### File Locations
- **Main config**: `docker-compose.yml`
- **Environment**: `.env` (secrets), `.env.example` (template)
- **Grafana dashboards**: `grafana/dashboards/*.json`
- **Prometheus config**: `prometheus/prometheus.yml`
- **Documentation**: `docs/SETUP_GUIDE.md`, `docs/OPERATIONS_GUIDE.md`

### Scripts
- `./scripts/export_grafana_dashboards.sh` - Export dashboards (needs `GRAFANA_API_KEY`)
- `./scripts/import_grafana_dashboards.sh` - Import dashboards
- `./scripts/backup_grafana_dashboards.sh` - Auto backup + git commit
- `./scripts/validate_secrets.sh` - Validate `.env` configuration
- `./scripts/status.sh` - Check service status
- `./scripts/setup-git-hooks.sh` - Install Git pre-commit hooks

### Grafana Operations
```bash
# Export dashboards
source .env && GRAFANA_API_KEY=$GRAFANA_API_KEY ./scripts/export_grafana_dashboards.sh

# Import dashboard via API
source .env && curl -X POST \
  -H "Authorization: Bearer $GRAFANA_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d @grafana/dashboards/dashboard.json \
  "http://localhost:3000/api/dashboards/db"
```

### Prometheus Metrics
- InfluxDB metrics: `http://localhost:8086/metrics`
- Node metrics: `http://localhost:9100/metrics`
- Container metrics: `http://localhost:8081/metrics`

### Git Workflow
- Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`
- Pre-commit hooks validate docker compose syntax and block `.env` commits
- Always backup dashboards before/after changes

### Common Tasks

**Restart a service:**
```bash
docker compose restart grafana
```

**View logs:**
```bash
docker compose logs -f influxdb
```

**Update containers:**
```bash
docker compose pull && docker compose up -d
```

**Check all services:**
```bash
./scripts/status.sh
```

## Code Style

- Shell scripts: Use `#!/bin/bash`, include error handling with `set -e`
- YAML: 2-space indentation
- JSON dashboards: Exported from Grafana, don't manually edit unless necessary
- Documentation: Markdown with clear headings and code blocks

## Testing Changes

1. Make changes to config files
2. Validate: `docker compose config -q`
3. Apply: `docker compose up -d`
4. Verify: `docker compose ps` and check logs
5. Export dashboards if changed in Grafana UI
6. Commit with descriptive message

## Related Projects

- ESP Temperature Sensors: https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor
