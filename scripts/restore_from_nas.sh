#!/bin/bash
# Restore Docker volumes and configs from NAS backup
# Usage: ./restore_from_nas.sh [YYYYMMDD]
# If no date provided, uses most recent backup

set -euo pipefail

# Configuration
NAS_HOST="192.168.0.1"
NAS_SHARE="G"
NAS_USER="admin"
NAS_PASS="canada99"
MOUNT_POINT="/mnt/nas-backup"
HOSTNAME=$(hostname)
BACKUP_BASE="${MOUNT_POINT}/docker-backups/${HOSTNAME}"
LOG_FILE="/home/aachten/docker/logs/restore-$(date +%Y%m%d-%H%M%S).log"

# Ensure log directory exists
mkdir -p /home/aachten/docker/logs

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
    # Check if mount is persistent (in fstab) - if so, leave it mounted
    if grep -q "$MOUNT_POINT" /etc/fstab; then
        log "NAS mount is persistent (fstab), leaving mounted"
    elif mountpoint -q "$MOUNT_POINT"; then
        sudo umount "$MOUNT_POINT" 2>/dev/null || log "Warning: Failed to unmount $MOUNT_POINT"
    fi
}

trap cleanup EXIT

log "=========================================="
log "Starting Docker restore from NAS"
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

# Determine backup timestamp to restore
if [ $# -eq 1 ]; then
    BACKUP_TIMESTAMP="$1"
    BACKUP_DIR="${BACKUP_BASE}/${BACKUP_TIMESTAMP}"
else
    log "No timestamp specified, finding most recent backup..."
    BACKUP_TIMESTAMP=$(ls -1 "$BACKUP_BASE" | grep "^2" | sort -r | head -n1)
    BACKUP_DIR="${BACKUP_BASE}/${BACKUP_TIMESTAMP}"
fi

if [ ! -d "$BACKUP_DIR" ]; then
    error_exit "Backup directory not found: $BACKUP_DIR"
fi

log "Using backup from: $BACKUP_TIMESTAMP"
log "Backup location: $BACKUP_DIR"

# Verify checksums
log "Verifying backup integrity..."
if [ -f "${BACKUP_DIR}/checksums.txt" ]; then
    cd "${BACKUP_DIR}/volumes"
    if sha256sum -c "${BACKUP_DIR}/checksums.txt" 2>&1 | tee -a "$LOG_FILE"; then
        log "✅ Checksum verification passed"
    else
        error_exit "Checksum verification failed"
    fi
else
    log "Warning: No checksums file found, skipping verification"
fi

# Confirm before proceeding
read -p "⚠️  This will OVERWRITE existing volumes and configs. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    log "Restore cancelled by user"
    exit 0
fi

# Stop containers
log "Stopping Docker containers..."
cd /home/aachten/docker
docker compose down || error_exit "Failed to stop containers"

# Restore Docker volumes
log "Restoring Docker volumes..."
for archive in "${BACKUP_DIR}"/volumes/*.tar.gz; do
    if [ -f "$archive" ]; then
        filename=$(basename "$archive")
        volume_name="${filename%-202*}"
        log "  - Restoring volume: $volume_name"
        
        # Create volume if it doesn't exist
        docker volume create "$volume_name" &>/dev/null || true
        
        # Restore data
        docker run --rm \
            -v "$volume_name":/data \
            -v "$archive":/backup.tar.gz:ro \
            alpine:latest \
            sh -c "rm -rf /data/* && tar xzf /backup.tar.gz -C /data" 2>>"$LOG_FILE" || \
            log "    Warning: Failed to restore $volume_name"
    fi
done

# Restore bind-mounted directories
log "Restoring bind-mounted directories..."
BIND_MOUNTS=(
    "/home/aachten/homeassistant:homeassistant"
    "/storage/nginx-proxy-manager:nginx-proxy-manager"
    "/storage/influxdb:influxdb"
)

for mount in "${BIND_MOUNTS[@]}"; do
    dst="${mount%%:*}"
    name="${mount##*:}"
    src="${BACKUP_DIR}/configs/${name}"
    
    if [ -d "$src" ]; then
        log "  - Restoring: $name → $dst"
        mkdir -p "$dst"
        rsync -a --delete "$src/" "$dst/" 2>>"$LOG_FILE" || \
            log "    Warning: Failed to restore $dst"
    else
        log "    Warning: Backup for $name not found, skipping"
    fi
done

# Restore repository configs (optional, prompt first)
read -p "Restore repository configs (docker-compose.yml, scripts, etc.)? (yes/no): " restore_repo
if [ "$restore_repo" = "yes" ]; then
    log "Restoring repository configuration..."
    rsync -a --delete \
        --exclude='.env' \
        "${BACKUP_DIR}/configs/docker-repo/" \
        /home/aachten/docker/ 2>>"$LOG_FILE" || \
        log "Warning: Failed to restore repository"
    
    # Restore .env separately (prompt)
    if [ -f "${BACKUP_DIR}/configs/docker-repo/.env" ]; then
        read -p "Restore .env file? (yes/no): " restore_env
        if [ "$restore_env" = "yes" ]; then
            cp "${BACKUP_DIR}/configs/docker-repo/.env" /home/aachten/docker/.env
            log ".env file restored"
        fi
    fi
fi

# Start containers
log "Starting Docker containers..."
cd /home/aachten/docker
docker compose up -d || error_exit "Failed to start containers"

log "=========================================="
log "✅ Restore completed successfully!"
log "Restored from: $BACKUP_DIR"
log "=========================================="

# Cleanup (unmount) happens in trap EXIT
exit 0
