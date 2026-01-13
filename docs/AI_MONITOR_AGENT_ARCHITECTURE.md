# AI Monitor: Agent-Based Architecture

## Philosophy Shift

**Current (Rule-Based with AI Triage)**:
```
Hard-coded queries → Snapshot → LLM analysis → Recommended actions
```

**Proposed (Agent-Based with Guardrails)**:
```
LLM observes → Query APIs (tools) → Iterative investigation → Guardrailed actions
```

## Core Architecture

### 1. Tool System (LLM Function Calling)

The LLM has access to these tools for investigation:

#### Observation Tools (Read-Only)
```python
tools = [
    {
        "name": "prom_query",
        "description": "Execute arbitrary PromQL query against Prometheus",
        "parameters": {
            "query": "string (PromQL)",
            "lookback": "string (e.g., '5m', '1h', default '5m')"
        }
    },
    {
        "name": "prom_list_metrics",
        "description": "List all available Prometheus metrics matching pattern",
        "parameters": {
            "pattern": "string (regex, optional)"
        }
    },
    {
        "name": "docker_inspect",
        "description": "Get detailed info about a container",
        "parameters": {
            "container": "string (name or id)",
            "include_logs": "bool (default false)",
            "log_lines": "int (default 50)"
        }
    },
    {
        "name": "docker_list",
        "description": "List all containers with status/health",
        "parameters": {
            "all": "bool (include stopped, default true)"
        }
    },
    {
        "name": "docker_stats",
        "description": "Get real-time resource usage for container",
        "parameters": {
            "container": "string"
        }
    },
    {
        "name": "docker_network_inspect",
        "description": "Inspect network connectivity between containers",
        "parameters": {
            "network": "string (network name)"
        }
    },
    {
        "name": "system_info",
        "description": "Get host system metrics (CPU, memory, disk, network)",
        "parameters": {}
    },
    {
        "name": "http_check",
        "description": "Test HTTP endpoint availability",
        "parameters": {
            "url": "string",
            "expected_status": "int (default 200)",
            "headers": "dict (optional)"
        }
    }
]
```

#### Action Tools (Guardrailed)
```python
action_tools = [
    {
        "name": "restart_container",
        "description": "Restart a container (allowlist enforced)",
        "parameters": {
            "container": "string",
            "reason": "string (required for audit)"
        },
        "guardrails": {
            "allowlist": "AI_MONITOR_ALLOWED_CONTAINERS",
            "cooldown": "10 minutes",
            "max_per_hour": 3
        }
    },
    {
        "name": "scale_service",
        "description": "Scale docker-compose service replicas",
        "parameters": {
            "service": "string",
            "replicas": "int"
        },
        "guardrails": {
            "allowlist": "AI_MONITOR_SCALABLE_SERVICES",
            "max_replicas": 5
        }
    },
    {
        "name": "create_alert",
        "description": "Send alert to configured channels (Slack, PagerDuty, etc.)",
        "parameters": {
            "severity": "enum (low, medium, high, critical)",
            "title": "string",
            "message": "string",
            "include_snapshot": "bool (default true)"
        }
    },
    {
        "name": "mark_resolved",
        "description": "Mark current investigation as resolved",
        "parameters": {
            "summary": "string",
            "actions_taken": "list[string]"
        }
    }
]
```

### 2. Agent Loop

```python
class AgentMonitor:
    def investigate(self, trigger: str) -> Investigation:
        """
        LLM-driven investigation with tool calls.
        
        Args:
            trigger: Initial trigger (e.g., "High error rate", "Container crash")
        
        Returns:
            Investigation object with findings and actions taken
        """
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT  # See below
            },
            {
                "role": "user",
                "content": f"Investigate: {trigger}"
            }
        ]
        
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # LLM decides next action (query or remediation)
            response = llm.call(
                messages=messages,
                tools=tools + action_tools,
                tool_choice="auto"
            )
            
            # If LLM wants to use tools, execute them
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    result = self.execute_tool(
                        tool_call.name,
                        tool_call.arguments
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })
                continue
            
            # LLM has concluded investigation
            if response.content:
                return Investigation(
                    trigger=trigger,
                    findings=response.content,
                    tool_calls_made=self._extract_tool_history(messages),
                    actions_taken=self._extract_actions(messages)
                )
        
        # Max iterations reached
        return Investigation(
            trigger=trigger,
            findings="Investigation incomplete (max iterations reached)",
            tool_calls_made=self._extract_tool_history(messages),
            actions_taken=[]
        )
```

### 3. System Prompt (Defines Agent Behavior)

