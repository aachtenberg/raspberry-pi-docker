#!/bin/bash
# Daily Docker backup to NAS (192.168.0.1)
# Backs up volumes and configs without stopping containers
# Retention: 30 days

set -euo pipefail

# Configuration
NAS_HOST="192.168.0.1"
NAS_SHARE="G"
NAS_USER="admin"
NAS_PASS="canada99"
MOUNT_POINT="/mnt/nas-backup"
HOSTNAME=$(hostname)
BACKUP_BASE="${MOUNT_POINT}/docker-backups/${HOSTNAME}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"
LOG_FILE="/home/aachten/docker/logs/backup-$(date +%Y%m%d).log"

# Ensure log directory exists
mkdir -p /home/aachten/docker/logs

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Error handler
error_exit() {
    log "ERROR: $1"
    
    # Write failure metrics
    METRICS_FILE="/var/lib/node_exporter/textfile_collector/docker_backup.prom"
    cat > "${METRICS_FILE}.$$" << EOF
# HELP docker_backup_status Status of last backup (1=success, 0=failure)
# TYPE docker_backup_status gauge
docker_backup_status{hostname="${HOSTNAME}"} 0

# HELP docker_backup_last_attempt_timestamp Unix timestamp of last backup attempt
# TYPE docker_backup_last_attempt_timestamp gauge
docker_backup_last_attempt_timestamp{hostname="${HOSTNAME}"} $(date +%s)
EOF
    mv "${METRICS_FILE}.$$" "${METRICS_FILE}" 2>/dev/null || true
    cleanup
    exit 1
}

# Cleanup function
cleanup() {
    log "Cleaning up..."
    # Only unmount if we mounted it (not if it's from fstab)
    # Check if mount is persistent (in fstab) - if so, leave it mounted
    if grep -q "$MOUNT_POINT" /etc/fstab; then
        log "NAS mount is persistent (fstab), leaving mounted"
    elif mountpoint -q "$MOUNT_POINT"; then
        sudo umount "$MOUNT_POINT" 2>/dev/null || log "Warning: Failed to unmount $MOUNT_POINT"
    fi
}

trap cleanup EXIT

log "=========================================="
log "Starting Docker backup to NAS"
log "=========================================="

# Check NAS connectivity
log "Checking NAS connectivity..."
if ! ping -c 2 -W 5 "$NAS_HOST" &>/dev/null; then
    error_exit "NAS host $NAS_HOST is unreachable"
fi

# Create mount point
log "Creating mount point..."
sudo mkdir -p "$MOUNT_POINT"

# Mount NAS share (if not already mounted via fstab)
if mountpoint -q "$MOUNT_POINT"; then
    log "NAS already mounted at $MOUNT_POINT"
else
    log "Mounting NAS share //${NAS_HOST}/${NAS_SHARE}..."
    if ! sudo mount "$MOUNT_POINT" 2>/dev/null; then
        # Fallback to manual mount if fstab mount fails
        if ! sudo mount -t cifs "//${NAS_HOST}/${NAS_SHARE}" "$MOUNT_POINT" \
            -o username="${NAS_USER}",password="${NAS_PASS}",uid=$(id -u),gid=$(id -g),file_mode=0644,dir_mode=0755,vers=2.0; then
            error_exit "Failed to mount NAS share"
        fi
    fi
    log "NAS mounted successfully at $MOUNT_POINT"
fi

# Create backup directory structure
log "Creating backup directory structure..."
mkdir -p "${BACKUP_DIR}"/{volumes,configs,metadata}

# Backup Docker volumes (live, without stopping containers)
log "Backing up Docker volumes..."
VOLUMES=(
    "docker_grafana-data"
    "docker_prometheus-data"
    "docker_influxdb3-data"
    "docker_influxdb3-explorer-db"
    "docker_portainer-data"
    "docker_mosquitto-data"
    "docker_mosquitto-log"
)

for volume in "${VOLUMES[@]}"; do
    log "  - Backing up volume: $volume"
    if docker volume inspect "$volume" &>/dev/null; then
        docker run --rm \
            -v "$volume":/data:ro \
            -v "${BACKUP_DIR}/volumes":/backup \
            alpine:latest \
            tar czf "/backup/${volume}-${TIMESTAMP}.tar.gz" -C /data . 2>>"$LOG_FILE" || \
            log "    Warning: Failed to backup $volume"
    else
        log "    Warning: Volume $volume does not exist, skipping"
    fi
done

