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

### JSON Payload Structure
```json
{
  "device": "Spa",
  "chip_id": "A1B2C3D4",
  "event_type": "wifi_reconnect",
  "severity": "warning",
  "message": "WiFi connection lost, reconnecting...",
  "error_code": "WIFI_DISCONNECT",
  "duration_ms": 2345,
  "timestamp": 1704236400000
}
```

### Field Types
**Tags** (indexed, for filtering):
- `device`: Device name (e.g., "Spa", "Main Cottage", "Pump House")
- `chip_id`: ESP32 chip ID
- `topic`: MQTT topic

**String Fields**:
- `event_type`: Event category (wifi_reconnect, ota_update, deep_sleep, error, warning, info)
- `severity`: Event severity (info, warning, error, critical)
- `message`: Human-readable event description
- `error_code`: Optional error code for debugging
- `status`: Optional status field

**Numeric Fields**:
- `duration_ms`: Event duration in milliseconds
- `timestamp`: Unix timestamp (milliseconds)
- Any other numeric values

## Event Types

### Connectivity Events
- `wifi_reconnect`: WiFi connection restored after disconnection
- `wifi_connect`: Initial WiFi connection on boot
- `mqtt_reconnect`: MQTT broker reconnection
- `network_timeout`: Network operation timeout

### System Events
- `ota_update`: Over-the-air firmware update
- `deep_sleep`: Entering deep sleep mode
- `wakeup`: Waking from deep sleep
- `reboot`: Device reboot
- `low_battery`: Battery voltage below threshold
- `heap_low`: Low free heap memory

### Error Events
- `sensor_error`: Temperature sensor read failure
- `mqtt_publish_failed`: Failed to publish to MQTT
- `wifi_failed`: WiFi connection permanently failed
- `heap_exhausted`: Out of memory

## Telegraf Configuration

### Input Plugin
```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto-broker:1883"]
  topics = ["esp-sensor-hub/+/events"]
  qos = 0
  data_format = "json"
  name_override = "esp_events"
  tag_keys = ["device", "chip_id"]
  json_string_fields = ["event_type", "severity", "message", "error_code", "status"]
```

### Outputs
1. **InfluxDB 3 Core**: `esp_events` database for historical queries
2. **Prometheus**: `:9273/metrics` endpoint with counters

## InfluxDB 3 Queries

### Recent events by device
```sql
SELECT time, device, event_type, severity, message
FROM esp_events
WHERE time > now() - interval '1 hour'
ORDER BY time DESC
LIMIT 50
```

### Event counts by type
```sql
SELECT event_type, count(*) as count
FROM esp_events
WHERE time > now() - interval '24 hours'
GROUP BY event_type
ORDER BY count DESC
```

### Error events
```sql
SELECT time, device, event_type, message, error_code
FROM esp_events
WHERE severity IN ('error', 'critical')
  AND time > now() - interval '7 days'
ORDER BY time DESC
```

## Prometheus Metrics

Telegraf exposes event counters via Prometheus:

```
esp_events{device="Spa",event_type="wifi_reconnect",severity="warning"} 5
esp_events{device="Main Cottage",event_type="error",severity="error"} 2
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
      
      - alert: ESPCriticalEvent
        expr: esp_events{severity="critical"} > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Critical event on {{ $labels.device }}"
          description: "{{ $labels.event_type }}: {{ $labels.message }}"
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

### Severity Distribution
```sql
SELECT
  severity,
  count(*) as count
FROM esp_events
WHERE time >= $__timeFrom AND time <= $__timeTo
GROUP BY severity
```

## ESP Device Implementation

### Example Arduino Code
```cpp
void publishEvent(const char* eventType, const char* severity, const char* message) {
  StaticJsonDocument<256> doc;
  doc["device"] = DEVICE_NAME;
  doc["chip_id"] = getChipId();
  doc["event_type"] = eventType;
  doc["severity"] = severity;
  doc["message"] = message;
  doc["timestamp"] = millis();
  
  char buffer[256];
  serializeJson(doc, buffer);
  
  String topic = "esp-sensor-hub/" + String(DEVICE_NAME) + "/events";
  mqttClient.publish(topic.c_str(), buffer, false);
}

// Usage
publishEvent("wifi_reconnect", "warning", "WiFi connection restored");
publishEvent("sensor_error", "error", "Failed to read temperature sensor");
publishEvent("deep_sleep", "info", "Entering deep sleep for 60s");
```

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
