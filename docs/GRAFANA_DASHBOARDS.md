# Grafana Dashboard Management

This guide explains how to export, import, and version control Grafana dashboards using the provided automation script.

## Overview

The  script automatically exports all Grafana dashboards to JSON files, making it easy to:
- 📦 **Back up** dashboard configurations
- 🔄 **Share** dashboards between Grafana instances
- 📝 **Version control** dashboard changes in Git
- 🚀 **Automate** dashboard deployment

## Quick Start

### Export All Dashboards



The script will:
1. Connect to Grafana (localhost:3000)
2. Fetch all dashboards via API
3. Export each dashboard as JSON to 
4. Add metadata (export timestamp, version, etc.)

### Commit to Git

On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

## Authentication Methods

The export script supports two authentication methods:

### 1. API Key Authentication (Recommended)

Using an API key is more secure and doesn't expose your password:



The script automatically uses the  from your  file.

**To generate a new API key:**
1. Log in to Grafana (http://localhost:3000)
2. Go to Administration → Service Accounts
3. Click "Add service account"
4. Name: "dashboard-export", Role: "Viewer"
5. Click "Add service account token"
6. Copy the token and add to :
   

### 2. Password Authentication (Fallback)

If no API key is configured, provide password via environment variable:



Or set  and  in :


## Exported Dashboard Format

Each exported dashboard includes:



### File Naming Convention

Dashboards are saved with sanitized filenames:
- **Dashboard**: "Temperatures Rue Romain"
- **Filename**: 

Special characters are replaced with underscores.

## Importing Dashboards

### Via Grafana UI

1. Go to **Dashboards** → **Import**
2. Click **Upload JSON file**
3. Select a file from 
4. Review settings and click **Import**

### Via API (Automated)

Import all dashboards programmatically:

Importing *.json...

Or with password authentication:



## Use Cases

### 1. Regular Backups

Schedule automatic exports using cron:



### 2. Disaster Recovery

If Grafana data is lost, restore dashboards from Git:



### 3. Sharing Dashboards

Share your dashboards with others:

1. Export dashboards to JSON
2. Commit to Git and push
3. Others clone the repo and import the JSON files

### 4. Multi-Environment Deployment

Use the same dashboards across dev/staging/prod:



## Script Options

The export script accepts several environment variables:



## Troubleshooting

### Connection Refused

**Error**: 

**Solution**: Ensure Grafana is running:


### Authentication Failed (401)

**Error**: 

**Solutions**:
1. Verify API key is valid:
   
2. Check Grafana credentials:
   
3. Reset Grafana password:
   

### No Dashboards Found

**Error**: 

**Solution**: Ensure dashboards exist in Grafana:
1. Log in to Grafana (http://localhost:3000)
2. Go to **Dashboards** → **Browse**
3. Create or import some dashboards first

### Permission Denied

**Error**: 

**Solution**: Create output directory:


### jq Command Not Found

**Error**: 

**Solution**: Install jq:
Hit:1 https://repos.influxdata.com/ubuntu jammy InRelease
Hit:3 http://archive.ubuntu.com/ubuntu jammy InRelease
Get:4 http://security.ubuntu.com/ubuntu jammy-security InRelease [129 kB]
Hit:2 https://prod-cdn.packages.k8s.io/repositories/isv:/kubernetes:/core:/stable:/v1.28/deb  InRelease
Get:5 http://archive.ubuntu.com/ubuntu jammy-updates InRelease [128 kB]
Get:6 http://archive.ubuntu.com/ubuntu jammy-backports InRelease [127 kB]
Get:7 http://archive.ubuntu.com/ubuntu jammy-updates/main amd64 Packages [3080 kB]
Fetched 3465 kB in 2s (2170 kB/s)
Reading package lists...
Reading package lists...
Building dependency tree...
Reading state information...
jq is already the newest version (1.6-2.1ubuntu3.1).
0 upgraded, 0 newly installed, 0 to remove and 40 not upgraded.

## Dashboard JSON Structure

Understanding the exported JSON format helps with manual editing:



### Key Fields

- **uid**: Unique identifier for the dashboard (must be unique)
- **title**: Display name in Grafana
- **panels**: Array of visualization panels
- **templating**: Dashboard variables (e.g., device selector)
- **version**: Increments with each save

### Editing Dashboards

You can manually edit exported JSON files:

1. Export dashboard to JSON
2. Edit the file (change title, panels, etc.)
3. Change the  to create a new dashboard
4. Import the modified JSON

**Example**: Clone a dashboard with different title:


## Best Practices

### 1. Regular Exports

Export dashboards after significant changes:


### 2. Meaningful Commit Messages

Use semantic commit messages:
- 
- 
- 
- 

### 3. Review Changes Before Commit

Check what changed:


### 4. Keep API Key Secure

- Store API key in  (gitignored)
- Use Viewer role (read-only)
- Rotate keys periodically
- Never commit API keys to Git

### 5. Test Imports

After exporting, test that dashboards can be imported:
1. Delete a dashboard in Grafana
2. Re-import from JSON file
3. Verify all panels render correctly

## Related Documentation

- [Secrets Setup](SECRETS_SETUP.md) - Configure Grafana API key
- [Main README](../README.md) - Full infrastructure documentation
- [Grafana API Docs](https://grafana.com/docs/grafana/latest/developers/http_api/) - Official Grafana API reference

## Support

- **Script Location**: 
- **Output Directory**: 
- **Issues**: Report in GitHub repository issues

---

**Last Updated**: November 2025
