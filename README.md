# Raspberry Pi Docker Infrastructure

Production-ready Docker Compose stack for home IoT monitoring and automation. Designed to work with [ESP temperature sensors](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor) for complete end-to-end temperature monitoring.

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

- [Secrets Setup Guide](docs/SECRETS_SETUP.md) - **Configure credentials before deploying**
- [Making Repository Public Checklist](MAKING_PUBLIC_CHECKLIST.md) - Steps to safely make this repo public


## Grafana Dashboard Management

### Export Dashboards to Version Control

Export all Grafana dashboards as JSON files for backup and version control:

```bash
cd ~/docker

# Export dashboards (will prompt for password)
GRAFANA_PASSWORD=<grafana_password> ./scripts/export_grafana_dashboards.sh

# Dashboards will be saved to grafana/dashboards/*.json
```

**Commit to Git:**
```bash
git add grafana/dashboards/
git commit -m "chore: export Grafana dashboards"
git push
```

### Import Dashboards

To restore or share dashboards:

1. **Via Grafana UI**:
   - Go to Dashboards → Import
   - Upload JSON file from `grafana/dashboards/`
   - Click Import

2. **Via API** (automated):
   ```bash
   for file in grafana/dashboards/*.json; do
     curl -X POST -H "Content-Type: application/json" \
       -u admin:<password> \
       -d @"$file" \
       http://localhost:3000/api/dashboards/db
   done
   ```

### Dashboard Files

Exported dashboards include metadata:
- Export timestamp
- Dashboard title and UID
- Folder location
- Version number

Perfect for:
- 📦 Backing up dashboard configurations
- 🔄 Sharing dashboards between Grafana instances
- 📝 Version controlling dashboard changes
- 🚀 Automating dashboard deployment


## Grafana Dashboard Management

### Export Dashboards to Version Control

Export all Grafana dashboards as JSON files for backup and version control:

```bash
cd ~/docker

# Export dashboards (will prompt for password)
GRAFANA_PASSWORD=<grafana_password> ./scripts/export_grafana_dashboards.sh

# Dashboards will be saved to grafana/dashboards/*.json
```

**Commit to Git:**
```bash
git add grafana/dashboards/
git commit -m "chore: export Grafana dashboards"
git push
```

### Import Dashboards

To restore or share dashboards:

1. **Via Grafana UI**:
   - Go to Dashboards → Import
   - Upload JSON file from `grafana/dashboards/`
   - Click Import

2. **Via API** (automated):
   ```bash
   for file in grafana/dashboards/*.json; do
     curl -X POST -H "Content-Type: application/json" \
       -u admin:<password> \
       -d @"$file" \
       http://localhost:3000/api/dashboards/db
   done
   ```

### Dashboard Files

Exported dashboards include metadata:
- Export timestamp
- Dashboard title and UID
- Folder location
- Version number

Perfect for:
- 📦 Backing up dashboard configurations
- 🔄 Sharing dashboards between Grafana instances
- 📝 Version controlling dashboard changes
- 🚀 Automating dashboard deployment
