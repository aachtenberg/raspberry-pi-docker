#!/bin/bash
# Complete setup for raspberrypi2 (192.168.0.147)
# Deploys monitoring + configures automated backups

set -e

PI_HOST="192.168.0.147"
PI_USER="aachten"
DOCKER_DIR="/home/$PI_USER/docker/raspberry-pi2"

echo "=========================================="
echo "Setting up raspberrypi2 ($PI_HOST)"
echo "=========================================="
echo ""

# 1. Create directory structure
echo "[1/5] Creating directory structure on pi2..."
ssh "$PI_USER@$PI_HOST" "mkdir -p $DOCKER_DIR/logs"

# 2. Copy Docker Compose and backup scripts
echo "[2/5] Copying Docker Compose and scripts..."
scp ./raspberry-pi2/docker-compose.yml "$PI_USER@$PI_HOST:$DOCKER_DIR/"
scp ./raspberry-pi2/backup_to_nas.sh "$PI_USER@$PI_HOST:$DOCKER_DIR/"

# Make backup script executable
ssh "$PI_USER@$PI_HOST" "chmod +x $DOCKER_DIR/backup_to_nas.sh"

# 3. Start monitoring containers
echo "[3/5] Starting monitoring containers..."
ssh "$PI_USER@$PI_HOST" "cd $DOCKER_DIR && docker compose up -d"

# 4. Setup automated backups (systemd timer)
echo "[4/5] Setting up automated daily backups..."
scp ./raspberry-pi2/docker-backup.service "$PI_USER@$PI_HOST:/tmp/"
scp ./raspberry-pi2/docker-backup.timer "$PI_USER@$PI_HOST:/tmp/"

ssh "$PI_USER@$PI_HOST" << 'ENDSSH'
# Move systemd files to correct location
sudo mv /tmp/docker-backup.service /etc/systemd/system/
sudo mv /tmp/docker-backup.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the timer
sudo systemctl enable docker-backup.timer
sudo systemctl start docker-backup.timer

echo "Systemd backup timer enabled"
ENDSSH

# 5. Setup NAS mount (if not already configured)
echo "[5/5] Configuring NAS mount..."
ssh "$PI_USER@$PI_HOST" << 'ENDSSH'
# Create mount point
sudo mkdir -p /mnt/nas-backup

# Check if already in fstab
if ! grep -q "/mnt/nas-backup" /etc/fstab; then
    echo ""
    echo "⚠️  NAS mount not found in /etc/fstab"
    echo ""
    echo "To enable persistent NAS mount, add this line to /etc/fstab:"
    echo "//192.168.0.1/G /mnt/nas-backup cifs credentials=/root/.nas-credentials,uid=1000,gid=1000,file_mode=0644,dir_mode=0755,vers=2.0,nofail,x-systemd.automount 0 0"
    echo ""
    echo "And create /root/.nas-credentials with:"
    echo "username=admin"
    echo "password=canada99"
    echo "chmod 600 /root/.nas-credentials"
    echo ""
else
    echo "✓ NAS mount already configured in /etc/fstab"
fi
ENDSSH

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo "=========================================="
echo ""
echo "Verification:"
echo "  SSH: ssh $PI_USER@$PI_HOST"
echo "  Status: cd $DOCKER_DIR && docker compose ps"
echo "  Backup timer: systemctl list-timers docker-backup.timer"
echo "  Test backup: sudo bash $DOCKER_DIR/backup_to_nas.sh"
echo ""
echo "Monitoring endpoints:"
echo "  Node Exporter: http://$PI_HOST:9100/metrics"
echo "  cAdvisor: http://$PI_HOST:8080/metrics"
echo ""
echo "Next steps:"
echo "  1. Restart Prometheus on main Pi to pick up new targets:"
echo "     cd /home/aachten/docker && docker compose restart prometheus"
echo "  2. Configure NAS mount on pi2 if not already done (see above)"
echo "  3. Verify first backup runs: ssh to pi2 and check logs in $DOCKER_DIR/logs/"
echo ""
