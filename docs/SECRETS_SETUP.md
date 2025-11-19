# Secrets Configuration Guide

This guide explains how to configure your `.env` file for the Raspberry Pi Docker infrastructure.

## Quick Setup

1. **Copy the template**:
   ```bash
   cd ~/docker
   cp .env.example .env
   ```

2. **Edit `.env`** with your actual credentials

3. **Validate configuration**:
   ```bash
   ./scripts/validate_secrets.sh
   ```

4. **Deploy stack**:
   ```bash
   docker compose up -d
   ```

## Required Secrets

### Cloudflare Tunnel Token

**What it is**: Authentication token for Cloudflare Tunnel to enable remote access

**How to get it**:
1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Navigate to **Access** → **Tunnels**
3. Find your tunnel (or create new one)
4. Click **Configure**
5. Copy the tunnel token (long base64-encoded string)

**Add to `.env`**:
```bash
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiZWEyNmZkZjVhOWVh...
```

### InfluxDB Configuration

#### Admin Username
**Default**: `admin`

You can keep this as is or change it.

```bash
INFLUXDB_ADMIN_USERNAME=admin
```

#### Admin Password
**What it is**: Password for InfluxDB web UI login

**Recommendations**:
- Use strong password (12+ characters)
- Mix of letters, numbers, symbols
- Don't reuse passwords from other services

```bash
INFLUXDB_ADMIN_PASSWORD=YourSecurePassword123!
```

#### Organization ID
**What it is**: 16-character hex ID for your InfluxDB organization

**How to get it** (if already setup):
```bash
# SSH to your Pi
ssh pi@192.168.0.167

# Query InfluxDB
docker exec -it influxdb influx org list
# Copy the "ID" column value
```

**For new setup**: Use any 16-character hex string, or let InfluxDB generate one on first startup.

```bash
INFLUXDB_ORG_ID=abc123def4567890
```

#### Bucket Name
**What it is**: Name of the InfluxDB bucket for storing sensor data

**Default**: `sensor_data`

This should match the bucket configured in your ESP devices (`include/secrets.h`).

```bash
INFLUXDB_BUCKET=sensor_data
```

#### Admin API Token
**What it is**: Long-lived token for API access (used by ESP devices and Grafana)

**How to generate** (after InfluxDB is running):
1. Open InfluxDB UI: `http://192.168.0.167:8086`
2. Login with admin username/password
3. Click **Data** → **API Tokens**
4. Click **Generate API Token** → **All Access Token**
5. Copy the generated token (looks like: `Mqj3XYZ_example_token...`)

**For new setup**: You can use any long random string, or let InfluxDB generate one.

```bash
INFLUXDB_ADMIN_TOKEN=Mqj3XYZ_example_token_abc123_REPLACE_WITH_YOUR_ACTUAL_TOKEN_FROM_INFLUXDB==
```

## Optional Configuration

### Grafana Admin Password

Uncomment and set if you want to pre-configure Grafana password:

```bash
GRAFANA_ADMIN_PASSWORD=YourGrafanaPassword
```

Otherwise, Grafana will prompt you to change password on first login (default: admin/admin).

## Complete Example

Here's a complete working `.env` file (with fake credentials):

```bash
# Environment variables for Docker Compose
# DO NOT commit this file to version control

# Cloudflare Tunnel Token
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiZXhhbXBsZSIsInQiOiIxMjM0NTY3OCIsInMiOiJhYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5eiJ9

# InfluxDB Configuration
INFLUXDB_ADMIN_USERNAME=admin
INFLUXDB_ADMIN_PASSWORD=MySecurePassword123!
INFLUXDB_ORG_ID=abc123def4567890
INFLUXDB_BUCKET=sensor_data
INFLUXDB_ADMIN_TOKEN=Mqj3XYZ_example_token_abc123==
```

## Security Best Practices

### Do NOT:
- ❌ Commit `.env` file to Git
- ❌ Share screenshots showing your secrets
- ❌ Use weak passwords (< 12 characters)
- ❌ Use same password across multiple services
- ❌ Store secrets in public pastebins or forums

### DO:
- ✅ Keep `.env` only on your Raspberry Pi
- ✅ Use strong, unique passwords
- ✅ Regenerate tokens if accidentally exposed
- ✅ Backup `.env` to secure location (encrypted)
- ✅ Enable 2FA on Cloudflare account

