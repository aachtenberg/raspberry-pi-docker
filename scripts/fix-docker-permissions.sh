#!/bin/bash
# fix-docker-permissions.sh
# Run this script after reboot if permissions are broken

set -e

echo "=== Fixing /storage ownership ==="
sudo chown -R aachten:aachten /storage
echo "✓ /storage ownership fixed"

echo ""
echo "=== Fixing Docker volume permissions ==="

# Prometheus (runs as nobody - uid 65534)
echo "  → Fixing Prometheus volume..."
sudo chown -R 65534:65534 /storage/docker/volumes/docker_prometheus-data/_data/
sudo chmod 775 /storage/docker/volumes/docker_prometheus-data/_data/

# Grafana (runs as uid 472)
echo "  → Fixing Grafana volume..."
sudo chown -R 472:472 /storage/docker/volumes/docker_grafana-data/_data/
sudo chmod 775 /storage/docker/volumes/docker_grafana-data/_data/

# Mosquitto (runs as uid 1883)
echo "  → Fixing Mosquitto volumes..."
sudo chown -R 1883:1883 /storage/docker/volumes/docker_mosquitto-data/_data/
sudo chown -R 1883:1883 /storage/docker/volumes/docker_mosquitto-log/_data/
sudo chmod 755 /storage/docker/volumes/docker_mosquitto-data/_data/
sudo chmod 755 /storage/docker/volumes/docker_mosquitto-log/_data/

# InfluxDB3 (runs as uid 1000 - aachten)
echo "  → Fixing InfluxDB3 volume..."
sudo chown -R 1000:1000 /storage/docker/volumes/docker_influxdb3-data/_data/
sudo chmod 755 /storage/docker/volumes/docker_influxdb3-data/_data/

# Portainer (runs as root but we use aachten for consistency)
echo "  → Fixing Portainer volume..."
sudo chown -R aachten:aachten /storage/docker/volumes/docker_portainer-data/_data/
sudo chmod 755 /storage/docker/volumes/docker_portainer-data/_data/

echo "✓ Docker volume permissions fixed"

echo ""
echo "=== Fixing bind mount permissions ==="

# Nginx Proxy Manager (runs as root)
echo "  → Fixing Nginx Proxy Manager..."
sudo chown -R root:root /storage/nginx-proxy-manager/data/
sudo chown -R root:root /storage/nginx-proxy-manager/letsencrypt/
sudo chmod -R 755 /storage/nginx-proxy-manager/

# InfluxDB legacy (if exists)
if [ -d "/storage/influxdb/data" ]; then
    echo "  → Fixing InfluxDB v2 (legacy)..."
    sudo chown -R aachten:aachten /storage/influxdb/data/
    sudo chmod 700 /storage/influxdb/data/
fi

if [ -d "/storage/influxdb/config" ]; then
    sudo chown -R aachten:aachten /storage/influxdb/config/
    sudo chmod 775 /storage/influxdb/config/
fi

echo "✓ Bind mount permissions fixed"

echo ""
echo "=== Fixing Docker daemon directories ==="
sudo chown -R aachten:aachten /storage/docker/buildkit
sudo chmod 711 /storage/docker/buildkit

sudo chown -R aachten:aachten /storage/docker/containers
sudo chmod 710 /storage/docker/containers

sudo chown -R aachten:aachten /storage/docker/image
sudo chmod 700 /storage/docker/image

sudo chown -R aachten:aachten /storage/docker/network
sudo chmod 750 /storage/docker/network

# overlay2 is managed by Docker daemon - leave as root
sudo chown -R root:root /storage/docker/overlay2
sudo chmod 710 /storage/docker/overlay2

sudo chown -R aachten:aachten /storage/docker/volumes
sudo chmod 701 /storage/docker/volumes

sudo chown -R aachten:aachten /storage/docker/plugins
sudo chmod 700 /storage/docker/plugins

sudo chown -R aachten:aachten /storage/docker/tmp
sudo chmod 700 /storage/docker/tmp

echo "✓ Docker daemon directories fixed"

echo ""
echo "=== Restarting Docker containers ==="
cd /home/aachten/docker
docker compose restart
echo "✓ Docker compose stack restarted"

echo ""
echo "=== Fixing PDC agent ==="
docker update --restart=unless-stopped pdc-agent 2>/dev/null || echo "PDC agent already configured"
docker start pdc-agent 2>/dev/null || echo "PDC agent already running"
echo "✓ PDC agent checked"

echo ""
echo "=== Verification ==="
docker ps --format 'table {{.Names}}\t{{.Status}}'

echo ""
echo "✓ All fixes applied!"
echo ""
echo "Run 'docker logs <container-name>' to check for any errors"
