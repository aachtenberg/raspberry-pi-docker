# InfluxDB 3 Core Deployment Guide

## Overview

InfluxDB 3 Core is the next-generation time-series database engine integrated into this Docker Compose setup. It runs alongside InfluxDB 2.7, enabling migration evaluation and parallel data ingestion during transition periods.

**Reference Repository**: https://github.com/aachtenberg/influxdbv3-core

## Quick Start

### Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| **InfluxDB 3 Core API** | `http://localhost:8181` | HTTP API for writes/queries (requires token) |
| **Explorer UI** | `http://localhost:8888` | Web interface for data exploration |

### Start Services

```bash
cd /home/aachten/docker
docker compose up -d influxdb3-core influxdb3-explorer
```

### Verify Services

```bash
# Check container status
docker compose ps | grep influxdb3

# View logs
docker compose logs -f influxdb3-core
docker compose logs -f influxdb3-explorer
```

## Authentication: Creating an Admin Token

InfluxDB 3 Core **requires authentication** for all API operations. You must create an admin token first.

### Step 1: Generate Admin Token

After containers are running, create an admin token:

```bash
docker compose exec influxdb3-core influxdb3 create token --admin
```

**Output:**
```
New token created successfully!

Token: apiv3_EXAMPLE_TOKEN_REPLACE_WITH_YOUR_ACTUAL_TOKEN_VALUE_HERE
HTTP Requests Header: Authorization: Bearer apiv3_EXAMPLE_TOKEN_REPLACE_WITH_YOUR_ACTUAL_TOKEN_VALUE_HERE

IMPORTANT: Store this token securely, as it will not be shown again.
```

### Step 2: Save Token to `.env`

Add the token to your `.env` file:

```bash
echo "INFLUXDB3_ADMIN_TOKEN=<your-token-value>" >> .env
```

⚠️ **Important**: Add `.env` to `.gitignore` - never commit credentials!

### Step 3: Test Token Access

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"
```

**Expected output:**
```
+---------------+
| iox::database |
+---------------+
| _internal     |
+---------------+
```

## Common Operations

### Create Database

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 create database mydb --token "${TOKEN}"
```

### List Databases

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"
```

### CLI: Write Data

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 write mydb \
  --token "${TOKEN}" \
  temperature,location=bedroom value=22.5 \
  temperature,location=living_room value=23.1
```

### HTTP API: Write Data

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
curl -X POST http://localhost:8181/api/v1/write?org=&bucket=mydb \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: text/plain" \
  -d 'temperature,sensor=kitchen value=21.8'
```

### HTTP API: Query Data

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
curl -s -X POST http://localhost:8181/api/v1/query \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT time, measurement, field, tags FROM temperature LIMIT 10",
    "database": "mydb"
  }'
```

## Using Explorer UI

The web-based Explorer UI (`http://localhost:8888`) provides:
- **Database browser** - explore schemas
- **Query builder** - write SQL or InfluxQL
- **Data preview** - view results with charts

The Explorer UI **does not require token authentication** for local access on the Docker network, but requires proper network connectivity.

### Access Explorer UI

1. Open browser: `http://localhost:8888`
2. Left panel shows available databases
3. Click database to explore tables
4. Use query editor to run SQL queries

## Getting Started: First Database and Query

### Step 1: Create Database

Using CLI:
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 create database sensor_data --token "${TOKEN}"
```

Or using Explorer UI:
1. Open `http://localhost:8888`
2. Click "New Database"
3. Enter name: `sensor_data`

### Step 2: Write Sample Data

Using CLI:
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 write sensor_data --token "${TOKEN}" \
  temperature,room=bedroom,floor=1 value=22.5 \
  temperature,room=living_room,floor=0 value=23.1 \
  humidity,room=bedroom,floor=1 value=45 \
  humidity,room=living_room,floor=0 value=52
```

Or using HTTP API:
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
curl -X POST http://localhost:8181/api/v1/write?org=&bucket=sensor_data \
  -H "Authorization: Bearer ${TOKEN}" \
  -d 'temperature,room=bedroom value=22.5
temperature,room=living_room value=23.1'
```

### Step 3: Query Data

Using CLI:
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
docker compose exec influxdb3-core influxdb3 query sensor_data --token "${TOKEN}" \
  "SELECT time, room, value FROM temperature LIMIT 10"
