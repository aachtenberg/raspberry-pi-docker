# Raspberry Pi Docker Infrastructure

Home automation and monitoring stack with InfluxDB 3 Core, Grafana Cloud, Home Assistant, and ESP sensor integration.

## Quick Start

```bash
# Clone repository
git clone https://github.com/aachtenberg/raspberry-pi-docker.git ~/docker
cd ~/docker

# Configure secrets
cp .env.example .env
nano .env  # Add your tokens and credentials

# Deploy all services
docker compose up -d

# Verify deployment
./scripts/status.sh
```

**📚 Documentation:**
- **[Setup Guide](docs/SETUP.md)** - Complete installation and configuration
- **[Operations Guide](docs/OPERATIONS.md)** - Daily operations, backup, troubleshooting  
- **[Reference Guide](docs/REFERENCE.md)** - Architecture, integrations, advanced topics

---

## What This Does

Receives, stores, and visualizes sensor data from ESP devices:

- **ESP Sensors** → MQTT → Telegraf → **InfluxDB 3 Core** (time-series database)
- **Grafana Cloud** → Dashboards & alerting (via pdc-agent)
- **Home Assistant** → Automation & smart home control
- **Prometheus Stack** → System & container monitoring
- **Cloudflare Tunnel** → Secure remote access

**Perfect for:**
- 🏠 Multi-location temperature monitoring
- 📊 Long-term trend analysis
- 🔔 Automated alerts
- 🌐 Remote dashboard access
- 📈 System observability

---

## Architecture

```
ESP Sensors → MQTT (1883) → Telegraf → InfluxDB 3 Core (8181)
                                            ↓
                                    Grafana Cloud (pdc-agent)
                                            ↓
                               Prometheus Stack (monitoring)
                                            ↓
                            Cloudflare Tunnel (remote access)
```

**Related:** [ESP Sensor Firmware](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor)

## InfluxDB

InfluxDB 3 Core is the default. InfluxDB 2.7 support is retained as an optional override for users who prefer v2.

### InfluxDB 3 Core (default)

- **API**: `http://localhost:8181`
- **Reference**: [InfluxDB 3 Setup Guide](docs/INFLUXDB3_SETUP.md)

### InfluxDB 2.7 (optional)

- Provided via an override compose file: `docker-compose.influxdb2.yml`
- Enable with:

```bash
docker compose -f docker-compose.yml -f docker-compose.influxdb2.yml up -d influxdb
```

- v2 credentials use `.env` variables: `INFLUXDB_USERNAME`, `INFLUXDB_PASSWORD`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`, `INFLUXDB_TOKEN`
- v2 data persists under `/storage/docker/volumes/docker_influxdb-data`

### Quick Start with InfluxDB 3

```bash
# Start InfluxDB 3 Core
docker compose up -d influxdb3-core

# Check service status
docker compose ps | grep influxdb3

# View startup logs
docker compose logs influxdb3-core
```

For detailed integration instructions, see the [InfluxDB 3 Setup Guide](docs/INFLUXDB3_SETUP.md).

### 1. Configure Secrets

```bash
cd ~/docker

# Copy the example file
cp .env.example .env

## Services

| Service | Port | Purpose |
|---------|------|---------|
| InfluxDB 3 Core | 8181 | Time-series database |
| Grafana (local) | 3000 | Dashboards (deprecated, use Cloud) |
| Prometheus | 9090 | Metrics collection |
| Home Assistant | 8123 | Home automation |
| Mosquitto | 1883, 9001 | MQTT broker (MQTT + WebSocket) |
| Nginx Proxy Manager | 81, 8080 | Reverse proxy |

---

## Security Note

**This repository contains no secrets.**

All credentials are stored in `.env` (gitignored). Clone and create your own `.env` from `.env.example`.

See [Setup Guide](docs/SETUP.md) for configuration details.

---

## Common Commands

```bash
# Start all services
docker compose up -d

# Check status
./scripts/status.sh

# View logs
docker compose logs -f <service>

# Restart service
docker compose restart <service>

# Update all
docker compose pull && docker compose up -d
```

---

## Backup

**Automated:** Daily at 3:00 AM to NAS  
**Manual:** `sudo bash ./scripts/backup_to_nas.sh`  
**Restore:** `sudo bash ./scripts/restore_from_nas.sh`

See [Operations Guide](docs/OPERATIONS.md) for details.

---

## Support

- **ESP Sensor Firmware:** https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor
- **Documentation:** [Setup](docs/SETUP.md) | [Operations](docs/OPERATIONS.md) | [Reference](docs/REFERENCE.md)
- **Issues:** https://github.com/aachtenberg/raspberry-pi-docker/issues
