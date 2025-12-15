#!/bin/bash
set -e -o pipefail

# Download all dashboards from Grafana Cloud
# Usage: ./download_grafana_dashboards.sh [output-directory]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$PROJECT_ROOT/grafana/dashboards-cloud}"

# Load environment variables
if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    echo "❌ .env file not found at $PROJECT_ROOT/.env"
    exit 1
fi

source "$PROJECT_ROOT/.env"

if [[ -z "$GRAFANA_CLOUD_URL" ]] || [[ -z "$GRAFANA_CLOUD_API_KEY" ]]; then
    echo "❌ Missing Grafana Cloud credentials in .env"
    echo "Required: GRAFANA_CLOUD_URL and GRAFANA_CLOUD_API_KEY"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "📥 Downloading dashboards from Grafana Cloud..."
echo "   Instance: $GRAFANA_CLOUD_URL"
echo "   Output: $OUTPUT_DIR"
echo ""

# Get all dashboards
SEARCH_RESPONSE=$(curl -s -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" \
    "$GRAFANA_CLOUD_URL/api/search?type=dash-db")

# Check if response is valid
if ! echo "$SEARCH_RESPONSE" | jq -e 'type == "array"' > /dev/null 2>&1; then
    echo "❌ Failed to fetch dashboards"
    echo "$SEARCH_RESPONSE" | jq '.'
    exit 1
fi

DASHBOARD_COUNT=$(echo "$SEARCH_RESPONSE" | jq 'length')
echo "Found $DASHBOARD_COUNT dashboards"
echo ""

if [[ $DASHBOARD_COUNT -eq 0 ]]; then
    echo "No dashboards found in Grafana Cloud"
    exit 0
fi

# Download each dashboard
SUCCESS_COUNT=0
for row in $(echo "$SEARCH_RESPONSE" | jq -r '.[] | @base64'); do
    _jq() {
        echo "$row" | base64 --decode | jq -r "$1"
    }
    
    DASH_UID=$(_jq '.uid')
    TITLE=$(_jq '.title')
    FOLDER=$(_jq '.folderTitle // "General"')
    
    echo "───────────────────────────────────────────────────────"
    echo "📊 $TITLE"
    echo "   UID: $DASH_UID"
    echo "   Folder: $FOLDER"
    
    # Get dashboard JSON
    DASHBOARD_JSON=$(curl -s -H "Authorization: Bearer $GRAFANA_CLOUD_API_KEY" \
        "$GRAFANA_CLOUD_URL/api/dashboards/uid/$DASH_UID")
    
    # Extract just the dashboard model
    DASHBOARD_MODEL=$(echo "$DASHBOARD_JSON" | jq '.dashboard')
    
    if [[ -z "$DASHBOARD_MODEL" ]] || [[ "$DASHBOARD_MODEL" == "null" ]]; then
        echo "   ⚠️  Failed to download"
        continue
    fi
    
    # Sanitize title for filename
    FILENAME=$(echo "$TITLE" | sed 's/[^a-zA-Z0-9_-]/_/g' | tr '[:upper:]' '[:lower:]').json
    OUTPUT_PATH="$OUTPUT_DIR/$FILENAME"
    
    # Save dashboard
    if echo "$DASHBOARD_MODEL" | jq '.' > "$OUTPUT_PATH" 2>/dev/null; then
        echo "   ✓ Saved to: $FILENAME"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo "   ⚠️  Failed to save"
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ Downloaded $SUCCESS_COUNT dashboards to $OUTPUT_DIR"
echo ""
