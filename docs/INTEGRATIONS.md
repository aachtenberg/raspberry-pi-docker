# Data Integrations & Pipelines

This guide covers all data ingestion pipelines: MQTT → Telegraf → InfluxDB 3, plus Home Assistant, Surveillance, and ESP sensor data.

## Table of Contents

- [MQTT → Telegraf → InfluxDB 3](#mqtt--telegraf--influxdb-3-core)
- [Temperature Sensor Pipeline](#temperature-sensor-pipeline)
- [Home Assistant Integration](#home-assistant-integration)
- [Surveillance/Camera Data](#surveillancecamera-data)
- [Telegraf Configuration](#telegraf-configuration-reference)

---

## MQTT → Telegraf → InfluxDB 3 Core

### Architecture Overview

```
MQTT Broker (Mosquitto)
    ├─ homeassistant/sensor/+/state        → Telegraf → InfluxDB 3 (homeassistant bucket)
    ├─ surveillance/camera/+/snapshot       → Telegraf → InfluxDB 3 (surveillance bucket)
    └─ esp-sensor-hub/+/{temperature,events} → Telegraf → InfluxDB 3 (temperature_data bucket)
```

### Key Concepts

- **Telegraf Bridge**: Standalone service consuming MQTT topics and writing to InfluxDB 3 Core via HTTP API
- **JSON Parsing**: Telegraf transforms JSON payloads into InfluxDB line protocol
- **Device Tags**: Regex processor extracts device identifiers from MQTT topic paths into queryable tags
- **Authentication**: Bearer token stored in `.env` as `INFLUXDB3_ADMIN_TOKEN`
- **Namepass Filters**: Route specific measurement types to specific InfluxDB 3 databases

### Start Telegraf

```bash
docker compose up -d telegraf

# Check logs
docker compose logs -f telegraf
```

### Verify Data Flow

```bash
# 1. Check MQTT broker has messages
mosquitto_sub -h 127.0.0.1 -t 'homeassistant/sensor/+/state' | head -20

# 2. Query InfluxDB 3 to confirm ingestion
docker compose exec influxdb3-core influxdb3 query \
  --token "$INFLUXDB3_ADMIN_TOKEN" \
  "SELECT COUNT(*) FROM homeassistant" \
  --database homeassistant
```

---

## Temperature Sensor Pipeline

### MQTT Topics

ESP sensor hubs publish to the following topics:

```
esp-sensor-hub/{device_id}/temperature
├─ payload: JSON {"device": "Big-Garage", "celsius": 24.5, "fahrenheit": 76.1}

esp-sensor-hub/{device_id}/events
└─ payload: JSON {"device": "Big-Garage", "event": "startup", "chip_id": "ABC123"}
```

### Telegraf Processing

**Input Plugin**: Consumes JSON from MQTT
```toml
[[inputs.mqtt_consumer]]
  topics = ["esp-sensor-hub/+/temperature"]
  data_format = "json"
  tag_keys = ["device", "chip_id"]
  name_override = "esp_temperature"
```

**Regex Processor**: Extracts device ID from topic
```toml
[[processors.regex]]
  pattern = "^esp-sensor-hub/([^/]+)/.*$"
  replacement = "${1}"
  result_key = "device"
```

**Output Plugin**: Writes to `temperature_data` database
```toml
[[outputs.http]]
  url = "http://localhost:8181/write?db=temperature_data"
  namepass = ["esp_temperature", "esp_events"]
  [outputs.http.headers]
    Authorization = "Bearer $INFLUXDB3_ADMIN_TOKEN"
```

### InfluxDB 3 Tables

```sql
-- esp_temperature table (auto-created)
-- Fields: time, device, celsius, fahrenheit
-- Tags: device, chip_id

-- esp_events table (auto-created)
-- Fields: time, device, event, status, message
-- Tags: device

-- Check table schemas
SELECT * FROM esp_temperature LIMIT 1;
SELECT * FROM esp_events LIMIT 1;
```

### Grafana Integration

See **TEMPERATURE_MONITORING.md** for complete dashboard setup with FlightSQL queries.

---

## Home Assistant Integration

### MQTT Topic Pattern

```
homeassistant/sensor/{entity_id}/state
├─ payload: JSON with entity attributes
```

### Telegraf Config

```toml
[[inputs.mqtt_consumer]]
  topics = ["homeassistant/sensor/+/state"]
  data_format = "json"
  tag_keys = ["entity_id"]
  name_override = "homeassistant"

[[outputs.http]]
  url = "http://localhost:8181/write?db=homeassistant"
  namepass = ["homeassistant"]
  [outputs.http.headers]
    Authorization = "Bearer $INFLUXDB3_ADMIN_TOKEN"
```

### Verify Data Ingestion

```sql
-- Query recent Home Assistant data
SELECT * FROM homeassistant LIMIT 100;

-- Count records by entity
SELECT COUNT(*) FROM homeassistant GROUP BY entity_id;
```

---

## Surveillance/Camera Data

### MQTT Topic Pattern

```
surveillance/camera/{camera_id}/snapshot
└─ payload: JSON with timestamp, snapshot_path, etc.
```

### Telegraf Config

```toml
[[inputs.mqtt_consumer]]
  topics = ["surveillance/#"]
  data_format = "json"
  tag_keys = ["camera_id"]
  name_override = "surveillance"

[[outputs.http]]
  url = "http://localhost:8181/write?db=surveillance"
  namepass = ["surveillance"]
  [outputs.http.headers]
    Authorization = "Bearer $INFLUXDB3_ADMIN_TOKEN"
```

---

## Telegraf Configuration Reference

### File Location

`/home/aachten/docker/telegraf/telegraf.conf`

### Structure

```toml
[agent]
  # Global settings
  interval = "10s"
  round_interval = true

[outputs]
  # Multiple InfluxDB 3 outputs (one per database)

[[inputs.mqtt_consumer]]
  # MQTT input plugin #1

[[inputs.mqtt_consumer]]
  # MQTT input plugin #2

[[processors.regex]]
  # Regex processor for tag extraction
```

### Common Commands

```bash
# Validate configuration syntax
docker compose exec telegraf telegraf -config /etc/telegraf/telegraf.conf -test

# Reload configuration (restart service)
docker compose restart telegraf

# View logs
docker compose logs -f telegraf

# Check environment variables
docker compose exec telegraf env | grep INFLUXDB
```

### Debugging

**No data appearing in InfluxDB 3?**

1. Check Telegraf is running: `docker compose ps telegraf`
2. Check MQTT broker has messages: `mosquitto_sub -h 127.0.0.1 -t 'esp-sensor-hub/#'`
3. Check Telegraf logs: `docker compose logs telegraf | grep -i error`
4. Verify bearer token is set: `docker compose exec telegraf env INFLUXDB3_ADMIN_TOKEN`
5. Test HTTP connectivity: `docker compose exec telegraf curl -H "Authorization: Bearer $INFLUXDB3_ADMIN_TOKEN" http://localhost:8181/health`

**Telegraf parsing errors?**

- Ensure JSON format matches expected schema (celsius, fahrenheit, device fields)
- Check `data_format = "json"` is set in MQTT input plugin
- Verify `tag_keys` matches actual JSON field names

---

## Adding a New Data Pipeline

### Steps

1. **Create MQTT topic** on Mosquitto (ensure devices publish to `/esp-sensor-hub/`, `/homeassistant/`, etc.)
2. **Add Telegraf input plugin** in `telegraf/telegraf.conf`:
   ```toml
   [[inputs.mqtt_consumer]]
     topics = ["your/topic/+/state"]
     data_format = "json"
     tag_keys = ["device_id", "other_tag"]
     name_override = "your_measurement"
   ```
3. **Add Telegraf output plugin** to route to InfluxDB 3:
   ```toml
   [[outputs.http]]
     url = "http://localhost:8181/write?db=your_database"
     namepass = ["your_measurement"]
     [outputs.http.headers]
       Authorization = "Bearer $INFLUXDB3_ADMIN_TOKEN"
   ```
4. **Create InfluxDB 3 database** (if needed):
   ```bash
   docker compose exec influxdb3-core influxdb3 create database \
     --token "$INFLUXDB3_ADMIN_TOKEN" your_database
   ```
5. **Test**: `docker compose restart telegraf && sleep 2 && docker compose logs telegraf`
6. **Query**: `SELECT * FROM your_measurement LIMIT 5;` in InfluxDB 3 Explorer

---

## References

- InfluxDB 3 Core: [INFLUXDB3_SETUP.md](INFLUXDB3_SETUP.md)
- Temperature Monitoring Dashboard: [TEMPERATURE_MONITORING.md](TEMPERATURE_MONITORING.md)
- Operations Guide: [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md)
- Telegraf Docs: https://docs.influxdata.com/telegraf/
