#!/bin/bash
set -e

# Create or update a Grafana Cloud dashboard via API
# Usage: ./create_grafana_dashboard.sh <dashboard-json-file> [folder-name]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables
if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    echo "❌ .env file not found at $PROJECT_ROOT/.env"
    echo "Copy .env.example and fill in GRAFANA_CLOUD_URL and GRAFANA_CLOUD_API_KEY"
    exit 1
fi

source "$PROJECT_ROOT/.env"

if [[ -z "$GRAFANA_CLOUD_URL" ]] || [[ -z "$GRAFANA_CLOUD_API_KEY" ]]; then
    echo "❌ Missing Grafana Cloud credentials in .env"
    echo "Required: GRAFANA_CLOUD_URL and GRAFANA_CLOUD_API_KEY"
    exit 1
fi

# Check arguments
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <dashboard-json-file> [folder-name]"
    echo ""
    echo "Example:"
    echo "  $0 grafana/dashboards/temperature_data__influxdb_3_.json"
    echo "  $0 grafana/dashboards/raspberry_pi___docker_monitoring.json 'System Monitoring'"
    exit 1
fi

DASHBOARD_FILE="$1"
FOLDER_NAME="${2:-General}"

if [[ ! -f "$DASHBOARD_FILE" ]]; then
    echo "❌ Dashboard file not found: $DASHBOARD_FILE"
    exit 1
fi

echo "📊 Creating/updating dashboard in Grafana Cloud..."
echo "   Instance: $GRAFANA_CLOUD_URL"
echo "   Dashboard: $(basename "$DASHBOARD_FILE")"
echo "   Folder: $FOLDER_NAME"
echo ""

# Find or create folder
FOLDER_ID=""
FOLDER_UID=""
if [[ "$FOLDER_NAME" != "General" ]]; then
    echo "🔍 Looking for folder: $FOLDER_NAME"
    FOLDERS_JSON=$(curl -s -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" "$GRAFANA_CLOUD_URL/api/folders")
    
    # Check if response is an array
    if echo "$FOLDERS_JSON" | jq -e 'type == "array"' > /dev/null 2>&1; then
        FOLDER_UID=$(echo "$FOLDERS_JSON" | jq -r ".[] | select(.title==\"$FOLDER_NAME\") | .uid")
    fi
    
    if [[ -z "$FOLDER_UID" ]] || [[ "$FOLDER_UID" == "null" ]]; then
        echo "📁 Creating folder: $FOLDER_NAME"
        FOLDER_CREATE=$(curl -s -X POST -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" \
            -H "Content-Type: application/json" \
            -d "{\"title\":\"$FOLDER_NAME\"}" \
            "$GRAFANA_CLOUD_URL/api/folders")
        
        FOLDER_UID=$(echo "$FOLDER_CREATE" | jq -r '.uid')
        
        if [[ -z "$FOLDER_UID" ]] || [[ "$FOLDER_UID" == "null" ]]; then
            echo "❌ Failed to create folder"
            echo "$FOLDER_CREATE" | jq '.'
            exit 1
        fi
    fi
    
    echo "✓ Folder UID: $FOLDER_UID"
fi

# Read dashboard JSON
DASHBOARD_JSON=$(cat "$DASHBOARD_FILE")

# Wrap dashboard JSON in API format
API_PAYLOAD=$(jq -n \
    --argjson dashboard "$DASHBOARD_JSON" \
    --arg folderUid "$FOLDER_UID" \
    '{
        dashboard: ($dashboard | .id = null),
        folderUid: (if $folderUid != "" then $folderUid else null end),
        overwrite: true,
        message: "Updated via API"
    }')

# Create/update dashboard
echo "🚀 Pushing dashboard to Grafana Cloud..."
RESPONSE=$(curl -s -X POST -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$API_PAYLOAD" \
    "$GRAFANA_CLOUD_URL/api/dashboards/db")

# Check response
STATUS=$(echo "$RESPONSE" | jq -r '.status // empty')
URL=$(echo "$RESPONSE" | jq -r '.url // empty')
DASH_UID=$(echo "$RESPONSE" | jq -r '.uid // empty')

if [[ "$STATUS" == "success" ]] && [[ -n "$URL" ]]; then
    echo ""
    echo "✅ Dashboard created/updated successfully!"
    echo "   UID: $DASH_UID"
    echo "   URL: $GRAFANA_CLOUD_URL$URL"
    echo ""
else
    echo ""
    echo "❌ Failed to create dashboard"
    echo "$RESPONSE" | jq '.'
    exit 1
fi
