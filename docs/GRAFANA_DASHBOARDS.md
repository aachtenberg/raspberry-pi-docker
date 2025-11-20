# Grafana Dashboard Management

This guide explains how to export, import, and version control Grafana dashboards using the provided automation scripts.

## Overview

Grafana dashboard management scripts make it easy to:
- 📦 **Back up** dashboard configurations
- 🔄 **Share** dashboards between Grafana instances
- 📝 **Version control** dashboard changes in Git
- 🚀 **Automate** dashboard deployment
- 💾 **Restore** dashboards from JSON files

## Quick Start

### Export All Dashboards

```bash
cd ~/docker
./scripts/export_grafana_dashboards.sh
```

Dashboards are saved to `grafana/dashboards/*.json`.

### Import All Dashboards

```bash
cd ~/docker
./scripts/import_grafana_dashboards.sh
```

Or import a specific dashboard:

```bash
./scripts/import_grafana_dashboards.sh temperatures_rue_romain.json
```

### Commit to Git

```bash
git add grafana/dashboards/
git commit -m "chore: export Grafana dashboards"
git push
```

## Authentication

Both scripts support multiple authentication methods.

### API Keys (Recommended)

Using API keys is more secure and doesn't expose passwords.

**Two types of keys:**

1. **Export Key** (Viewer role - read-only):
   ```bash
   GRAFANA_API_KEY=glsa_...
   ```

2. **Import Key** (Editor role - write access):
   ```bash
   GRAFANA_ADMIN_API_KEY=glsa_...
   ```

#### Creating API Keys

1. Log in to Grafana: http://localhost:3000
2. Go to **Administration** → **Service Accounts**
3. Click **Add service account**
4. Create two accounts:
   - Name: "dashboard-export", Role: "Viewer"
   - Name: "dashboard-admin", Role: "Editor"
5. For each account, click **Add service account token**
6. Copy tokens and add to `.env`:

```bash
# Read-only key for exports
GRAFANA_API_KEY=glsa_EXAMPLE_KEY_FOR_EXPORT_READONLY_xxxxxxxxxxxx

# Write key for imports
GRAFANA_ADMIN_API_KEY=glsa_EXAMPLE_KEY_FOR_IMPORT_EDITOR_xxxxxxxxxxxxx
```

### Password Authentication (Fallback)

Provide password via environment variable:

```bash
GRAFANA_PASSWORD=your_password ./scripts/export_grafana_dashboards.sh
GRAFANA_PASSWORD=your_password ./scripts/import_grafana_dashboards.sh
```

Or the scripts will prompt you interactively.

## Exporting Dashboards

### Export All

```bash
cd ~/docker
./scripts/export_grafana_dashboards.sh
```

**Output:**
```
📥 Grafana Dashboard Export Tool
==================================

📁 Output directory: ./grafana/dashboards
🔑 Authentication: API Key

🔌 Testing Grafana connection...
✅ Connected to Grafana

📊 Fetching dashboard list...
   Found 3 dashboards

   📊 Docker Containers - Raspberry Pi
      ✅ docker_containers_-_raspberry_pi.json
   📊 Raspberry Pi & Docker Monitoring
      ✅ raspberry_pi___docker_monitoring.json
   📊 Temperatures Rue Romain
      ✅ temperatures_rue_romain.json

==================================
✅ Export complete!
   Exported: 3 dashboards
   Location: ./grafana/dashboards
```

### Export Options

```bash
# Custom Grafana URL
GRAFANA_URL=http://192.168.1.100:3000 ./scripts/export_grafana_dashboards.sh

# Custom output directory
OUTPUT_DIR=/tmp/dashboards ./scripts/export_grafana_dashboards.sh

# With password
GRAFANA_PASSWORD=admin ./scripts/export_grafana_dashboards.sh
```

## Importing Dashboards

### Import All

```bash
cd ~/docker
./scripts/import_grafana_dashboards.sh
```

