# Autonomous SRE: Master Plan & Architecture

**Status**: Phase 3 Complete (Proactive Monitoring + Runbook Learning)
**Last Updated**: January 14, 2026
**Branch**: `feature/agent-based-monitoring`

---

## Table of Contents

1. [Vision & Philosophy](#vision--philosophy)
2. [Architecture Overview](#architecture-overview)
3. [OODA Loop Design](#ooda-loop-design)
4. [Knowledge Base & Learning](#knowledge-base--learning)
5. [Verification Loop](#verification-loop)
6. [Multi-Agent System](#multi-agent-system)
7. [Phase Roadmap](#phase-roadmap)
8. [Current Implementation Status](#current-implementation-status)
9. [Configuration Reference](#configuration-reference)
10. [Tool Catalog](#tool-catalog)
11. [Next Steps](#next-steps)

---

## Vision & Philosophy

### Core Principles

**From Rule-Based to Autonomous Intelligence**:
- ❌ **Old**: Hard-coded patterns → Alert → Human investigates → Manual remediation
- ✅ **New**: LLM observes metrics → Tool-based investigation → Autonomous remediation → Verification → Learning

**Key Tenets**:
1. **Tool-Based Discovery**: No pre-defined patterns; agent uses observation tools to discover issues
2. **Closed-Loop Verification**: Every action is verified; outcomes recorded for learning
3. **Persistent Memory**: Historical incidents inform future investigations (RAG-style similarity search)
4. **Confidence-Based Execution**: Historical success rates determine autonomous vs human-approval thresholds
5. **Multi-Agent Coordination**: Specialized agents for different operational domains
6. **Continuous Learning**: Every investigation improves the knowledge base

### Motivation

**The Problem**:
- InfluxDB authentication errors weren't detected because container was "healthy"
- Pattern-based monitoring misses new/unexpected failure modes
- Agents need to figure out issues dynamically, not follow rigid rules

**The Solution**:
- Metric-based triggers (scrape quality degraded, targets down, restarts)
- LLM investigates using tools (logs, Prometheus queries, Docker inspect)
- Learns from outcomes to improve over time

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AUTONOMOUS SRE SYSTEM                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐     │
│  │   Observe    │──────▶│   Orient     │──────▶│   Decide     │     │
│  │              │      │              │      │              │     │
│  │ Metrics      │      │ Knowledge    │      │ Confidence   │     │
│  │ Logs         │      │ Base         │      │ Scoring      │     │
│  │ Health       │      │ Query        │      │ Guardrails   │     │
│  └──────────────┘      └──────────────┘      └──────────────┘     │
│         │                                              │            │
│         │                                              ▼            │
│         │                                     ┌──────────────┐     │
│         │                                     │     Act      │     │
│         │                                     │              │     │
│         │                                     │ Restart      │     │
│         │                                     │ Scale        │     │
│         │                                     │ Alert        │     │
│         │                                     └──────────────┘     │
│         │                                              │            │
│         │              ┌──────────────┐                │            │
│         └──────────────│   Verify     │◀───────────────┘            │
│                        │              │                             │
│                        │ Re-check     │                             │
│                        │ Metrics      │                             │
│                        │ Validate     │                             │
│                        └──────────────┘                             │
│                               │                                     │
│                               ▼                                     │
│                      ┌──────────────┐                               │
│                      │  Knowledge   │                               │
│                      │     Base     │                               │
│                      │              │                               │
│                      │ SQLite/      │                               │
│                      │ PostgreSQL   │                               │
│                      └──────────────┘                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

              OODA LOOP: Observe → Orient → Decide → Act → Verify
```

### Components

1. **Agent Monitor** (`agent_monitor.py`): Main LLM-driven agent with tool calling
2. **Knowledge Base** (`knowledge_base.py`): Persistent memory with SQLAlchemy ORM
3. **Guardrail Enforcer**: Safety constraints on actions (allowlist, cooldowns, rate limits)
4. **Tool System**: Observation tools (read-only) + Action tools (guardrailed)
5. **Verification Loop**: Post-action validation with automated checks
6. **Web UI** (`web_ui.py`): Investigation dashboard and incident history

---

## OODA Loop Design

### 1. Observe Phase

**Triggers** (what motivates the agent to investigate):
- **Prometheus Metrics**:
  - `up{job="influxdb3"} == 1` but scrape quality degraded (high error rate in logs)
  - Targets down: `up{} == 0`
  - Recent restarts: `changes(container_last_seen[5m]) > 0`
  - Anomalous resource usage: `container_memory_usage_bytes > threshold`
- **Docker Events**:
  - Container health state changes (healthy → unhealthy)
  - OOM kills
  - Container exits with non-zero code
- **MQTT Events**:
  - Device offline/online transitions
  - Sensor anomalies (e.g., temperature out of range)
- **HTTP Synthetic Checks**:
  - Endpoint failures configured via `AI_MONITOR_HTTP_CHECKS`

**Data Sources**:
- Prometheus (metrics, alerts)
- Docker API (container status, logs, stats)
- InfluxDB (sensor data, historical trends)
- MQTT (real-time events)

### 2. Orient Phase

**Knowledge Base Query**:
```python
similar_incidents = kb.find_similar_incidents(
    trigger="influxdb3 scrape failures",
    trigger_type="metric_anomaly",
    limit=5
)
```

**Context Enrichment**:
- Load similar past incidents with resolutions
- Calculate confidence scores for known actions
- Retrieve relevant runbooks if pattern matches

**Output**: Investigation plan informed by history

### 3. Decide Phase

**Confidence-Based Execution**:
```python
confidence = kb.calculate_action_confidence(
    action_type="restart_container",
    target="influxdb3-core",
    trigger_type="metric_anomaly"
)

if confidence >= 0.9:
    execute_automatically()
elif confidence >= 0.5:
    request_human_approval()
else:
    escalate_to_human()
```

**Guardrails**:
- Container allowlist enforcement
- Cooldown periods (default 10 minutes)
- Rate limits (max 3 restarts/hour)
- Blast radius checks (don't restart multiple critical services simultaneously)

### 4. Act Phase

**Available Actions**:
- `restart_container`: Restart with reason logging
- `scale_service`: Adjust replica count (for scalable services)
- `create_alert`: Escalate to PagerDuty/Slack
- `mark_resolved`: Close investigation without action
- `run_command`: Execute arbitrary command in container (requires approval)

**Action Recording**:
```python
action = ActionTaken(
    action_type="restart_container",
    target="influxdb3-core",
    parameters={"reason": "authentication errors persisting"},
    timestamp=datetime.now(timezone.utc),
    success=True
)
```

### 5. Verify Phase

**Verification Checks** (auto-generated based on trigger type):
```python
verifications = [
    VerificationCheck(
        check_type="prometheus_query",
        description="Confirm influxdb3 scrape success rate > 90%",
        query='sum(rate(up{job="influxdb3"}[5m])) / count(up{job="influxdb3"})',
        expected_threshold=0.9,
        passed=True
    ),
    VerificationCheck(
        check_type="docker_health",
        description="Container running and healthy",
        target="influxdb3-core",
        passed=True
    )
]
```

**Wait Period**: 60 seconds stabilization time before verification

**Outcome Recording**:
- `resolved`: Action successful, verifications passed
- `partial`: Action taken but issue persists
- `failed`: Action failed or made things worse
- `escalated`: Beyond agent capabilities

---

## Knowledge Base & Learning

### Database Schema

**SQLAlchemy Models** (supports SQLite + PostgreSQL):

1. **Incident** (main investigation record)
   - `trigger`, `trigger_type`, `outcome`, `root_cause`, `resolution_summary`
   - Timestamps: `detected_at`, `started_at`, `completed_at`
   - Relationships: `actions[]`, `tool_calls[]`, `verifications[]`

2. **Action** (remediation actions)
   - `action_type`, `target`, `parameters`, `success`, `resolved_incident`
   - Links to parent `incident_id`

3. **ToolCall** (audit trail)
   - `tool_name`, `arguments`, `result`, `error_message`, `duration_ms`
   - Complete trace of investigation steps

4. **Verification** (post-action checks)
   - `check_type`, `check_description`, `passed`, `details`
   - Validates action outcomes

5. **Runbook** (learned procedures)
   - `pattern`, `steps`, `success_count`, `avg_resolution_time_seconds`
   - Automatically generated from successful incident resolutions

6. **Pattern** (recurring issues)
   - `pattern_signature`, `occurrence_count`, `first_seen`, `last_seen`
   - Enables proactive monitoring when pattern detected

### Learning Mechanisms

**Similarity Search** (RAG-style):
```python
similar = kb.find_similar_incidents(
    trigger="influxdb3 authentication error",
    trigger_type="metric_anomaly",
    limit=5
)
# Returns past incidents with matching triggers/types
```

**Confidence Scoring**:
```python
confidence = kb.calculate_action_confidence(
    action_type="restart_container",
    target="influxdb3-core",
    trigger_type="metric_anomaly"
)
# Returns: (confidence_score, total_attempts, successful_attempts)
# Example: (0.85, 20, 17) = 85% success rate over 20 attempts
```

**Runbook Generation**:
After 3+ successful resolutions of the same pattern, automatically create runbook with steps.

**Pattern Detection**:
When same `pattern_signature` occurs 5+ times, enable proactive monitoring to catch it earlier.

### Database Abstraction

**Configuration** (via `.env`):
```bash
# SQLite (default for development)
KNOWLEDGE_BASE_DB_TYPE=sqlite
KNOWLEDGE_BASE_SQLITE_PATH=/app/incidents/knowledge.db

# PostgreSQL (production on raspberrypi2)
KNOWLEDGE_BASE_DB_TYPE=postgresql
KNOWLEDGE_BASE_PG_HOST=raspberrypi2.local
KNOWLEDGE_BASE_PG_PORT=5432
KNOWLEDGE_BASE_PG_DATABASE=sre_knowledge
KNOWLEDGE_BASE_PG_USER=sre_agent
KNOWLEDGE_BASE_PG_PASSWORD=<secret>
```

**Connection Pooling**:
- PostgreSQL: QueuePool (size=5-10)
- SQLite: StaticPool (single connection)

---

## Verification Loop

### Purpose

**Closed-Loop Control**: Ensure actions actually resolved the issue (not just "action completed").

### Implementation

```python
def _verify_resolution(self, investigation: Investigation) -> bool:
    """
    Post-action verification with automated checks.
    
    Steps:
    1. Generate verification checks based on trigger type
    2. Wait for system stabilization (60s default)
    3. Execute each verification check
    4. Record results to knowledge base
    5. Update investigation outcome
    """
    
    # Generate checks
    checks = self._generate_verification_checks(investigation)
    
    # Wait for stabilization
    time.sleep(60)
    
    # Run verifications
    for check in checks:
        if check.check_type == "prometheus_query":
            result = self._verify_prometheus_query(check)
        elif check.check_type == "docker_health":
            result = self._verify_docker_health(check)
        elif check.check_type == "http_check":
            result = self._verify_http_check(check)
        
        check.passed = result
        investigation.verifications.append(check)
    
    # Determine overall outcome
    all_passed = all(v.passed for v in investigation.verifications)
    return all_passed
```

### Verification Check Types

1. **Prometheus Query**: Re-run metric check to confirm issue resolved
2. **Docker Health**: Verify container running and healthy
3. **HTTP Check**: Validate endpoint responding correctly
4. **Log Pattern**: Check logs for absence of error messages
5. **Resource Usage**: Confirm resource metrics within normal range

### Auto-Generation Logic

Based on `trigger_type`:
- `metric_anomaly` → Prometheus query verification
- `container_failure` → Docker health + logs check
- `http_failure` → HTTP check with same URL
- `resource_exhaustion` → Resource usage validation

---

## Multi-Agent System

### Hierarchy (Future - Phase 4+)

```
┌───────────────────────────────────────────────────────────┐
│                  Orchestrator Agent                        │
│  (Assigns investigations to specialized agents)            │
└───────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┬────────────────┐
        │                │                │                │
┌───────▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐  ┌──────▼──────┐
│ Container    │  │ Network      │  │ Performance │  │ Application │
│ Health Agent │  │ Agent        │  │ Agent       │  │ Agent       │
│              │  │              │  │             │  │             │
│ - Docker     │  │ - Latency    │  │ - Resource  │  │ - Logs     │
│ - Restarts   │  │ - Timeouts   │  │ - Scaling   │  │ - Errors   │
│ - Health     │  │ - DNS        │  │ - Quotas    │  │ - APM      │
└──────────────┘  └──────────────┘  └─────────────┘  └─────────────┘
```

### Agent Communication

**Message Queue** (NATS/Redis Streams):
```python
{
    "type": "investigation_request",
    "priority": "high",
    "trigger": "influxdb3 scrape failures",
    "assigned_to": "container_health_agent",
    "correlation_id": "inv-20260114-001"
}
```

**Shared Knowledge Base**: All agents read/write to same PostgreSQL database

---

## Phase Roadmap

### ✅ Phase 0: Foundation (Complete)

**Goal**: Tool-based investigation with guardrails

**Delivered**:
- ✅ Tool system (observation + action tools)
- ✅ Guardrail enforcer (allowlist, cooldowns, rate limits)
- ✅ LLM integration (Claude 3.5 Sonnet, Gemini 2.0 Flash)
- ✅ Agent loop with function calling
- ✅ Prometheus metric-based triggers
- ✅ Incident reporting with markdown output

**Metrics**:
- 15+ observation tools available
- 5+ action tools with guardrails
- 60-second monitoring cycle

---

### ✅ Phase 1: Execution Mode (Complete)

**Goal**: Move from dry-run to autonomous action execution

**Delivered**:
- ✅ Execute mode enabled (`AI_MONITOR_EXECUTE_ACTIONS=true`)
- ✅ Action execution with Docker SDK
- ✅ Audit logging for all actions
- ✅ Web UI for investigation tracking
- ✅ Incident history with markdown reports

**Metrics**:
- Actions auto-executed within guardrail limits
- Full audit trail in logs and incident files

---

### ✅ Phase 2: Verification Loop + Memory (Complete)

**Goal**: Closed-loop verification and persistent learning

**Delivered**:
- ✅ Knowledge base with SQLite backend (extensible to PostgreSQL)
- ✅ SQLAlchemy ORM with 6 tables (incidents, actions, tool_calls, verifications, runbooks, patterns)
- ✅ Verification loop infrastructure (`_verify_resolution()`)
- ✅ Auto-generated verification checks based on trigger type
- ✅ Similarity search for past incidents (`find_similar_incidents()`)
- ✅ Confidence scoring based on historical success rates (`calculate_action_confidence()`)
- ✅ Investigation enhanced with structured action/verification tracking
- ✅ Database health checks and connection pooling

**Metrics**:
- Database: 0 incidents recorded (just initialized)
- Verification enabled: `AI_MONITOR_VERIFICATION_ENABLED=true`
- Knowledge base enabled: `AI_MONITOR_KNOWLEDGE_BASE_ENABLED=true`

**Files Modified**:
- `ai-monitor/knowledge_base.py` (NEW - 565 lines, 20KB)
- `ai-monitor/agent_monitor.py` (MODIFIED - enhanced Investigation class, verification loop)
- `ai-monitor/requirements.txt` (added sqlalchemy, psycopg2-binary)
- `ai-monitor/Dockerfile` (includes knowledge_base.py)
- `docker-compose.yml` (knowledge base environment variables)

---

### ✅ Phase 3: Proactive Monitoring + Runbook Learning (Complete)

**Goal**: Predict issues before they occur; auto-generate runbooks

**Delivered**:
- ✅ Knowledge query tools for agents (`query_knowledge_base`, `get_runbook`, `check_action_confidence`, `get_incident_trends`)
- ✅ Automatic runbook generation after 3+ successful resolutions of same pattern
- ✅ Pattern detection and signature matching (auto-enables proactive checks after 5+ occurrences)
- ✅ Scheduled proactive scans (every 15 minutes default)
- ✅ Confidence-based execution thresholds (high >85%, medium 50-85%, low <50%)
- ✅ Resource forecasting checks (disk >85%, memory >90%)
- ✅ Trend analysis and alerting (daily rate, resolution rate, trending issues)
- ✅ Updated system prompt teaching agent to use knowledge base first

**Knowledge Base Tools Added**:
```python
# Search past incidents (RAG-style)
query_knowledge_base(query="influxdb error", trigger_type="container_unhealthy")

# Get learned procedures
get_runbook(pattern="container_unhealthy")

# Check confidence before action
check_action_confidence(action_type="restart_container", target="influxdb3-core", trigger_type="container_unhealthy")

# Analyze trends
get_incident_trends(days=7)
```

**Proactive Checks Implemented**:
- Docker health checks for unhealthy containers
- Docker status checks for exited containers
- Prometheus query checks for configured alerts
- Resource threshold checks (disk/memory exhaustion)
- Trend analysis for incident rate and resolution rate

**Files Modified**:
- `ai-monitor/knowledge_base.py` (expanded to ~1100 lines with Phase 3 methods)
- `ai-monitor/agent_monitor.py` (added knowledge tools, proactive scan, confidence-based execution)

**Metrics**:
- 4 new knowledge tools available to agent
- Proactive scan interval: 15 minutes (configurable)
- Confidence thresholds: 85% (auto), 50% (proceed), <50% (escalate)

---

### 🔮 Phase 4: Multi-Agent Coordination

**Goal**: Specialized agents for different operational domains

**Architecture**:
- **Orchestrator Agent**: Routes investigations to specialized agents
- **Container Health Agent**: Docker, Kubernetes, restart policies
- **Network Agent**: DNS, latency, timeouts, connectivity
- **Performance Agent**: Resource usage, scaling, quotas
- **Application Agent**: Logs, errors, APM traces

**Communication**:
- Message queue (NATS or Redis Streams)
- Shared knowledge base (PostgreSQL)
- Agent registration and discovery

**Benefits**:
- Parallel investigation of complex issues
- Specialized context/prompts per domain
- Reduced LLM context size (domain-specific tools only)

---

### 🔮 Phase 5: Config Management + Self-Healing

**Goal**: Agent modifies system configuration to prevent recurrence

**Capabilities**:
- Adjust resource limits (memory, CPU)
- Update health check thresholds
- Modify scaling policies
- Tune rate limits and timeouts
- Generate Prometheus alert rules

**Example**:
```python
# After resolving OOM kill 3 times by restarting
action = {
    "type": "update_config",
    "target": "influxdb3-core",
    "changes": {
        "memory_limit": "4GB"  # increased from 2GB
    },
    "reason": "Prevent recurring OOM kills (3 incidents in 7 days)"
}
```

**Guardrails**:
- Configuration change allowlist
- Human approval required for critical services
- Rollback capability if verification fails

---

### 🔮 Phase 6: Full Autonomy + Root Cause Analysis

**Goal**: Complete autonomy with deep root cause investigations

**Features**:
- Distributed tracing integration (Jaeger, OpenTelemetry)
- Correlation analysis across metrics/logs/traces
- Dependency graph awareness
- Blast radius calculation before actions
- Automated postmortem generation

**Root Cause Analysis**:
```python
investigation.root_cause = """
1. Primary Cause: InfluxDB 3 token rotation not propagated to Prometheus
2. Contributing Factors:
   - No validation of token at startup
   - Health check doesn't verify /metrics endpoint
   - Missing alert for scrape failure with healthy container
3. Propagation Path: Token updated in .env → Not copied to prometheus/influxdb3_token
4. Resolution: Token sync + add pre-flight validation
5. Prevention: Add token validation to InfluxDB health check
"""
```

**Postmortem Auto-Generation**:
- Timeline reconstruction from tool calls
- Impact analysis (services affected, duration)
- Action effectiveness evaluation
- Preventive measures recommended

---

## Current Implementation Status

### Completed ✅

**Phase 0 (Foundation)**:
- Tool system with 15+ observation tools
- Guardrail enforcer with allowlist/cooldowns/rate limits
- LLM integration (Claude, Gemini) with function calling
- Agent monitoring loop (60s cycle)
- Prometheus metric-based triggers
- Markdown incident reports

**Phase 1 (Execution)**:
- Execute mode enabled
- Docker SDK action execution
- Audit logging
- Web UI dashboard
- Incident history tracking

**Phase 2 (Verification + Memory)**:
- Knowledge base database (SQLite/PostgreSQL abstraction)
- 6 SQLAlchemy tables (incidents, actions, tool_calls, verifications, runbooks, patterns)
- Verification loop with auto-generated checks
- Similarity search (RAG)
- Confidence scoring
- Investigation enhanced with structured tracking

**Phase 3 (Proactive + Learning)**:
- Knowledge query tools (`query_knowledge_base`, `get_runbook`, `check_action_confidence`, `get_incident_trends`)
- Automatic runbook generation after 3+ successful resolutions
- Pattern detection with proactive check enablement (5+ occurrences)
- Scheduled proactive scans (15-minute interval)
- Confidence-based execution thresholds (85%/50%)
- Resource forecasting (disk/memory exhaustion prediction)
- Trend analysis and alerting
- Updated autonomous system prompt

### In Progress 🚧

**Phase 3 Validation**:
- [ ] Trigger test incidents to validate full learning flow
- [ ] Verify runbook auto-generation after 3 similar incidents
- [ ] Test pattern detection and proactive check enablement
- [ ] Validate confidence-based execution decisions
- [ ] Test PostgreSQL backend on raspberrypi2

### Pending ⏳

**Phase 4+ (Future)**:
- Multi-agent coordination (orchestrator + specialized agents)
- Config management and self-healing
- Full autonomy with root cause analysis
- See Phase Roadmap section above

---

## Configuration Reference

### Environment Variables

**Core Agent Settings**:
```bash
# LLM Configuration
AI_MONITOR_LLM_BACKEND=gemini                    # "claude" | "gemini"
AI_MONITOR_ANTHROPIC_API_KEY=<secret>
AI_MONITOR_GEMINI_API_KEY=<secret>

# Monitoring Behavior
AI_MONITOR_INTERVAL_SECONDS=60                   # Check interval
AI_MONITOR_MAX_TOOL_CALLS=20                     # Per investigation
AI_MONITOR_MAX_INVESTIGATION_TIME_SECONDS=300    # 5 minute timeout
AI_MONITOR_EXECUTE_ACTIONS=true                  # Enable action execution

# Knowledge Base
AI_MONITOR_KNOWLEDGE_BASE_ENABLED=true
AI_MONITOR_VERIFICATION_ENABLED=true
KNOWLEDGE_BASE_DB_TYPE=sqlite                    # "sqlite" | "postgresql"
KNOWLEDGE_BASE_SQLITE_PATH=/app/incidents/knowledge.db

# PostgreSQL (production)
KNOWLEDGE_BASE_PG_HOST=raspberrypi2.local
KNOWLEDGE_BASE_PG_PORT=5432
KNOWLEDGE_BASE_PG_DATABASE=sre_knowledge
KNOWLEDGE_BASE_PG_USER=sre_agent
KNOWLEDGE_BASE_PG_PASSWORD=<secret>

# Guardrails
AI_MONITOR_ALLOWED_CONTAINERS=influxdb3-core,mosquitto,nginx-proxy-manager,prometheus,telegraf,telemetry-collector
AI_MONITOR_GUARDRAIL_COOLDOWN_SECONDS=600        # 10 minutes
AI_MONITOR_GUARDRAIL_MAX_RESTARTS_PER_HOUR=3

# HTTP Synthetic Checks
AI_MONITOR_HTTP_CHECKS="http://nginx-proxy-manager:81|200;http://app:8080|200|Authorization=Bearer%20token"

# Observability
AI_MONITOR_PROMETHEUS_URL=http://prometheus:9090
AI_MONITOR_INCIDENTS_DIR=/app/incidents
```

### Prometheus Integration

**Metric-Based Triggers**:
```yaml
# Scrape quality degraded (container healthy but errors in metrics)
ai_monitor_trigger:
  query: |
    (up{job="influxdb3"} == 1) and 
    (rate(prometheus_tsdb_compaction_errors_total[5m]) > 0)

# Targets down
ai_monitor_trigger:
  query: up{} == 0

# Recent container restarts
ai_monitor_trigger:
  query: changes(container_last_seen[5m]) > 0
```

**Agent Metrics Exported**:
- `ai_investigations_total{outcome}`: Investigation count by outcome
- `ai_investigation_duration_seconds`: Investigation latency
- `ai_tool_calls_total{tool_name}`: Tool usage statistics
- `ai_actions_taken_total{action_type,success}`: Action execution stats
- `ai_verification_checks_total{check_type,passed}`: Verification results
- `ai_knowledge_base_incidents_total`: Total incidents in database
- `ai_http_check_ok{target}`: Synthetic check results (0=fail, 1=pass)
- `ai_http_check_latency_ms{target}`: Endpoint latency

---

## Tool Catalog

### Observation Tools (Read-Only)

| Tool | Description | Parameters |
|------|-------------|------------|
| `prom_query` | Execute PromQL query | `query` (string), `lookback` (string, default "5m") |
| `prom_list_metrics` | List available metrics | `pattern` (regex, optional) |
| `docker_list` | List all containers | `all` (bool, include stopped) |
| `docker_inspect` | Container details + logs | `container` (name), `include_logs` (bool), `log_lines` (int) |
| `docker_stats` | Real-time resource usage | `container` (name) |
| `docker_network_inspect` | Network connectivity | `network` (name) |
| `system_info` | Host metrics (CPU/mem/disk) | None |
| `http_check` | Test HTTP endpoint | `url` (string), `expected_status` (int), `headers` (dict) |
| `influxdb_query` | Query InfluxDB 3 Core | `database` (string), `query` (SQL), `limit` (int) |
| `mqtt_subscribe` | Listen to MQTT topic | `topic` (string), `timeout` (int) |

### Action Tools (Guardrailed)

| Tool | Description | Guardrails |
|------|-------------|------------|
| `restart_container` | Restart a container | Allowlist, 10min cooldown, 3/hour max |
| `scale_service` | Adjust replica count | Scalable services only, min/max limits |
| `create_alert` | Escalate to PagerDuty/Slack | Rate limited |
| `mark_resolved` | Close investigation | None (safe) |
| `run_command` | Execute command in container | Allowlist, requires approval |

### Knowledge Base Tools (Phase 3 - Implemented)

| Tool | Description | Parameters |
|------|-------------|------------|
| `query_knowledge_base` | Search past incidents and resolutions | `query` (natural language), `trigger_type` (filter), `outcome` (filter), `limit` (int) |
| `get_runbook` | Retrieve auto-generated runbook | `pattern` (string - trigger type or keyword) |
| `check_action_confidence` | Get confidence score for proposed action | `action_type`, `target`, `trigger_type` |
| `get_incident_trends` | Analyze incident trends over time | `days` (int, default 7) |

---

## Next Steps

### Immediate (Phase 3 Validation)

1. **Trigger Test Incidents**:
   - Manually break something (e.g., stop InfluxDB, inject bad token)
   - Wait for agent to detect, query knowledge base, and investigate
   - Verify agent uses `query_knowledge_base` and `check_action_confidence` tools
   - Confirm knowledge base records incident with all details

2. **Validate Learning Flow**:
   - Trigger same issue type 3+ times
   - Verify runbook is auto-generated after 3rd resolution
   - Confirm agent retrieves and follows runbook on 4th occurrence

3. **Test Pattern Detection**:
   - Trigger same pattern 5+ times
   - Confirm proactive check is auto-enabled
   - Verify proactive scan detects issue before trigger fires

4. **Test Confidence-Based Execution**:
   - With historical data, verify confidence scores affect decisions
   - Confirm high-confidence actions (>85%) proceed confidently
   - Verify low-confidence actions (<50%) are escalated

5. **PostgreSQL Migration** (Production):
   - Create database on raspberrypi2: `CREATE DATABASE sre_knowledge;`
   - Create user: `CREATE USER sre_agent WITH PASSWORD '...';`
   - Update `.env` with PostgreSQL settings
   - Restart agent and verify connection

### Short-Term (Phase 4 Initiation)

1. **Multi-Agent Architecture Design**:
   - Design agent communication protocol (message queue)
   - Plan orchestrator agent responsibilities
   - Define specialized agent domains (container, network, performance, application)

2. **Agent Specialization**:
   - Create Container Health Agent (Docker, restarts, health)
   - Create Network Agent (DNS, latency, timeouts)
   - Create Performance Agent (resources, scaling)
   - Create Application Agent (logs, errors, APM)

### Medium-Term (Phase 4-5)

1. **Multi-Agent Architecture**:
   - Design agent communication protocol (message queue)
   - Implement orchestrator agent
   - Create specialized agents (container, network, performance, application)

2. **Configuration Management**:
   - Add `update_config` action tool
   - Implement rollback capability
   - Create approval workflow for config changes

3. **Root Cause Analysis**:
   - Integrate distributed tracing (Jaeger/OpenTelemetry)
   - Build dependency graph from service mesh
   - Implement correlation analysis

### Long-Term (Phase 6)

1. **Full Autonomy**:
   - Remove all human approval requirements for proven actions
   - Implement blast radius calculation
   - Add automated postmortem generation

2. **Self-Improvement**:
   - LLM fine-tuning on successful investigations
   - Prompt optimization based on outcomes
   - Tool usage pattern analysis

---

## Success Metrics

### Phase 2 (Complete)
- ✅ Knowledge base initialized: `total_incidents=0, health=true`
- ✅ Incident recording with full audit trail
- ✅ Verification loop executes and updates outcomes
- ✅ Similarity search implemented

### Phase 3 (Complete - Awaiting Validation)
- ✅ Knowledge query tools implemented (4 tools)
- ✅ Confidence-based execution implemented (85%/50% thresholds)
- ✅ Automatic runbook generation implemented (after 3+ resolutions)
- ✅ Pattern detection implemented (proactive after 5+ occurrences)
- ✅ Proactive monitoring scan implemented (15-min interval)
- ⏳ Validation: 50%+ incidents have matching past incidents
- ⏳ Validation: Runbooks auto-generated after pattern resolution
- ⏳ Validation: Proactive issues caught before critical threshold

### Phase 4 (Target)
- 5+ specialized agents operational
- 100%+ increase in investigation throughput (parallel processing)
- 90%+ agent correlation accuracy (right agent for the issue)

### Phase 5 (Target)
- 50%+ recurring issues prevented via config changes
- 0 manual config tweaks needed for learned issues
- 95%+ config changes successfully applied

### Phase 6 (Target)
- 95%+ incidents resolved autonomously (no human intervention)
- 100% incidents have complete root cause analysis
- 80%+ postmortems auto-generated within 1 hour of resolution

---

## Appendix

### Related Documentation
- [AI_MONITOR_AGENT_ARCHITECTURE.md](AI_MONITOR_AGENT_ARCHITECTURE.md) - Original agent architecture design
- [AI_AGENT_DATA_TOOLS.md](AI_AGENT_DATA_TOOLS.md) - Detailed tool specifications
- [AI_MONITOR.md](AI_MONITOR.md) - Monitoring system overview
- [OPERATIONS.md](OPERATIONS.md) - Operational procedures

### Key Files
- `ai-monitor/agent_monitor.py` - Main agent implementation
- `ai-monitor/knowledge_base.py` - Persistent memory system
- `ai-monitor/web_ui.py` - Investigation dashboard
- `ai-monitor/monitor.py` - Deprecated rule-based monitor

### Repositories
- Main: `aachtenberg/raspberry-pi-docker`
- Branch: `feature/agent-based-monitoring`
- Camera Dashboard: `aachtenberg/camera-dashboard` (separate stack on Pi 2)

---

**Document Version**: 1.0  
**Last Review**: January 14, 2026  
**Next Review**: After Phase 3 completion
