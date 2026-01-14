#!/bin/bash
# init-dirs.sh
# Initialize all required directories for the monitoring stack
# Run this once on fresh clone or after directory cleanup
# Everything here creates directories that containers expect to exist as bind mounts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Initializing directory structure ==="
echo ""

# Prometheus config files (if missing)
echo "  → Setting up prometheus directory..."
mkdir -p "$PROJECT_ROOT/prometheus"
if [ ! -f "$PROJECT_ROOT/prometheus/influxdb3_token" ]; then
    touch "$PROJECT_ROOT/prometheus/influxdb3_token"
    chmod 600 "$PROJECT_ROOT/prometheus/influxdb3_token"
    echo "    ✓ Created prometheus/influxdb3_token (copy token from .env)"
else
    echo "    ✓ prometheus/influxdb3_token exists"
fi

# Mosquitto config directory
echo "  → Setting up mosquitto directory..."
mkdir -p "$PROJECT_ROOT/mosquitto"
echo "    ✓ mosquitto/"

# AI Monitor incidents directory
echo "  → Setting up ai-monitor directories..."
mkdir -p "$PROJECT_ROOT/ai-monitor/incidents"
mkdir -p "$PROJECT_ROOT/ai-monitor/templates"
echo "    ✓ ai-monitor/incidents"

# Logs directory
echo "  → Setting up logs directory..."
mkdir -p "$PROJECT_ROOT/logs"
echo "    ✓ logs/"

echo ""
echo "✅ Directory structure initialized!"
echo ""
echo "ℹ️  Note: Docker volumes (like pdc-agent-ssh, prometheus-data, etc.) are"
echo "   managed automatically by Docker and don't need manual setup."
echo ""
echo "📋 Next steps:"
echo "   1. Copy .env.example to .env and fill in secrets"
echo "   2. Run ./scripts/setup-local-configs.sh for network configs"
echo "   3. Copy InfluxDB3 token from .env to prometheus/influxdb3_token"
echo "   4. Start services: docker compose up -d"
echo ""
