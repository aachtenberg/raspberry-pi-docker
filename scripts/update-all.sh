#!/bin/bash
# Update all Docker containers to latest versions

cd ~/docker

echo "Pulling latest images..."
sudo docker compose pull

echo "Recreating containers with new images..."
sudo docker compose up -d

echo "Removing old images..."
sudo docker image prune -f

echo ""
echo "✅ Update complete!"
sudo docker compose ps
