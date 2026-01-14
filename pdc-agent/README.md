# PDC Agent Configuration

This directory contains configuration for Grafana's Private Data Center (PDC) agent, which bridges local Prometheus metrics to Grafana Cloud.

## Volume Management

The PDC agent uses a **Docker named volume** (`pdc-agent-ssh`) for SSH key storage:

```yaml
volumes:
  - pdc-agent-ssh:/home/pdc/.ssh
```

✅ **Fully automatic** - No manual setup required!

On first start, the PDC agent will:
1. Docker creates the volume automatically with correct permissions (UID 30000:30000)
2. PDC agent generates SSH keypair in `/home/pdc/.ssh/`
3. PDC agent requests certificate from Grafana Cloud
4. Establishes secure tunnel for metric forwarding

## After Power Loss / Reboot

Everything comes back automatically:
- Docker volumes persist on disk
- Containers have `restart: unless-stopped` policy
- SSH keys remain in `pdc-agent-ssh` volume
- PDC agent reconnects to Grafana Cloud automatically

No manual intervention needed. 🎉

## Troubleshooting

### Permission Denied Errors

```
level=error msg="cannot start ssh client: mkdir /home/pdc/.ssh/: permission denied"
```

**Solution**: Run `./scripts/init-dirs.sh` or manually fix permissions as shown above.

### Container Crash Loop

Check logs:
```bash
docker logs pdc-agent --tail 50
```

Common causes:
- Missing/incorrect `GRAFANA_PDC_*` environment variables in `.env`
- Permission issues with SSH directory
- Network connectivity to Grafana Cloud

### Verify Connectivity

When working correctly, logs show:
```
level=info msg="starting ssh client"
level=info msg="  #1 1.2.3.4 (t4 [forwarded-tcpip] ...)"
```

## Environment Variables

Required in `.env`:
- `GRAFANA_PDC_TOKEN` - PDC agent token from Grafana Cloud
- `GRAFANA_PDC_CLUSTER` - Cluster ID (e.g., `prod-us-central-0`)
- `GRAFANA_PDC_GCLOUD_HOSTED_GRAFANA_ID` - Your Grafana Cloud instance ID

Get these from: Grafana Cloud → Connections → Private Data Source Connect

## Architecture

```
Local Prometheus (port 9090)
         ↓
    pdc-agent (SSH tunnel)
         ↓
   Grafana Cloud
         ↓
  Your Dashboards
```

The agent scrapes Prometheus and forwards metrics to Grafana Cloud, enabling:
- Remote dashboard access without exposing Prometheus
- Grafana Cloud alerting on local metrics
- Public dashboard sharing
