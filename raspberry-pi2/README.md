# Raspberry Pi 2 Monitoring Setup

Configuration for raspberrypi2 (192.168.0.146) - monitoring exporters + AI monitor for camera dashboard stack.

## Services

- **node-exporter** (port 9100) - System metrics
- **telegraf** (port 9273) - Docker + host metrics
- **timescaledb** (port 5433) - Time-series database (camera dashboard)
- **postgres-exporter** (port 9188) - TimescaleDB metrics
- **promtail** (port 9080) - Log shipping to Grafana Cloud
- **ai-monitor** (port 8001) - Self-healing + LLM triage for Pi2 containers

## AI Monitor (NEW)

Pi2 runs its own ai-monitor instance monitoring local containers via Docker socket. It:
- Monitors camera dashboard services (postgres, api, web, sftp)
- Monitors exporters (telegraf, promtail, postgres-exporter)
- Reports metrics to Pi1's Prometheus on port 8001
- Shares same Claude/Gemini API keys from `.env`

**Protected services** (never auto-restart): `postgres`, `timescaledb`, `mediamtx`

See [docs/AI_MONITOR.md](../docs/AI_MONITOR.md) for full documentation.

## Quick Setup

From main Pi (raspberrypi), run:

```bash
cd ~/docker
./scripts/setup-pi2-complete.sh
```

This will:
1. Create directory structure
2. Copy docker-compose.yml and backup script
3. Start monitoring containers
4. Configure automated daily backups (3 AM)
5. Setup NAS mount (if needed)

## Manual Steps

### 1. Deploy Monitoring

```bash
cd ~/docker
scp -r raspberry-pi2/ aachten@raspberrypi2.local:/home/aachten/docker/

ssh aachten@raspberrypi2.local
cd ~/docker/raspberry-pi2
docker compose up -d
```

### 2. Setup Backups

On raspberrypi2:

```bash
# Test backup manually
sudo bash /home/aachten/docker/raspberry-pi2/backup_to_nas.sh

# Enable automated backups
sudo cp docker-backup.service /etc/systemd/system/
sudo cp docker-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable docker-backup.timer
sudo systemctl start docker-backup.timer

# Verify timer
systemctl list-timers docker-backup.timer
```

### 3. Configure NAS Mount

Add to `/etc/fstab`:

```
//192.168.0.1/G /mnt/nas-backup cifs credentials=/root/.nas-credentials,uid=1000,gid=1000,file_mode=0644,dir_mode=0755,vers=2.0,nofail,x-systemd.automount 0 0
```

Create `/root/.nas-credentials`:

```
username=admin
password=canada99
```

```bash
sudo chmod 600 /root/.nas-credentials
sudo mount /mnt/nas-backup
```

## Backup Details

- **Schedule:** Daily at 3:00 AM
- **Location:** `/mnt/nas-backup/docker-backups/raspberrypi2/`
- **Retention:** 30 days
- **What's backed up:**
  - Docker volumes (if any)
  - docker-compose.yml
  - Configuration files
  - Metadata (networks, volumes list)

## Verification

**Check services:**
```bash
docker compose ps
```

**Check metrics:**
```bash
curl http://localhost:9100/metrics | head
curl http://localhost:8080/metrics | head
```

**Check backup timer:**
```bash
systemctl status docker-backup.timer
journalctl -u docker-backup.service -n 50
```

**View backup logs:**
```bash
tail -f /home/aachten/docker/raspberry-pi2/logs/backup-*.log
```

**List backups:**
```bash
ls -lth /mnt/nas-backup/docker-backups/raspberrypi2/
```

## Integration with Main Pi

On main Pi (raspberrypi), Prometheus scrapes these targets:

```yaml
- job_name: 'raspberry-pi2'
  static_configs:
    - targets: ['raspberrypi2.local:9100']  # node-exporter
      labels:
        instance: 'raspberry-pi2'

- job_name: 'cadvisor-pi2'
  static_configs:
    - targets: ['raspberrypi2.local:8080']  # cadvisor
      labels:
        instance: 'raspberry-pi2'
```

After setup, restart Prometheus:
```bash
cd /home/aachten/docker && docker compose restart prometheus
```

Verify in Prometheus: http://raspberrypi:9090/targets

## Troubleshooting

**Containers won't start:**
```bash
docker compose logs
docker compose restart
```

**Backup fails:**
```bash
# Check NAS connectivity
ping 192.168.0.1

# Check mount
mountpoint /mnt/nas-backup

# Check logs
tail -f /home/aachten/docker/raspberry-pi2/logs/backup-*.log

# Manual backup
sudo bash /home/aachten/docker/raspberry-pi2/backup_to_nas.sh
```

**Metrics not showing in Prometheus:**
- Verify services are running: `docker compose ps`
- Test metrics locally: `curl http://localhost:9100/metrics`
- Check Prometheus config includes pi2 targets
- Restart Prometheus on main Pi

## Maintenance

**Update containers:**
```bash
docker compose pull
docker compose up -d
```

**View backup history:**
```bash
journalctl -u docker-backup.service --since "7 days ago"
```

**Manual backup:**
```bash
sudo bash /home/aachten/docker/raspberry-pi2/backup_to_nas.sh
```
