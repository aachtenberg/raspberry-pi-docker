# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **Mosquitto MQTT Broker Monitoring**
  - Enabled `$SYS/#` topic publishing (sys_interval 10 seconds)
  - Telegraf input for mosquitto $SYS metrics collection
  - Grafana Cloud dashboard: "Mosquitto MQTT Broker" (uid: mosquitto-broker)
  - Tracks: connected clients, message rates, network throughput, connection load, queue stats, memory usage, uptime
  - Production-grade tuning: persistence, queue limits, connection management, comprehensive logging

- **Mosquitto Broker Configuration Enhancements**
  - Comprehensive production tuning for ESP sensors and surveillance
  - Queue management: max_queued_messages (1000), max_queued_bytes (10MB), max_inflight_messages (20)
  - Message size limit: 10MB (sufficient for camera snapshots)
  - Connection limits: max_connections (100), max_keepalive (0 = client-specified)
  - Performance tuning: retry_interval (20s), persistent_client_expiration (5m)
  - Enhanced logging: timestamps, connection messages, all log levels
  - autosave_interval (300s) for persistence management

- **Camera Dashboard PostgreSQL Backup**
  - Updated Pi 2 backup script to include `camera-dashboard_postgres-data` volume
  - Backup metrics exported to Prometheus via node-exporter textfile collector
  - Infrastructure Health dashboard updated to query both Pi 1 and Pi 2 backup metrics

- **Grafana Cloud Dashboard Updates**
  - Fixed datasource UID in all dashboards (cf6z7j8gxto1sc)
  - Infrastructure Health dashboard: unified backup status queries for both Pis
  - Romain Temperature Data: added battery monitoring panels for Spa/Sauna sensors
  - PostgreSQL Monitoring: comprehensive database health dashboard (12 panels)

- **Raspberry Pi 2 Telegraf Enhancements**
  - Added Prometheus input to scrape node-exporter metrics (including backup status)
  - Combined metrics output on port 9273 (docker stats + node-exporter + backup metrics)
  - Enables centralized monitoring of Pi 2 infrastructure via Pi 1 Prometheus

- **ESP Sensor Hub Status Monitoring**
  - Added `esp-sensor-hub/+/status` MQTT topic support in Telegraf
  - New InfluxDB 3 measurement: `esp_status` (battery, wifi, uptime, heap, health)
  - Tracks: battery_voltage, battery_percent, wifi_rssi, uptime_seconds, free_heap, sensor_healthy, wifi_connected, wifi_reconnects, sensor_read_failures
  - Battery monitoring panels added to Romain Temperature dashboard

### Changed
- **Prometheus Configuration**
  - Updated Pi 2 target IP from 192.168.0.147 to 192.168.0.146 (telegraf-pi2, postgres)
  - Added mosquitto-exporter scrape target (port 9234)
  - Removed obsolete ai-monitor scrape job

- **Docker Compose Updates**
  - Removed orphaned mosquitto-exporter service (switched to Telegraf-based collection)

- **Nginx Proxy Manager (Camera Dashboard)**
  - Simplified proxy configurations for `/api`, `/streams`, and `/` routes
  - Removed `$server` and `$port` variables in favor of direct proxy_pass URLs

### Fixed
- **Prometheus Target Connectivity**
  - Restored Prometheus to bridge network (was incorrectly on host mode)
  - Fixed DNS resolution for influxdb3-core and other services

- **Mosquitto File Permissions**
  - mosquitto.conf ownership issue resolved (UID 1883 conflict)
  - Added `sudo chown aachten:aachten` fix to operations guide

### Removed
- **Local Grafana container** - Deprecated in favor of Grafana Cloud
  - Removed grafana service from docker-compose.yml
  - Removed grafana-data volume
  - All visualization now via Grafana Cloud (pdc-agent)
  - Updated all documentation to remove grafana references

- **InfluxDB 3 Explorer UI** - Removed unused web interface
  - Removed influxdb3-explorer service from docker-compose.yml
  - Removed influxdb3-explorer-db volume
  - Removed Explorer UI references from documentation (port 8888)
  - InfluxDB 3 API access via CLI and Grafana Cloud sufficient for operations
