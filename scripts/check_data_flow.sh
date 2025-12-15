#!/bin/bash
# Data Flow Health Check Script
# Verifies MQTT → Telegraf → InfluxDB v3 pipeline is working

set -e

cd "$(dirname "$0")/.."

echo "==================================================================="
echo "Data Flow Health Check"
echo "==================================================================="
echo

# Load environment variables
source .env

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check 1: Mosquitto is running
echo -n "1. Checking Mosquitto MQTT Broker... "
if docker compose ps mosquitto | grep -q "Up"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    exit 1
fi

# Check 2: Telegraf is running
echo -n "2. Checking Telegraf... "
if docker compose ps telegraf | grep -q "Up"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    exit 1
fi

# Check 3: InfluxDB v3 is running
echo -n "3. Checking InfluxDB v3 Core... "
if docker compose ps influxdb3-core | grep -q "Up"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    exit 1
fi

# Check 4: MQTT messages are being received
echo -n "4. Checking MQTT messages... "
MQTT_COUNT=$(timeout 15s docker compose exec -T mosquitto mosquitto_sub -h localhost -t '#' -C 3 2>/dev/null | wc -l || echo "0")
if [ "$MQTT_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Receiving messages ($MQTT_COUNT in 15s)${NC}"
else
    echo -e "${YELLOW}⚠ No messages received${NC}"
fi

# Check 5: Telegraf buffer status
echo -n "5. Checking Telegraf buffer... "
BUFFER_ERRORS=$(docker compose logs --tail 50 telegraf 2>/dev/null | grep "Error writing" | wc -l)
BUFFER_LINES=$(docker compose logs --tail 10 telegraf 2>/dev/null | grep "Buffer fullness" | tail -1)
if [ "${BUFFER_ERRORS:-0}" -eq 0 ]; then
    echo -e "${GREEN}✓ No errors${NC}"
    if [ -n "$BUFFER_LINES" ]; then
        echo "   $BUFFER_LINES"
    fi
else
    echo -e "${YELLOW}⚠ $BUFFER_ERRORS errors in last 50 lines${NC}"
fi

# Check 6: Recent temperature data in InfluxDB v3
echo -n "6. Checking InfluxDB v3 temperature data... "
LATEST_TEMP=$(curl -s -H "Authorization: Bearer ${INFLUXDB3_ADMIN_TOKEN}" \
    "http://localhost:8181/api/v3/query_sql?db=temperature_data&q=SELECT%20MAX(time)%20as%20latest%20FROM%20esp_temperature&format=json" 2>/dev/null)

if echo "$LATEST_TEMP" | grep -q "latest"; then
    LATEST_TIME=$(echo "$LATEST_TEMP" | jq -r '.[0].latest' 2>/dev/null)
    echo -e "${GREEN}✓ Data found${NC}"
    echo "   Latest: $LATEST_TIME"

    # Check if data is recent (within last 5 minutes)
    LATEST_EPOCH=$(date -d "$LATEST_TIME" +%s 2>/dev/null || echo "0")
    NOW_EPOCH=$(date +%s)
    AGE=$((NOW_EPOCH - LATEST_EPOCH))

    if [ "$AGE" -lt 300 ]; then
        echo -e "   ${GREEN}✓ Data is fresh (${AGE}s old)${NC}"
    else
        echo -e "   ${YELLOW}⚠ Data is stale (${AGE}s old)${NC}"
    fi
else
    echo -e "${RED}✗ No data found or query failed${NC}"
fi

# Check 7: Total records count
echo -n "7. Checking total temperature records... "
TOTAL_COUNT=$(curl -s -H "Authorization: Bearer ${INFLUXDB3_ADMIN_TOKEN}" \
    "http://localhost:8181/api/v3/query_sql?db=temperature_data&q=SELECT%20COUNT(*)%20as%20total%20FROM%20esp_temperature&format=json" 2>/dev/null | jq -r '.[0].total' 2>/dev/null || echo "0")

if [ "$TOTAL_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ $TOTAL_COUNT records${NC}"
else
    echo -e "${YELLOW}⚠ No records found${NC}"
fi

echo
echo "==================================================================="
echo "Health check complete!"
echo "==================================================================="
