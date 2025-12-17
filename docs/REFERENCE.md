# Reference Guide

Advanced topics, architecture details, integrations, and special configurations for the Raspberry Pi Docker infrastructure.

## Table of Contents

- [Architecture](#architecture)
- [Data Integrations](#data-integrations)
- [Temperature Monitoring](#temperature-monitoring)
- [Victron Solar System](#victron-solar-system)
- [MCP Servers (AI Assistance)](#mcp-servers-ai-assistance)
- [Permissions Reference](#permissions-reference)
- [Making Repository Public](#making-repository-public)

---

## Architecture

### System Overview

```
┌─────────────────┐
│  ESP Sensors    │ (WiFi)
│  (4 devices)    │
└────────┬────────┘
         │ MQTT/HTTP
         ▼
┌─────────────────┐
│  Raspberry Pi   │
│  192.168.x.x    │
├─────────────────┤
│  Mosquitto      │──┐
│  (MQTT:1883)    │  │
└────────┬────────┘  │
         │            │ MQTT Subscribe
         │            ▼
         │       ┌─────────────┐
         │       │  Telegraf   │
         │       │  (bridge)   │
         │       └──────┬──────┘
         │              │ HTTP Write
         ▼              ▼
    ┌─────────────────────┐
    │  InfluxDB 3 Core    │
    │  (8181)             │
    └──────────┬──────────┘
               │ Query
               ▼
    ┌─────────────────────┐
    │  pdc-agent          │
    │  (Grafana Cloud)    │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  Grafana Cloud      │
    │  (Dashboards)       │
    └─────────────────────┘
```

### Service Ports

| Service | Internal Port | Host Port | Purpose |
|---------|---------------|-----------|---------|
| InfluxDB 3 Core | 8086 | 8181 | Time-series database API |
| InfluxDB 3 Explorer | 80 | 8888 | Web UI for InfluxDB 3 |
| Prometheus | 9090 | 9090 | Metrics scraping |
| Node Exporter | 9100 | 9100 | System metrics |
| cAdvisor | 8080 | 8081 | Container metrics |
| Grafana (local) | 3000 | 3000 | Dashboards (deprecated) |
| Home Assistant | 8123 | 8123 | Home automation |
| Mosquitto | 1883 | 1883 | MQTT broker |
| Nginx Proxy Manager | 80/443 | 8080/8443 | Reverse proxy |
| NPM Admin UI | 81 | 81 | NPM web interface |

### Docker Networks

**monitoring** bridge network:
- All services communicate via this network
- Services reference each other by container name
- Example: Telegraf writes to `http://influxdb3-core:8181`

### Volume Strategy

**Named volumes** (Docker-managed):
- `influxdb3-data` - InfluxDB 3 database files
- `prometheus-data` - Prometheus time-series data
- `grafana-data` - Grafana dashboards (legacy local)
- `mosquitto-data` - MQTT broker persistence
- `mosquitto-log` - MQTT logs
- `portainer-data` - Portainer configuration

**Bind mounts** (host directories):

- `/storage/nginx-proxy-manager` → NPM data & SSL certs
- `/storage/influxdb` → InfluxDB 2.x data (legacy)

---

## Data Integrations

### MQTT → Telegraf → InfluxDB 3 Pipeline

**Data flow:**
```
MQTT Broker
  ├─ homeassistant/sensor/+/state → homeassistant database
  ├─ surveillance/camera/+/snapshot → surveillance database
  └─ esp-sensor-hub/+/temperature → temperature_data database
```

**Telegraf configuration:** `telegraf/telegraf.conf`

**Key sections:**

**1. MQTT Input:**
```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "homeassistant/sensor/+/state",
    "esp-sensor-hub/+/temperature"
  ]
  data_format = "json"
  tag_keys = ["device", "chip_id"]
```

**2. Regex Processor (extract device from topic):**
```toml
[[processors.regex]]
  pattern = "^esp-sensor-hub/([^/]+)/.*$"
  replacement = "${1}"
  result_key = "device"
```

**3. Output to InfluxDB 3:**
```toml
[[outputs.http]]
  url = "http://influxdb3-core:8181/api/v1/write?db=temperature_data"
  method = "POST"
  data_format = "influx"
  namepass = ["esp_temperature"]
  [outputs.http.headers]
    Authorization = "Bearer ${INFLUXDB3_ADMIN_TOKEN}"
```

**Verify data flow:**
```bash
# 1. Watch MQTT
docker compose exec mosquitto mosquitto_sub -t '#' -v | head -20

# 2. Check Telegraf logs
docker compose logs telegraf | grep "wrote"

# 3. Query InfluxDB
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 query temperature_data \
  --token "${TOKEN}" \
  "SELECT COUNT(*) FROM esp_temperature"
```

### Home Assistant Integration

**MQTT Configuration:**
1. Settings → Devices & Services → Add Integration → MQTT
2. Host: `mosquitto`
3. Port: `1883`
4. Keep default settings

**Auto-discovery:**
- Telegraf automatically subscribes to `homeassistant/sensor/+/state`
- JSON payloads transformed to InfluxDB line protocol
- Data written to `homeassistant` database

**Example Home Assistant sensor:**
```yaml
sensor:
  - platform: mqtt
    name: "Living Room Temperature"
    state_topic: "homeassistant/sensor/living_room_temp/state"
    unit_of_measurement: "°C"
    value_template: "{{ value_json.state }}"
```

**Query in InfluxDB:**
```sql
SELECT time, entity_id, state
FROM homeassistant
WHERE time > now() - INTERVAL '1 hour'
ORDER BY time DESC
```

### ESP Sensor Integration

**Device firmware:** https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor

**MQTT Topics:**
```
esp-sensor-hub/{device_id}/temperature
  payload: {"device": "Big-Garage", "celsius": 24.5, "fahrenheit": 76.1}

esp-sensor-hub/{device_id}/events
  payload: {"device": "Big-Garage", "event": "startup", "chip_id": "ABC123"}
```

**InfluxDB 3 Schema:**
```
measurement: esp_temperature
tags: device, chip_id
fields: celsius, fahrenheit
time: timestamp
```

**Device configuration:**
- WiFi SSID/Password
- InfluxDB URL: `http://192.168.x.x:8181`
- Database: `temperature_data`
- Token: `INFLUXDB3_ADMIN_TOKEN` from `.env`

---

## Temperature Monitoring

### Dashboard Setup (Grafana Cloud)

**Primary visualization:** Grafana Cloud dashboards

**Data source configuration:**
1. Add datasource: **InfluxDB FlightSQL**
2. URL: `http://influxdb3-core:8181` (if using pdc-agent tunnel)
3. Database: `temperature_data`
4. Authentication: Bearer token (if external access)

**FlightSQL Query Example:**
```sql
SELECT
  time,
  device,
  celsius
FROM esp_temperature
WHERE time >= $__timeFrom AND time <= $__timeTo
ORDER BY time, device
```

### Panel Configurations

**Gauge Panel (Latest Temperature):**
```sql
SELECT celsius, fahrenheit
FROM esp_temperature
WHERE device = 'Big-Garage'
  AND time >= $__timeFrom
  AND time <= $__timeTo
ORDER BY time DESC
LIMIT 1
```

**Config:**
- Unit: Celsius
- Min: -10°C, Max: 30°C
- Thresholds:
  - -10° → dark-blue
  - 0° → light-blue
  - 15° → light-green
  - 20° → dark-green
  - 25° → orange
  - 31° → red

**Timeseries Panel (Multi-Device):**
```sql
SELECT time, device, celsius
FROM esp_temperature
WHERE time >= $__timeFrom AND time <= $__timeTo
ORDER BY time, device
```

**Transformations:**
1. Filter fields: Keep `time`, `device`, `celsius`
2. Organize: Order as time, device, celsius

**Field overrides:**
```json
{
  "matcher": {"id": "byName", "options": "celsius"},
  "properties": [
    {"id": "displayName", "value": "${__field.labels.device}"}
  ]
}
```

**Legend:**
- Display mode: Table
- Calcs: min, max, median, last
- Placement: Bottom

### Adding New Sensors

**1. Flash ESP firmware with config:**
- Device name (e.g., "Basement")
- WiFi credentials
- InfluxDB URL, token, database

**2. Verify data flow:**
```bash
# Watch MQTT
mosquitto_sub -h 127.0.0.1 -t 'esp-sensor-hub/+/temperature'

# Query InfluxDB
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 query temperature_data \
  --token "${TOKEN}" \
  "SELECT * FROM esp_temperature WHERE device = 'Basement' LIMIT 10"
```

**3. Update Grafana dashboard:**
- Device will automatically appear in multi-device timeseries
- For dedicated gauge: duplicate panel, update WHERE clause

---

## Victron Solar System

### Device Setup

**Device:** Victron MPPT/Battery Shunt Monitor at IP `192.168.0.176`

**Configuration:**
- Device name: `bgsolarmon`
- Domain: `bgsolarmon.xgrunt.com`
- InfluxDB URL: `http://192.168.0.167:8086` (InfluxDB 2.x)
- Organization: `[INFLUXDB_ORG_ID]`
- Bucket: `sensor_data`
- Token: `[INFLUXDB_ADMIN_TOKEN]`

**Measurement schema:**
```
measurement: battery (or victron)
fields:
  - soc: State of Charge (%)
  - voltage: Battery Voltage (V)
  - current: Battery Current (A)
  - time_remaining: Time to empty (minutes)
  - consumed_ah: Consumed Amp Hours
  - max_voltage: Maximum voltage recorded
  - min_voltage: Minimum voltage recorded
  - deepest_discharge: Deepest discharge percentage
tags:
  - device: bgsolarmon
  - location: your_location
```

### Nginx Proxy Manager Configuration

**Create proxy host for web interface:**

File: `nginx-proxy-manager/data/nginx/proxy_host/X.conf`

```nginx
server {
  set $forward_scheme http;
  set $server         "192.168.0.176";
  set $port           80;

  listen 80;
  listen [::]:80;

  server_name bgsolarmon.xgrunt.com;

  location / {
    proxy_pass $forward_scheme://$server:$port;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

**Reload Nginx:**
```bash
docker compose exec nginx-proxy-manager nginx -s reload
```

### Grafana Dashboard

**Panels:**
1. **Battery State of Charge** - Gauge showing current %
2. **Voltage Over Time** - Timeseries
3. **Current Flow** - Timeseries (positive = charging, negative = discharging)
4. **Time Remaining** - Stat panel
5. **Consumed Ah** - Counter

**Query examples:**
```sql
-- State of Charge
SELECT soc FROM battery WHERE device = 'bgsolarmon' ORDER BY time DESC LIMIT 1

-- Voltage history
SELECT time, voltage FROM battery WHERE device = 'bgsolarmon' AND time > now() - INTERVAL '24 hours'
```

---

## MCP Servers (AI Assistance)

Model Context Protocol servers enhance VS Code Copilot with file system and Docker access.

### Installed Servers

**1. Filesystem MCP:**
- Direct file access for configs, scripts, logs
- Full read/write access to `/home/aachten/docker/`

**2. Docker MCP:**
- Manage containers, images, volumes
- View logs, inspect containers
- Execute commands in containers

### Configuration

**VS Code settings.json:**
```json
{
  "github.copilot.chat.mcp.servers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/aachten/docker"
      ]
    },
    "docker": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-docker"]
    }
  }
}
```

### Prerequisites

```bash
# Node.js 20+
node --version

# Docker socket access
ls -la /var/run/docker.sock

# User in docker group
groups | grep docker
```

### Usage with Copilot

Example prompts that leverage MCP:

- "Show me the Telegraf configuration"
- "List all running containers"
- "What's in the Prometheus logs?"
- "Check disk usage on Docker volumes"
- "Restart the influxdb3-core container"

### Troubleshooting MCP

**MCP servers not loading:**
```bash
# Check Node.js installed
node --version

# Reload VS Code
# Cmd+Shift+P → "Developer: Reload Window"
```

**Permission denied on Docker socket:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in
```

---

## Permissions Reference

### Container User IDs

Different containers run as different users:

| Container | UID | GID | User Name |
|-----------|-----|-----|-----------|
| prometheus | 65534 | 65534 | nobody:nogroup |
| grafana | 472 | 472 | grafana:grafana |
| mosquitto | 1883 | 1883 | mosquitto:mosquitto |
| influxdb3-core | 1000 | 1000 | aachten:aachten |
| nginx-proxy-manager | 0 | 0 | root:root |
| portainer | 0 | 0 | root:root |

### Volume Permissions

**Docker-managed volumes (_data directories):**
```bash
/var/lib/docker/volumes/docker_prometheus-data/_data/
  drwxrwxr-x (775) 65534:65534

/var/lib/docker/volumes/docker_grafana-data/_data/
  drwxrwxr-x (775) 472:472

/var/lib/docker/volumes/docker_mosquitto-data/_data/
  drwxr-xr-x (755) 1883:1883

/var/lib/docker/volumes/docker_influxdb3-data/_data/
  drwxr-xr-x (755) 1000:1000

/var/lib/docker/volumes/docker_portainer-data/_data/
  drwxr-xr-x (755) aachten:aachten
```

**Bind mounts:**
```bash
/storage/nginx-proxy-manager/data/
  drwxr-xr-x (755) root:root

/storage/influxdb/data/
  drwx------ (700) aachten:aachten

/home/aachten/homeassistant/
  drwxr-xr-x (755) aachten:aachten
```

### Permission Notation

**Octal to symbolic:**
- `755` = `rwxr-xr-x` (owner: full, group/others: read+execute)
- `775` = `rwxrwxr-x` (owner/group: full, others: read+execute)
- `750` = `rwxr-x---` (owner: full, group: read+execute, others: none)
- `700` = `rwx------` (owner: full, group/others: none)
- `664` = `rw-rw-r--` (owner/group: read+write, others: read)

### Fixing Permission Issues

**Automated fix:**
```bash
./scripts/fix-docker-permissions.sh
```

**Manual fix for specific service:**
```bash
# Example: Prometheus
sudo chown -R 65534:65534 /var/lib/docker/volumes/docker_prometheus-data/_data/
sudo chmod 775 /var/lib/docker/volumes/docker_prometheus-data/_data/
docker compose restart prometheus
```

### /storage Mount (NVME)

**Issue:** After reboot, `/storage` ownership reverts to root:root

**Solution:** Systemd service auto-fixes ownership

**Service file:** `/etc/systemd/system/fix-storage-ownership.service`

```ini
[Unit]
Description=Fix ownership of /storage after mount
After=storage.mount
RequiresMountsFor=/storage

[Service]
Type=oneshot
ExecStart=/bin/chown -R aachten:aachten /storage
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

**Check status:**
```bash
sudo systemctl status fix-storage-ownership.service
```

---

## Making Repository Public

### Security Checklist

**✅ Before making public:**

1. **Verify `.env` is gitignored:**
   ```bash
   git check-ignore -v .env
   # Should show: .gitignore:X:.env
   ```

2. **Check for secrets in history:**
   ```bash
   git log --all -S "token" --oneline
   git log --all -S "password" --oneline
   ```

3. **Verify sensitive files excluded:**
   ```bash
   cat .gitignore | grep -E "\.env|\.key|\.pem|\.crt"
   ```

4. **Test from fresh clone:**
   ```bash
   cd /tmp
   git clone /home/aachten/docker test-clone
   cd test-clone
   ls -la .env  # Should NOT exist
   ls -la .env.example  # Should exist
   ```

5. **Run validation script:**
   ```bash
   ./scripts/validate_secrets.sh
   # Should fail with "placeholder" warnings (expected)
   ```

### Files That Will Be Public

**Safe to share:**
- `docker-compose.yml` (uses `${VARIABLES}`)
- `.env.example` (placeholders only)
- `.gitignore` (protects secrets)
- All `docs/`, `scripts/`, configs
- README and setup guides

**Never public (gitignored):**
- `.env` (actual credentials)
- `*.key`, `*.pem`, `*.crt` files
- Backup files
- Docker volume data

### Making It Public

```bash
# 1. Final verification
./scripts/validate_secrets.sh
git status  # Ensure no .env staged

# 2. Push to GitHub
git push origin main

# 3. Change repository visibility
# GitHub → Settings → Danger Zone → Change visibility → Public
```

### After Making Public

- Update README with public repository URL
- Add LICENSE file
- Enable GitHub Issues
- Add CONTRIBUTING.md if accepting contributions

---

## Additional Resources

### InfluxDB 3 Core
- Docs: https://docs.influxdata.com/influxdb3/core/
- API Reference: https://docs.influxdata.com/influxdb3/core/api/
- GitHub: https://github.com/aachtenberg/influxdbv3-core

### Grafana
- Cloud: https://grafana.com/
- Docs: https://grafana.com/docs/
- FlightSQL Datasource: https://grafana.com/grafana/plugins/grafana-influxdb-flightsql-datasource/

### Home Assistant
- Docs: https://www.home-assistant.io/docs/
- MQTT Integration: https://www.home-assistant.io/integrations/mqtt/

### ESP Sensors
- Firmware: https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor
- Setup Guide: https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor/blob/main/docs/guides/SECRETS_SETUP.md

### Docker
- Compose: https://docs.docker.com/compose/
- Networking: https://docs.docker.com/network/
- Volumes: https://docs.docker.com/storage/volumes/

---

**For setup and daily operations, see:**
- [Setup Guide](SETUP.md) - Initial installation
- [Operations Guide](OPERATIONS.md) - Daily operations, backup, troubleshooting
