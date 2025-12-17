# Operations & Maintenance Guide

Daily operations, monitoring, backup/restore procedures, and troubleshooting for the Raspberry Pi Docker infrastructure.

## Daily Operations

### Check System Status

```bash
# Quick overview
./scripts/status.sh

# Detailed container status
docker compose ps

# Check specific service
docker compose ps <service_name>
```

### View Logs

```bash
# All services (last 100 lines)
docker compose logs --tail 100

# Specific service (follow/tail mode)
docker compose logs -f <service_name>

# Last 24 hours only
docker compose logs --since 24h

# Examples
docker compose logs -f influxdb3-core
docker compose logs -f telegraf | grep "wrote"
docker compose logs -f pdc-agent | grep "connected"
```

### Restart Services

```bash
# Restart specific service
docker compose restart <service_name>

# Restart all services
docker compose restart

# Stop and start (full restart)
docker compose down
docker compose up -d

# Restart with fresh images
docker compose pull
docker compose up -d
```

### Update Services

```bash
# Pull latest images
docker compose pull

# Recreate and restart containers
docker compose up -d

# Or use the update script
./scripts/update-all.sh
```

---

## Monitoring

### AI Monitor - Self-Healing System

**Autonomous monitoring and remediation agent** (see [AI_MONITOR.md](./AI_MONITOR.md) for full docs)

