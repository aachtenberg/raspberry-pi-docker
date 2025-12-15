# Complete Setup Guide

This guide covers initial installation, configuration, and first-time setup of all services in the Raspberry Pi Docker infrastructure.

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/aachtenberg/raspberry-pi-docker.git ~/docker
cd ~/docker

# 2. Copy environment template
cp .env.example .env

# 3. Edit secrets (see Configuration section below)
nano .env

# 4. Start all services
docker compose up -d

# 5. Verify deployment
./scripts/status.sh
```

## Architecture Overview

```
ESP Sensors → MQTT (1883) → Telegraf → InfluxDB 3 Core (8181)
                                            ↓
                                    Grafana Cloud (pdc-agent)
                                            ↓
                               Prometheus Stack (monitoring)
                                            ↓
                            Cloudflare Tunnel (remote access)
```

**Key Services:**
- **InfluxDB 3 Core** (8181) - Time-series database (default)
- **Grafana Cloud** - Dashboards & alerting (via pdc-agent)
- **Telegraf** - MQTT → InfluxDB bridge
- **Prometheus** (9090) + Node Exporter + cAdvisor - System metrics
- **Home Assistant** (8123) - Home automation
- **Mosquitto** (1883) - MQTT broker
- **Nginx Proxy Manager** (81, 8080, 8443) - Reverse proxy
- **Cloudflared** - Secure tunnel

---

## Configuration

### Environment Variables (.env)

All secrets and credentials are stored in `.env` (gitignored, never commit!).

Copy the template:
```bash
cp .env.example .env
```

Edit and configure the following sections:

#### 1. Cloudflare Tunnel

Get your tunnel token from [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/):
1. Navigate to **Access** → **Tunnels**
2. Find your tunnel or create new one
3. Copy the token

```bash
CLOUDFLARE_TUNNEL_TOKEN=<redacted>
```

#### 2. InfluxDB 3 Core

After starting InfluxDB 3, generate an admin token:

```bash
docker compose up -d influxdb3-core
docker compose exec influxdb3-core influxdb3 create token --admin
```

Copy the token output and add to `.env`:

```bash
INFLUXDB3_ADMIN_TOKEN=<influxdb3_token>
```

**Optional - InfluxDB 2.7 (legacy):** If you need InfluxDB 2.x instead:
```bash
INFLUXDB_USERNAME=admin
INFLUXDB_PASSWORD=YourSecurePassword123
INFLUXDB_ORG=your_org_name
INFLUXDB_ORG_ID=16-char-hex-string
INFLUXDB_BUCKET=sensor_data
INFLUXDB_ADMIN_TOKEN=EXAMPLE_TOKEN
```

#### 3. Grafana Cloud (pdc-agent)

Get credentials from your Grafana Cloud account:

```bash
GRAFANA_PDC_TOKEN=your_pdc_token_here
GRAFANA_PDC_CLUSTER=your_cluster_name
GRAFANA_PDC_GCLOUD_HOSTED_GRAFANA_ID=your_grafana_instance_id
```

**Note:** Legacy local Grafana (port 3000) is deprecated but still available for local testing.

#### 4. Telegraf

Telegraf uses the InfluxDB 3 token to write data:

```bash
# Already configured above
INFLUXDB3_ADMIN_TOKEN=<influxdb3_token>
```

#### 5. Optional Services

**Portainer (if enabled):**
```bash
PORTAINER_ADMIN_PASSWORD=YourPortainerPassword
```

**Grafana Local (legacy, optional):**
```bash
GRAFANA_API_KEY=<grafana_api_key>
GRAFANA_ADMIN_API_KEY=<grafana_admin_api_key>
```

### Validate Configuration

Run the validation script to check for missing values:

```bash
./scripts/validate_secrets.sh
```

---

## Service Setup

### InfluxDB 3 Core

**1. Start the service:**
```bash
docker compose up -d influxdb3-core influxdb3-explorer
```

**2. Create admin token:**
```bash
docker compose exec influxdb3-core influxdb3 create token --admin
```

Save token to `.env` as `INFLUXDB3_ADMIN_TOKEN`.

**3. Create databases:**
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)

# Temperature sensor data
docker compose exec influxdb3-core influxdb3 create database temperature_data --token "${TOKEN}"

# Home Assistant data (via MQTT)
docker compose exec influxdb3-core influxdb3 create database homeassistant --token "${TOKEN}"

# Surveillance data
docker compose exec influxdb3-core influxdb3 create database surveillance --token "${TOKEN}"
```

