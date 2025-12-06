#!/bin/bash
# Export all Grafana dashboards to JSON files for version control

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD}"
GRAFANA_API_KEY="${GRAFANA_API_KEY}"
OUTPUT_DIR="${OUTPUT_DIR:-./grafana/dashboards}"

echo "🔍 Grafana Dashboard Export Tool"
echo "=================================="
echo ""

# Check for uncommitted changes in dashboards directory
UNCOMMITTED=$(git diff --name-only 2>/dev/null | grep "^$OUTPUT_DIR")
if [ -n "$UNCOMMITTED" ]; then
    echo "⚠️  Warning: Uncommitted changes found in $OUTPUT_DIR:"
    echo "$UNCOMMITTED"
    echo ""
    read -p "Do you want to continue and overwrite these changes? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Export cancelled. Commit or discard your changes first:"
        echo "   git status"
        exit 1
    fi
fi

# Check if credentials are provided
if [ -z "$GRAFANA_PASSWORD" ] && [ -z "$GRAFANA_API_KEY" ]; then
    echo "⚠️  No credentials provided"
    echo ""
    echo "Usage Option 1 (Username/Password):"
    echo "  GRAFANA_PASSWORD=your_password ./scripts/export_grafana_dashboards.sh"
    echo ""
    echo "Usage Option 2 (API Key - Recommended):"
    echo "  GRAFANA_API_KEY=your_api_key ./scripts/export_grafana_dashboards.sh"
    echo ""
    echo "To create an API key:"
    echo "  1. Go to Grafana UI → Configuration → API Keys"
    echo "  2. Click 'Add API key'"
    echo "  3. Name: 'Dashboard Export', Role: 'Viewer'"
    echo "  4. Copy the generated key"
    echo ""
    exit 1
fi

# Set authentication method
if [ -n "$GRAFANA_API_KEY" ]; then
    AUTH_HEADER="Authorization: Bearer $GRAFANA_API_KEY"
    AUTH_TYPE="API Key"
else
    AUTH_HEADER=""
    AUTH_TYPE="Username/Password"
fi

mkdir -p "$OUTPUT_DIR"
echo "📁 Output directory: $OUTPUT_DIR"
echo "🔑 Authentication: $AUTH_TYPE"
echo ""

echo "🔌 Testing Grafana connection..."

if [ -n "$GRAFANA_API_KEY" ]; then
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH_HEADER" "$GRAFANA_URL/api/search")
else
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/search")
fi

if [ "$STATUS" != "200" ]; then
    echo "❌ Failed to connect to Grafana (HTTP $STATUS)"
    echo ""
    if [ "$STATUS" == "401" ]; then
        echo "💡 Tip: Check your credentials"
        echo "   - For password auth: Verify username and password"
        echo "   - For API key: Ensure key has Viewer role or higher"
    fi
    exit 1
fi

echo "✅ Connected to Grafana"
echo ""

echo "📊 Fetching dashboard list..."

if [ -n "$GRAFANA_API_KEY" ]; then
    DASHBOARDS=$(curl -s -H "$AUTH_HEADER" "$GRAFANA_URL/api/search?type=dash-db")
else
    DASHBOARDS=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/search?type=dash-db")
fi

if ! echo "$DASHBOARDS" | jq empty 2>/dev/null; then
    echo "❌ Invalid response from Grafana"
    exit 1
fi

DASHBOARD_COUNT=$(echo "$DASHBOARDS" | jq '. | length')
echo "   Found $DASHBOARD_COUNT dashboards"
echo ""

if [ "$DASHBOARD_COUNT" -eq 0 ]; then
    echo "⚠️  No dashboards found"
    echo "   Create some dashboards in Grafana first"
    exit 0
fi

EXPORTED=0
FAILED=0

echo "$DASHBOARDS" | jq -c '.[]' | while read -r dashboard; do
    DASHBOARD_UID=$(echo "$dashboard" | jq -r '.uid')
    DASHBOARD_TITLE=$(echo "$dashboard" | jq -r '.title')
    
    FILENAME=$(echo "$DASHBOARD_TITLE" | sed 's/[^a-zA-Z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]')
    
    echo "   📊 $DASHBOARD_TITLE"
    
    if [ -n "$GRAFANA_API_KEY" ]; then
        DASHBOARD_JSON=$(curl -s -H "$AUTH_HEADER" "$GRAFANA_URL/api/dashboards/uid/$DASHBOARD_UID")
    else
        DASHBOARD_JSON=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/dashboards/uid/$DASHBOARD_UID")
    fi
    
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
        
        echo "      ✅ ${FILENAME}.json"
        EXPORTED=$((EXPORTED + 1))
    else
        echo "      ❌ Failed"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "=================================="
echo "✅ Export complete!"
echo "   Exported: $DASHBOARD_COUNT dashboards"
echo "   Location: $OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "  git add $OUTPUT_DIR/*.json"
echo "  git commit -m 'chore: export Grafana dashboards'"
echo "  git push"