```python
SYSTEM_PROMPT = """You are an SRE agent monitoring a Raspberry Pi Docker infrastructure.

MISSION:
- Proactively detect and resolve infrastructure issues
- Minimize false positives and unnecessary restarts
- Provide clear explanations for all actions

TOOLS AVAILABLE:
- Observation: Query Prometheus, inspect containers, check system health
- Actions: Restart containers (allowlist only), send alerts, create incident reports

WORKFLOW:
1. When triggered, use observation tools to understand the issue
2. Form hypotheses and test them with targeted queries
3. If you identify a clear problem with a known solution, take action
4. If uncertain or outside your remediation scope, create an alert for humans
5. Always call mark_resolved() when investigation complete

GUARDRAILS (ENFORCED BY SYSTEM):
- Can only restart containers in allowlist
- Restart cooldown: 10 minutes per container
- Max 3 restarts per hour across all containers
- Cannot modify volumes, networks, or host system
- Cannot expose new ports or change security settings

INVESTIGATION BEST PRACTICES:
- Start broad (list all containers, check Prometheus scrape health)
- Then narrow based on findings (inspect specific containers, query related metrics)
- Check dependencies (if API failing, check database connectivity)
- Look for cascading failures (upstream service down affecting downstream)
- Consider resource constraints (memory pressure causing OOM kills)

EXAMPLES:

Example 1 - Container crash:
1. docker_list() → see container "api" is exited
2. docker_inspect(container="api", include_logs=true) → see OOMKilled
3. prom_query(query='docker_container_mem_usage{name="api"}[1h]') → see memory leak
4. restart_container(container="api", reason="OOMKilled, restarting to restore service")
5. create_alert(severity="medium", title="API memory leak", message="Restarted due to OOM. Investigate memory leak in code.")
6. mark_resolved(summary="API restarted after OOM. Alert created for dev team.")

Example 2 - Performance degradation:
1. prom_query(query='rate(http_request_duration_seconds[5m])') → see latency spike
2. docker_list() → all containers running
3. system_info() → see CPU at 95%
4. docker_stats(container="nginx") → nginx using 80% CPU
5. prom_query(query='rate(nginx_http_requests_total[5m])') → see request spike
6. create_alert(severity="high", title="Traffic spike", message="Nginx CPU at 80% due to 10x traffic. Consider scaling.")
7. mark_resolved(summary="Traffic spike identified. Alert sent. No action needed - system handling load.")

Example 3 - False alarm:
1. prom_query(query='up{job="node-exporter"}') → shows down momentarily
2. prom_query(query='up{job="node-exporter"}[5m]') → see it's back up (transient blip)
3. mark_resolved(summary="Transient scrape failure, target back up. No action needed.")

REMEMBER:
- You are running in a loop; be efficient with queries
- Don't restart containers unless clearly beneficial
- When in doubt, alert humans instead of taking action
- Always provide reasoning for actions
"""
```

### 4. Trigger System

Instead of hard-coded queries, use **change detection**:

```python
class TriggerDetector:
    """Detect state changes that warrant investigation."""
    
    def __init__(self):
        self.last_state = {}
    
    def check_triggers(self) -> List[str]:
        """Return list of triggers for agent to investigate."""
        triggers = []
        
        # Container state changes
        current_containers = self._get_container_states()
        for name, state in current_containers.items():
            prev = self.last_state.get(name, {})
            if state["health"] != prev.get("health"):
                if state["health"] == "unhealthy":
                    triggers.append(f"Container {name} became unhealthy")
            if state["status"] != prev.get("status"):
                if state["status"] == "exited":
                    triggers.append(f"Container {name} exited unexpectedly")
        
        # Prometheus target changes
        current_targets = self._get_prom_targets()
        prev_targets = self.last_state.get("prom_targets", {})
        for target, up in current_targets.items():
            if not up and prev_targets.get(target, True):
                triggers.append(f"Prometheus target {target} went down")
        
        # Alert firing changes (use Prometheus Alertmanager API)
        current_alerts = self._get_firing_alerts()
        prev_alerts = self.last_state.get("alerts", set())
        new_alerts = current_alerts - prev_alerts
        for alert in new_alerts:
            triggers.append(f"Alert firing: {alert}")
        
        # Metric threshold breaches (configurable)
        if self._check_metric_threshold("node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100", "<", 10):
            triggers.append("Host memory below 10%")
        
        if self._check_metric_threshold("node_filesystem_avail_bytes{mountpoint='/'} / node_filesystem_size_bytes * 100", "<", 15):
            triggers.append("Root filesystem below 15%")
        
        # Update state for next iteration
        self.last_state = {
            **current_containers,
            "prom_targets": current_targets,
            "alerts": current_alerts
        }
        
        return triggers
```