**4. Verify databases:**
```bash
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"
```

**5. Access Explorer UI:**
```
http://localhost:8888
```

**Optional - Switch to InfluxDB 2.7:**
```bash
docker compose -f docker-compose.yml -f docker-compose.influxdb2.yml up -d influxdb
```

### Telegraf (MQTT Bridge)

Telegraf subscribes to MQTT topics and writes to InfluxDB 3 Core.

**1. Ensure token is configured:**
```bash
# Check .env has INFLUXDB3_ADMIN_TOKEN
grep INFLUXDB3_ADMIN_TOKEN .env
```

**2. Start Telegraf:**
```bash
docker compose up -d telegraf
```

**3. Verify it's running:**
```bash
docker compose logs -f telegraf

# Expected output: "wrote N metrics" every 10s
```

**4. Test with MQTT message:**
```bash
docker compose exec mosquitto mosquitto_pub \
  -t "homeassistant/sensor/test_room/state" \
  -m '{"state": "22.5", "attributes": {"unit_of_measurement": "°C"}}'
```

**5. Query InfluxDB to confirm:**
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 query homeassistant \
  --token "${TOKEN}" \
  "SELECT * FROM homeassistant LIMIT 10"
```

### Grafana Cloud (pdc-agent)

**1. Get Grafana Cloud credentials:**
- Sign up at [grafana.com](https://grafana.com/)
- Navigate to your Cloud portal
- Get PDC agent token from **Connections** → **Add Private Data Source**

**2. Configure `.env`:**
```bash
GRAFANA_PDC_TOKEN=<your_token>
GRAFANA_PDC_CLUSTER=<your_cluster>
GRAFANA_PDC_GCLOUD_HOSTED_GRAFANA_ID=<your_instance_id>
```

**3. Start pdc-agent:**
```bash
docker compose up -d pdc-agent
```

**4. Verify connection:**
```bash
docker compose logs pdc-agent | grep -i "connected\|authenticated"
```

**5. Access dashboards:**
- Go to your Grafana Cloud instance
- Add InfluxDB 3 Core as datasource (FlightSQL)
- Use `http://influxdb3-core:8181` if using Grafana Cloud agent tunnel

### Prometheus Stack

Prometheus collects system and container metrics.

**1. Start Prometheus services:**
```bash
docker compose up -d prometheus node-exporter cadvisor
```

**2. Verify targets:**
```
http://localhost:9090/targets
```

All targets should show "UP" status.

**3. Test a query:**
```
http://localhost:9090/graph
```

Query: `node_memory_MemAvailable_bytes`

### Home Assistant

**1. Start Home Assistant:**
```bash
docker compose up -d homeassistant
```

**2. Initial setup:**
```
http://localhost:8123
```

Follow on-screen setup wizard.

**3. Configure MQTT integration:**
- Go to **Settings** → **Devices & Services**
- Add **MQTT** integration
- Host: `mosquitto`
- Port: `1883`
- Username/Password: (if configured in mosquitto.conf)

### Nginx Proxy Manager

**1. Start NPM:**
```bash
docker compose up -d nginx-proxy-manager
```

**2. Initial login:**
```
http://localhost:81
```

Default credentials:
- Email: `admin@example.com`
- Password: `changeme`

**Change password immediately after first login!**

**3. Add proxy hosts:**
- Go to **Hosts** → **Proxy Hosts**
- Add entries for each service you want to expose
- Configure SSL certificates via Let's Encrypt

### Cloudflare Tunnel

**1. Ensure token is in `.env`:**
```bash
grep CLOUDFLARE_TUNNEL_TOKEN .env
```

**2. Start cloudflared:**
```bash
docker compose up -d cloudflared
```

**3. Verify connection:**
```bash
docker compose logs cloudflared | grep -i "connected\|registered"
```

**4. Configure tunnel routes in Cloudflare dashboard:**
- Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/)
- **Access** → **Tunnels** → Your tunnel → **Public Hostnames**
- Add routes for services (e.g., `grafana.yourdomain.com` → `http://localhost:3000`)

