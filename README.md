# Unified Docker Compose Stack

This directory contains all Docker services for the Raspberry Pi home automation system.

## Quick Start

### 1. Configure Secrets

**IMPORTANT**: Before deploying, you must configure your secrets:

[?2004h[?1049h[22;0;0t[1;24r(B[m[4l[?7h[39;49m[?1h=[?1h=[?25l[39;49m(B[m[H[2J[22;35H(B[0;7m[ New File ](B[m[H(B[0;7m  GNU nano 6.2                          .env                                    [1;79H(B[m
[23d(B[0;7m^G(B[m Help[14G(B[0;7m^O(B[m Write Out (B[0;7m^W(B[m Where Is  (B[0;7m^K(B[m Cut[53G(B[0;7m^T(B[m Execute   (B[0;7m^C(B[m Location
[24d(B[0;7m^X(B[m Exit[14G(B[0;7m^R(B[m Read File (B[0;7m^\(B[m Replace   (B[0;7m^U(B[m Paste     (B[0;7m^J(B[m Justify   (B[0;7m^/(B[m Go To Line
[2d[?12l[?25h[24;1H[?1049l[23;0;0t
[?1l>[?2004l

See [docs/SECRETS_SETUP.md](docs/SECRETS_SETUP.md) for detailed instructions on obtaining:
- Cloudflare Tunnel Token
- InfluxDB credentials
- Other service passwords

### 2. Validate Configuration

🔍 Validating secrets configuration...

✅ include/secrets.h exists
✅ include/secrets.h is properly gitignored
✅ No placeholder values found (YOUR_*, YOUR-*)
✅ WiFi networks configured: 3
✅ InfluxDB URL configured: "http://192.168.0.167:8086"
✅ InfluxDB token length: 89 characters (looks valid)
⚠️  Warning: Found common example values. Make sure these are your actual credentials.
✅ InfluxDB Organization ID format looks valid

✅ Configuration looks good!

Next steps:
  1. Build: platformio run -e esp8266 (or -e esp32dev)
  2. Flash: platformio run -e esp8266 --target upload
  3. Monitor: platformio device monitor -b 115200

### 3. Deploy Services



### 4. Verify Services



## Security Note

**This repository does not contain any secrets or credentials.**

All sensitive configuration is stored in , which is gitignored. Anyone cloning this repository must create their own  file from the provided template.

See [docs/SECRETS_SETUP.md](docs/SECRETS_SETUP.md) for complete setup instructions.

## Directory Structure



## What This Does

This infrastructure receives, stores, and visualizes temperature data from multiple ESP8266/ESP32 devices:

- **4 ESP Devices** send temperature readings every 15 seconds
- **InfluxDB** stores time-series data (time-series database)
- **Grafana** creates beautiful dashboards and graphs
- **Home Assistant** provides home automation and alerts
- **Prometheus Stack** monitors system health and logs
- **Cloudflare Tunnel** enables secure remote access

Perfect for:
- 🏠 Home temperature monitoring across multiple locations
- 📊 Long-term temperature trend analysis
- 🔔 Temperature-based alerts and automation
- 🌐 Remote access to dashboards from anywhere
- 📈 System monitoring and observability

## Architecture

```
ESP Devices (4) → Raspberry Pi → InfluxDB → Grafana/Home Assistant
                                    ↓
                              Prometheus → System Monitoring
                                    ↓
                            Cloudflare Tunnel → Remote Access
```

See [ESP Temperature Sensor Project](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor) for the device firmware.


### 1. Configure Secrets

**IMPORTANT**: Before deploying, you must configure your secrets:

```bash
cd ~/docker

# Copy the example file
cp .env.example .env

# Edit with your actual credentials
nano .env
```

See [docs/SECRETS_SETUP.md](docs/SECRETS_SETUP.md) for detailed instructions on obtaining:
- Cloudflare Tunnel Token
- InfluxDB credentials
- Other service passwords

### 2. Validate Configuration

```bash
./scripts/validate_secrets.sh
```

### 3. Deploy Services

```bash
sudo docker compose up -d
```

### 4. Verify Services

```bash
sudo docker compose ps
sudo docker compose logs -f
```

## Security Note

**This repository does not contain any secrets or credentials.**

All sensitive configuration is stored in `.env`, which is gitignored. Anyone cloning this repository must create their own `.env` file from the provided template.

See [docs/SECRETS_SETUP.md](docs/SECRETS_SETUP.md) for complete setup instructions.

## Directory Structure

```
/home/aachten/docker/
├── docker-compose.yml          # Master compose file (all services)
├── .env                        # Environment variables (gitignored - YOU CREATE THIS)
├── .env.example                # Template for .env file (tracked in Git)
├── README.md                   # This file
├── docs/
│   └── SECRETS_SETUP.md        # Comprehensive secrets setup guide
├── scripts/
│   └── validate_secrets.sh     # Validation script for .env
├── influxdb/                   # InfluxDB configs (if needed)
├── grafana/
│   └── grafana.ini             # Grafana configuration
├── prometheus/
│   ├── prometheus.yml          # Prometheus scrape config
│   ├── loki-config.yml         # Loki configuration
│   └── promtail-config.yml     # Promtail configuration
├── mosquitto/
│   └── mosquitto.conf          # MQTT broker config
├── nginx-proxy-manager/        # (data in /home/aachten/nginx-proxy-manager/)
├── homeassistant/              # (data in /home/aachten/homeassistant/)
└── cloudflared/                # Cloudflare tunnel (token in .env)
```

## Services

| Service | Port(s) | Purpose |
|---------|---------|---------|
| InfluxDB | 8086 | Time-series database for ESP sensor data |
| Grafana | 3000 | Dashboards and visualization |
| Prometheus | 9090 | Metrics collection |
| Loki | 3100 | Log aggregation |
| Node Exporter | 9100 | System metrics |
| cAdvisor | 8081 | Container metrics |
| Promtail | - | Log shipping to Loki |
| Home Assistant | 8123 | Home automation |
| Mosquitto | 1883 | MQTT broker |
| Nginx Proxy Manager | 81, 8080, 8443 | Reverse proxy |
| Cloudflared | - | Cloudflare tunnel |

## Common Commands

### Start all services
```bash
cd ~/docker
sudo docker compose up -d
```

### Stop all services
```bash
cd ~/docker
sudo docker compose down
```

### View running services
```bash
cd ~/docker
sudo docker compose ps
```

### View logs
```bash
# All services
sudo docker compose logs -f

# Specific service
sudo docker compose logs -f influxdb
sudo docker compose logs -f grafana
```

### Restart a service
```bash
sudo docker compose restart influxdb
```

### Update images and restart
```bash
cd ~/docker
sudo docker compose pull
sudo compose up -d
```

### Check resource usage
```bash
sudo docker stats
```

## Volumes

Data is persisted in Docker volumes:

```bash
# List volumes
sudo docker volume ls

# Inspect a volume
sudo docker volume inspect docker_influxdb-data

# Backup a volume
sudo docker run --rm -v docker_influxdb-data:/data -v ~/backups:/backup alpine tar czf /backup/influxdb-backup.tar.gz /data
```

## Backup & Restore

### Backup everything
```bash
cd ~/docker
sudo docker compose down
sudo tar czf ~/docker-backup-$(date +%Y%m%d).tar.gz ~/docker /var/lib/docker/volumes/docker_*
sudo docker compose up -d
```

### Restore from backup
```bash
cd ~/docker
sudo docker compose down
sudo tar xzf ~/docker-backup-YYYYMMDD.tar.gz -C /
sudo docker compose up -d
```

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo docker compose logs [service-name]

# Restart service
sudo docker compose restart [service-name]

# Recreate service
sudo docker compose up -d --force-recreate [service-name]
```

### Port conflicts
```bash
# Check what's using a port
sudo netstat -tulpn | grep :8086
```

### Clean up old containers
```bash
# Remove stopped containers
sudo docker container prune

# Remove unused volumes (BE CAREFUL!)
sudo docker volume prune
```

## Network

All services (except those with `network_mode: host`) are on the `monitoring` bridge network and can communicate using their service names:

- `http://influxdb:8086`
- `http://grafana:3000`
- `http://prometheus:9090`
- etc.

## Environment Variables

Sensitive data is stored in `.env` file:
- `CLOUDFLARE_TUNNEL_TOKEN` - Cloudflare tunnel authentication
- `INFLUXDB_ADMIN_PASSWORD` - InfluxDB admin password
- `INFLUXDB_ORG_ID` - InfluxDB organization ID
- `INFLUXDB_ADMIN_TOKEN` - InfluxDB API token

**Never commit .env to version control!**

## Migration from Old Setup

The migration script has already been run. Old directories:
- `~/git/grafana/` → Configs copied to `~/docker/grafana/`
- `~/prometheus/` → Configs copied to `~/docker/prometheus/`
- `~/git/mqtt-docker/` → Configs copied to `~/docker/mosquitto/`
- `~/influxdb-docker/` → Superseded by unified setup
- `~/nginx-proxy-manager/` → Data directory still referenced
- `~/homeassistant/` → Data directory still referenced

Old directories can be removed after verifying everything works.

## Related Projects

- **ESP Temperature Sensors**: https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor
  - 4 deployed ESP8266/ESP32 devices sending temperature data to InfluxDB
  - See their [Secrets Setup Guide](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor/blob/main/docs/guides/SECRETS_SETUP.md)

## Documentation

- **[Setup Guide](docs/SETUP_GUIDE.md)** - Complete installation and configuration
- **[Operations Guide](docs/OPERATIONS_GUIDE.md)** - Daily operations, monitoring, and maintenance
- [Making Repository Public Checklist](MAKING_PUBLIC_CHECKLIST.md) - Steps to safely make this repo public

## Quick Operations

### Dashboard Management

```bash
# Export all Grafana dashboards
./scripts/export_grafana_dashboards.sh

# Import dashboards from JSON
./scripts/import_grafana_dashboards.sh

# Automated daily backup (2 AM cron)
./scripts/backup_grafana_dashboards.sh
```

### System Monitoring

```bash
# Check all service status
./scripts/status.sh

# View logs
docker compose logs -f

# Resource usage
docker stats
```

## Support

For issues or questions:
- **ESP Device Firmware**: [github.com/aachtenberg/esp12f_ds18b20_temp_sensor](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor)
- **Pi Infrastructure**: This repository
- **InfluxDB**: [docs.influxdata.com/influxdb/v2.7/](https://docs.influxdata.com/influxdb/v2.7/)
- **Grafana**: [grafana.com/docs/](https://grafana.com/docs/)
- **Docker**: [docs.docker.com/](https://docs.docker.com/)
