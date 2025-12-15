#!/bin/bash
# Setup monitoring on raspberrypi2 (192.168.0.147)
# Installs node-exporter and cadvisor for system and Docker monitoring

set -e

PI_HOST="192.168.0.147"
PI_USER="pi"

echo "Setting up monitoring on raspberrypi2 ($PI_HOST)"
echo "=================================================="

# Create directories
echo "Creating directories..."
ssh "$PI_USER@$PI_HOST" "sudo mkdir -p /opt/monitoring /etc/systemd/system"

# Install node-exporter
echo "Installing node-exporter..."
ssh "$PI_USER@$PI_HOST" << 'EOF'
  # Download latest node-exporter
  cd /tmp
  LATEST_VERSION=$(curl -s https://api.github.com/repos/prometheus/node_exporter/releases/latest | grep tag_name | cut -d'"' -f4)
  wget https://github.com/prometheus/node_exporter/releases/download/${LATEST_VERSION}/node_exporter-${LATEST_VERSION#v}.linux-armv7.tar.gz
  tar xzf node_exporter-*.tar.gz
  sudo mv node_exporter-*/node_exporter /usr/local/bin/
  rm -rf node_exporter-* *.tar.gz
  
  # Create systemd service
  sudo tee /etc/systemd/system/node-exporter.service > /dev/null <<'SERVEOF'
[Unit]
Description=Node Exporter
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/node_exporter
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVEOF
  
  # Enable and start
  sudo systemctl daemon-reload
  sudo systemctl enable node-exporter
  sudo systemctl start node-exporter
  echo "Node Exporter started on port 9100"
EOF

# Install cadvisor (Docker container monitoring)
echo "Installing cadvisor..."
ssh "$PI_USER@$PI_HOST" << 'EOF'
  # Create systemd service for cadvisor docker container
  sudo tee /etc/systemd/system/cadvisor.service > /dev/null <<'SERVEOF'
[Unit]
Description=cAdvisor
After=docker.service
Requires=docker.service

[Service]
Type=simple
ExecStart=docker run \
  --rm \
  --name=cadvisor \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --volume=/dev/kmsg:/dev/kmsg:ro \
  --publish=8080:8080 \
  --device=/dev/kmsg:r \
  gcr.io/cadvisor/cadvisor:v0.50.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVEOF
  
  # Enable and start
  sudo systemctl daemon-reload
  sudo systemctl enable cadvisor
  sudo systemctl start cadvisor
  echo "cAdvisor started on port 8080"
EOF

echo ""
echo "=================================================="
echo "✓ Monitoring setup complete on raspberrypi2!"
echo "=================================================="
echo ""
echo "Verification:"
echo "  System metrics: curl http://$PI_HOST:9100/metrics"
echo "  Docker metrics: curl http://$PI_HOST:8080/metrics"
echo ""
echo "Next: Restart Prometheus to pick up the new targets:"
echo "  docker-compose restart prometheus"
