# AI Monitor - Self-Healing & Triage System

## Overview

The AI monitor is an autonomous agent that monitors Docker container health and Prometheus metrics, providing:
- **Self-healing**: Automatic restart of unhealthy containers with guardrails
- **LLM triage**: Human-readable explanations of infrastructure issues via Claude API or local Ollama
- **Prometheus metrics**: Observability into the monitoring system itself

## Architecture

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────┐
│   Prometheus    │─────▶│  AI Monitor  │─────▶│   Docker    │
│  (metrics API)  │      │   (Python)   │      │  (restarts) │
└─────────────────┘      └──────────────┘      └─────────────┘
                                │
                                ├─────▶ Claude API (triage)
                                │
                                └─────▶ Prometheus metrics (:8000)
```

## Features

### Self-Heal
- Monitors container health via Docker socket and Prometheus `up==0` queries
- Automatically restarts containers in allowlist if unhealthy or exited
- **Guardrails**:
  - 10-minute cooldown per container (prevents restart loops)
  - Max 2 restarts per monitoring cycle
  - Only restarts explicitly allowlisted services

**Current allowlist**: `telegraf`, `prometheus`  
**Protected** (not auto-restarted): `mosquitto-broker` (ESP devices can't auto-reconnect)

### LLM Triage
- Gathers snapshot of Prometheus down targets, Docker health, and resource usage
- Sends to Claude API (or Ollama fallback) for analysis
- Returns structured JSON with:
  - `severity`: low/medium/high
  - `confidence`: 0.0-1.0
  - `summary`: Human-readable explanation
  - `recommended_actions`: Specific remediation steps

### Observability
Exposes Prometheus metrics on port 8000:
- `ai_monitor_restarts_total{container="..."}` - Total restarts per container
- `ai_monitor_triage_calls_total{backend="claude|ollama",status="success|error|timeout"}` - LLM triage outcomes
- `ai_monitor_healthy_containers` - Current healthy container count
- `ai_monitor_unhealthy_containers` - Current unhealthy container count
- `ai_monitor_last_run_timestamp` - Last monitoring cycle timestamp

## Configuration

### Environment Variables (.env)

```bash
# AI Monitor Settings
AI_MONITOR_PROMETHEUS_URL=http://prometheus:9090
AI_MONITOR_INTERVAL_SECONDS=60
AI_MONITOR_EXECUTE=true  # Set to false for dry-run mode

# Self-Heal Settings
AI_MONITOR_SELF_HEAL_DOCKER_HEALTH=true
AI_MONITOR_RESTART_UNHEALTHY=true
AI_MONITOR_RESTART_EXITED=true
AI_MONITOR_RESTART_COOLDOWN_SECONDS=600
AI_MONITOR_MAX_RESTARTS_PER_RUN=2

# Allowlist (comma-separated, no spaces)
# WARNING: Do NOT include mosquitto-broker (ESP devices can't reconnect)
AI_MONITOR_ALLOWED_CONTAINERS=telegraf,prometheus

# LLM Backend Selection (priority: Claude > Gemini > Ollama)

# Claude API (recommended - fast, reliable, $0.25/1M tokens)
CLAUDE_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-3-haiku-20240307

# Gemini API (cheaper alternative - $0.075/1M tokens, 70% less)
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.0-flash-exp

# Ollama (fallback, runs on secondary Pi)
AI_MONITOR_OLLAMA_URL=http://<SECONDARY_PI_IP>:11434
AI_MONITOR_OLLAMA_MODEL=qwen2.5:1.5b
AI_MONITOR_OLLAMA_TIMEOUT_SECONDS=90
```

### Adding/Removing Services from Allowlist

**To allow auto-restart of a service:**
```bash
# Edit .env
AI_MONITOR_ALLOWED_CONTAINERS=telegraf,prometheus,new-service

# Restart ai-monitor
docker compose up -d --force-recreate ai-monitor
```

**⚠️ Services to NEVER auto-restart:**
- `mosquitto-broker` - ESP devices in field can't auto-reconnect
- `influxdb3-core` - Data integrity risk
- `nginx-proxy-manager` - Breaks active connections
- `homeassistant` - Complex state management

## Usage

### Check Status
```bash
# View ai-monitor logs
docker compose logs -f ai-monitor

