#!/bin/bash
# Backup all Docker volumes and configurations

BACKUP_DIR=~/backups
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/docker-infrastructure-$TIMESTAMP.tar.gz"

echo "Creating backup directory..."
mkdir -p $BACKUP_DIR

echo "Backing up Docker infrastructure to $BACKUP_FILE"
cd ~/docker

# Stop containers for consistent backup
sudo docker compose down

# Create backup
sudo tar czf $BACKUP_FILE     ~/docker     /var/lib/docker/volumes/docker_*     ~/nginx-proxy-manager     ~/homeassistant

# Restart containers
sudo docker compose up -d

echo "✅ Backup complete: $BACKUP_FILE"
ls -lh $BACKUP_FILE
