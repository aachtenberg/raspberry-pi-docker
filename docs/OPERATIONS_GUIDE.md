# Operations and Maintenance Guide

This guide covers daily operations, monitoring, dashboard management, and maintenance tasks for the Raspberry Pi Docker infrastructure.

## Dashboard Management

### Grafana Dashboard Operations

#### Export All Dashboards

```bash
cd ~/docker
./scripts/export_grafana_dashboards.sh
```

The script automatically:
- Connects to Grafana API
- Exports all dashboards as JSON
- Saves to `grafana/dashboards/`
- Includes metadata (timestamp, version)

#### Import Dashboards

```bash
# Import all dashboards from JSON files
./scripts/import_grafana_dashboards.sh

# Import specific dashboard
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d @grafana/dashboards/temperatures_rue_romain.json \
  "http://localhost:3000/api/dashboards/db"
```

#### Available Dashboards

1. **Temperatures Rue Romain** - ESP sensor temperature monitoring
2. **Raspberry Pi & Docker Monitoring** - System resource monitoring  
3. **Docker Containers** - Container status and metrics
4. **InfluxDB Performance Monitoring** - Database performance metrics

### Dashboard Version Control

#### Manual Backup and Commit

```bash
# Export latest versions
./scripts/export_grafana_dashboards.sh

# Review changes
git diff grafana/dashboards/

# Commit changes
git add grafana/dashboards/
git commit -m "feat: update temperature dashboard with new panels"
git push
```

#### Automated Backup

Dashboards are automatically backed up daily at 2 AM via cron:

```bash
# View backup schedule
crontab -l

# Check backup logs
tail -f ~/docker/logs/grafana_backup.log

# Manual backup run
./scripts/backup_grafana_dashboards.sh
```

The automated script:
- Exports all dashboards
- Commits changes to Git (if any)
- Pushes to GitHub
- Logs all activity

## System Monitoring

### Check Service Status

```bash
# Quick status overview
./scripts/status.sh

# Detailed container status
docker compose ps

# Resource usage
docker stats

# System resources
df -h
free -h
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f influxdb
docker compose logs -f grafana

# Last 100 lines
docker compose logs --tail=100 prometheus
```

### Monitor Performance

#### Key Metrics to Watch

**System Level:**
- CPU usage (target: <80%)
- Memory usage (target: <90%) 
- Disk space (target: <85%)
- Network I/O

**Application Level:**
- InfluxDB write rate (~240 writes/hour from 4 ESP devices)
- Grafana response time
- Prometheus scrape success rate
- MQTT message throughput

#### Performance Dashboards

1. **Raspberry Pi & Docker Monitoring**:
   - System CPU, memory, disk usage
   - Container resource consumption
   - Network traffic

2. **InfluxDB Performance Monitoring**:
   - Database operations rate
   - Memory allocation
   - HTTP request rate
   - Garbage collection metrics

### Prometheus Queries

#### Useful Queries for Monitoring

```promql
# Service uptime
up{job="influxdb"}
up{job="raspberry-pi"}

# Memory usage
go_memstats_alloc_bytes{job="influxdb"}
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes

# CPU usage
rate(node_cpu_seconds_total[5m])

# Disk usage
(node_filesystem_size_bytes - node_filesystem_free_bytes) / node_filesystem_size_bytes

# Container stats
rate(container_cpu_usage_seconds_total[5m])
container_memory_usage_bytes
```

## Maintenance Tasks

### Regular Maintenance (Weekly)

```bash
# Update container images
cd ~/docker
docker compose pull

# Restart with new images
docker compose up -d

# Clean up old images
docker image prune -f

# Check disk usage
docker system df
```

### Container Management

```bash
# Restart specific service
docker compose restart grafana

# Recreate service (with new config)
docker compose up -d --force-recreate influxdb

# Scale service (if applicable)
docker compose up -d --scale prometheus=1

# View container resource limits
docker inspect influxdb | grep -A5 -B5 Memory
```

### Data Management

#### InfluxDB Maintenance