## Validation

Before deploying, validate your configuration:

```bash
cd ~/docker
./scripts/validate_secrets.sh
```

Expected output:
```
✅ .env exists
✅ .env is properly gitignored
✅ No placeholder values found
✅ All required variables present
✅ InfluxDB token length: 87 characters (looks valid)
✅ InfluxDB Organization ID format looks valid
✅ docker-compose.yml syntax is valid

✅ Configuration looks good!
```

## Troubleshooting

### Error: ".env not found"

You haven't created `.env` yet:

```bash
cd ~/docker
cp .env.example .env
vim .env
```

### Error: "Placeholder values found"

You have `YOUR_*` placeholders still in `.env`:

```bash
# Edit .env and replace all YOUR_* placeholders
vim .env
```

### InfluxDB fails to start with "401 Unauthorized"

- **Check token**: Make sure `INFLUXDB_ADMIN_TOKEN` matches your InfluxDB setup
- **Check org ID**: Verify `INFLUXDB_ORG_ID` is correct
- **Reset InfluxDB**: Remove volume and recreate:
  ```bash
  docker compose down
  docker volume rm docker_influxdb-data
  docker compose up -d
  ```

### Cloudflare Tunnel not connecting

- **Check token**: Verify `CLOUDFLARE_TUNNEL_TOKEN` is correct
- **Check tunnel status**: Go to Cloudflare Dashboard → Tunnels
- **Check logs**:
  ```bash
  docker compose logs cloudflared
  ```

### ESP devices can't write to InfluxDB

After changing InfluxDB secrets, update ESP device credentials:

1. Edit `include/secrets.h` on your ESP project
2. Update `INFLUXDB_TOKEN` to match `.env`
3. Update `INFLUXDB_ORG` to match `INFLUXDB_ORG_ID`
4. Reflash all devices:
   ```bash
   cd ~/PlatformIO/esp12f_ds18b20_temp_sensor
   ./scripts/deploy_all_devices.sh
   ```

## Rotating Credentials

### If InfluxDB Token Compromised:

1. **Revoke old token** in InfluxDB UI:
   - Data → API Tokens → Find token → Delete

2. **Generate new token**:
   - Data → API Tokens → Generate API Token → All Access Token

3. **Update `.env`**:
   ```bash
   vim ~/docker/.env
   # Update INFLUXDB_ADMIN_TOKEN
   ```

4. **Restart services**:
   ```bash
   docker compose down
   docker compose up -d
   ```

5. **Update ESP devices** (see above)

### If Cloudflare Token Compromised:

1. **Revoke tunnel** in Cloudflare Dashboard
2. **Create new tunnel** and get new token
3. **Update `.env`**:
   ```bash
   vim ~/docker/.env
   # Update CLOUDFLARE_TUNNEL_TOKEN
   ```
4. **Restart cloudflared**:
   ```bash
   docker compose restart cloudflared
   ```

## Backup & Recovery

### Backup Secrets

```bash
# Encrypt and backup .env to secure location
tar czf secrets-backup-$(date +%Y%m%d).tar.gz .env
# Store on encrypted USB drive or secure cloud storage
```

### Restore Secrets

```bash
# Extract backup
tar xzf secrets-backup-YYYYMMDD.tar.gz
# Validate
./scripts/validate_secrets.sh
# Deploy
docker compose up -d
```

## Environment-Specific Configurations

### Development Setup

Use separate values for testing:

```bash
INFLUXDB_BUCKET=sensor_data_dev
INFLUXDB_ORG_ID=dev_org_123456789
```

### Production Setup

Use production values:

```bash
INFLUXDB_BUCKET=sensor_data
INFLUXDB_ORG_ID=abc123def4567890
```

## Getting Help

If you're stuck:

1. Run validation script: `./scripts/validate_secrets.sh`
2. Check logs: `docker compose logs -f`
3. Verify services: `docker compose ps`
4. Check InfluxDB UI: `http://192.168.0.167:8086`

## Related Documentation

- [Main README](../README.md) - General setup and usage
- [ESP Secrets Setup](https://github.com/aachtenberg/esp12f_ds18b20_temp_sensor/blob/main/docs/guides/SECRETS_SETUP.md) - ESP device secrets
- [Docker Compose Reference](https://docs.docker.com/compose/environment-variables/) - Environment variables in Docker

