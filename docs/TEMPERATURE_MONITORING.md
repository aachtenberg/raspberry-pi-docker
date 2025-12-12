# Temperature Monitoring Dashboard

Complete guide for the **Temperature Data (InfluxDB 3)** Grafana dashboard.

## Overview

The Temperature Monitoring dashboard visualizes real-time and historical temperature data from ESP sensor hubs connected via MQTT.

**Data Flow**: ESP sensors → MQTT → Telegraf → InfluxDB 3 Core → Grafana FlightSQL queries

**Dashboard Features**:
- 🌡️ **Big Garage Gauge**: Latest temperature with color-coded thresholds
- 📈 **Temperature by Device (24h)**: Multi-device timeseries with colored lines
- 📊 **Legend Table**: Min, max, median, last statistics per device
- 🔄 **Auto-refresh**: 30 seconds by default
- ⏱️ **Time Range**: 12 hours by default (customizable)

---

## Quick Start

### 1. Verify Data is Flowing

```bash
# Check MQTT broker
mosquitto_sub -h 127.0.0.1 -t 'esp-sensor-hub/+/temperature' | head -5

# Expected output: {"device": "Big-Garage", "celsius": 24.5, "fahrenheit": 76.1}

# Verify InfluxDB 3 has data
docker compose exec influxdb3-core influxdb3 query \
  --token "$INFLUXDB3_ADMIN_TOKEN" \
  "SELECT COUNT(*) FROM esp_temperature"
```

### 2. Access Dashboard

```
http://localhost:3000/d/tempdb3/temperature-data-influxdb-3
```

### 3. Configure Grafana Datasource (if not present)

1. Go to Grafana → Configuration → Data Sources
2. Add new datasource:
   - **Name**: `influxdbv3`
   - **Type**: InfluxDB FlightSQL
   - **URL**: `http://influxdb3-core:8181`
   - **Database**: `temperature_data`
   - **Bearer Token**: (leave empty for local access; use `$INFLUXDB3_ADMIN_TOKEN` for external)
3. Test connection → Save

---

## Dashboard Panels

### Panel 1: Big Garage (Gauge)

**Purpose**: Display latest temperature with visual feedback

**Type**: Gauge

**Query**:
```sql
SELECT celsius, fahrenheit 
FROM esp_temperature 
WHERE device = 'Big-Garage' 
  AND time >= $__timeFrom 
  AND time <= $__timeTo 
ORDER BY time DESC 
LIMIT 1
```

**Configuration**:
- **Unit**: Celsius
- **Min**: -10°C, **Max**: 30°C
- **Thresholds** (absolute mode):
  - `null` → dark-blue
  - -10° → dark-blue
  - 0° → light-blue
  - 15° → light-green
  - 20° → dark-green
  - 25° → orange
  - 30° → dark-orange
  - 31° → red
- **Transparency**: Enabled
- **Reduce options**: `lastNotNull` (shows latest value only)

**Modifying for New Devices**:
1. Duplicate this panel
2. Change WHERE clause: `WHERE device = 'Your-Device-Name'`
3. Update title

---

### Panel 2: Temperature by Device (24h) (Timeseries)

**Purpose**: Track temperature trends for all connected devices

**Type**: Timeseries

**Query**:
```sql
SELECT time, device, celsius 
FROM esp_temperature 
WHERE time >= $__timeFrom 
  AND time <= $__timeTo 
ORDER BY time, device
```

**Configuration**:
- **Unit**: Celsius
- **Line Width**: 2
- **Interpolation**: Smooth
- **Span Nulls**: Enabled
- **Transparency**: Enabled

**Thresholds** (absolute mode):
- `null` → dark-blue
- -10° → dark-blue
- 0° → light-blue
- 15° → light-green
- 20° → dark-green
- 25° → orange
- 30° → dark-orange
- 31° → red

**Legend Configuration**:
- **Display Mode**: Table
- **Placement**: Bottom
- **Calculations**: min, max, median, last
- **Values**: [min, max, median, last]

**Transformations**:
1. Filter Fields by Name: Keep `[time, device, celsius]`
2. Organize Fields: Reorder as `[time, device, celsius]`

**Field Overrides**:
- Match: `celsius` field
  - Display Name: `${__field.labels.device}` (shows device name in legend)
  - Color Mode: Thresholds
- Match: `device` field
  - Hide from Legend: true

---

## FlightSQL Query Guide

### Time Macros

- `$__timeFrom`: Start time in milliseconds
- `$__timeTo`: End time in milliseconds
- Example: `WHERE time >= $__timeFrom AND time <= $__timeTo`

### Common Queries

```sql
-- Latest for all devices
SELECT time, device, celsius, fahrenheit 
FROM esp_temperature 
ORDER BY time DESC 
LIMIT 1;

-- Last 24 hours by device
SELECT time, device, celsius 
FROM esp_temperature 
WHERE time >= now() - interval '24 hours'
ORDER BY time DESC;

-- Hourly average
SELECT 
  date_bin(interval '1 hour', time, timestamp '2025-01-01 00:00:00') as hour,
  device,
  avg(celsius) as avg_celsius,
  min(celsius) as min_celsius,
  max(celsius) as max_celsius
FROM esp_temperature
WHERE time >= now() - interval '7 days'
GROUP BY hour, device
ORDER BY hour DESC;

-- Temperature alerts (>30°C)
SELECT time, device, celsius 
FROM esp_temperature 
WHERE celsius > 30 
ORDER BY time DESC 
LIMIT 10;
```

