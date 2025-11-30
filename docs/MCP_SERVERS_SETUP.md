# MCP Servers Setup Guide

This guide explains how to configure and use Model Context Protocol (MCP) servers for enhanced AI assistance with this Docker infrastructure.

## Installed MCP Servers

### 1. Filesystem MCP Server
**Purpose**: Direct file system access for managing configs, scripts, and logs

**Capabilities**:
- Read/write configuration files
- Edit docker-compose.yml, prometheus configs, grafana settings
- Manage scripts in `/scripts/` directory
- Access logs for debugging

**Allowed Directories**:
- `/home/aachten/docker/` - Full access to project directory
- `/var/lib/docker/volumes/` - Read-only access to Docker volumes (requires sudo)

### 2. Docker MCP Server
**Purpose**: Manage Docker containers, images, and resources

**Capabilities**:
- List and inspect containers
- View container logs
- Monitor resource usage
- Manage images and volumes
- Execute commands in containers
- Network inspection

**Docker Socket**: Uses `/var/run/docker.sock` for communication

## Configuration

### VS Code Settings

Add to your VS Code `settings.json` (or configure in Copilot settings):

```json
{
  "github.copilot.chat.mcp.servers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/aachten/docker"
      ]
    },
    "docker": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-docker"
      ]
    }
  }
}
```

### Cline/Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or equivalent:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/aachten/docker"
      ]
    },
    "docker": {
      "command": "node",
      "args": [
        "/path/to/docker-mcp-server/index.js"
      ],
      "env": {
        "DOCKER_HOST": "unix:///var/run/docker.sock"
      }
    }
  }
}
```

## Prerequisites

### Node.js and npm

```bash
# Check if Node.js is installed
node --version
npm --version

# Install if needed (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Or use nvm (recommended)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
```

### Docker Socket Access

Ensure your user has Docker access:

```bash
# Add user to docker group (if not already)
sudo usermod -aG docker $USER

# Logout and login, or use:
newgrp docker

# Test Docker access
docker ps
```

## Testing MCP Servers

### Test Filesystem Server

```bash
# Test that npx can run the filesystem server
npx -y @modelcontextprotocol/server-filesystem /home/aachten/docker --help
```

### Test Docker Server

```bash
# Install Docker MCP server globally
npm install -g @modelcontextprotocol/server-docker

# Test Docker connectivity
docker info
docker ps
```

## Example Use Cases

### With Filesystem MCP Server

**Ask Copilot:**
- "Show me all services in docker-compose.yml"
- "Update the Grafana port in docker-compose.yml to 3001"
- "What's in the latest grafana backup log?"
- "Add a new scrape job to prometheus.yml for a new device"
- "Create a new backup script for InfluxDB"

### With Docker MCP Server

**Ask Copilot:**
- "List all running containers"
- "Show me the logs for the influxdb container"
- "What's the resource usage of the grafana container?"
- "Restart the prometheus container"
- "Inspect the monitoring network"
- "Check which volumes are being used"

### Combined Queries

**Ask Copilot:**
- "Check if grafana container is running, and if so, show me grafana.ini"
- "Find which containers are using the most CPU and check their configs"
- "Show logs for containers with errors and suggest config fixes"
- "List all environment variables in docker-compose for running containers"

## Troubleshooting

### Filesystem Server Issues

**Error: Permission denied**
```bash
# Check file permissions
ls -la /home/aachten/docker/

# Fix ownership if needed
sudo chown -R $USER:$USER /home/aachten/docker/
```

**Error: npx command not found**
```bash
# Install Node.js (see Prerequisites)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Docker Server Issues

**Error: Cannot connect to Docker daemon**
```bash
# Check Docker service
sudo systemctl status docker

# Start Docker if stopped
sudo systemctl start docker

# Check socket permissions
ls -la /var/run/docker.sock
```

**Error: Permission denied accessing docker.sock**
```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Or run with sudo (not recommended for MCP)
```

### MCP Server Not Loading

**Check VS Code/Copilot logs:**
1. Open Command Palette (Ctrl+Shift+P)
2. Search: "Developer: Show Logs"
3. Select "Extension Host"
4. Look for MCP-related errors

**Restart required:**
- After changing settings.json
- After installing Node.js
- After adding user to docker group

## Security Considerations

### Filesystem Server

- **Limited scope**: Only access `/home/aachten/docker/` directory
- **No system files**: Cannot access `/etc/`, `/root/`, etc.
- **User permissions**: Operates with your user's permissions

### Docker Server

- **Socket access**: Direct access to Docker daemon
- **Container control**: Can start/stop/delete containers
- **Volume access**: Can inspect but not directly modify volume data
- **Network access**: Can view network configurations

**Best practices:**
- Use MCP servers only in trusted environments
- Don't expose Docker socket over network
- Keep Node.js and MCP packages updated
- Review changes before applying to production

## Advanced Configuration

### Custom Filesystem Paths

Allow multiple directories:

```json
{
  "github.copilot.chat.mcp.servers": {
    "filesystem-docker": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/aachten/docker"]
    },
    "filesystem-homeassistant": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/aachten/homeassistant"]
    }
  }
}
```

### Docker with Remote Host

Connect to remote Docker daemon:

```json
{
  "docker-remote": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-docker"],
    "env": {
      "DOCKER_HOST": "tcp://192.168.0.167:2375"
    }
  }
}
```

**⚠️ Warning**: Remote Docker access should use TLS encryption in production.

## Monitoring MCP Usage

### Check MCP Server Logs

VS Code logs MCP server output. To debug:

```bash
# VS Code Extension Host logs
# View → Output → Select "Extension Host"

# Check for MCP initialization messages
# Look for "MCP server started" or error messages
```

### Performance Monitoring

MCP servers run as separate processes:

```bash
# Find MCP processes
ps aux | grep mcp
ps aux | grep "server-filesystem"
ps aux | grep "server-docker"

# Monitor resource usage
top -p $(pgrep -f "server-filesystem")
```

## Updates

### Update MCP Servers

```bash
# Using npx (automatic latest version)
# No action needed - npx always fetches latest with -y flag

# Or install globally and update
npm update -g @modelcontextprotocol/server-filesystem
npm update -g @modelcontextprotocol/server-docker
```

### Check Versions

```bash
# List globally installed MCP packages
npm list -g | grep modelcontextprotocol

# Check npm registry for latest versions
npm view @modelcontextprotocol/server-filesystem version
npm view @modelcontextprotocol/server-docker version
```

## Related Documentation

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Filesystem Server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
- [Docker Server](https://github.com/modelcontextprotocol/servers/tree/main/src/docker)
- [VS Code Copilot Settings](https://code.visualstudio.com/docs/copilot/copilot-settings)

## Support

For issues with:
- **MCP Servers**: [GitHub - modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers/issues)
- **This Infrastructure**: [GitHub - raspberry-pi-docker](https://github.com/aachtenberg/raspberry-pi-docker/issues)
- **VS Code Copilot**: [VS Code GitHub Copilot Documentation](https://code.visualstudio.com/docs/copilot)

---

**Last Updated**: November 21, 2025
