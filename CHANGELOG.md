# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- **AI Monitor** - Autonomous self-healing and triage system
  - Monitors container health via Docker socket and Prometheus
  - Auto-restarts unhealthy containers (telegraf, prometheus) with guardrails
  - 10-minute cooldown per container prevents restart loops
  - Max 2 restarts per monitoring cycle
  - Claude API integration for LLM-powered triage (human-readable issue explanations)
  - Fallback to local Ollama (raspberrypi2) for triage
  - Prometheus metrics endpoint (`:8000/metrics`) for observability
  - Grafana Cloud dashboard: "AI Monitor - Self-Heal Metrics"
  - Structured logging with JSON output
  - Documentation: `docs/AI_MONITOR.md`

- **Ollama service** on secondary Raspberry Pi (port 11434)
  - Model: qwen2.5:1.5b
  - Used for fallback LLM triage (Claude preferred due to speed)

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
  - Added Ollama URL and model settings
  - Cleaned up duplicate `AI_MONITOR_ALLOWED_CONTAINERS` entries

### Fixed
- **ESP temperature sensor data flow restored**
  - Root cause: mosquitto-broker restart at 2025-12-16 17:14 EST broke ESP connections
  - ESP devices connected but not auto-reconnecting after broker restart
  - Solution: Manual mosquitto restart + protection from future auto-restarts
  - Verification: Temperature data flowing to InfluxDB3 and Grafana Cloud

- **Telegraf MQTT subscription reliability**
  - Ensured clean reconnection after mosquitto restarts
  - Verified all MQTT consumers reconnect properly

### Security
- Added `.env` to `.gitignore` (pre-commit hooks block commits)
- Claude API key stored in local `.env` only (not committed)

### Technical Debt
- Local Ollama (qwen2.5:1.5b) consistently times out (>90s) on triage prompts
  - Claude API is faster (~11s) and more reliable
  - Ollama kept for testing/fallback only

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