### 5. Complete Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     Main Monitor Loop                        │
│                                                              │
│  1. TriggerDetector.check_triggers()                        │
│     → Returns: ["Container api exited", "Memory < 10%"]     │
│                                                              │
│  2. For each trigger:                                       │
│     a. AgentMonitor.investigate(trigger)                    │
│        ├─> LLM decides: "Call docker_inspect(api)"          │
│        ├─> Execute tool → Return logs/stats                 │
│        ├─> LLM decides: "Call prom_query(memory)"           │
│        ├─> Execute tool → Return time series                │
│        ├─> LLM concludes: "OOMKill, restart needed"         │
│        ├─> LLM calls: restart_container(api)                │
│        │   └─> Guardrails check: In allowlist? → Yes        │
│        │   └─> Guardrails check: Within cooldown? → Yes     │
│        │   └─> Execute: docker restart api                  │
│        └─> LLM calls: mark_resolved(summary=...)            │
│                                                              │
│     b. Save investigation report                            │
│                                                              │
│  3. Update Prometheus metrics                               │
│     - investigations_total                                  │
│     - actions_taken_total{type="restart"}                   │
│     - tool_calls_total{tool="docker_inspect"}               │
│                                                              │
│  4. Sleep(interval)                                         │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Considerations

### Cost Management
- **Tool call limits**: Max 20 tool calls per investigation
- **Context pruning**: Summarize tool results if messages get long
- **Caching**: Cache prometheus metrics for 30s to avoid redundant queries
- **Batching**: If multiple triggers, investigate in parallel where safe

### Safety
- **Dry-run mode**: Log what would be done without executing
- **Audit log**: All tool calls and actions logged to structured JSON
- **Rollback**: Track state before actions for potential rollback
- **Human approval**: For critical actions (scale down prod, delete data)

### Observability
```python
# Prometheus metrics for the agent itself
INVESTIGATIONS_TOTAL = Counter("ai_agent_investigations_total", ["trigger_type", "outcome"])
TOOL_CALLS_TOTAL = Counter("ai_agent_tool_calls_total", ["tool_name", "success"])
ACTIONS_TAKEN_TOTAL = Counter("ai_agent_actions_total", ["action_type"])
INVESTIGATION_DURATION = Histogram("ai_agent_investigation_duration_seconds")
LLM_COST_TOTAL = Counter("ai_agent_llm_cost_dollars")  # Estimate based on tokens
```

### Guardrail Enforcement

```python
class GuardrailEnforcer:
    """Enforce action guardrails before execution."""
    
    def check_action(self, action: ToolCall) -> GuardrailResult:
        if action.name == "restart_container":
            container = action.args["container"]
            
            # Check allowlist
            if container not in self.allowed_containers:
                return GuardrailResult(
                    allowed=False,
                    reason=f"Container {container} not in allowlist"
                )
            
            # Check cooldown
            last_restart = self.restart_history.get(container, 0)
            if time.time() - last_restart < self.cooldown_seconds:
                return GuardrailResult(
                    allowed=False,
                    reason=f"Restart cooldown active (last: {last_restart})"
                )
            
            # Check rate limit
            recent_restarts = self._count_recent_restarts(window_seconds=3600)
            if recent_restarts >= self.max_restarts_per_hour:
                return GuardrailResult(
                    allowed=False,
                    reason=f"Rate limit: {recent_restarts}/hr (max: {self.max_restarts_per_hour})"
                )
            
            return GuardrailResult(allowed=True)
        
        # Add checks for other actions...
```

## Benefits Over Current Design

1. **Discovers novel failures**: Not limited to pre-programmed queries
2. **Context-aware**: Can drill down based on initial findings
3. **Explains reasoning**: Tool calls show investigation path
4. **Flexible**: Easy to add new tools without changing core logic
5. **Auditable**: Complete trace of investigation in logs
6. **Cost-controlled**: Tool call limits prevent runaway costs
7. **Safe**: Guardrails enforced before execution

## Migration Path

### Phase 1: Hybrid Mode (Current + Agent)
- Keep existing rule-based checks
- Add agent-based investigation for failures that slip through
- Compare results, tune guardrails

### Phase 2: Agent-Primary
- Let agent handle most investigations
- Keep a few critical hard-coded checks (e.g., disk space) as fallback

### Phase 3: Fully Agent-Based
- Remove hard-coded queries entirely
- Agent decides what to monitor based on available metrics

## Configuration Example

```yaml
# .env additions
AI_MONITOR_MODE=agent  # "rules" | "hybrid" | "agent"
AI_MONITOR_ALLOWED_CONTAINERS=prometheus,grafana,influxdb3-core,nginx-proxy-manager
AI_MONITOR_SCALABLE_SERVICES=api,worker
AI_MONITOR_MAX_TOOL_CALLS=20
AI_MONITOR_MAX_INVESTIGATION_TIME_SECONDS=300
AI_MONITOR_GUARDRAIL_COOLDOWN_SECONDS=600
AI_MONITOR_GUARDRAIL_MAX_RESTARTS_PER_HOUR=3
```

## Next Steps

1. Implement tool system (observation + action tools)
2. Add guardrail enforcer
3. Build agent loop with Claude/Gemini function calling
4. Test in dry-run mode against historical incidents
5. Deploy in hybrid mode alongside existing monitor
6. Tune system prompt and guardrails based on results
7. Graduate to agent-primary mode