```

Using HTTP API:
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
curl -X POST http://localhost:8181/api/v1/query \
  -H "Authorization: Bearer ${TOKEN}" \
  -d 'SELECT time, room, value FROM temperature LIMIT 10&database=sensor_data'
```

Using Explorer UI:
1. Open `http://localhost:8888`
2. Select `sensor_data` database
3. Click "Query"
4. Run: `SELECT time, room, value FROM temperature LIMIT 10`

## Architecture & Services

### influxdb3-core

- **Image**: `influxdb:3-core`
- **Port**: 8181 (container maps port 8086 → host 8181)
- **Storage**: Named volume `influxdb3-data` at `/var/lib/influxdb3`
- **Mode**: File-based object store
- **Network**: Docker bridge network `monitoring`

**Configuration:**
```yaml
influxdb3-core:
  image: influxdb:3-core
  ports:
    - '8181:8086'
  volumes:
    - influxdb3-data:/var/lib/influxdb3
  command:
    - influxdb3
    - serve
    - --node-id=influxdb-node-0
    - --object-store=file
    - --data-dir=/var/lib/influxdb3/data
```

### influxdb3-explorer

- **Image**: `influxdata/influxdb3-ui:latest`
- **Port**: 8888
- **Storage**: Named volume `influxdb3-explorer-db` for session persistence
- **Mode**: Admin mode enabled
- **Depends On**: `influxdb3-core`

**Configuration:**
```yaml
influxdb3-explorer:
  image: influxdata/influxdb3-ui:latest
  ports:
    - '8888:80'
  environment:
    - MODE=admin
  depends_on:
    - influxdb3-core
```

## Grafana Integration

### Using InfluxDB 3 Core as Datasource

Grafana can query InfluxDB 3 Core for visualization of sensor data.

**Datasource Configuration:**

1. Open Grafana: `http://localhost:3000`
2. Go to **Configuration** > **Data Sources**
3. Click **Add data source**
4. Select **InfluxDB FlightSQL**
5. Configure:
   - **Name**: InfluxDB 3 Core
   - **HTTP URL**: `http://influxdb3-core:8181` (internal Docker network)
   - **Database**: Leave empty initially
   - **Authentication**: 
     - If using same Docker network: No authentication required
     - If external: Add Bearer token in Custom HTTP Headers

**Example Datasource Configuration:**

```yaml
apiVersion: 1
datasources:
  - name: InfluxDB 3 Core
    type: influxdb-flight
    access: proxy
    url: http://influxdb3-core:8181
    isDefault: false
    jsonData:
      httpMethod: POST
      authType: bearer
      bearerToken: ${INFLUXDB3_ADMIN_TOKEN}
```

### Querying from Grafana

Create a new dashboard and add panel:

1. Select **InfluxDB 3 Core** datasource
2. Use SQL query:

```sql
SELECT 
  time,
  room,
  value
FROM temperature
WHERE time > now() - interval '24 hours'
ORDER BY time
```

3. Visualize as graph, gauge, or table

## Integration with Home Assistant

### MQTT → InfluxDB 3 Flow

Home Assistant can send sensor data via MQTT, then Telegraf can write to InfluxDB 3 Core:

```
Home Assistant → Mosquitto (MQTT) → Telegraf → InfluxDB 3 Core
```

### Telegraf Configuration

Create `telegraf.conf` to read MQTT and write to InfluxDB 3 Core:

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = ["homeassistant/sensor/+/state"]

[[outputs.influxdb_v2]]
  urls = ["http://influxdb3-core:8181"]
  token = "${INFLUXDB3_ADMIN_TOKEN}"
  organization = ""
  bucket = "homeassistant"
  skip_verify = false
```

## Data Migration from InfluxDB 2.7

### Export from InfluxDB 2.7

```bash
docker compose exec influxdb influx backup \
  /var/backups/influxdb2-backup \
  --token ${INFLUXDB_ADMIN_TOKEN}
```

### Restore to InfluxDB 3 Core

InfluxDB 3 Core uses different storage, so direct restore isn't supported. Instead, use data export/import:

```bash
# Export from InfluxDB 2.7 as CSV
docker compose exec influxdb influx query \
  --org ${INFLUXDB_ORG_ID} \
  'from(bucket: "sensor_data") |> range(start: -30d)' \
  --format csv > data_export.csv

