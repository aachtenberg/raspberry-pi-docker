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

### Nginx Proxy Manager Configuration

**File Locations:**
- Proxy host configs: `nginx-proxy-manager/data/nginx/proxy_host/*.conf`
- Each config file represents one proxy host entry
- Configs are tracked in git for version control

**Adding a new proxy entry:**

1. **Determine the next config number:**
   ```bash
   ls nginx-proxy-manager/data/nginx/proxy_host/ | grep -o "[0-9]*" | sort -n | tail -1
   # Use next number (e.g., if max is 5, use 6)
   ```

2. **Create config file** (e.g., `6.conf` for spa.xgrunt.com → 192.168.0.213:80):
   ```bash
   cat > nginx-proxy-manager/data/nginx/proxy_host/6.conf << 'EOF'
   # ------------------------------------------------------------
   # spa.xgrunt.com
   # ------------------------------------------------------------
   
   map $scheme $hsts_header {
       https   "max-age=63072000; preload";
   }
   
   server {
     set $forward_scheme http;
     set $server         "192.168.0.213";
     set $port           80;
   
     listen 80;
     listen [::]:80;
   
     server_name spa.xgrunt.com;
     http2 off;
   
     # Block Exploits
     include conf.d/include/block-exploits.conf;
   
     # Proxy
     location / {
       proxy_pass            $forward_scheme://$server:$port;
       
       # Timeouts
       proxy_connect_timeout 600s;
       proxy_send_timeout    600s;
       proxy_read_timeout    600s;
   
       # Proxy headers
       proxy_set_header Host                $host;
       proxy_set_header X-Forwarded-Scheme  $scheme;
       proxy_set_header X-Forwarded-Proto   $scheme;
       proxy_set_header X-Forwarded-For     $remote_addr;
       proxy_set_header X-Real-IP           $remote_addr;
       proxy_http_version                   1.1;
       proxy_set_header Connection          "";
       proxy_buffering                      off;
       proxy_request_buffering              off;
       proxy_max_temp_file_size             0;
   
       # WebSocket support
       proxy_set_header Upgrade           $http_upgrade;
       proxy_set_header Connection        $connection_upgrade;
     }
   }
   EOF
   ```

3. **Reload nginx:**
   ```bash
   docker compose exec -T nginx-proxy-manager nginx -s reload
   ```

4. **Test the proxy:**
   ```bash
   curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" \
     -H "Host: spa.xgrunt.com" http://localhost:8080/
   ```

5. **Commit to git:**
   ```bash
   git add -f nginx-proxy-manager/data/nginx/proxy_host/6.conf
   git commit -m "feat: add spa.xgrunt.com proxy (192.168.0.213)"
   git push
   ```

**Editing existing proxy entries:**

1. Edit the corresponding `.conf` file in `nginx-proxy-manager/data/nginx/proxy_host/`
2. Update `server_name`, `$server`, or `$port` as needed
3. Reload: `docker compose exec -T nginx-proxy-manager nginx -s reload`
4. Test and commit

**Proxy variables to customize:**
- `$server`: Target IP address (e.g., `192.168.0.213`)
- `$port`: Target port (default 80)
- `server_name`: Domain(s) to listen on (e.g., `spa.xgrunt.com`)
- `proxy_connect_timeout`: Connection timeout in seconds

**Notes:**
- Cloudflare tunnel automatically handles HTTPS/SSL routing
- Each proxy host config gets its own numbered file
- Configs are reloaded without container restart
- Add both HTTP (port 80) and HTTPS (port 443) server blocks for full support

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
