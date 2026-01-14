#!/bin/bash
# export-health-metrics.sh
# Export infrastructure health metrics for AI agent investigation
# This runs periodically (via cron or systemd timer) to populate Prometheus with
# health signals that the AI agent can query and investigate proactively.

set -e

METRICS_FILE="/var/lib/node_exporter/textfile_collector/infrastructure_health.prom"
TEMP_FILE="${METRICS_FILE}.$$"

# Ensure directory exists
sudo mkdir -p /var/lib/node_exporter/textfile_collector

# Start metrics file
cat > "$TEMP_FILE" << 'EOF'
# Infrastructure Health Metrics for AI Agent
# These metrics provide signals for proactive investigation

EOF

# ===== Backup Health =====
BACKUP_AGE=$(curl -s 'http://localhost:9090/api/v1/query?query=time()-docker_backup_last_success_timestamp' 2>/dev/null | jq -r '.data.result[0].value[1] // "0"' | awk '{print int($1)}')
BACKUP_STALE=0
if [ "$BACKUP_AGE" -gt 86400 ]; then  # >24 hours
    BACKUP_STALE=1
fi

cat >> "$TEMP_FILE" << EOF
# HELP infra_backup_age_seconds Time since last successful backup
# TYPE infra_backup_age_seconds gauge
infra_backup_age_seconds{hostname="$(hostname)"} $BACKUP_AGE

# HELP infra_backup_stale Backup is stale (>24h old)
# TYPE infra_backup_stale gauge
infra_backup_stale{hostname="$(hostname)"} $BACKUP_STALE

EOF

# ===== Disk Space Health =====
ROOT_USAGE=$(df / | tail -1 | awk '{print int($5)}')
ROOT_CRITICAL=0
if [ "$ROOT_USAGE" -gt 85 ]; then
    ROOT_CRITICAL=1
fi

NAS_AVAILABLE=$(mountpoint -q /mnt/nas-backup && echo 1 || echo 0)

cat >> "$TEMP_FILE" << EOF
# HELP infra_disk_usage_percent Disk usage percentage
# TYPE infra_disk_usage_percent gauge
infra_disk_usage_percent{mountpoint="/",hostname="$(hostname)"} $ROOT_USAGE

# HELP infra_disk_critical Disk usage critical (>85%)
# TYPE infra_disk_critical gauge
infra_disk_critical{mountpoint="/",hostname="$(hostname)"} $ROOT_CRITICAL

# HELP infra_nas_available NAS mount is accessible
# TYPE infra_nas_available gauge
infra_nas_available{hostname="$(hostname)"} $NAS_AVAILABLE

EOF

# ===== Data Freshness (InfluxDB3) =====
INFLUX_LAST_WRITE=$(docker exec influxdb3-core influxdb3 query --database sensors --token "$(grep INFLUXDB3_ADMIN_TOKEN /home/aachten/docker/.env | cut -d= -f2)" \
    "SELECT time FROM temperature ORDER BY time DESC LIMIT 1" 2>/dev/null | \
    grep -E '^[0-9]{4}' | head -1 || echo "")

if [ -n "$INFLUX_LAST_WRITE" ]; then
    INFLUX_LAST_TS=$(date -d "$INFLUX_LAST_WRITE" +%s 2>/dev/null || echo 0)
    INFLUX_AGE=$(($(date +%s) - INFLUX_LAST_TS))
    INFLUX_STALE=0
    if [ "$INFLUX_AGE" -gt 3600 ]; then  # >1 hour
        INFLUX_STALE=1
    fi
else
    INFLUX_AGE=999999
    INFLUX_STALE=1
fi

cat >> "$TEMP_FILE" << EOF
# HELP infra_data_age_seconds Time since last data write
# TYPE infra_data_age_seconds gauge
infra_data_age_seconds{database="influxdb3",measurement="temperature",hostname="$(hostname)"} $INFLUX_AGE

# HELP infra_data_stale Data is stale (>1h old)
# TYPE infra_data_stale gauge
infra_data_stale{database="influxdb3",measurement="temperature",hostname="$(hostname)"} $INFLUX_STALE

EOF

# ===== Service Health =====
# Check critical services have recent metrics
PROM_UP=$(curl -s 'http://localhost:9090/api/v1/query?query=up{job="prometheus"}' 2>/dev/null | jq -r '.data.result[0].value[1] // "0"')
TELEGRAF_UP=$(curl -s 'http://localhost:9090/api/v1/query?query=up{job="telegraf"}' 2>/dev/null | jq -r '.data.result[0].value[1] // "0"')
MOSQUITTO_UP=$(curl -s 'http://localhost:9090/api/v1/query?query=up{job="mosquitto"}' 2>/dev/null | jq -r '.data.result[0].value[1] // "0"')
PDC_AGENT_UP=$(docker ps --filter "name=pdc-agent" --filter "status=running" --format "{{.Names}}" | grep -q pdc && echo 1 || echo 0)

cat >> "$TEMP_FILE" << EOF
# HELP infra_service_healthy Service is healthy and scraped recently
# TYPE infra_service_healthy gauge
infra_service_healthy{service="prometheus",hostname="$(hostname)"} $PROM_UP
infra_service_healthy{service="telegraf",hostname="$(hostname)"} $TELEGRAF_UP
infra_service_healthy{service="mosquitto",hostname="$(hostname)"} $MOSQUITTO_UP
infra_service_healthy{service="pdc-agent",hostname="$(hostname)"} $PDC_AGENT_UP

EOF

# Move to final location atomically
sudo mv "$TEMP_FILE" "$METRICS_FILE"
sudo chmod 644 "$METRICS_FILE"

echo "✅ Health metrics exported to $METRICS_FILE"
