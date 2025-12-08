# InfluxDB 3 Core Setup Guide

## Overview

InfluxDB 3 Core has been added to the Docker Compose setup for IoT/Camera deployments. It runs alongside the existing InfluxDB 2.7 to allow for gradual migration.

## Services

### influxdb3-core
- **Image**: `influxdb:3-core`
- **Port**: 8181
- **Container**: `influxdb3-core`
- **Data**: `/var/lib/influxdb3/data`
- **Volumes**: `influxdb3-data`, `influxdb3-plugins`

### influxdb3-explorer
- **Image**: `influxdata/influxdb3-ui:latest`
- **Port**: 8888
- **Container**: `influxdb3-explorer`
- **UI**: http://localhost:8888

## Current Status: ARM64 Compatibility Issue

### Problem
InfluxDB 3 Core has a known issue on ARM64 (Raspberry Pi) related to jemalloc memory allocation:
```
<jemalloc>: Unsupported system page size
memory allocation of 48 bytes failed
```

### Root Cause
The jemalloc memory allocator doesn't support the page size configuration on some ARM64 systems, causing immediate crashes on startup.

## Solutions / Workarounds

### Option 1: Use InfluxDB Cloud or x86_64 Host
Deploy InfluxDB 3 Core on a separate x86_64 machine and connect to it remotely.

### Option 2: Disable jemalloc
Try building a custom image with jemalloc disabled:
```bash
# Custom Dockerfile
FROM influxdb:3-core
ENV LD_PRELOAD=
RUN echo "disable_jemalloc=true" >> /etc/influxdb
```

### Option 3: Use InfluxDB 2.7 for Now
Keep using the existing InfluxDB 2.7 until ARM64 support improves in InfluxDB 3.

### Option 4: Wait for Upstream Fix
Monitor the InfluxDB GitHub repository for ARM64-specific releases.

## Testing InfluxDB 3 Core

Once a working solution is found, test with:

```bash
# Start the service
docker compose up -d influxdb3-core influxdb3-explorer

# Check status
docker compose ps | grep influxdb3

# View logs
docker compose logs -f influxdb3-core

# Access Explorer UI
open http://localhost:8888
```

## Configuration Reference

Current docker-compose configuration:
```yaml
influxdb3-core:
  image: influxdb:3-core
  container_name: influxdb3-core
  restart: no  # Disabled due to ARM64 issues
  ports:
    - '8181:8181'
  volumes:
    - influxdb3-data:/var/lib/influxdb3/data
    - influxdb3-plugins:/var/lib/influxdb3/plugins
  environment:
    - TZ=UTC
  networks:
    - monitoring
```

## Coexistence with InfluxDB 2.7

Both databases can run simultaneously:
- **InfluxDB 2.7**: Port 8086 (existing sensor data)
- **InfluxDB 3**: Port 8181 (camera IoT data)

This allows:
- ✅ Gradual data migration
- ✅ Testing before full migration
- ✅ Different retention policies per instance
- ✅ Fallback if needed

## Next Steps

1. **Resolve ARM64 issue**: Find or implement a workaround
2. **Set up camera IoT endpoint**: Configure devices to send data to port 8181
3. **Configure Explorer UI**: Set up admin credentials and buckets
4. **Create migration plan**: Define timeline for moving sensor data to InfluxDB 3
5. **Test performance**: Compare query performance between v2.7 and v3

## References

- [InfluxDB 3 Documentation](https://docs.influxdata.com/influxdb/v3.0/)
- [InfluxDB GitHub Issues](https://github.com/influxdata/influxdb)
- [ARM64 Build Issues](https://github.com/influxdata/influxdb/labels/platform%2Farm64)