# Check metrics
curl http://localhost:8000/metrics | grep ai_monitor

# Test triage (dry-run mode)
docker compose exec -T -e AI_MONITOR_EXECUTE=false ai-monitor \
  python -c 'from monitor import AiMonitor; AiMonitor().run_once()'
```

### Trigger Manual Triage
```bash
# Kill a container to test
docker kill telegraf

# Wait 60s for monitoring cycle, then check logs
docker compose logs ai-monitor | grep "AI triage"
```

### View Grafana Dashboard
Dashboard: **AI Monitor - Self-Heal Metrics**  
URL: https://your-grafana-cloud/d/ai-monitor-metrics/

Panels:
- Health status gauge (healthy vs unhealthy containers)
- Total restarts by container
- Restart rate over time
- LLM triage call outcomes (by backend: claude/ollama)
- Health timeline

## Troubleshooting

### Self-heal not triggering
1. Check allowlist: `docker compose logs ai-monitor | grep allowed_containers`
2. Verify execute mode: `AI_MONITOR_EXECUTE=true` in `.env`
3. Check cooldown: Container may be in 10-min cooldown period
4. View container health: `docker compose ps`

### Claude triage failing with 404
- Check model access: Only `claude-3-haiku-20240307` available on some API tiers
- Verify API key: `docker compose exec ai-monitor env | grep CLAUDE_API_KEY`
- Test manually: `docker compose exec ai-monitor python -c "import anthropic; print(anthropic.Anthropic(api_key='...').models.list())"`

### Ollama triage timeouts
- Local Ollama (qwen2.5:1.5b) consistently times out (>90s) on complex prompts
- **Solution**: Use Claude API instead (faster, ~11s response time)
- Ollama runs on secondary Pi (port 11434) for testing only

### Metrics not showing in Prometheus
1. Check scrape config: `prometheus/prometheus.yml` should have `ai-monitor:8000` target
2. Verify metrics endpoint: `curl http://localhost:8000/metrics`
3. Check Prometheus targets: http://localhost:9090/targets

## Design Decisions

### Why not restart mosquitto-broker?
**Problem**: When mosquitto restarts, all ESP sensor devices (Main Cottage, Spa, Pump House, Small Garage) disconnect and require manual power cycle to reconnect. These devices are deployed in the field with no easy physical access.

**Solution**: Remove mosquitto from allowlist. If broker fails, Claude will alert via triage, but won't auto-restart. Manual intervention required.

### Why Cloud LLMs over local Ollama?
- **Speed**: Claude ~11s, Gemini ~3-5s vs Ollama qwen2.5:1.5b >90s (timeout)
- **Reliability**: Cloud LLMs 100% success rate vs Ollama frequent timeouts
- **Cost**: Negligible for this use case - ~$0.15-0.50/month
- **Quality**: Better structured output, higher confidence scores
- **Backend priority**: Claude (if key present) → Gemini → Ollama

### Why 10-minute cooldown?
Prevents restart loops for services with persistent issues (e.g., config errors, resource exhaustion). Gives time for alerts and manual investigation.

## Integration with Existing Stack

- **Prometheus**: Scrapes ai-monitor metrics endpoint, provides data source for queries
- **Grafana Cloud**: Visualizes ai-monitor metrics and container health
- **Docker**: ai-monitor mounts `/var/run/docker.sock` for health checks and restarts
- **Telegraf**: Allowlisted service, gets auto-restarted if fails
- **Ollama** (optional): Runs on raspberrypi2, provides fallback LLM triage

## Future Enhancements

1. **Webhook alerts**: Send triage results to Slack/Discord/PagerDuty
2. **Multi-host monitoring**: Extend to monitor both raspberrypi and raspberrypi2
3. **Smarter restart logic**: Check service dependencies before restart
4. **Trend analysis**: Use historical data to predict failures
5. **Auto-rollback**: Revert container to previous version if restart fails repeatedly

## References

- Code: `/home/aachten/docker/ai-monitor/monitor.py`
- Prometheus config: `/home/aachten/docker/prometheus/prometheus.yml`
- Grafana dashboard: `/home/aachten/docker/grafana/dashboards-cloud/ai_monitor_metrics.json`
- Claude API docs: https://docs.anthropic.com/claude/reference/