The AI monitor continuously checks container health and automatically restarts failed services with guardrails:
- **Allowlisted services**: telegraf, prometheus (safe to auto-restart)
- **Protected services**: mosquitto-broker (ESP devices can't reconnect), influxdb3-core, nginx-proxy-manager
- **Cooldown**: 10 minutes per container
- **LLM triage**: Claude API provides human-readable explanations of issues

**Check AI monitor status:**
```bash
# View logs
docker compose logs -f ai-monitor

# Check metrics
curl http://localhost:8000/metrics | grep ai_monitor

# Recent restarts
curl -s http://localhost:8000/metrics | grep "ai_monitor_restarts_total"

# Triage outcomes
curl -s http://localhost:8000/metrics | grep "ai_monitor_triage_calls_total"
```

**Grafana dashboard**: AI Monitor - Self-Heal Metrics

### Grafana Cloud Dashboards

**Primary monitoring interface:** Grafana Cloud (configured via pdc-agent)

Access your dashboards at: `https://dashboards.grafana.com` (or your Grafana Cloud URL)

**Check pdc-agent status:**
```bash
docker compose logs pdc-agent | grep -E "connected|authenticated"
```

Expected output:
```
level=info msg="Authenticated to private-datasource-connect..."
level=info msg="Connection established"
```

**If pdc-agent not connected:**
```bash
# Check .env has required vars
grep GRAFANA_PDC .env

# Restart agent
docker compose restart pdc-agent
```

### Prometheus Metrics

**Local Prometheus:** `http://localhost:9090`

**Check scrape targets:**
```
http://localhost:9090/targets
```

All should show "UP" status.

**Useful queries:**
```promql
# CPU usage
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory usage
100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))

# Disk usage
100 - ((node_filesystem_avail_bytes{mountpoint="/"} * 100) / node_filesystem_size_bytes{mountpoint="/"})

# Container count
count(container_last_seen)
```

### InfluxDB 3 Core Status

**Check database health:**
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"
```

**Check recent data:**
```bash
docker compose exec influxdb3-core influxdb3 query temperature_data \
  --token "${TOKEN}" \
  "SELECT COUNT(*) FROM esp_temperature"
```

**Explorer UI:** `http://localhost:8888`

### Telegraf Data Flow

**Current MQTT subscriptions:**
- `esp-sensor-hub/+/temperature` → InfluxDB3 `temperature_data` database (ESP temperature sensors)
- `surveillance/#` → InfluxDB3 `surveillance` database (ESP32 cameras)

**Verify Telegraf is writing:**
```bash
docker compose logs telegraf --tail 50 | grep "wrote"
```

Expected: `wrote N metrics` every 10 seconds

**Check MQTT messages:**
```bash
# All topics
docker exec mosquitto-broker mosquitto_sub -t '#' -v | head -20

# ESP temperature sensors only
docker exec mosquitto-broker mosquitto_sub -t 'esp-sensor-hub/+/temperature' -v

# Surveillance cameras only
docker exec mosquitto-broker mosquitto_sub -t 'surveillance/#' -v
```

**Check Telegraf Prometheus metrics:**
```bash
curl -s http://localhost:9273/metrics | grep esp_temperature_celsius
```

Expected: Current temperature readings from Main-Cottage, Spa, Pump-House, Small-Garage

---

## Backup & Restore

### Automated Backups

**Main Pi (raspberrypi):**
- **Schedule:** Daily at 3:00 AM via systemd timer
- **Backup location:** `/mnt/nas-backup/docker-backups/raspberrypi/`

**Secondary Pi (raspberrypi2):**
- **Schedule:** Daily at 3:00 AM via systemd timer
- **Backup location:** `/mnt/nas-backup/docker-backups/raspberrypi2/`
- **Setup:** See [raspberry-pi2/README.md](../raspberry-pi2/README.md)

**What's backed up:**
- Docker volumes (Grafana, Prometheus, InfluxDB3, Portainer, Mosquitto)
- Bind-mounted directories (Home Assistant, Nginx Proxy Manager)
- Repository configs (docker-compose.yml, scripts, configs)
- `.env` file (unencrypted)

**What's NOT backed up:**
- Docker images (pulled fresh)
- Containers (rebuilt from compose)
- Networks (defined in compose)

**Check backup status:**
```bash
# View systemd timer status
sudo systemctl status docker-backup.timer

# List recent backups
ls -lth /mnt/nas-backup/docker-backups/raspberrypi/ | head -10

# View last backup log
sudo journalctl -u docker-backup.service -n 100
```

### Manual Backup

```bash
cd ~/docker
sudo bash ./scripts/backup_to_nas.sh
```

**Backup directory structure:**
```
/mnt/nas-backup/docker-backups/raspberrypi/YYYYMMDD-HHMMSS/
├── checksums.txt
├── volumes/
│   ├── docker_grafana-data-*.tar.gz
│   ├── docker_prometheus-data-*.tar.gz
│   ├── docker_influxdb3-data-*.tar.gz
│   └── ...
└── configs/
    ├── homeassistant/
    ├── nginx-proxy-manager/
    └── docker-repo/
```

**Retention:** 30 days (automatic cleanup)

### Restore from Backup

**Restore latest backup:**
```bash
cd ~/docker
sudo bash ./scripts/restore_from_nas.sh
```

**Restore specific backup:**
```bash
sudo bash ./scripts/restore_from_nas.sh 20251214-231749
```

**⚠️ Warning:** This will:
1. Stop all containers
2. **Overwrite existing data**
3. Restart containers

**What gets restored:**
- All Docker volumes
- Bind-mounted directories
- Repository configs (if confirmed)
- `.env` file (if confirmed)

**After restore:**
```bash
# Verify services
docker compose ps

# Check logs
docker compose logs -f <service>
```

### Backup Verification

```bash
# Verify checksums
cd /mnt/nas-backup/docker-backups/raspberrypi/<timestamp>/volumes
sha256sum -c ../checksums.txt
```

Expected: All files show "OK"

---

## Troubleshooting

### Service Won't Start

**1. Check logs:**
```bash
docker compose logs <service_name> --tail 100
```

**2. Check port conflicts:**
```bash
sudo netstat -tulpn | grep <port>
```

**3. Check volume permissions:**
```bash
sudo ls -la /var/lib/docker/volumes/ | grep <volume_name>
```

**4. Restart service:**
```bash
docker compose restart <service_name>
```

**5. Full recreate:**
```bash
docker compose down <service_name>
docker compose up -d <service_name>
```

### Permission Issues

**Symptoms:**
- "Permission denied" errors in logs
- Container exits immediately
- Can't write to volumes

**Fix script:**
```bash
./scripts/fix-docker-permissions.sh
```

**Manual fix for specific service:**
```bash
# Example: Fix Prometheus permissions
sudo chown -R 65534:65534 /var/lib/docker/volumes/docker_prometheus-data/_data/
sudo chmod 775 /var/lib/docker/volumes/docker_prometheus-data/_data/

# Restart container
docker compose restart prometheus
```

**Container User IDs:**
| Container | UID:GID | User |
|-----------|---------|------|
| prometheus | 65534:65534 | nobody:nogroup |
| grafana | 472:472 | grafana:grafana |
| mosquitto | 1883:1883 | mosquitto:mosquitto |
| influxdb3-core | 1000:1000 | aachten:aachten |
| nginx-proxy-manager | 0:0 | root:root |
| portainer | 0:0 | root:root |

### InfluxDB Connection Issues

**Problem:** 401 Unauthorized

**Solutions:**
```bash
# 1. Verify token in .env
grep INFLUXDB3_ADMIN_TOKEN .env

# 2. Test token
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"

# 3. Generate new token if lost
docker compose exec influxdb3-core influxdb3 create token --admin
# Update .env with new token
```

**Problem:** Database doesn't exist

```bash
# Create missing database
docker compose exec influxdb3-core influxdb3 create database temperature_data --token "${TOKEN}"
```

### Telegraf Not Writing Data

**Check Telegraf logs:**
```bash
docker compose logs telegraf --tail 100
```

**Common issues:**

**1. Token not configured:**
```bash
# Check .env
grep INFLUXDB3_ADMIN_TOKEN .env

# Restart Telegraf
docker compose restart telegraf
```

**2. Database doesn't exist:**
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 create database homeassistant --token "${TOKEN}"
```

**3. MQTT broker down:**
```bash
docker compose ps mosquitto
docker compose restart mosquitto
```

**4. Test MQTT → Telegraf → InfluxDB:**
```bash
# Publish test message
docker compose exec mosquitto mosquitto_pub \
  -t "homeassistant/sensor/test/state" \
  -m '{"state": "99", "attributes": {"unit_of_measurement": "test"}}'

# Check Telegraf received it
docker compose logs telegraf | grep "wrote"

# Query InfluxDB
docker compose exec influxdb3-core influxdb3 query homeassistant \
  --token "${TOKEN}" \
  "SELECT * FROM homeassistant WHERE time > now() - INTERVAL '1 minute'"
```

### No MQTT Messages

**Check broker status:**
```bash
docker compose ps mosquitto
docker compose logs mosquitto
```

**Test broker:**
```bash
# Subscribe to all topics
docker compose exec mosquitto mosquitto_sub -t '#' -v

# In another terminal, publish
docker compose exec mosquitto mosquitto_pub -t "test" -m "hello"
```

**Check ESP sensor connectivity:**
- Verify WiFi connection
- Check InfluxDB URL/token in ESP config
- View ESP serial output for errors

### Cloudflare Tunnel Not Connected

**Check logs:**
```bash
docker compose logs cloudflared | grep -E "error|registered|connected"
```

**Verify token:**
```bash
grep CLOUDFLARE_TUNNEL_TOKEN .env
```

**Restart tunnel:**
```bash
docker compose restart cloudflared
```

**Check Cloudflare dashboard:**
- Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/)
- **Access** → **Tunnels**
- Verify tunnel shows "Healthy"

### Container Keeps Restarting

**Check logs:**
```bash
docker compose logs <service> --tail 200
```

**Check resource limits:**
```bash
# Memory usage
docker stats <container_name> --no-stream

# Disk space
df -h
```

**Check dependencies:**
```bash
# Ensure required services are running
docker compose ps

# Example: Telegraf needs mosquitto and influxdb3-core
docker compose ps mosquitto influxdb3-core
```

### Grafana Cloud Agent (pdc-agent) Issues

**Check connection:**
```bash
docker compose logs pdc-agent | grep -E "authenticated|error"
```

**Verify credentials:**
```bash
grep GRAFANA_PDC .env
```

**Restart agent:**
```bash
docker compose restart pdc-agent
```

**Check restart policy:**
```bash
docker inspect pdc-agent --format 'RestartPolicy: {{.HostConfig.RestartPolicy.Name}}'
```

Should show: `unless-stopped`

---

## Maintenance Tasks

### Weekly

- Check disk space: `df -h`
- Review logs for errors: `docker compose logs --since 7d | grep -i error`
- Verify backups completed: `ls -lth /mnt/nas-backup/docker-backups/raspberrypi/ | head -10`

### Monthly

- Update Docker images: `docker compose pull && docker compose up -d`
- Review Grafana Cloud dashboards for anomalies
- Check certificate expiration in Nginx Proxy Manager
- Clean up old Docker images: `docker image prune -a`

### As Needed

- Rotate tokens if exposed
- Update firmware on ESP sensors
- Review Home Assistant automations
- Add new sensors/services as needed

---

## Command Reference

### Docker Compose

```bash
# Start services
docker compose up -d [service]

# Stop services
docker compose down [service]

# Restart
docker compose restart [service]

# View logs
docker compose logs -f [service]

# Pull updates
docker compose pull

# Check status
docker compose ps

# Validate config
docker compose config -q
```

### InfluxDB 3 Core

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)

# Show databases
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"

# Create database
docker compose exec influxdb3-core influxdb3 create database <name> --token "${TOKEN}"

# Query data
docker compose exec influxdb3-core influxdb3 query <database> --token "${TOKEN}" "SELECT * FROM <table> LIMIT 10"

# Create token
docker compose exec influxdb3-core influxdb3 create token --admin
```

### MQTT

```bash
# Subscribe to all topics
docker compose exec mosquitto mosquitto_sub -t '#' -v

# Publish message
docker compose exec mosquitto mosquitto_pub -t "topic/name" -m "message"

# Subscribe to specific topic
docker compose exec mosquitto mosquitto_sub -t "homeassistant/sensor/+/state"
```

---

## Getting Help

- **Check logs first:** `docker compose logs <service>`
- **Verify config:** `./scripts/validate_secrets.sh`
- **Review documentation:** [Setup Guide](SETUP.md), [Reference Guide](REFERENCE.md)
- **GitHub Issues:** https://github.com/aachtenberg/raspberry-pi-docker/issues
- **Grafana Cloud Support:** https://grafana.com/support/

---

**For advanced topics, integrations, and architecture details, see [Reference Guide](REFERENCE.md).**