---

## Panel JSON Reference

For manual editing or programmatic dashboard generation, see:
`docs/influxv3-sql-example.json`

Key JSON properties:
```json
{
  "type": "timeseries",
  "fieldConfig": {
    "defaults": {
      "custom": {
        "drawStyle": "line",
        "lineInterpolation": "smooth",
        "lineWidth": 2,
        "spanNulls": true
      },
      "color": { "mode": "palette-classic" },
      "thresholds": {
        "mode": "absolute",
        "steps": [
          { "value": null, "color": "dark-blue" },
          { "value": -10, "color": "dark-blue" },
          ...
        ]
      }
    },
    "overrides": [
      {
        "matcher": { "id": "byName", "options": "celsius" },
        "properties": [
          { "id": "displayName", "value": "${__field.labels.device}" },
          { "id": "color", "value": { "mode": "thresholds" } }
        ]
      }
    ]
  },
  "transformations": [
    {
      "id": "filterFieldsByName",
      "options": { "include": { "names": ["time", "device", "celsius"] } }
    },
    {
      "id": "organize",
      "options": {
        "indexByName": { "time": 0, "device": 1, "celsius": 2 },
        "renameByName": {}
      }
    }
  ]
}
```

---

## Adding New Sensor Devices

### Prerequisites

1. ESP device publishing to `esp-sensor-hub/{device_id}/temperature` with JSON payload
2. Telegraf running and consuming from MQTT
3. Data flowing into `esp_temperature` table

### Steps

1. **Verify device data exists**:
   ```sql
   SELECT DISTINCT device FROM esp_temperature;
   ```

2. **Create new gauge panel** (duplicate Big Garage):
   - Title: "Your Device Name"
   - Query: `WHERE device = 'Your-Device-Name'`
   - Same thresholds and colors

3. **Rename in legend** (if needed):
   - Field override: `displayName = "Your Device Label"`

4. **Export and commit**:
   ```bash
   ./scripts/export_grafana_dashboards.sh
   git add grafana/dashboards/temperature_data_influxdb3.json
   git commit -m "feat: add {device_name} temperature gauge"
   ```

---

## Troubleshooting

### Dashboard shows "No data"

1. **Check InfluxDB 3 connection**:
   ```bash
   # Test query in Explorer UI (http://localhost:8888)
   SELECT COUNT(*) FROM esp_temperature;
   ```

2. **Check datasource**:
   - Grafana → Data Sources → influxdbv3 → Test

3. **Check time range**:
   - Ensure selected time range contains data (default: last 12h)
   - MQTT data may only be ~24h old

4. **Check device name**:
   - Verify device name matches: `SELECT DISTINCT device FROM esp_temperature`

### Legend not showing device names

- Verify transformation: `filterFieldsByName` + `organize` are applied
- Verify field override: `celsius` displayName = `${__field.labels.device}`
- Check for typos in device field selector

### Colors not matching thresholds

- Verify **color mode**: `"mode": "thresholds"` (not `palette-classic`)
- Verify threshold steps are complete (must include all temperature ranges)
- Check threshold values are in ascending order

### Timeseries showing straight line (no variation)

- Increase time range (e.g., 24h → 7 days)
- Verify multiple temperature readings exist: `SELECT COUNT(*) FROM esp_temperature`
- Check line interpolation: Should be `smooth`, not `linear`

---

## Export & Import

### Export Dashboard

```bash
./scripts/export_grafana_dashboards.sh
# Creates: grafana/dashboards/temperature_data_influxdb3.json
```

### Import Dashboard

```bash
./scripts/import_grafana_dashboards.sh grafana/dashboards/temperature_data_influxdb3.json
# Automatically overwrites existing dashboard (by title match)
```

---

## Database Schema

### esp_temperature Table

```sql
-- Columns
time        timestamp      -- Measurement timestamp
device      string (tag)   -- Device identifier (e.g., "Big-Garage")
celsius     float          -- Temperature in Celsius
fahrenheit  float          -- Temperature in Fahrenheit

-- Typical retention
Infinite

-- Sample row
| time                | device     | celsius | fahrenheit |
|---------------------|------------|---------|------------|
| 2025-12-12 15:30:00 | Big-Garage | 24.5    | 76.1       |
```

### Verify Schema

```sql
SELECT * FROM esp_temperature LIMIT 1;
DESCRIBE TABLE esp_temperature;
```

---

## References

- **Data Ingestion**: [INTEGRATIONS.md](INTEGRATIONS.md)
- **InfluxDB 3 Setup**: [INFLUXDB3_SETUP.md](INFLUXDB3_SETUP.md)
- **Grafana Best Practices**: [.github/copilot-instructions.md](../.github/copilot-instructions.md#grafana--influxdb-3-flightsql-queries-best-practices)
- **Example Panel JSON**: `docs/influxv3-sql-example.json`

---

**Last Updated**: December 12, 2025