# Parse CSV and write to InfluxDB 3 Core using custom script
# (See migration guide for details)
```

## Troubleshooting

### 401 Unauthorized Errors

**Problem**: API calls return `401 Unauthorized`

**Solution**: Ensure token is included in requests:
```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
# Verify token works
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"
```

### Container Won't Start

**Problem**: influxdb3-core container exits immediately

**Solutions**:
```bash
# Check logs for errors
docker compose logs influxdb3-core | tail -50

# Verify port 8181 isn't in use
netstat -an | grep 8181

# Check volume permissions
ls -la /var/lib/docker/volumes/ | grep influxdb3
```

### Explorer UI Won't Connect

**Problem**: Cannot access `http://localhost:8888`

**Solutions**:
1. Wait 10 seconds after startup for UI to initialize
2. Clear browser cache
3. Check services are running:
   ```bash
   docker compose ps | grep influxdb3
   ```
4. Check network connectivity:
   ```bash
   docker compose exec influxdb3-explorer ping influxdb3-core
   ```

### No Databases Appear in Explorer

**Problem**: Explorer shows empty database list

**Solutions**:
1. Create a database first:
   ```bash
   TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)
   docker compose exec influxdb3-core influxdb3 create database test --token "${TOKEN}"
   ```
2. Refresh Explorer UI (F5 or Cmd+R)

### Token Lost or Forgotten

**Problem**: Admin token not saved or lost

**Solution**: Create a new token:
```bash
docker compose exec influxdb3-core influxdb3 create token --admin
# Save to .env
echo "INFLUXDB3_ADMIN_TOKEN=<new-token>" >> .env
```

**Note**: Old tokens will still be valid. Store new token in `.env` for convenience.

## CLI Command Reference

### Database Operations

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)

# Create database
docker compose exec influxdb3-core influxdb3 create database mydb --token "${TOKEN}"

# List databases
docker compose exec influxdb3-core influxdb3 show databases --token "${TOKEN}"

# Delete database (use with caution!)
docker compose exec influxdb3-core influxdb3 delete database mydb --token "${TOKEN}"
```

### Data Operations

```bash
TOKEN=$(grep INFLUXDB3_ADMIN_TOKEN .env | cut -d= -f2)

# Write line protocol
docker compose exec influxdb3-core influxdb3 write mydb --token "${TOKEN}" \
  'temperature,room=kitchen value=21.5'

# Query data
docker compose exec influxdb3-core influxdb3 query mydb --token "${TOKEN}" \
  'SELECT * FROM temperature LIMIT 10'
```

### Token Operations

```bash
# Create admin token
docker compose exec influxdb3-core influxdb3 create token --admin

# Create read-only token
docker compose exec influxdb3-core influxdb3 create token --readonly

# List tokens
docker compose exec influxdb3-core influxdb3 show tokens
```

## Performance Notes

- InfluxDB 3 Core uses Arrow/Parquet columnar storage
- Query performance improved over InfluxDB 2.x
- Disk usage typically 50-70% of InfluxDB 2.x for same data
- File-based object store suitable for Raspberry Pi
- Network mode: Docker bridge (not host network for flexibility)

## Next Steps

1. **Create your first database** - Use CLI or Explorer UI
2. **Configure data ingestion** - Home Assistant, MQTT, Telegraf, or HTTP API
3. **Set up Grafana dashboards** - Query InfluxDB 3 Core data
4. **Monitor performance** - Check logs and resource usage

## Reference Documentation

- **InfluxDB 3 Core Docs**: https://docs.influxdata.com/influxdb3/core/
- **InfluxDB API Reference**: https://docs.influxdata.com/influxdb3/core/api/
- **InfluxQL Language**: https://docs.influxdata.com/influxdb3/core/reference/influxql/
- **GitHub Repository**: https://github.com/aachtenberg/influxdbv3-core

## Support

For issues or questions:
1. Check logs: `docker compose logs influxdb3-core`
2. Test CLI directly: `docker compose exec influxdb3-core influxdb3 --help`
3. Review InfluxDB documentation at https://docs.influxdata.com/influxdb3/
