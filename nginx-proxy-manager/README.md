# Nginx Proxy Manager Configuration

This directory contains the Nginx Proxy Manager configuration files that are mounted into the container. You can now manage proxy configurations via files instead of only using the UI.

## Directory Structure

```
nginx-proxy-manager/
├── data/
│   ├── database.sqlite          # NPM database (UI-managed proxy hosts)
│   ├── nginx/
│   │   ├── proxy_host/          # Proxy host configurations
│   │   │   ├── 1.conf          # Individual proxy configs
│   │   │   ├── 2.conf
│   │   │   └── ...
│   │   ├── custom/              # Custom nginx includes
│   │   ├── dead_host/           # Dead/disabled hosts
│   │   ├── redirection_host/    # Redirect rules
│   │   └── stream/              # TCP/UDP stream configs
│   ├── logs/                    # Access and error logs
│   ├── letsencrypt-acme-challenge/
│   └── custom_ssl/              # Custom SSL certificates
└── letsencrypt/                 # Let's Encrypt certificates
```

## Managing Configurations

### Method 1: Via Web UI (Recommended for beginners)
- Access: http://localhost:81
- Changes made in UI automatically update files in `data/nginx/`
- Container reloads nginx automatically

### Method 2: Direct File Editing (Advanced)
1. Edit config files in `data/nginx/proxy_host/*.conf`
2. Reload nginx: `docker exec nginx-proxy-manager nginx -s reload`
3. Or restart container: `docker compose restart nginx-proxy-manager`

## Example: Adding a New Proxy Host Manually

Create a new file `data/nginx/proxy_host/custom.conf`:

```nginx
server {
  set $forward_scheme http;
  set $server         "your-internal-ip";
  set $port           80;

  listen 80;
  listen [::]:80;

  server_name example.xgrunt.com;
  http2 off;

  # Block Exploits
  include conf.d/include/block-exploits.conf;

  access_log /data/logs/proxy-host-custom_access.log proxy;
  error_log /data/logs/proxy-host-custom_error.log warn;

  location / {
    # Proxy!
    include conf.d/include/proxy.conf;
  }

  # Custom
  include /data/nginx/custom/server_proxy[.]conf;
}
```

Then reload: `docker exec nginx-proxy-manager nginx -s reload`

## Current Proxy Hosts

Check `data/nginx/proxy_host/` for all configured hosts:

```bash
ls -l data/nginx/proxy_host/
```

View a specific config:

```bash
cat data/nginx/proxy_host/1.conf
```

## Backup

The entire configuration is version-controlled with this repository:
- `data/nginx/` - All nginx configs
- `database.sqlite` - NPM database (tracked changes)
- `letsencrypt/` - SSL certificates (gitignored for security)

## Troubleshooting

### Check nginx syntax
```bash
docker exec nginx-proxy-manager nginx -t
```

### View nginx logs
```bash
docker exec nginx-proxy-manager tail -f /data/logs/proxy-host-*_error.log
```

### Reload after manual changes
```bash
docker exec nginx-proxy-manager nginx -s reload
```

### Full restart
```bash
docker compose restart nginx-proxy-manager
```

## Notes

- The UI and file-based configs work together - changes in one reflect in the other
- Manually created configs won't appear in the UI but will work
- Database file (`database.sqlite`) contains UI metadata
- SSL certificates are auto-renewed via Let's Encrypt
