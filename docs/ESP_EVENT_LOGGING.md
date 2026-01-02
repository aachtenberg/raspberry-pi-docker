# ESP Event Logging

## Overview
ESP sensor devices can publish events to MQTT topic `esp-sensor-hub/{device}/events` which are captured by Telegraf and stored in both InfluxDB 3 Core and exposed to Prometheus for dashboards and alerting.

## Data Flow
```
ESP Device → MQTT (esp-sensor-hub/{device}/events) 
          → Telegraf 
          → InfluxDB 3 Core (esp_events database)
          → Prometheus (:9273/metrics)
          → Grafana Cloud
```

## Event Message Format

### Temperature Sensor Events
**Topic**: `esp-sensor-hub/{device-name}/events`

```json
{
  "device": "Spa",
  "chip_id": "A0B1C2D3E4F5",
  "firmware_version": "1.0.3-build20251222",
  "schema_version": 1,
  "event": "ota_start",
  "severity": "warning",
  "timestamp": 12345,
  "uptime_seconds": 3600,
  "free_heap": 45000,
  "message": "OTA update starting (sketch)"
}
```

### Surveillance Camera Events
**Topic**: `surveillance/{device-name}/events`

```json
{
  "device": "Front Door Cam",
  "chip_id": "1234567890ABCDEF",
  "trace_id": "a1b2c3d4e5f6",
  "traceparent": "00-a1b2c3d4e5f6-1234567890ab-01",
  "seq_num": 42,
  "schema_version": 1,
  "location": "surveillance",
  "timestamp": 12345,
  "event": "motion_detected",
  "severity": "info",
  "uptime": 3600,
  "free_heap": 120000
}
```

### Field Types
**Tags** (indexed, for filtering):
- `device`: Device name (from MQTT topic)
- `chip_id`: ESP32/ESP8266 chip ID
- `location`: Fixed as "surveillance" for cameras
- `topic`: MQTT topic path

**String Fields**:
- `event`: Event name (see Event Types below)
- `severity`: Event severity (info, warning, error)
- `message`: Human-readable event description (optional)
- `firmware_version`: Device firmware version
- `trace_id`: Distributed tracing ID (surveillance only)
- `traceparent`: W3C trace context (surveillance only)

**Numeric Fields**:
- `timestamp`: Device uptime in milliseconds
- `uptime_seconds`: Device uptime in seconds
- `free_heap`: Free heap memory in bytes
- `seq_num`: Sequence number (surveillance only)
- `schema_version`: Message schema version

## Event Types

## Event Types

### Temperature Sensor Events
- `ota_start`: OTA update beginning
- `ota_complete`: OTA update successful
- `ota_error`: OTA update failed
- `ota_warning`: OTA-related warnings
- `sensor_error`: DS18B20 read failures
- `deep_sleep_config`: Deep sleep configuration changes
- `deep_sleep_warning`: Deep sleep configuration warnings
- `device_restart`: Device restarting via MQTT command
- `config_portal`: WiFi configuration portal events
- `device_configured`: Device name/WiFi configured
- `wifi_connected`: WiFi connection established
- `command_error`: MQTT command processing errors

### Surveillance Camera Events
- `motion_detected`: Motion detected by camera
- `camera_error`: Camera sensor or processing error
- `reconnect`: MQTT/WiFi reconnection
- `image_capture`: Image captured and published
- `config_change`: Configuration updated

### Severity Levels
- `info`: Normal operational events
- `warning`: Important events requiring attention
- `error`: Failure conditions

## Telegraf Configuration

### Input Plugins
```toml
# Temperature Sensor Events
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto-broker:1883"]
  topics = ["esp-sensor-hub/+/events"]
  qos = 0
  data_format = "json"
  name_override = "esp_events"
  tag_keys = ["device", "chip_id"]
  json_string_fields = ["event", "severity", "message", "firmware_version"]

# Surveillance Camera Events
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto-broker:1883"]
  topics = ["surveillance/+/events"]
  qos = 0
  data_format = "json"
  name_override = "surveillance_events"
  tag_keys = ["device", "chip_id", "location"]
  json_string_fields = ["event", "severity", "trace_id", "traceparent"]
```

### Subscription Examples
```bash
# All temperature sensor events
mosquitto_sub -h localhost -t "esp-sensor-hub/+/events" -v

# All surveillance camera events
mosquitto_sub -h localhost -t "surveillance/+/events" -v

# All events from both device types
mosquitto_sub -h localhost -t "+/+/events" -v
```

### Outputs
1. **InfluxDB 3 Core**: `esp_events` database for historical queries (both temperature sensors and cameras)
2. **Prometheus**: `:9273/metrics` endpoint with counters

## InfluxDB 3 Queries

