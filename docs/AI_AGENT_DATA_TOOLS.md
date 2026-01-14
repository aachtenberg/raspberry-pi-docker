# AI Agent Data-Layer Investigation Tools

## Overview
The AI agent has direct access to MQTT and InfluxDB 3 Core for deep data-layer investigations beyond infrastructure metrics.

## Why Data-Layer Access?
**Problem**: Metrics alone can't diagnose data quality issues. Example: "Temperature dashboard broken" could be:
- Data not arriving (MQTT issue)
- Data arriving but not written (Telegraf/InfluxDB issue)  
- Data written but schema wrong (measurement/tag mismatch)
- Data exists but query broken (FlightSQL issue)

**Solution**: Agent can now:
1. Subscribe to MQTT topics to see raw sensor data
2. Query InfluxDB directly to validate data freshness and schema
3. Investigate end-to-end data flow from device → MQTT → Telegraf → InfluxDB → Grafana

## Available Tools

### MQTT Tools

#### `mqtt_subscribe`
Subscribe to MQTT topics and receive live messages.

**Use cases:**
- Check if ESP device is publishing
- Validate message formats (JSON structure)
- Diagnose QoS/retain issues
- See actual sensor payloads

**Parameters:**
- `topics`: Array of topic strings (supports wildcards `#` multi-level, `+` single-level)
- `duration_seconds`: How long to listen (default 5, max 30)
- `max_messages`: Message limit (default 20, max 100)

**Example:**
```json
{
  "topics": ["sensors/temperature/#", "sensors/battery/+"],
  "duration_seconds": 10,
  "max_messages": 50
}
```

#### `mqtt_inspect`
Get MQTT broker statistics via `$SYS` topics.

**Use cases:**
- Check broker health
- See connected clients count
- Monitor message throughput
- Check retained message count

**Returns:**
- Uptime, client connections, message rates, subscriptions, retained messages

### InfluxDB 3 Core Tools

#### `influxdb_query`
Execute FlightSQL query against InfluxDB 3 Core.

**Use cases:**
- Check data freshness: `SELECT time, device, temperature FROM romain_temperature ORDER BY time DESC LIMIT 10`
- Validate schemas: Check column names and types
- Investigate gaps: `SELECT COUNT(*) FROM ... WHERE time > now() - INTERVAL '1 hour'`
- Analyze patterns: Query specific devices, time ranges, tag combinations

**Parameters:**
- `database`: Database name (e.g., "sensors", "iot_data")
- `query`: SQL query string
- `limit`: Row limit (default 50, max 200) - auto-added if missing

**Example:**
```json
{
  "database": "sensors",
  "query": "SELECT time, device, temperature FROM romain_temperature WHERE time > now() - INTERVAL '1 hour' ORDER BY time DESC",
  "limit": 20
}
```

#### `influxdb_list`
List databases, tables, or schema information.

**Use cases:**
- Discover what databases exist
- List tables/measurements in a database
- Check column schema for a table

**Parameters:**
- `show`: What to list ("databases", "tables", "columns")
- `database`: Required for "tables" and "columns"
- `table`: Required for "columns"

**Examples:**
```json
{"show": "databases"}
{"show": "tables", "database": "sensors"}
{"show": "columns", "database": "sensors", "table": "romain_temperature"}
```

## Connection Configuration

### MQTT
- **Host**: `mosquitto-broker` (Docker service name)
- **Port**: 1883 (plain MQTT)
- **Auth**: None (internal network)

### InfluxDB 3 Core
- **Host**: `influxdb3-core`
- **gRPC Port**: 8182 (FlightSQL)
- **Auth**: Bearer token from `INFLUXDB3_ADMIN_TOKEN` env var
- **Protocol**: FlightSQL over gRPC

## Dependencies
- `paho-mqtt==2.1.0` - MQTT client
- `adbc-driver-flightsql==1.3.0` - InfluxDB 3 FlightSQL driver
- `pyarrow==18.1.0` - Arrow data format for FlightSQL

## Design Philosophy

**No rigid rules or patterns** - Agent discovers when to use these tools through investigation:
- Tool descriptions explain capabilities, not prescriptive workflows
- No example patterns in system prompt constraining usage
- Agent figures out investigation approaches based on context

**Read-only by design**:
- MQTT: Subscribe only (no publish)
- InfluxDB: Query only (no writes/deletes)
- Preserves data integrity while enabling deep investigation

**Security boundaries**:
- MQTT limited to internal broker (no external connections)
- InfluxDB uses admin token but queries only
- No ability to corrupt data or publish malicious messages

## Example Investigation Flow

**Scenario**: "romain_temperature dashboard shows no data"

**Traditional metrics approach** (limited):
1. `prom_query('up{job="telegraf"}')` → Telegraf is up
2. `prom_query('rate(mosquitto_messages_received_total[5m])')` → Messages flowing
3. **Dead end** - metrics look fine but dashboard broken

**Data-layer approach** (comprehensive):
1. `mqtt_subscribe(["sensors/romain/temperature"])` → See raw ESP device data
2. `influxdb_list({"show": "tables", "database": "sensors"})` → Check table exists
3. `influxdb_query({"database": "sensors", "query": "SELECT * FROM romain_temperature ORDER BY time DESC LIMIT 5"})` → Check latest data
4. **Root cause found**: Data exists but measurement name changed from `temperature` to `romain_temperature`, dashboard queries wrong table

## Observability

Tool usage tracked via Prometheus metrics:
```
ai_agent_tool_calls_total{tool_name="mqtt_subscribe", success="true"}
ai_agent_tool_calls_total{tool_name="influxdb_query", success="false"}
```

View in Grafana Cloud dashboard: [AI Agent - Investigation Metrics](https://aachten.grafana.net/d/ai-agent-metrics)

## Troubleshooting

### MQTT connection fails
- Check mosquitto-broker container running: `docker ps | grep mosquitto`
- Verify network connectivity: `docker exec ai-agent ping mosquitto-broker`
- Check broker logs: `docker logs mosquitto-broker`

### InfluxDB query fails
- Verify INFLUXDB3_ADMIN_TOKEN set in `.env` and passed to ai-agent container
- Check InfluxDB running: `docker ps | grep influxdb3-core`
- Test gRPC port: `docker exec ai-agent nc -zv influxdb3-core 8182`
- Check database exists: `influxdb_list({"show": "databases"})`

### Tool not available errors
- Check dependencies installed: `docker exec ai-agent pip list | grep -E "paho-mqtt|adbc-driver"`
- Rebuild container: `docker compose build ai-agent && docker compose up -d ai-agent`

## Future Enhancements

Potential additions (not yet implemented):
- **MQTT publish** for testing (with guardrails)
- **InfluxDB writes** for data repair (read-only currently)
- **Historical MQTT** via retained messages analysis
- **Data quality metrics** (schema drift detection, gap analysis)
- **Cross-system correlation** (MQTT → Telegraf → InfluxDB trace)