**Output:**
```
📥 Grafana Dashboard Import Tool
==================================

📁 Dashboard directory: ./grafana/dashboards
   Found: 3 dashboard(s)

🔑 Authentication: Admin API Key

🔌 Testing Grafana connection...
✅ Connected to Grafana

📥 Importing all dashboards...

   📊 Docker Containers - Raspberry Pi
      ✅ docker_containers_-_raspberry_pi.json
         URL: http://localhost:3000/d/1e9281de.../docker-containers-raspberry-pi
   📊 Raspberry Pi & Docker Monitoring
      ✅ raspberry_pi___docker_monitoring.json
         URL: http://localhost:3000/d/VKtkKcAVz/raspberry-pi-and-docker-monitoring
   📊 Temperatures Rue Romain
      ✅ temperatures_rue_romain.json
         URL: http://localhost:3000/d/adk6dmr/temperatures-rue-romain

==================================
✅ Import complete!
   Imported: 3 dashboard(s)
```

### Import Specific Dashboard

```bash
# By filename
./scripts/import_grafana_dashboards.sh temperatures_rue_romain.json

# By full path
./scripts/import_grafana_dashboards.sh grafana/dashboards/temperatures_rue_romain.json
```

### Import Options

```bash
# Show help
./scripts/import_grafana_dashboards.sh --help

# Custom Grafana URL
GRAFANA_URL=http://192.168.1.100:3000 ./scripts/import_grafana_dashboards.sh

# Custom dashboard directory
DASHBOARD_DIR=/tmp/dashboards ./scripts/import_grafana_dashboards.sh

# With password
GRAFANA_PASSWORD=admin ./scripts/import_grafana_dashboards.sh
```

### Dashboard Overwrites

The import script will **overwrite** existing dashboards with the same UID. This is useful for:
- Restoring dashboards from backup
- Updating dashboards from version control
- Deploying changes across environments

**Note:** The dashboard UID determines if a dashboard is new or an update.

## Exported Dashboard Format

Each exported dashboard includes metadata:

```json
{
  "meta": {
    "exported": "2025-11-20 14:08:20",
    "title": "Temperatures Rue Romain",
    "uid": "adk6dmr",
    "folder": "General",
    "version": 17
  },
  "dashboard": {
    "title": "Temperatures Rue Romain",
    "uid": "adk6dmr",
    "panels": [/* panel configs */],
    "templating": {/* variables */},
    "annotations": {/* annotations */}
  }
}
```

### File Naming Convention

Dashboards are saved with sanitized filenames:
- **Dashboard**: "Temperatures Rue Romain"
- **Filename**: `temperatures_rue_romain.json`

Special characters and spaces are replaced with underscores.

## Use Cases

### 1. Regular Backups

Schedule automatic exports using cron:

```bash
# Add to crontab (crontab -e)
0 2 * * * cd /home/aachten/docker && ./scripts/export_grafana_dashboards.sh && git add grafana/dashboards/ && git commit -m "chore: automated dashboard backup" && git push
```

### 2. Disaster Recovery

If Grafana data is lost, restore dashboards from Git:

```bash
cd ~/docker
git pull

# Import all dashboards
./scripts/import_grafana_dashboards.sh
```

### 3. Sharing Dashboards

Share your dashboards with others or across environments:

```bash
# On source system - export
cd ~/docker
./scripts/export_grafana_dashboards.sh
git add grafana/dashboards/
git commit -m "feat: add new monitoring dashboard"
git push

# On target system - import
cd ~/docker
git pull
./scripts/import_grafana_dashboards.sh
```

### 4. Multi-Environment Deployment

Use the same dashboards across dev/staging/prod:

```bash
# Export from production
cd ~/docker-prod
./scripts/export_grafana_dashboards.sh
git push

# Import to staging
cd ~/docker-staging
git pull
./scripts/import_grafana_dashboards.sh
```

### 5. Dashboard Version Control

Track dashboard changes over time:

```bash
# Export after changes
./scripts/export_grafana_dashboards.sh

# Review changes
git diff grafana/dashboards/

# Commit with description
git add grafana/dashboards/
git commit -m "feat: add CPU temperature alert threshold"
git push
```

## Troubleshooting

### Export Issues

#### Connection Refused

**Error**: `curl: (7) Failed to connect to localhost port 3000`

**Solution**: Ensure Grafana is running:
```bash
sudo docker compose ps grafana
sudo docker compose logs grafana
```

#### Authentication Failed (401)

**Error**: `❌ Invalid response from Grafana`

**Solutions**:
1. Verify API key:
   ```bash
   grep GRAFANA_API_KEY ~/docker/.env
   ```
2. Test connection:
   ```bash
   curl -H "Authorization: Bearer $GRAFANA_API_KEY" http://localhost:3000/api/health
   ```

