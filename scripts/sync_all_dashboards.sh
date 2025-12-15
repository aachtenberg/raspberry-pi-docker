#!/bin/bash
set -e

# Sync all local dashboards to Grafana Cloud
# Usage: ./sync_all_dashboards.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="$PROJECT_ROOT/grafana/dashboards"

echo "🔄 Syncing all dashboards to Grafana Cloud..."
echo ""

# Check if dashboard directory exists
if [[ ! -d "$DASHBOARD_DIR" ]]; then
    echo "❌ Dashboard directory not found: $DASHBOARD_DIR"
    exit 1
fi

# Count dashboards
DASHBOARD_COUNT=$(find "$DASHBOARD_DIR" -name "*.json" -type f | wc -l)
if [[ $DASHBOARD_COUNT -eq 0 ]]; then
    echo "❌ No dashboard JSON files found in $DASHBOARD_DIR"
    exit 1
fi

echo "Found $DASHBOARD_COUNT dashboards to sync"
echo ""

# Sync each dashboard
SUCCESS_COUNT=0
FAIL_COUNT=0

for dashboard in "$DASHBOARD_DIR"/*.json; do
    echo "───────────────────────────────────────────────────────"
    DASHBOARD_NAME=$(basename "$dashboard")
    
    # Determine folder based on dashboard name
    FOLDER="General"
    if [[ "$DASHBOARD_NAME" =~ temperature ]]; then
        FOLDER="Sensors"
    elif [[ "$DASHBOARD_NAME" =~ raspberry_pi|docker|influxdb_performance ]]; then
        FOLDER="System Monitoring"
    elif [[ "$DASHBOARD_NAME" =~ victron ]]; then
        FOLDER="Solar"
    elif [[ "$DASHBOARD_NAME" =~ camera|esp32 ]]; then
        FOLDER="Cameras"
    fi
    
    if "$SCRIPT_DIR/create_grafana_dashboard.sh" "$dashboard" "$FOLDER"; then
        ((SUCCESS_COUNT++))
    else
        ((FAIL_COUNT++))
        echo "⚠️  Failed to sync: $DASHBOARD_NAME"
    fi
    echo ""
done

echo "═══════════════════════════════════════════════════════"
echo "✅ Sync complete: $SUCCESS_COUNT successful, $FAIL_COUNT failed"
echo ""
