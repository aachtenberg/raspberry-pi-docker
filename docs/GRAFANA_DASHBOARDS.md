# Grafana Dashboard Management

This guide explains how to export, import, and version control Grafana dashboards using the provided automation script.

## Overview

The export_grafana_dashboards.sh script automatically exports all Grafana dashboards to JSON files, making it easy to:
- 📦 **Back up** dashboard configurations
- 🔄 **Share** dashboards between Grafana instances
- 📝 **Version control** dashboard changes in Git
- 🚀 **Automate** dashboard deployment

## Quick Start

### Export All Dashboards

```bash
cd ~/docker
./scripts/export_grafana_dashboards.sh
```

The script will:
1. Connect to Grafana (localhost:3000)
2. Fetch all dashboards via API
3. Export each dashboard as JSON to grafana/dashboards/
4. Add metadata (export timestamp, version, etc.)

### Commit to Git

```bash
git add grafana/dashboards/
git commit -m "chore: export Grafana dashboards"
git push
```

## Authentication Methods

The export script supports two authentication methods:

### 1. API Key Authentication (Recommended)

Using an API key is more secure and does not expose your password:

```bash
cd ~/docker
./scripts/export_grafana_dashboards.sh
```

The script automatically uses the GRAFANA_API_KEY from your .env file.

### 2. Password Authentication (Fallback)

If no API key is configured, provide password via environment variable:

```bash
GRAFANA_PASSWORD=your_password ./scripts/export_grafana_dashboards.sh
```

## Exported Dashboard Format

Each exported dashboard includes metadata and full configuration.

File naming convention:
- Dashboard: "Temperatures Rue Romain"
- Filename: temperatures_rue_romain.json

## Importing Dashboards

### Via Grafana UI

1. Go to Dashboards → Import
2. Click Upload JSON file
3. Select a file from grafana/dashboards/
4. Review settings and click Import

### Via API (Automated)

Import all dashboards programmatically:

```bash
cd ~/docker/grafana/dashboards

for file in *.json; do
  echo "Importing $file..."
  curl -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $GRAFANA_API_KEY" \
    -d @"$file" \
    http://localhost:3000/api/dashboards/db
done
```

## Use Cases

1. **Regular Backups** - Export dashboards periodically
2. **Disaster Recovery** - Restore dashboards from Git
3. **Sharing Dashboards** - Share configurations with team
4. **Multi-Environment** - Deploy same dashboards across environments

## Troubleshooting

### Connection Refused

Ensure Grafana is running:
```bash
sudo docker compose ps grafana
```

### Authentication Failed (401)

Verify API key or reset password:
```bash
sudo docker exec grafana grafana-cli admin reset-admin-password newpassword
```

### jq Command Not Found

Install jq:
```bash
sudo apt-get update && sudo apt-get install -y jq
```

## Best Practices

1. Export dashboards after significant changes
2. Use meaningful commit messages
3. Review changes before committing
4. Keep API keys secure in .env
5. Test imports after exporting

## Related Documentation

- [Secrets Setup](SECRETS_SETUP.md) - Configure Grafana API key
- [Main README](../README.md) - Full infrastructure documentation

---

**Last Updated**: November 2025
