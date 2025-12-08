# InfluxDB 3 Core Deployment Guide

## Overview

InfluxDB 3 Core is the next-generation time-series database engine integrated into this Docker Compose setup. It runs alongside InfluxDB 2.7, enabling migration evaluation and parallel data ingestion during transition periods.

**Reference Repository**: https://github.com/aachtenberg/influxdbv3-core

## Quick Start

### Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| **InfluxDB 3 Core API** | `http://localhost:8181` | HTTP API for writes/queries |
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

## Getting Started: First Database and Query

### Step 1: Access Explorer UI

Open your browser to: `http://localhost:8888`

### Step 2: Create a Database

1. Click **Databases** in the left menu
2. Click **Create Database**
3. Enter name: `sensor_data`
4. Click **Create**

### Step 3: Write Sample Data

1. Click **Write Data** in the left menu
2. Select database: `sensor_data`
3. Paste sample line protocol:
   ```
   temperature,sensor=living_room,location=ground_floor temp=22.5,humidity=45 1701270000000000000
   temperature,sensor=bedroom,location=first_floor temp=20.1,humidity=50 1701270000000000000
   ```
4. Click **Write**

### Step 4: Query Data

1. Click **Query Data** in the left menu
2. Select database: `sensor_data`
3. Enter SQL query:
   ```sql
   SELECT * FROM temperature LIMIT 10
   ```
4. Click **Execute**

### Step 5: Integrate with Grafana

1. Open Grafana: `http://localhost:3000`
2. Add InfluxDB 3 as data source (see Grafana Integration section above)
3. Create dashboard querying your sample data

## Architecture

### Services

#### influxdb3-core
- **Image**: `influxdb:3-core`
- **Port**: `8181` (mapped from internal 8086)
- **Data Storage**: Named volume `influxdb3-data` at `/var/lib/influxdb3`
- **Startup Time**: ~6 seconds
- **Features**:
  - File-based object storage
  - Single-node core mode
  - UTC timezone
  - No plugins enabled

#### influxdb3-explorer
- **Image**: `influxdata/influxdb3-ui:latest`
- **Port**: `8888` (web interface)
- **Session Storage**: Named volume `influxdb3-explorer-db`
- **Admin Mode**: Enabled
- **Depends On**: `influxdb3-core`

### Network
Both services connect to the `monitoring` bridge network, allowing communication with other services (Grafana, Prometheus, etc.).

## API Usage

⚠️ **Note**: InfluxDB 3 Core is primarily accessed through the **Explorer UI** (`http://localhost:8888`). Direct HTTP API access is available but requires specific endpoint configuration beyond the scope of this setup.

### Primary Method: Explorer UI

Access the web interface at `http://localhost:8888` to:
- Create and manage databases
- Write data via line protocol
- Query data with SQL or Flux
- Visualize results
- Manage retention policies

### Secondary Method: SQL Queries (via Explorer UI)

1. Open `http://localhost:8888`
2. Select database
3. Write SQL queries directly in the UI:
   ```sql
   SELECT * FROM measurement
   SELECT time, field1 FROM measurement WHERE time > now() - interval '1 hour'
   ```

### Flux Queries (via Explorer UI)

1. Open `http://localhost:8888`
2. Switch to Flux query mode
3. Write Flux queries:
   ```flux
   from(bucket:"mydb") 
   |> range(start:-1h)
   |> filter(fn: (r) => r._measurement == "measurement")
   ```

### Line Protocol Data Ingestion

For programmatic writes, use the HTTP endpoint:

```bash
# Write data via curl (requires proper authentication setup)
curl -X POST http://localhost:8181/write \
  -H "Content-Type: text/plain" \
  -d 'measurement,tag1=value1 field1=10.5'
```

**Note**: InfluxDB 3 Core may require additional configuration for direct HTTP API access. Use Explorer UI for initial setup and testing.

## Integration with Existing Services

### Grafana Integration

1. **Add Data Source**:
   - Grafana URL: `http://localhost:3000`
   - Go to Configuration → Data Sources → Add data source
   - Select **InfluxDB**
   - Configure:
     - Name: `InfluxDB 3 Core`
     - Query Language: **SQL** (recommended) or Flux
     - URL: `http://influxdb3-core:8086` (internal container network)
     - Leave auth fields empty (no authentication required for local setup)

2. **Test Connection**:
   - Click "Save & Test"
   - You should see "datasource is working" message

3. **Create Dashboards**:
   - Create new dashboard
   - Add panel with InfluxDB 3 data source
   - Use SQL or Flux queries same as InfluxDB 2.7

**Note**: Ensure you have data in InfluxDB 3 before creating queries. Use Explorer UI (`http://localhost:8888`) to verify databases and tables exist.

### Home Assistant Integration

