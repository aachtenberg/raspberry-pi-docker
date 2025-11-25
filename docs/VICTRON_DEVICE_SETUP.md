# Victron ESP32 Device Setup (192.168.0.176)

This guide covers the setup and configuration for the new Victron MPPT/Battery Shunt monitoring device at IP `192.168.0.176`.

## Overview

- **Device IP**: `192.168.0.176`
- **Device Name**: bgsolarmon (Victron MPPT and Battery Shunt Monitor)
- **Web Interface Port**: 80
- **Domain**: `bgsolarmon.xgrunt.com`
- **InfluxDB Bucket**: `sensor_data` (same as other devices)
- **Access**: Internal + Remote via Cloudflare Tunnel

## Step 1: Configure ESP32 Device Firmware

Update the ESP32 device configuration with the following InfluxDB credentials:

### Required Configuration

```
InfluxDB URL: http://192.168.0.167:8086
Organization: [INFLUXDB_ORG_ID from .env]
Bucket: sensor_data
Token: [INFLUXDB_ADMIN_TOKEN from .env]
Device Name: bgsolarmon
Measurement: battery (or victron - align with dashboard expectations)
```

### Measurement Fields Expected

The device should send data with these fields (align with `victron_battery_monitoring.json` dashboard):

```
measurement: battery
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

See: [Victron Battery Monitoring Dashboard](../grafana/dashboards/victron_battery_monitoring.json)

## Step 2: Configure Nginx Proxy Manager

Access the Nginx Proxy Manager admin panel and create a new proxy rule.

### Access Admin UI
```bash
# Open in browser or SSH tunnel
http://localhost:81
```

### Create Proxy Rule

1. **Click "Proxy Hosts"** in the left menu
2. **Click "Add Proxy Host"** button
3. **Fill in the following:**

| Field | Value |
|-------|-------|
| Domain Names | `bgsolarmon.xgrunt.com` |
| Scheme | `http` |
| Forward Hostname/IP | `192.168.0.176` |
| Forward Port | `80` |
| Cache Assets | `On` |
| Block Common Exploits | `On` |
| Websockets Support | `Off` |

4. **SSL Tab:**
   - SSL Certificate: `Request a new SSL Certificate`
   - Force SSL: `On`
   - HTTP/2 Support: `On`
   - Email: your-email@xgrunt.com
   - I Agree to the Let's Encrypt Terms: ✓

5. **Advanced Tab (Optional):**
   - Add Custom Locations if needed for specific paths

6. **Click "Save"**

### Expected Result

- Nginx will request SSL certificate from Let's Encrypt
- Both `http://bgsolarmon.xgrunt.com` and `https://bgsolarmon.xgrunt.com` will work
- Requests will be forwarded to `http://192.168.0.176:80`

## Step 3: Configure Cloudflare Tunnel

Add routing rule to expose the device through Cloudflare Tunnel.

### Access Cloudflare Dashboard

1. Go to: https://one.dash.cloudflare.com/
2. Navigate to: **Access** → **Tunnels** → **raspberry-pi-docker** (or your tunnel name)
3. Click **Public Hostname** tab
4. Click **Create a public hostname**

### Create Tunnel Route

| Field | Value |
|-------|-------|
| Subdomain | `bgsolarmon` |
| Domain | `xgrunt.com` |
| Type | `HTTP` |
| URL | `http://localhost:8080` |

**Explanation**: 
- Requests to `bgsolarmon.xgrunt.com` are routed through Cloudflare
- Cloudflare tunnel connects back to your Raspberry Pi at `localhost:8080` (nginx port)
- Nginx internally routes to `192.168.0.176:80`

5. **Click "Save hostname"**

### DNS Verification

Check that DNS is properly configured:

```bash
# Should resolve to Cloudflare nameservers
nslookup bgsolarmon.xgrunt.com

# Test from internal network
curl -H "Host: bgsolarmon.xgrunt.com" http://192.168.0.167:8080

# Test from external network (after propagation)
curl https://bgsolarmon.xgrunt.com
```

## Step 4: Verify Connectivity

### Test Internal Access

```bash
# From Raspberry Pi
curl http://bgsolarmon.xgrunt.com
curl https://bgsolarmon.xgrunt.com

# Check Nginx logs
docker compose logs -f nginx-proxy-manager | grep bgsolarmon

# Check device accessibility
curl http://192.168.0.176
```

### Test Remote Access (After DNS Propagation)

```bash
# From external network
curl https://bgsolarmon.xgrunt.com

# Check Cloudflare tunnel status
docker compose logs -f cloudflared | grep bgsolarmon
```

