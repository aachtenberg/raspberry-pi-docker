#!/bin/bash

#
# Grafana Dashboard Import Script
# Imports one or all Grafana dashboards from JSON files
#

set -e

# Show help
show_help() {
    cat << HELP
Grafana Dashboard Import Script

Usage:
  ./scripts/import_grafana_dashboards.sh [DASHBOARD_FILE]

Examples:
  # Import all dashboards
  ./scripts/import_grafana_dashboards.sh

  # Import specific dashboard by filename
  ./scripts/import_grafana_dashboards.sh temperatures_rue_romain.json

  # Import specific dashboard by full path
  ./scripts/import_grafana_dashboards.sh grafana/dashboards/temperatures_rue_romain.json

Authentication:
  Uses GRAFANA_ADMIN_API_KEY from .env (recommended - has write permissions)
  Falls back to GRAFANA_API_KEY (may not have write permissions)
  Falls back to GRAFANA_PASSWORD if no API key
  Prompts for password if none are set

Environment Variables:
  GRAFANA_URL              Grafana URL (default: http://localhost:3000)
  GRAFANA_ADMIN_API_KEY    Admin API key with write permissions (from .env)
  GRAFANA_API_KEY          Regular API key (may be read-only)
  GRAFANA_USER             Username (default: admin)
  GRAFANA_PASSWORD         Password (fallback authentication)
  DASHBOARD_DIR            Dashboard directory (default: ./grafana/dashboards)

Options:
  -h, --help               Show this help message

HELP
}

# Check for help flag
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
    exit 0
fi

# Configuration
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
DASHBOARD_DIR="${DASHBOARD_DIR:-./grafana/dashboards}"
GRAFANA_USER="${GRAFANA_USER:-admin}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

echo -e "${BLUE}📥 Grafana Dashboard Import Tool${NC}"
echo "=================================="
echo ""

# Check if dashboard directory exists
if [ ! -d "$DASHBOARD_DIR" ]; then
    echo -e "${RED}❌ Dashboard directory not found: $DASHBOARD_DIR${NC}"
    exit 1
fi

# Count JSON files
DASHBOARD_COUNT=$(find "$DASHBOARD_DIR" -name "*.json" -type f | wc -l)
if [ "$DASHBOARD_COUNT" -eq 0 ]; then
    echo -e "${RED}❌ No dashboard JSON files found in $DASHBOARD_DIR${NC}"
    exit 1
fi

echo -e "${BLUE}📁 Dashboard directory:${NC} $DASHBOARD_DIR"
echo -e "${BLUE}   Found:${NC} $DASHBOARD_COUNT dashboard(s)"
echo ""

# Determine authentication method
USE_API_KEY=false
if [ -n "$GRAFANA_ADMIN_API_KEY" ]; then
    API_KEY="$GRAFANA_ADMIN_API_KEY"
    USE_API_KEY=true
    echo -e "${BLUE}🔑 Authentication:${NC} Admin API Key"
elif [ -n "$GRAFANA_API_KEY" ]; then
    API_KEY="$GRAFANA_API_KEY"
    USE_API_KEY=true
    echo -e "${BLUE}🔑 Authentication:${NC} API Key"
elif [ -n "$GRAFANA_PASSWORD" ]; then
    echo -e "${BLUE}🔑 Authentication:${NC} Password"
else
    echo -e "${YELLOW}⚠️  No API key or password found${NC}"
    echo ""
    read -sp "Enter Grafana password for user $GRAFANA_USER: " GRAFANA_PASSWORD
    echo ""
fi

echo ""

# Test Grafana connection
echo -e "${BLUE}🔌 Testing Grafana connection...${NC}"
if [ "$USE_API_KEY" = true ]; then
    HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $API_KEY" "$GRAFANA_URL/api/health")
else
    HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/health")
fi

if [ "$HEALTH_CHECK" != "200" ]; then
    echo -e "${RED}❌ Failed to connect to Grafana (HTTP $HEALTH_CHECK)${NC}"
    echo -e "${YELLOW}   Check GRAFANA_URL, credentials, and that Grafana is running${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Connected to Grafana${NC}"
echo ""

# Function to import a single dashboard
import_dashboard() {
    local file="$1"
    local filename=$(basename "$file")
    local dashboard_title=$(jq -r '.meta.title // .dashboard.title // "Unknown"' "$file" 2>/dev/null || echo "Unknown")
    
    echo -e "${BLUE}   📊 $dashboard_title${NC}"
    
    # Extract dashboard JSON and wrap it properly for import
    # Grafana API expects: {"dashboard": {...}, "overwrite": true}
    local payload=$(jq '{dashboard: .dashboard, overwrite: true, message: "Imported from JSON file"}' "$file" 2>/dev/null)
    
    if [ -z "$payload" ] || [ "$payload" = "null" ]; then
        echo -e "${RED}      ❌ Invalid JSON format${NC}"
        return 1
    fi
    
    # Import dashboard
    if [ "$USE_API_KEY" = true ]; then
        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $API_KEY" \
            -d "$payload" \
            "$GRAFANA_URL/api/dashboards/db")
    else
        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
            -H "Content-Type: application/json" \
            -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
            -d "$payload" \
            "$GRAFANA_URL/api/dashboards/db")
    fi
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | head -n-1)
    
    if [ "$HTTP_CODE" = "200" ]; then
        local dashboard_url=$(echo "$BODY" | jq -r '.url // ""' 2>/dev/null)
        echo -e "${GREEN}      ✅ $filename${NC}"
        if [ -n "$dashboard_url" ] && [ "$dashboard_url" != "null" ]; then
            echo -e "${GREEN}         URL: $GRAFANA_URL$dashboard_url${NC}"
        fi
        return 0
    else
        local error_msg=$(echo "$BODY" | jq -r '.message // .error // ""' 2>/dev/null || echo "Unknown error")
        echo -e "${RED}      ❌ Failed (HTTP $HTTP_CODE): $error_msg${NC}"
        return 1
    fi
}