- **Local Ollama fallback/service (raspberrypi2)** - Removed due to slow (>90s) responses and frequent timeouts
- **Autoheal (willfarrell) on raspberrypi2** - Removed; only node-exporter and telegraf remain

### Added
- **AI Monitor** - Autonomous self-healing and triage system
  - Monitors container health via Docker socket and Prometheus
  - Auto-restarts unhealthy containers (telegraf, prometheus) with guardrails
  - 10-minute cooldown per container prevents restart loops
  - Max 2 restarts per monitoring cycle
  - Claude API integration for LLM-powered triage (human-readable issue explanations)
  - Prometheus metrics endpoint (`:8000/metrics`) for observability
  - Grafana Cloud dashboard: "AI Monitor - Self-Heal Metrics"
  - Structured logging with JSON output
  - Documentation: `docs/AI_MONITOR.md`

### Changed
- **Telegraf configuration cleanup**
  - Removed unused Home Assistant MQTT input (`homeassistant/sensor/+/state`)
  - Removed unused Home Assistant InfluxDB output
  - Kept only active inputs: `esp-sensor-hub/+/temperature`, `surveillance/#`
  - Clearer configuration comments
  
- **AI Monitor allowlist protection**
  - Removed `mosquitto-broker` from auto-restart allowlist
  - Reason: ESP devices in field cannot auto-reconnect after broker restart
  - Protected services: mosquitto-broker, influxdb3-core, nginx-proxy-manager, homeassistant

- **Prometheus scrape configuration**
  - Added ai-monitor metrics endpoint (`:8000`) with labels `instance=raspberry-pi, service=ai-monitor`

- **Environment variables**
  - Added AI monitor configuration section to `.env.example`
  - Added Claude API credentials (`CLAUDE_API_KEY`, `CLAUDE_MODEL`)
  - Cleaned up duplicate `AI_MONITOR_ALLOWED_CONTAINERS` entries

### Fixed
- **ESP temperature sensor data flow restored**
  - Root cause: mosquitto-broker restart at 2025-12-16 17:14 EST broke ESP connections
  - ESP devices connected but not auto-reconnecting after broker restart

- **pdc-agent crash loop after power outage**
  - Root cause: grafana/pdc-agent:latest (v0.0.50) has broken OpenSSL libraries on ARM64
  - Symptom: `invalid SSH version: failed to run ssh -V command: exit status 127`
  - Library error: `Error relocating /usr/lib/libcrypto.so.3: symbol not found`
  - Solution: Pinned to grafana/pdc-agent:0.0.48 with working OpenSSL 3.5.4
  - Note: Issue occurred after power outage because Docker pulled broken `:latest` image
  - Documented in docker-compose.yml with version pin comment
  - Solution: Manual mosquitto restart + protection from future auto-restarts
  - Verification: Temperature data flowing to InfluxDB3 and Grafana Cloud

- **Telegraf MQTT subscription reliability**
  - Ensured clean reconnection after mosquitto restarts
  - Verified all MQTT consumers reconnect properly

### Security
- Added `.env` to `.gitignore` (pre-commit hooks block commits)
- Claude API key stored in local `.env` only (not committed)

### Technical Debt
None noted.

## [Previous] - Pre-AI Monitor

### Existing Features
- Docker Compose stack with 13 containers across 2 Raspberry Pis
- Telegraf → Prometheus → Grafana Cloud monitoring pipeline
- InfluxDB 3 Core for time-series data (ESP sensors, surveillance cameras)
- MQTT broker (Mosquitto) for ESP device communication
- Nginx Proxy Manager for reverse proxy and SSL
- Cloudflare Tunnel for remote access
- Home Assistant integration
- Automated daily backups to NAS (systemd timers)
- Prometheus for metrics collection
- Node Exporter, cAdvisor for system metrics
- PDC Agent (Private Data Center) for Grafana Cloud integration