### Verify Data Flow to InfluxDB

```bash
# Query recent data from device
docker exec influxdb influx query \
  'from(bucket: "sensor_data") 
   |> range(start: -1h) 
   |> filter(fn: (r) => r._measurement == "battery" and r.device == "bgsolarmon") 
   |> count()'

# Should show count > 0 if data is being written
```

## Step 5: Monitor in Grafana

The device data should automatically appear in the existing **Victron Battery Monitoring** dashboard.

1. Open Grafana: `http://localhost:3000`
2. Go to: **Dashboards** → **Victron Battery Monitoring**
3. Verify new device data appears in panels
4. Data typically takes 1-5 minutes to appear after first write

### Add Device Filter (Optional)

If you want to filter by specific device:

1. Edit dashboard
2. Add panel variable for device selection
3. Use in queries: `|> filter(fn: (r) => r.device == var.device)`

## Step 6: Monitor Prometheus Metrics

The device endpoint is now scraped by Prometheus.

```bash
# View Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.device == "bgsolarmon")'

# Query metrics from device
curl 'http://localhost:9090/api/v1/query?query=up{device="bgsolarmon"}'
```

## Step 7: Commit Configuration Changes

```bash
cd ~/docker

# Review changes
git diff prometheus/prometheus.yml

# Commit
git add prometheus/prometheus.yml
git commit -m "feat: add Victron device (192.168.0.176) to Prometheus scrape config"
git push origin main
```

## Troubleshooting

### Device Not Sending Data to InfluxDB

1. **Check device connectivity**:
   ```bash
   ping 192.168.0.176
   curl http://192.168.0.176
   ```

2. **Verify InfluxDB credentials in device**:
   - Check ESP32 web interface for stored configuration
   - Ensure token, org, and bucket match `.env` file

3. **Check InfluxDB token permissions**:
   ```bash
   docker compose logs influxdb | grep -i "token\|error"
   ```

### Nginx Proxy Rule Not Working

1. **Verify proxy rule exists**:
   - Check Nginx Proxy Manager UI at `http://localhost:81`
   - Confirm `bgsolarmon.xgrunt.com` is listed

2. **Check nginx logs**:
   ```bash
   docker compose logs nginx-proxy-manager | grep bgsolarmon
   ```

3. **Test direct connection**:
   ```bash
   curl -v http://192.168.0.176:80
   ```

### Cloudflare Tunnel Not Routing Correctly

1. **Verify tunnel is running**:
   ```bash
   docker compose ps cloudflared
   docker compose logs cloudflared
   ```

2. **Check tunnel status**:
   - Go to Cloudflare Dashboard → Access → Tunnels
   - Verify tunnel shows "Connected"

3. **Verify hostname routing**:
   - Go to Cloudflare Dashboard → Access → Tunnels → Public Hostnames
   - Confirm `bgsolarmon.xgrunt.com` routes to `http://localhost:8080`

### SSL Certificate Issues

1. **Check certificate status**:
   ```bash
   docker compose logs nginx-proxy-manager | grep -i "letsencrypt\|ssl"
   ```

2. **Force renew certificate**:
   - Nginx Proxy Manager UI → Proxy Hosts → Edit → SSL Tab → Force Renew

3. **Manual renewal**:
   ```bash
   docker compose exec nginx-proxy-manager \
     certbot renew --dry-run
   ```

## Monitoring and Maintenance

### Daily Checks

```bash
# Verify device is sending data
curl https://bgsolarmon.xgrunt.com/api/health

# Check tunnel connectivity
docker compose logs --tail=20 cloudflared | grep -i "status\|connected"

# Monitor device metrics
curl http://localhost:9090/api/v1/query?query='up{device="bgsolarmon"}'
```

### Weekly Tasks

- Review Victron Battery Monitoring dashboard for anomalies
- Check device web interface for warnings/errors
- Verify InfluxDB is storing new data
- Monitor disk usage on Raspberry Pi

### Monthly Tasks

- Export Grafana dashboards: `./scripts/export_grafana_dashboards.sh`
- Review device data retention policies
- Check SSL certificate expiration: `certbot certificates`

## Related Documentation

- [Victron Battery Monitoring Dashboard](../grafana/dashboards/victron_battery_monitoring.json)
- [Nginx Proxy Manager Setup](https://nginxproxymanager.com/)
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [InfluxDB API Documentation](https://docs.influxdata.com/influxdb/cloud/api/)

---

**Created**: November 25, 2025
**Device IP**: 192.168.0.176
**Domain**: bgsolarmon.xgrunt.com