---

## Verification

### Check All Services

```bash
# Quick status
docker compose ps

# Detailed status with health checks
./scripts/status.sh
```

### Test Web Interfaces

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| InfluxDB 3 Explorer | http://localhost:8888 | None (no auth) |
| Prometheus | http://localhost:9090 | None |
| Home Assistant | http://localhost:8123 | Setup wizard |
| Nginx Proxy Manager | http://localhost:81 | admin@example.com / changeme |
| Grafana (legacy local) | http://localhost:3000 | admin / admin |

### Verify Data Flow

**1. Check MQTT broker:**
```bash
docker compose exec mosquitto mosquitto_sub -t '#' -v | head -20
```

You should see messages from ESP sensors or Home Assistant.

**2. Check InfluxDB has data:**
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 query temperature_data \
  --token "${TOKEN}" \
  "SELECT COUNT(*) FROM esp_temperature"
```

**3. Check Telegraf is writing:**
```bash
docker compose logs telegraf --tail 50 | grep "wrote"
```

**4. Check Prometheus is scraping:**
```
http://localhost:9090/targets
```

All should be "UP" (green).

---

## ESP Sensor Setup

To send temperature data to this infrastructure:

**1. Flash ESP firmware from:**
- https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor

**2. Configure WiFi and InfluxDB settings:**
- SSID/Password
- InfluxDB URL: `http://192.168.x.x:8181` (your Pi's IP)
- Database: `temperature_data`
- Token: Your `INFLUXDB3_ADMIN_TOKEN`

**3. Verify ESP is publishing:**
```bash
# Watch MQTT
mosquitto_sub -h 127.0.0.1 -t 'esp-sensor-hub/+/temperature'

# Expected: {"device": "Big-Garage", "celsius": 24.5, "fahrenheit": 76.1}
```

**4. Check data in InfluxDB:**
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 query temperature_data \
  --token "${TOKEN}" \
  "SELECT * FROM esp_temperature ORDER BY time DESC LIMIT 5"
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check specific service logs
docker compose logs <service_name> --tail 50

# Check for port conflicts
sudo netstat -tulpn | grep <port>

# Restart service
docker compose restart <service_name>
```

### InfluxDB 401 Unauthorized

- Verify token in `.env` matches generated token
- Regenerate token if lost:
  ```bash
  docker compose exec influxdb3-core influxdb3 create token --admin
  ```

### Telegraf Not Writing Data

```bash
# Check Telegraf logs
docker compose logs telegraf --tail 100

# Common issues:
# - INFLUXDB3_ADMIN_TOKEN not set in .env
# - Database doesn't exist (create with: influxdb3 create database <name>)
# - MQTT broker not running
```

### No MQTT Messages

```bash
# Check Mosquitto is running
docker compose ps mosquitto

# Test MQTT broker
docker compose exec mosquitto mosquitto_pub -t "test" -m "hello"
docker compose exec mosquitto mosquitto_sub -t "test" -C 1

# Check ESP sensor WiFi connection and config
```

### Cloudflare Tunnel Not Connected

```bash
# Check logs
docker compose logs cloudflared

# Verify token is correct (don't commit!)
grep CLOUDFLARE_TUNNEL_TOKEN .env

# Restart tunnel
docker compose restart cloudflared
```

---

## Security Best Practices

- **Never commit `.env`** - it contains all secrets
- Use strong, unique passwords for all services
- Change default passwords immediately (NPM, Home Assistant, Grafana)
- Regenerate tokens if accidentally exposed
- Keep Docker images updated: `docker compose pull`
- Monitor access logs in Nginx Proxy Manager
- Use Cloudflare Tunnel instead of opening ports
- Review Prometheus alerts regularly

---

## Next Steps

- [Operations Guide](OPERATIONS.md) - Daily operations, backup, maintenance
- [Reference Guide](REFERENCE.md) - Architecture, integrations, advanced topics
- Configure Grafana Cloud dashboards
- Set up Home Assistant automations
- Add ESP sensors to your network
- Configure alerts in Grafana Cloud

---

**Setup complete!** All services should now be running and accepting data.
