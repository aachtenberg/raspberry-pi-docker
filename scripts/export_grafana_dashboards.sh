#!/bin/bash
# Export all Grafana dashboards to JSON files for version control

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD}"
OUTPUT_DIR="${OUTPUT_DIR:-./grafana/dashboards}"

echo "🔍 Grafana Dashboard Export Tool"
echo "=================================="
echo ""

if [ -z "$GRAFANA_PASSWORD" ]; then
    echo "⚠️  GRAFANA_PASSWORD not set"
    echo ""
    echo "Usage:"
    echo "  GRAFANA_PASSWORD=your_password ./scripts/export_grafana_dashboards.sh"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
echo "📁 Output directory: $OUTPUT_DIR"
echo ""

echo "🔌 Testing Grafana connection..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/search")

if [ "$STATUS" != "200" ]; then
    echo "❌ Failed to connect to Grafana (HTTP $STATUS)"
    exit 1
fi

echo "✅ Connected to Grafana"
echo ""

echo "📊 Fetching dashboard list..."
DASHBOARDS=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/search?type=dash-db")

DASHBOARD_COUNT=$(echo "$DASHBOARDS" | jq '. | length')
echo "   Found $DASHBOARD_COUNT dashboards"
echo ""

echo "$DASHBOARDS" | jq -c '.[]' | while read -r dashboard; do
    DASHBOARD_UID=$(echo "$dashboard" | jq -r '.uid')
    DASHBOARD_TITLE=$(echo "$dashboard" | jq -r '.title')
    
    FILENAME=$(echo "$DASHBOARD_TITLE" | sed 's/[^a-zA-Z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]')
    
    echo "   Exporting: $DASHBOARD_TITLE"
    
    DASHBOARD_JSON=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
        "$GRAFANA_URL/api/dashboards/uid/$DASHBOARD_UID")
    
    if echo "$DASHBOARD_JSON" | jq empty 2>/dev/null; then
        echo "$DASHBOARD_JSON" | jq '{
            meta: {
                exported: (now | strftime("%Y-%m-%d %H:%M:%S")),
                title: .dashboard.title,
                uid: .dashboard.uid,
                folder: .meta.folderTitle,
                version: .dashboard.version
            },
            dashboard: .dashboard
        }' > "$OUTPUT_DIR/${FILENAME}.json"
        
        echo "      ✅ Saved to: ${FILENAME}.json"
    else
        echo "      ❌ Failed to export"
    fi
done

echo ""
echo "✅ Export complete!"
echo "   Location: $OUTPUT_DIR"