#### No Dashboards Found

**Error**: `Found 0 dashboards`

**Solution**: Create dashboards in Grafana first (http://localhost:3000)

### Import Issues

#### Permission Denied (403)

**Error**: `You'll need additional permissions. Permissions needed: dashboards:create, dashboards:write`

**Solution**: Use admin API key with Editor role. Create in Grafana UI under Service Accounts with Editor role, then add to `.env`:
```bash
echo "GRAFANA_ADMIN_API_KEY=glsa_..." >> .env
```

#### Invalid JSON Format

**Error**: `❌ Invalid JSON format`

**Solution**: Validate JSON file:
```bash
jq . grafana/dashboards/dashboard_name.json
```

#### Dashboard Already Exists

This is not an error - the script overwrites existing dashboards. Check output for the dashboard URL.

### General Issues

#### jq Command Not Found

**Error**: `bash: jq: command not found`

**Solution**: Install jq:
```bash
sudo apt-get update && sudo apt-get install -y jq
```

#### Permission Denied on Directory

**Error**: `Permission denied: grafana/dashboards/`

**Solution**: Create directory:
```bash
mkdir -p ~/docker/grafana/dashboards
chmod 755 ~/docker/grafana/dashboards
```

## Best Practices

### 1. Regular Exports

Export dashboards after significant changes:
```bash
./scripts/export_grafana_dashboards.sh
git add grafana/dashboards/
git commit -m "feat: add new temperature alert panel"
git push
```

### 2. Meaningful Commit Messages

Use semantic commit messages:
- `feat: add new CPU usage dashboard`
- `fix: correct temperature unit in panel`
- `chore: export dashboards for backup`

### 3. Review Changes Before Commit

Check what changed:
```bash
git diff grafana/dashboards/
```

### 4. Keep API Keys Secure

- Store keys in `.env` (gitignored)
- Use Viewer role for exports (read-only)
- Use Editor role for imports (write access)
- Rotate keys periodically
- Never commit API keys to Git

### 5. Test Imports

After exporting, verify dashboards can be imported:
1. Export dashboards
2. Delete a test dashboard in Grafana
3. Re-import from JSON file
4. Verify all panels render correctly

### 6. Separate Keys for Different Operations

Use different API keys:
- `GRAFANA_API_KEY` - Viewer role for exports
- `GRAFANA_ADMIN_API_KEY` - Editor role for imports

This follows the principle of least privilege.

## Script Reference

### export_grafana_dashboards.sh

**Purpose**: Export all Grafana dashboards to JSON files

**Usage**:
```bash
./scripts/export_grafana_dashboards.sh
```

**Environment Variables**:
- `GRAFANA_URL` - Grafana URL (default: http://localhost:3000)
- `GRAFANA_API_KEY` - API key from .env (recommended)
- `GRAFANA_USER` - Username (default: admin)
- `GRAFANA_PASSWORD` - Password (fallback)
- `OUTPUT_DIR` - Output directory (default: ./grafana/dashboards)

### import_grafana_dashboards.sh

**Purpose**: Import one or all Grafana dashboards from JSON files

**Usage**:
```bash
# Import all
./scripts/import_grafana_dashboards.sh

# Import specific
./scripts/import_grafana_dashboards.sh dashboard.json

# Show help
./scripts/import_grafana_dashboards.sh --help
```

**Environment Variables**:
- `GRAFANA_URL` - Grafana URL (default: http://localhost:3000)
- `GRAFANA_ADMIN_API_KEY` - Admin API key from .env (recommended)
- `GRAFANA_API_KEY` - Regular API key (fallback)
- `GRAFANA_USER` - Username (default: admin)
- `GRAFANA_PASSWORD` - Password (fallback)
- `DASHBOARD_DIR` - Dashboard directory (default: ./grafana/dashboards)

## Related Documentation

- [Secrets Setup](SECRETS_SETUP.md) - Configure Grafana API keys
- [Main README](../README.md) - Full infrastructure documentation
- [Grafana API Docs](https://grafana.com/docs/grafana/latest/developers/http_api/)

## Support

- **Script Location**: `/home/aachten/docker/scripts/`
- **Dashboard Directory**: `/home/aachten/docker/grafana/dashboards/`
- **Issues**: Report in GitHub repository

---

**Last Updated**: November 2025
