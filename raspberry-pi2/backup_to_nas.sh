#!/bin/bash
# Daily Docker backup to NAS (192.168.0.1) for raspberrypi2
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
DOCKER_DIR="/home/aachten/docker/raspberry-pi2"
LOG_FILE="${DOCKER_DIR}/logs/backup-$(date +%Y%m%d).log"

# Ensure log directory exists
mkdir -p "${DOCKER_DIR}/logs"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Error handler
error_exit() {
    log "ERROR: $1"
    cleanup
    exit 1
}

# Cleanup function
cleanup() {
    log "Cleaning up..."
    # Only unmount if we mounted it (not if it's from fstab)
    if grep -q "$MOUNT_POINT" /etc/fstab; then
        log "NAS mount is persistent (fstab), leaving mounted"
    elif mountpoint -q "$MOUNT_POINT"; then
        sudo umount "$MOUNT_POINT" 2>/dev/null || log "Warning: Failed to unmount $MOUNT_POINT"
    fi
}

trap cleanup EXIT

log "=========================================="
log "Starting Docker backup to NAS (raspberrypi2)"
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

# Backup Docker volumes for raspberrypi2 monitoring services
log "Backing up Docker volumes..."
# List all volumes with raspberrypi2 prefix
VOLUMES=$(docker volume ls --format "{{.Name}}" | grep "^raspberry-pi2_" || echo "")

if [ -n "$VOLUMES" ]; then
    for volume in $VOLUMES; do
        log "  - Backing up volume: $volume"
        docker run --rm \
            -v "$volume":/data:ro \
            -v "${BACKUP_DIR}/volumes":/backup \
            alpine:latest \
            tar czf "/backup/${volume}-${TIMESTAMP}.tar.gz" -C /data . 2>>"$LOG_FILE" || \
            log "    Warning: Failed to backup $volume"
    done
else
    log "  No volumes found with raspberry-pi2 prefix"
fi

# Backup repository configs
log "Backing up repository configuration..."
rsync -a --delete \
    --exclude='logs' \
    --exclude='*.log' \
    "${DOCKER_DIR}/" \
    "${BACKUP_DIR}/configs/docker-repo/" 2>>"$LOG_FILE" || \
    log "Warning: Failed to backup repository"

# Export Docker metadata
log "Exporting Docker metadata..."
cd "$DOCKER_DIR" && docker compose config > "${BACKUP_DIR}/metadata/docker-compose-resolved.yml" 2>>"$LOG_FILE"
docker network ls --format "{{.ID}}\t{{.Name}}\t{{.Driver}}" > "${BACKUP_DIR}/metadata/networks.txt" 2>>"$LOG_FILE"
docker volume ls --format "{{.Name}}\t{{.Driver}}\t{{.Mountpoint}}" > "${BACKUP_DIR}/metadata/volumes.txt" 2>>"$LOG_FILE"

# Generate checksums
log "Generating checksums..."
if ls "${BACKUP_DIR}/volumes/"*.tar.gz 1> /dev/null 2>&1; then
    cd "${BACKUP_DIR}/volumes" && sha256sum *.tar.gz > "${BACKUP_DIR}/checksums.txt" 2>>"$LOG_FILE" || log "Warning: Failed to generate checksums"
else
    log "No volume archives to checksum"
    touch "${BACKUP_DIR}/checksums.txt"
fi

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

log "=========================================="
log "✅ Backup completed successfully!"
log "Location: $BACKUP_DIR"
log "Size: $BACKUP_SIZE"
log "=========================================="

# Cleanup (unmount) happens in trap EXIT
exit 0
