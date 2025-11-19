#!/bin/bash
# Show status of all services

cd ~/docker

echo "========================================"
echo "  Docker Infrastructure Status"
echo "========================================"
echo ""

echo "Running Containers:"
sudo docker compose ps
echo ""

echo "System Resources:"
sudo docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
echo ""

echo "Disk Usage:"
sudo docker system df
echo ""

echo "Volume Sizes:"
sudo docker volume ls --format "table {{.Name}}" | grep docker_ | while read vol; do
    size=$(sudo du -sh /var/lib/docker/volumes/$vol/_data 2>/dev/null | cut -f1)
    echo "$vol: $size"
done