```yaml
# configuration.yaml
influxdb:
  api_version: 2
  ssl: false
  host: influxdb3-core  # Use container hostname on monitoring network
  port: 8086
  token: null
  organization: ""
  bucket: ""
  username: ""
  password: ""
  max_retries: 3
  default_measurement: "influxdb"
  tags: {}
  tag_attributes: {}
```

## Data Migration from InfluxDB 2.7

### Option 1: Federation (Recommended)

InfluxDB 3 can query InfluxDB 2.7 data via federation. Configure remote data source in Explorer UI.

### Option 2: Export/Import

```bash
# Export from InfluxDB 2.7
docker compose exec influxdb influx backup \
  /var/lib/influxdb2/backup \
  --token $INFLUXDB_ADMIN_TOKEN

# Restore to InfluxDB 3
docker compose exec influxdb3-core influx restore \
  /var/lib/influxdb3/backup \
  --bucket mybucket
```

### Option 3: Replication

Write to both databases simultaneously:
- InfluxDB 2.7: `http://localhost:8086` (existing)
- InfluxDB 3 Core: `http://localhost:8181` (new)

## Storage

### Volume Management

```bash
# View volumes
docker volume ls | grep influxdb3

# Inspect data location
docker volume inspect docker_influxdb3-data

# Backup data
docker run --rm \
  -v docker_influxdb3-data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/influxdb3-backup.tar.gz -C /data .

# Restore data
docker run --rm \
  -v docker_influxdb3-data:/data \
  -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/influxdb3-backup.tar.gz -C /data
```

## Monitoring

### Container Logs

```bash
# Follow real-time logs
docker compose logs -f influxdb3-core

# Last 100 lines
docker compose logs --tail=100 influxdb3-core

# Filter by level
docker compose logs influxdb3-core | grep ERROR
```

### Health Checks

```bash
# Check if core is running
docker compose ps influxdb3-core

# Test API connectivity
curl -v http://localhost:8181/

# Test Explorer UI
curl -s http://localhost:8888/ | grep -o '<title>.*</title>'
```

## Performance Tuning

### Recommended Settings

- **RAM**: 2GB minimum, 4GB+ recommended
- **Storage**: SSD recommended for data directory
- **Network**: Local connection preferred for low latency

### Scale Configuration

Edit `docker-compose.yml` for production:

```yaml
influxdb3-core:
  environment:
    # Add production settings
    - INFLUXDB_QUERY_LOG_ENABLED=true
    - INFLUXDB_TRACE_LOG_ENABLED=false
```

## Troubleshooting

### Service Fails to Start

**Error**: "unable to initialize python environment"

**Solution**: Plugin directory removed by design. InfluxDB 3 Core runs without plugins.

### Connection Refused

**Error**: `curl: (7) Failed to connect to localhost port 8181`

**Solution**:
```bash
# Wait for startup
sleep 10

# Check if port is listening
netstat -tlnp | grep 8181

# Check container logs
docker compose logs influxdb3-core
```

### Explorer UI Not Accessible

**Error**: `Cannot connect to InfluxDB`

**Solution**:
1. Verify services are running: `docker compose ps`
2. Check network: `docker network inspect docker_monitoring`
3. Verify internal connectivity: `docker compose exec influxdb3-explorer ping influxdb3-core`

### High Memory Usage

**Solution**:
- Limit query time ranges
- Implement retention policies
- Archive old data
- Review query complexity

## Best Practices

1. **Backups**: Regular backups of `influxdb3-data` volume
2. **Retention**: Set data retention policies to manage storage
3. **Monitoring**: Use Prometheus to scrape InfluxDB 3 metrics
4. **Security**: Use authentication tokens for production
5. **DNS**: Use container hostnames for internal communication

## Performance Comparison: InfluxDB 2.7 vs 3 Core

| Metric | InfluxDB 2.7 | InfluxDB 3 Core |
|--------|--------------|-----------------|
| **Port** | 8086 | 8181 |
| **Startup** | ~2s | ~6s |
| **Memory** | ~300MB idle | ~250MB idle |
| **Query Format** | InfluxQL, Flux | SQL, Flux |
| **Plugins** | Supported | Not (Core) |
| **Scaling** | Single node | Cluster ready |

## References

- **Source Repo**: https://github.com/aachtenberg/influxdbv3-core
- **Official Docs**: https://docs.influxdata.com/influxdb/latest/
- **API Docs**: https://docs.influxdata.com/influxdb/latest/api/
- **Migration Guide**: https://docs.influxdata.com/influxdb/latest/upgrade/migrate-data/

## Related Documentation

- [InfluxDB 2.7 Setup](./SETUP_GUIDE.md)
- [Grafana Configuration](../grafana/README.md)
- [Docker Compose Overview](../README.md)