# Backup bind-mounted directories
log "Backing up bind-mounted directories..."
BIND_MOUNTS=(
    "/home/aachten/homeassistant:homeassistant"
    "/storage/nginx-proxy-manager:nginx-proxy-manager"
    "/storage/influxdb:influxdb"
)

for mount in "${BIND_MOUNTS[@]}"; do
    src="${mount%%:*}"
    name="${mount##*:}"
    if [ -d "$src" ]; then
        log "  - Backing up: $src → ${name}"
        rsync -a --delete --info=progress2 "$src/" "${BACKUP_DIR}/configs/${name}/" 2>>"$LOG_FILE" || \
            log "    Warning: Failed to backup $src"
    else
        log "    Warning: Directory $src does not exist, skipping"
    fi
done

# Backup repository configs
log "Backing up repository configuration..."
rsync -a --delete \
    --exclude='.git' \
    --exclude='data' \
    --exclude='logs' \
    --exclude='*.log' \
    --exclude='__pycache__' \
    --exclude='node_modules' \
    --exclude='.vscode' \
    --exclude='.claude' \
    --exclude='.grok' \
    /home/aachten/docker/ \
    "${BACKUP_DIR}/configs/docker-repo/" 2>>"$LOG_FILE" || \
    log "Warning: Failed to backup repository"

# Copy .env file (unencrypted as requested)
log "Backing up .env file..."
if [ -f /home/aachten/docker/.env ]; then
    cp /home/aachten/docker/.env "${BACKUP_DIR}/configs/docker-repo/.env" || \
        log "Warning: Failed to backup .env"
fi

# Export Docker metadata
log "Exporting Docker metadata..."
docker compose -f /home/aachten/docker/docker-compose.yml config > "${BACKUP_DIR}/metadata/docker-compose-resolved.yml" 2>>"$LOG_FILE"
docker network ls --format "{{.ID}}\t{{.Name}}\t{{.Driver}}" > "${BACKUP_DIR}/metadata/networks.txt" 2>>"$LOG_FILE"
docker volume ls --format "{{.Name}}\t{{.Driver}}\t{{.Mountpoint}}" > "${BACKUP_DIR}/metadata/volumes.txt" 2>>"$LOG_FILE"

# Generate checksums
log "Generating checksums..."
cd "${BACKUP_DIR}/volumes" && sha256sum *.tar.gz > "${BACKUP_DIR}/checksums.txt" 2>>"$LOG_FILE" || log "Warning: Failed to generate checksums"

# Calculate backup size
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "Backup size: $BACKUP_SIZE"

# Cleanup old backups (keep last 30 days)
log "Cleaning up old backups (keeping last 30 days)..."
find "$BACKUP_BASE" -maxdepth 1 -type d -name "2*" -mtime +30 -exec rm -rf {} \; 2>>"$LOG_FILE" || \
    log "Warning: Failed to cleanup old backups"

# Verify backup
log "Verifying backup..."
if [ -f "${BACKUP_DIR}/checksums.txt" ] && [ -d "${BACKUP_DIR}/configs" ]; then
    log "✅ Backup verification passed"
else
    error_exit "Backup verification failed"
fi

BACKUP_SIZE_BYTES=$(du -sb "$BACKUP_DIR" | cut -f1)

log "=========================================="
log "✅ Backup completed successfully!"
log "Location: $BACKUP_DIR"
log "Size: $BACKUP_SIZE"
log "Duration: ${SECONDS}s"
log "=========================================="

# Write metrics for Prometheus
METRICS_FILE="/var/lib/node_exporter/textfile_collector/docker_backup.prom"
cat > "${METRICS_FILE}.$$" << EOF
# HELP docker_backup_last_success_timestamp Unix timestamp of last successful backup
# TYPE docker_backup_last_success_timestamp gauge
docker_backup_last_success_timestamp{hostname="${HOSTNAME}"} $(date +%s)

# HELP docker_backup_size_bytes Size of last backup in bytes
# TYPE docker_backup_size_bytes gauge
docker_backup_size_bytes{hostname="${HOSTNAME}"} ${BACKUP_SIZE_BYTES}

# HELP docker_backup_duration_seconds Duration of last backup in seconds
# TYPE docker_backup_duration_seconds gauge
docker_backup_duration_seconds{hostname="${HOSTNAME}"} ${SECONDS}

# HELP docker_backup_status Status of last backup (1=success, 0=failure)
# TYPE docker_backup_status gauge
docker_backup_status{hostname="${HOSTNAME}"} 1
EOF
mv "${METRICS_FILE}.$$" "${METRICS_FILE}"
log "Metrics written to ${METRICS_FILE}"

# Cleanup (unmount) happens in trap EXIT
exit 0
