# Raspberry Pi Docker Stack Setup Guide

This guide covers the complete setup and configuration of the Raspberry Pi home automation and monitoring infrastructure.

## Quick Start

1. **Clone repository**:
   ```bash
   git clone https://github.com/aachtenberg/raspberry-pi-docker.git
   cd raspberry-pi-docker
   ```

2. **Configure secrets** (see [Secrets Configuration](#secrets-configuration))

3. **Deploy services**:
   ```bash
   docker compose up -d
   ```

4. **Verify deployment** (see [Verification](#verification))

## Architecture Overview

This infrastructure receives, stores, and visualizes temperature data from multiple ESP8266/ESP32 devices:

```
4 ESP Devices → MQTT/HTTP → InfluxDB → Grafana Dashboards
                                ↓
                         Prometheus Stack → System Monitoring
                                ↓
                      Cloudflare Tunnel → Remote Access
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| InfluxDB | 8086 | Time-series database for ESP sensor data |
| Grafana | 3000 | Dashboards and visualization |
| Prometheus | 9090 | Metrics collection |
| Loki | 3100 | Log aggregation |
| Node Exporter | 9100 | System metrics |
| cAdvisor | 8081 | Container metrics |
| Home Assistant | 8123 | Home automation |
| Mosquitto | 1883 | MQTT broker |
| Nginx Proxy Manager | 81, 8080, 8443 | Reverse proxy |
| Cloudflared | - | Cloudflare tunnel |

## Secrets Configuration

### 1. Create Environment File

```bash
cd ~/docker
cp .env.example .env
vim .env
```

### 2. Required Secrets

#### Cloudflare Tunnel Token
1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Navigate to **Access** → **Tunnels**
3. Find your tunnel (or create new one)
4. Copy the tunnel token

```bash
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiZWEyNmZkZjVhOWVh...
```

#### InfluxDB Configuration

```bash
# Admin credentials
INFLUXDB_ADMIN_USERNAME=admin
INFLUXDB_ADMIN_PASSWORD=YourSecurePassword123!

# Organization (16-character hex string)
INFLUXDB_ORG_ID=abc123def4567890

# Bucket name (must match ESP device config)
INFLUXDB_BUCKET=sensor_data

# API Token (generate in InfluxDB UI after first setup)
INFLUXDB_ADMIN_TOKEN=Mqj3XYZ_example_token_abc123==
```

#### Grafana API Keys (for dashboard export/import)

```bash
# Read-only API key for exports
GRAFANA_API_KEY=glsa_example_read_key

# Admin API key for imports
GRAFANA_ADMIN_API_KEY=glsa_example_admin_key
```

### 3. Generate InfluxDB API Token

After InfluxDB starts:
1. Open http://localhost:8086
2. Login with admin credentials
3. Go to **Data** → **API Tokens**
4. Click **Generate API Token** → **All Access Token**
5. Copy token to `.env` file

### 4. Generate Grafana API Keys

1. Open http://localhost:3000 (admin/admin initially)
2. Go to **Administration** → **Service Accounts**
3. Create "dashboard-export" with Viewer role
4. Create "dashboard-admin" with Admin role
5. Generate tokens and add to `.env`

### 5. Validate Configuration

```bash
./scripts/validate_secrets.sh
```

## Verification

### Check All Services

```bash
docker compose ps
./scripts/status.sh
```

### Test Web Interfaces

- **Grafana**: http://localhost:3000
- **InfluxDB**: http://localhost:8086
- **Prometheus**: http://localhost:9090
- **Home Assistant**: http://localhost:8123
- **Nginx Proxy Manager**: http://localhost:81

### Verify Data Flow

1. **Check ESP devices**: Ensure temperature sensors are sending data
2. **Check InfluxDB**: Query `sensor_data` bucket for recent data
3. **Check Grafana**: Open temperature dashboard for live data

## MCP Servers Setup (Optional)

For enhanced AI assistance with VS Code/Copilot:

### 1. Configure VS Code Settings

Add to `.vscode/settings.json`:

```json
{
  "github.copilot.chat.mcp.servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/aachten/docker"]
    },
    "docker": {
      "command": "npx", 
      "args": ["-y", "@modelcontextprotocol/server-docker"]
    }
  }
}
```

### 2. Prerequisites

```bash
# Ensure Node.js 20+ is installed
node --version

# Ensure Docker access
docker ps
```

### 3. Reload VS Code

Restart VS Code to activate MCP servers for enhanced Docker and file management.

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs [service-name]

# Restart service
docker compose restart [service-name]
```

### InfluxDB Connection Issues

- Verify admin token is correct
- Check organization ID matches
- Ensure bucket exists

### Grafana Dashboard Issues

- Verify API keys have correct permissions
- Check data source configuration
- Ensure Prometheus is scraping metrics

### ESP Devices Not Sending Data

- Check device WiFi connection
- Verify InfluxDB credentials in device firmware
- Check MQTT broker connectivity

## Security Best Practices

- Never commit `.env` file
- Use strong, unique passwords
- Regenerate tokens if accidentally exposed
- Keep services updated
- Monitor access logs

## Backup and Recovery

### Automated Backups

Grafana dashboards are automatically backed up daily at 2 AM:

```bash
# View cron schedule
crontab -l

# Check backup logs
tail -f ~/docker/logs/grafana_backup.log
```

### Manual Backup

```bash
# Export dashboards
./scripts/export_grafana_dashboards.sh

# Backup volumes
docker compose down
tar czf backup-$(date +%Y%m%d).tar.gz ~/docker /var/lib/docker/volumes/docker_*
```

### Recovery

```bash
# Import dashboards
./scripts/import_grafana_dashboards.sh

# Restore volumes
docker compose down
tar xzf backup-YYYYMMDD.tar.gz -C /
docker compose up -d
```

## Related Projects

- **ESP Temperature Sensors**: [github.com/aachtenberg/esp12f_ds18b20_temp_sensor](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor)
- **Device Setup Guide**: [ESP Secrets Setup](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor/blob/main/docs/guides/SECRETS_SETUP.md)

## Getting Help

- **Infrastructure Issues**: [GitHub Issues](https://github.com/aachtenberg/raspberry-pi-docker/issues)
- **ESP Device Issues**: [Device Repository](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor/issues)
- **Documentation**: [InfluxDB](https://docs.influxdata.com/), [Grafana](https://grafana.com/docs/), [Prometheus](https://prometheus.io/docs/)

---

**Last Updated**: November 2025