```bash
# Check database size
docker exec influxdb influx bucket list
docker exec influxdb du -sh /var/lib/influxdb2/

# Backup InfluxDB data
docker exec influxdb influx backup /backup --bucket sensor_data
docker cp influxdb:/backup ./influxdb-backup-$(date +%Y%m%d)

# Query recent data
docker exec influxdb influx query 'from(bucket: "sensor_data") |> range(start: -1h) |> count()'
```

#### Log Rotation

```bash
# Check log sizes
docker system df
docker logs --details influxdb 2>&1 | wc -l

# Rotate logs (automatic via Docker)
docker system prune --volumes -f
```

### Network Management

```bash
# Inspect networks
docker network ls
docker network inspect docker_monitoring

# Check connectivity between services
docker exec grafana ping influxdb
docker exec prometheus wget -qO- http://influxdb:8086/health
```

### Backup Operations

#### Full System Backup

```bash
# Stop services
docker compose down

# Backup everything
tar czf ~/backup-$(date +%Y%m%d).tar.gz \
  ~/docker \
  /var/lib/docker/volumes/docker_*

# Restart services
docker compose up -d
```

#### Selective Backup

```bash
# Backup only persistent data
docker run --rm \
  -v docker_influxdb-data:/data \
  -v ~/backups:/backup \
  alpine tar czf /backup/influxdb-$(date +%Y%m%d).tar.gz /data

# Backup Grafana dashboards and settings
docker run --rm \
  -v docker_grafana-data:/data \
  -v ~/backups:/backup \
  alpine tar czf /backup/grafana-$(date +%Y%m%d).tar.gz /data
```

## Alerting and Notifications

### Home Assistant Integration

Temperature alerts are configured in Home Assistant:

```bash
# Check Home Assistant logs
docker compose logs homeassistant

# Access Home Assistant
open http://localhost:8123
```

### Prometheus Alerting (Future Enhancement)

Consider adding Alertmanager for:
- High temperature alerts
- Service down notifications
- Disk space warnings
- Memory usage alerts

## Troubleshooting

### Common Issues

#### Dashboard Not Loading
1. Check Grafana logs: `docker compose logs grafana`
2. Verify data source: Grafana → Configuration → Data Sources
3. Test InfluxDB connection: `curl http://localhost:8086/health`

#### No Temperature Data
1. Check ESP device connectivity
2. Verify InfluxDB token in device firmware
3. Check MQTT broker: `docker compose logs mosquitto-broker`
4. Query raw data: InfluxDB Data Explorer

#### High Memory Usage
1. Check container stats: `docker stats`
2. Identify memory-heavy containers
3. Restart heavy consumers: `docker compose restart <service>`
4. Consider resource limits in docker-compose.yml

#### Slow Dashboard Performance
1. Optimize Grafana queries (add time ranges)
2. Check InfluxDB performance dashboard
3. Consider data retention policies
4. Add query caching

### Recovery Procedures

#### Service Recovery
```bash
# Complete restart
docker compose down
docker compose up -d

# Reset specific service
docker compose stop grafana
docker volume rm docker_grafana-data
docker compose up -d grafana
# Re-import dashboards
```

#### Data Recovery
```bash
# Restore from backup
docker compose down
tar xzf backup-YYYYMMDD.tar.gz -C /
docker compose up -d

# Restore specific volume
docker volume create docker_influxdb-data
docker run --rm -v docker_influxdb-data:/data -v ~/backups:/backup alpine tar xzf /backup/influxdb-YYYYMMDD.tar.gz -C /data
```

## Performance Optimization

### Resource Tuning

```yaml
# Example resource limits in docker-compose.yml
services:
  influxdb:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
```

### Query Optimization

- Use appropriate time ranges in Grafana
- Leverage InfluxDB's `aggregateWindow()` function
- Cache frequently-used queries
- Monitor query performance in InfluxDB dashboard

### Storage Optimization

- Configure InfluxDB retention policies
- Regular cleanup of old container logs
- Monitor disk usage trends
- Consider log rotation policies

## Security Considerations

### Access Control
- Regular API key rotation
- Monitor access logs
- Use strong passwords
- Enable HTTPS for external access

### Network Security
- Firewall configuration
- VPN access for remote management
- Regular security updates
- Monitor unusual traffic patterns

---

**Last Updated**: November 2025