### Recent events by device
```sql
SELECT time, device, event, severity, message
FROM esp_events
WHERE time > now() - interval '1 hour'
ORDER BY time DESC
LIMIT 50
```

### Event counts by type
```sql
SELECT event, count(*) as count
FROM esp_events
WHERE time > now() - interval '24 hours'
GROUP BY event
ORDER BY count DESC
```

### Surveillance events with trace IDs
```sql
SELECT time, device, event, trace_id, seq_num
FROM surveillance_events
WHERE time > now() - interval '1 hour'
ORDER BY time DESC
```

### Error events
```sql
SELECT time, device, event, message
FROM esp_events
WHERE severity IN ('error')
  AND time > now() - interval '7 days'
ORDER BY time DESC
```

## Prometheus Metrics

Telegraf exposes event counters via Prometheus:

```
esp_events{device="Spa",event="ota_start",severity="warning"} 2
esp_events{device="Main Cottage",event="sensor_error",severity="error"} 1
surveillance_events{device="Front-Door-Cam",event="motion_detected",severity="info"} 15
```

### Alert Rules
```yaml
groups:
  - name: esp_events
    interval: 1m
    rules:
      - alert: HighESPErrorRate
        expr: rate(esp_events{severity="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on {{ $labels.device }}"
          description: "Device {{ $labels.device }} reporting {{ $value }} errors/sec"
      
      - alert: OTAUpdateFailed
        expr: increase(esp_events{event="ota_error"}[10m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "OTA update failed on {{ $labels.device }}"
      
      - alert: SensorReadFailures
        expr: increase(esp_events{event="sensor_error"}[5m]) > 3
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Multiple sensor failures on {{ $labels.device }}"
```

## Grafana Dashboards

### Event Timeline Panel
```sql
SELECT
  time,
  device,
  event_type,
  severity,
  message
FROM esp_events
WHERE time >= $__timeFrom AND time <= $__timeTo
ORDER BY time DESC
```

### Event Rate by Device
```sql
SELECT
  time_bucket('5m', time) as time_bucket,
  device,
  count(*) as event_count
FROM esp_events
WHERE time >= $__timeFrom AND time <= $__timeTo
GROUP BY time_bucket, device
ORDER BY time_bucket
```

### Event Type Distribution
```sql
SELECT
  event,
  count(*) as count
FROM esp_events
WHERE time >= $__timeFrom AND time <= $__timeTo
GROUP BY event
ORDER BY count DESC
```

### Severity Distribution
```sql
SELECT
  severity,
  count(*) as count
FROM esp_events
WHERE time >= $__timeFrom AND time <= $__timeTo
GROUP BY severity
```

## Device Implementation

**Note**: Event publishing is already implemented in your ESP devices (firmware 1.0.9+ for most devices, 1.0.13+ for newer ones). Events are automatically published for:
- OTA updates (start, complete, error, warning)
- Sensor errors
- Deep sleep configuration changes
- Device restarts
- WiFi/MQTT connection events
- Configuration portal activity

No firmware changes needed - events are already flowing to MQTT!

## Best Practices

1. **Use standard event_types**: Maintain consistency across devices
2. **Set appropriate severity**: info < warning < error < critical
3. **Include context in message**: Human-readable descriptions
4. **Add error_codes**: For programmatic error handling
5. **Include duration_ms**: For performance tracking events
6. **Rate limiting**: Don't flood with events (max ~1 event/sec per device)
7. **Batch on recovery**: If connection lost, summarize events rather than replaying all

## Retention & Cleanup

- InfluxDB 3: Events stored indefinitely (until manual cleanup)
- Prometheus: Metrics retained per global config (typically 15 days)
- Consider implementing retention policies for old events:
  ```sql
  DELETE FROM esp_events WHERE time < now() - interval '90 days'
  ```

## Troubleshooting

### Events not appearing in InfluxDB
1. Check Telegraf logs: `docker compose logs -f telegraf`
2. Verify MQTT topic: `mosquitto_sub -h localhost -t "esp-sensor-hub/#" -v`
3. Test InfluxDB write: `curl -H "Authorization: Bearer $TOKEN" http://localhost:8181/api/v3/query_sql --data-urlencode "q=SELECT * FROM esp_events LIMIT 1"`

### Prometheus metrics missing
1. Check Telegraf metrics endpoint: `curl http://localhost:9273/metrics | grep esp_events`
2. Verify Prometheus scrape config includes telegraf target
3. Check Prometheus targets: http://prometheus:9090/targets

## Related Documentation
- [OPERATIONS_GUIDE.md](OPERATIONS.md) - System operations
- [INFLUXDB3_SETUP.md](INFLUXDB3_SETUP.md) - InfluxDB 3 Core setup
- [AI_MONITOR.md](AI_MONITOR.md) - Automated alerting
