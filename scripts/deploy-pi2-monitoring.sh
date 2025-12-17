#!/bin/bash
# Deploy monitoring containers to raspberrypi2 (192.168.0.147)
# Copies docker-compose file and starts containers

set -e

PI_HOST="192.168.0.147"
PI_USER="aachten"
DOCKER_DIR="/home/$PI_USER/docker"

echo "Deploying monitoring to raspberrypi2 ($PI_HOST)"
echo "================================================"

# Create docker directory on pi2
echo "Creating docker directory on pi2..."
ssh "$PI_USER@$PI_HOST" "mkdir -p $DOCKER_DIR/raspberry-pi2"

# Copy docker-compose file
echo "Copying docker-compose file..."
scp ./raspberry-pi2/docker-compose.yml "$PI_USER@$PI_HOST:$DOCKER_DIR/raspberry-pi2/"

# Copy telegraf config (required by compose)
echo "Copying telegraf config..."
scp ./raspberry-pi2/telegraf.conf "$PI_USER@$PI_HOST:$DOCKER_DIR/raspberry-pi2/"

# Start containers
echo "Starting containers..."
ssh "$PI_USER@$PI_HOST" "cd $DOCKER_DIR/raspberry-pi2 && docker compose up -d"

echo ""
echo "================================================"
echo "✓ Deployment complete!"
echo "================================================"
echo ""
echo "Verification:"
echo "  SSH into pi2: ssh $PI_USER@$PI_HOST"
echo "  Check status: cd $DOCKER_DIR/raspberry-pi2 && docker compose ps"
echo "  System metrics: curl http://$PI_HOST:9100/metrics"
echo "  Docker metrics: curl http://$PI_HOST:8080/metrics"
echo ""
echo "Then restart Prometheus here to pick up new targets:"
echo "  cd /home/aachten/docker && docker compose restart prometheus"