# Check if specific dashboard file was provided
if [ -n "$1" ]; then
    # Import specific dashboard
    if [ -f "$1" ]; then
        DASHBOARD_FILE="$1"
    elif [ -f "$DASHBOARD_DIR/$1" ]; then
        DASHBOARD_FILE="$DASHBOARD_DIR/$1"
    else
        echo -e "${RED}❌ Dashboard file not found: $1${NC}"
        echo ""
        echo "Available dashboards in $DASHBOARD_DIR:"
        for file in "$DASHBOARD_DIR"/*.json; do
            if [ -f "$file" ]; then
                echo "  - $(basename "$file")"
            fi
        done
        exit 1
    fi
    
    echo -e "${BLUE}📥 Importing single dashboard...${NC}"
    echo ""
    
    if import_dashboard "$DASHBOARD_FILE"; then
        echo ""
        echo "=================================="
        echo -e "${GREEN}✅ Import complete!${NC}"
    else
        echo ""
        echo "=================================="
        echo -e "${RED}❌ Import failed${NC}"
        exit 1
    fi
else
    # Import all dashboards
    echo -e "${BLUE}📥 Importing all dashboards...${NC}"
    echo ""
    
    SUCCESS_COUNT=0
    FAIL_COUNT=0
    
    for file in "$DASHBOARD_DIR"/*.json; do
        if [ -f "$file" ]; then
            if import_dashboard "$file"; then
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
            else
                FAIL_COUNT=$((FAIL_COUNT + 1))
            fi
            echo ""
        fi
    done
    
    echo ""
    echo "=================================="
    if [ $FAIL_COUNT -eq 0 ]; then
        echo -e "${GREEN}✅ Import complete!${NC}"
        echo -e "${GREEN}   Imported: $SUCCESS_COUNT dashboard(s)${NC}"
    else
        echo -e "${YELLOW}⚠️  Import completed with errors${NC}"
        echo -e "${GREEN}   Imported: $SUCCESS_COUNT dashboard(s)${NC}"
        echo -e "${RED}   Failed: $FAIL_COUNT dashboard(s)${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  Open Grafana: $GRAFANA_URL"
echo "  Go to: Dashboards → Browse"
echo "  Verify imported dashboards appear correctly"
