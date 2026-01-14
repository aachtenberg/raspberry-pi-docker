#!/bin/bash
# verify-backup-coverage.sh
# Verify that all important data is being backed up

set -e

echo "=== Backup Coverage Verification ==="
echo ""

# Check what volumes exist
echo "📦 Docker Volumes:"
ACTUAL_VOLUMES=$(docker volume ls --format "{{.Name}}" | grep "^docker_" | sort)
BACKED_UP_VOLUMES=(
    "docker_prometheus-data"
    "docker_influxdb3-data"
    "docker_portainer-data"
    "docker_mosquitto-data"
    "docker_mosquitto-log"
    "docker_loki-data"
    "docker_pdc-agent-ssh"
)

for vol in $ACTUAL_VOLUMES; do
    if [[ " ${BACKED_UP_VOLUMES[@]} " =~ " ${vol} " ]]; then
        echo "  ✅ $vol (backed up)"
    else
        echo "  ⚠️  $vol (NOT backed up - excluded)"
    fi
done

echo ""
echo "📁 Bind Mount Directories:"
BIND_DIRS=(
    "/home/aachten/homeassistant"
    "/storage/nginx-proxy-manager"
    "/home/aachten/docker/ai-monitor/incidents"
)

for dir in "${BIND_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        SIZE=$(du -sh "$dir" 2>/dev/null | cut -f1)
        echo "  ✅ $dir ($SIZE)"
    else
        echo "  ❌ $dir (does not exist)"
    fi
done

echo ""
echo "📝 Config Files:"
CONFIG_FILES=(
    "/home/aachten/docker/.env"
    "/home/aachten/docker/docker-compose.yml"
    "/home/aachten/docker/prometheus/prometheus.yml"
    "/home/aachten/docker/prometheus/influxdb3_token"
    "/home/aachten/docker/mosquitto/mosquitto.conf"
    "/home/aachten/docker/telegraf/telegraf.conf"
)

for file in "${CONFIG_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (missing)"
    fi
done

echo ""
echo "🕐 Backup Schedule:"
if sudo systemctl is-active docker-backup.timer &>/dev/null; then
    NEXT_RUN=$(sudo systemctl status docker-backup.timer | grep "Trigger:" | cut -d: -f2- | xargs)
    echo "  ✅ Timer active - Next run: $NEXT_RUN"
else
    echo "  ❌ Timer not active"
fi

echo ""
echo "💾 NAS Mount:"
if mountpoint -q /mnt/nas-backup; then
    SIZE=$(df -h /mnt/nas-backup | tail -1 | awk '{print $3 " used / " $2 " total (" $5 " full)"}')
    echo "  ✅ Mounted at /mnt/nas-backup"
    echo "     $SIZE"
else
    echo "  ❌ Not mounted"
fi

echo ""
echo "📊 Recent Backups:"
if [ -d "/mnt/nas-backup/docker-backups/$(hostname)" ]; then
    BACKUP_COUNT=$(find /mnt/nas-backup/docker-backups/$(hostname) -maxdepth 1 -type d -name "2*" | wc -l)
    LATEST=$(ls -td /mnt/nas-backup/docker-backups/$(hostname)/2* 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        LATEST_DATE=$(basename "$LATEST")
        LATEST_SIZE=$(du -sh "$LATEST" 2>/dev/null | cut -f1)
        echo "  ✅ $BACKUP_COUNT backups found"
        echo "     Latest: $LATEST_DATE ($LATEST_SIZE)"
    else
        echo "  ⚠️  No backups found"
    fi
else
    echo "  ❌ Backup directory not found"
fi

echo ""
echo "=== Summary ==="
echo ""
echo "Backed up volumes: ${#BACKED_UP_VOLUMES[@]}"
echo "Bind mount dirs: ${#BIND_DIRS[@]}"
echo "Config files tracked: ${#CONFIG_FILES[@]}"
echo ""
echo "💡 Run './scripts/backup_to_nas.sh' to create a manual backup now"
echo ""
