"""
AI Agent-Based Monitor with Tool Calling and Guardrails.

This module implements an LLM-driven monitoring agent that:
1. Detects state changes (triggers)
2. Investigates using observation tools (Prometheus, Docker APIs)
3. Takes remediation actions within guardrails
4. Provides full audit trail of investigations
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from threading import Thread, Lock

import docker
import requests
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, start_http_server

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ================================ Utilities ===================================

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _log(level: str, msg: str, **fields: Any) -> None:
    log_level = os.getenv("AI_MONITOR_LOG_LEVEL", "info").strip().lower()
    allowed = {"debug": 10, "info": 20, "warn": 30, "error": 40}
    if allowed.get(level, 20) < allowed.get(log_level, 20):
        return

    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "msg": msg,
    }
    if fields:
        payload.update(fields)
    print(json.dumps(payload, ensure_ascii=False))


# ============================== Prometheus Metrics ============================

INVESTIGATIONS_TOTAL = Counter(
    "ai_agent_investigations_total",
    "Total investigations started",
    ["trigger_type", "outcome"]  # outcome: resolved|escalated|timeout|error
)

TOOL_CALLS_TOTAL = Counter(
    "ai_agent_tool_calls_total",
    "Total tool calls made",
    ["tool_name", "success"]
)

ACTIONS_TAKEN_TOTAL = Counter(
    "ai_agent_actions_total",
    "Total actions executed",
    ["action_type"]  # restart_container, scale_service, create_alert
)

INVESTIGATION_DURATION = Histogram(
    "ai_agent_investigation_duration_seconds",
    "Investigation duration",
    buckets=[1, 5, 10, 30, 60, 120, 300]
)

LLM_ITERATIONS = Histogram(
    "ai_agent_llm_iterations",
    "Number of LLM iterations per investigation",
    buckets=[1, 2, 3, 5, 10, 15, 20]
)

GUARDRAIL_BLOCKS_TOTAL = Counter(
    "ai_agent_guardrail_blocks_total",
    "Actions blocked by guardrails",
    ["action_type", "reason"]
)

ACTIVE_INVESTIGATIONS = Gauge(
    "ai_agent_active_investigations",
    "Number of investigations currently in progress"
)


# =============================== Data Models ==================================

@dataclass
class ToolCall:
    """Represents a tool call made by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class Investigation:
    """Complete investigation report."""
    trigger: str
    start_time: float
    end_time: Optional[float] = None
    outcome: str = "in_progress"  # in_progress, resolved, escalated, timeout, error
    findings: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)
    llm_iterations: int = 0


class GuardrailResult(BaseModel):
    """Result of guardrail check."""
    allowed: bool
    reason: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================== Tool Definitions ==============================

SYSTEM_PROMPT = """You are an SRE agent monitoring a Raspberry Pi Docker infrastructure.

MISSION:
- Proactively detect and resolve infrastructure issues
- Minimize false positives and unnecessary restarts
- Provide clear explanations for all actions

TOOLS AVAILABLE:
Observation tools (read-only):
- prom_query: Execute PromQL queries
- prom_list_metrics: List available Prometheus metrics
- docker_list: List all containers with status
- docker_inspect: Get detailed container info and logs
- docker_stats: Get real-time resource usage
- system_info: Get host system metrics
- http_check: Test HTTP endpoint availability

Action tools (guardrailed):
- restart_container: Restart a container (allowlist enforced)
- create_alert: Send alert to operators
- mark_resolved: Conclude investigation

WORKFLOW:
1. When triggered, use observation tools to understand the issue
2. Form hypotheses and test them with targeted queries
3. If you identify a clear problem with a known solution, take action
4. If uncertain or outside your remediation scope, create an alert for humans
5. Always call mark_resolved() when investigation complete with summary

GUARDRAILS (ENFORCED BY SYSTEM):
- Can only restart containers in allowlist
- Restart cooldown: 10 minutes per container
- Max 3 restarts per hour across all containers
- Cannot modify volumes, networks, or host system

INVESTIGATION BEST PRACTICES:
- Start broad (list containers, check Prometheus health)
- Then narrow based on findings (inspect specific containers)
- Check dependencies (if API failing, check database)
- Look for cascading failures (upstream → downstream)
- Consider resource constraints (memory pressure, disk full)

EXAMPLES:

Example 1 - Container crash:
1. docker_inspect(container="api", include_logs=true) → see OOMKilled
2. prom_query(query='docker_container_mem_usage{name="api"}[1h]') → see memory leak
3. restart_container(container="api", reason="OOMKilled, restarting to restore service")
4. create_alert(severity="medium", title="API memory leak detected")
5. mark_resolved(summary="API restarted after OOM. Alert created for dev team.")

Example 2 - False alarm:
1. docker_list() → all containers running
2. prom_query(query='up{job="node-exporter"}[5m]') → see transient blip, now back
3. mark_resolved(summary="Transient scrape failure, target back up. No action needed.")

REMEMBER:
- Be efficient with queries (max 20 tool calls per investigation)
- Don't restart containers unless clearly beneficial
- When in doubt, alert humans instead of taking action
- Always provide reasoning for actions in mark_resolved()
"""

OBSERVATION_TOOLS = [
    {
        "name": "prom_query",
        "description": "Execute arbitrary PromQL query against Prometheus. Use this to check metrics, identify anomalies, or investigate trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL query string (e.g., 'up', 'rate(http_requests_total[5m])')"
                },
                "lookback": {
                    "type": "string",
                    "description": "Time range for query (e.g., '5m', '1h', '24h'). Optional, defaults to instant query.",
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "prom_list_metrics",
        "description": "List all available Prometheus metrics. Use this to discover what metrics are available for investigation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Optional regex pattern to filter metrics (e.g., 'docker_.*', 'node_memory.*')"
                }
            }
        }
    },
    {
        "name": "docker_list",
        "description": "List all containers with their status and health. Use this to get an overview of container states.",
        "input_schema": {
            "type": "object",
            "properties": {
                "all": {
                    "type": "boolean",
                    "description": "Include stopped containers (default: true)"
                }
            }
        }
    },
    {
        "name": "docker_inspect",
        "description": "Get detailed information about a specific container, including configuration, state, and optionally logs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {
                    "type": "string",
                    "description": "Container name or ID"
                },
                "include_logs": {
                    "type": "boolean",
                    "description": "Include recent container logs (default: false)"
                },
                "log_lines": {
                    "type": "integer",
                    "description": "Number of log lines to include (default: 50)"
                }
            },
            "required": ["container"]
        }
    },
    {
        "name": "docker_stats",
        "description": "Get real-time resource usage statistics for a container (CPU, memory, network, disk I/O).",
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {
                    "type": "string",
                    "description": "Container name or ID"
                }
            },
            "required": ["container"]
        }
    },
    {
        "name": "system_info",
        "description": "Get host system metrics including CPU usage, memory, disk space, and load average.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "http_check",
        "description": "Test HTTP endpoint availability and response time. Use this to verify service health.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to test (e.g., 'http://nginx-proxy-manager:81/health')"
                },
                "expected_status": {
                    "type": "integer",
                    "description": "Expected HTTP status code (default: 200)"
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers as key-value pairs"
                }
            },
            "required": ["url"]
        }
    }
]

ACTION_TOOLS = [
    {
        "name": "restart_container",
        "description": "Restart a container. This action is subject to guardrails (allowlist, cooldown, rate limits).",
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {
                    "type": "string",
                    "description": "Container name to restart"
                },
                "reason": {
                    "type": "string",
                    "description": "Clear explanation of why restart is needed (required for audit trail)"
                }
            },
            "required": ["container", "reason"]
        }
    },
    {
        "name": "create_alert",
        "description": "Send an alert to operators. Use this when human intervention is needed or to notify about issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Alert severity level"
                },
                "title": {
                    "type": "string",
                    "description": "Short alert title"
                },
                "message": {
                    "type": "string",
                    "description": "Detailed alert message"
                }
            },
            "required": ["severity", "title", "message"]
        }
    },
    {
        "name": "mark_resolved",
        "description": "Mark the current investigation as complete. Always call this when done investigating.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of findings and actions taken"
                },
                "outcome": {
                    "type": "string",
                    "enum": ["resolved", "escalated"],
                    "description": "Investigation outcome (resolved=issue fixed, escalated=needs human attention)"
                }
            },
            "required": ["summary", "outcome"]
        }
    }
]

ALL_TOOLS = OBSERVATION_TOOLS + ACTION_TOOLS


# ============================= Guardrail Enforcer =============================

class GuardrailEnforcer:
    """Enforce safety guardrails on agent actions."""
    
    def __init__(self):
        self.allowed_containers = {
            c.strip() for c in os.getenv("AI_MONITOR_ALLOWED_CONTAINERS", "").split(",") if c.strip()
        }
        self.cooldown_seconds = _env_int("AI_MONITOR_GUARDRAIL_COOLDOWN_SECONDS", 600)
        self.max_restarts_per_hour = _env_int("AI_MONITOR_GUARDRAIL_MAX_RESTARTS_PER_HOUR", 3)
        self.restart_history: Dict[str, float] = {}
        self.restart_lock = Lock()
        
        _log("info", "Guardrail enforcer initialized",
             allowed_containers=sorted(self.allowed_containers),
             cooldown_seconds=self.cooldown_seconds,
             max_restarts_per_hour=self.max_restarts_per_hour)
    
    def check_restart_container(self, container: str) -> GuardrailResult:
        """Check if container restart is allowed."""
        with self.restart_lock:
            # Check allowlist
            if self.allowed_containers and container not in self.allowed_containers:
                GUARDRAIL_BLOCKS_TOTAL.labels(action_type="restart_container", reason="not_in_allowlist").inc()
                return GuardrailResult(
                    allowed=False,
                    reason=f"Container '{container}' not in allowlist. Allowed: {sorted(self.allowed_containers)}"
                )
            
            # Check cooldown
            now = time.time()
            last_restart = self.restart_history.get(container, 0)
            if now - last_restart < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - (now - last_restart))
                GUARDRAIL_BLOCKS_TOTAL.labels(action_type="restart_container", reason="cooldown").inc()
                return GuardrailResult(
                    allowed=False,
                    reason=f"Restart cooldown active for '{container}' ({remaining}s remaining)",
                    metadata={"last_restart": last_restart, "remaining_seconds": remaining}
                )
            
            # Check rate limit (last hour)
            hour_ago = now - 3600
            recent_restarts = [t for t in self.restart_history.values() if t > hour_ago]
            if len(recent_restarts) >= self.max_restarts_per_hour:
                GUARDRAIL_BLOCKS_TOTAL.labels(action_type="restart_container", reason="rate_limit").inc()
                return GuardrailResult(
                    allowed=False,
                    reason=f"Rate limit exceeded: {len(recent_restarts)} restarts in last hour (max: {self.max_restarts_per_hour})",
                    metadata={"recent_restarts": len(recent_restarts)}
                )
            
            return GuardrailResult(allowed=True, reason="All guardrails passed")
    
    def record_restart(self, container: str) -> None:
        """Record a successful restart."""
        with self.restart_lock:
            self.restart_history[container] = time.time()
    
    def check_action(self, tool_name: str, arguments: Dict[str, Any]) -> GuardrailResult:
        """Check if any action is allowed."""
        if tool_name == "restart_container":
            return self.check_restart_container(arguments["container"])
        elif tool_name in ["create_alert", "mark_resolved"]:
            return GuardrailResult(allowed=True, reason="No guardrails for this action")
        else:
            # Observation tools are always allowed
            return GuardrailResult(allowed=True)


# ================================ Tool Executor ===============================

class ToolExecutor:
    """Execute tools called by the LLM agent."""
    
    def __init__(self, guardrails: GuardrailEnforcer):
        self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
        self.docker_client = docker.DockerClient(base_url="unix://var/run/docker.sock")
        self.guardrails = guardrails
        self.execute_mode = _env_bool("AI_MONITOR_EXECUTE", False)
    
    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return result."""
        try:
            # Check guardrails for action tools
            if tool_name in ["restart_container", "create_alert", "mark_resolved"]:
                check = self.guardrails.check_action(tool_name, arguments)
                if not check.allowed:
                    return {
                        "success": False,
                        "error": f"Guardrail blocked: {check.reason}",
                        "metadata": check.metadata
                    }
            
            # Route to appropriate handler
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
            
            result = handler(arguments)
            TOOL_CALLS_TOTAL.labels(tool_name=tool_name, success="true").inc()
            return {"success": True, "data": result}
        
        except Exception as e:
            TOOL_CALLS_TOTAL.labels(tool_name=tool_name, success="false").inc()
            _log("error", "Tool execution failed", tool=tool_name, error=str(e))
            return {"success": False, "error": str(e)}
    
    # ----------------------- Observation Tools --------------------------------
    
    def _tool_prom_query(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Prometheus query."""
        query = args["query"]
        url = f"{self.prometheus_url}/api/v1/query"
        params = {"query": query}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "success":
            raise ValueError(f"Prometheus query failed: {data.get('error')}")
        
        return {
            "query": query,
            "result": data.get("data", {}).get("result", [])
        }
    
    def _tool_prom_list_metrics(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List available Prometheus metrics."""
        url = f"{self.prometheus_url}/api/v1/label/__name__/values"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "success":
            raise ValueError(f"Failed to list metrics: {data.get('error')}")
        
        metrics = data.get("data", [])
        
        # Filter by pattern if provided
        pattern = args.get("pattern")
        if pattern:
            import re
            regex = re.compile(pattern)
            metrics = [m for m in metrics if regex.search(m)]
        
        return {
            "total_metrics": len(metrics),
            "metrics": metrics[:100]  # Limit to 100 to avoid overwhelming context
        }
    
    def _tool_docker_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List all containers."""
        all_containers = args.get("all", True)
        containers = self.docker_client.containers.list(all=all_containers)
        
        result = []
        for c in containers:
            attrs = c.attrs or {}
            state = attrs.get("State", {})
            health = state.get("Health", {}) if isinstance(state, dict) else {}
            
            result.append({
                "name": c.name,
                "status": state.get("Status"),
                "health": health.get("Status"),
                "exit_code": state.get("ExitCode"),
                "started_at": state.get("StartedAt"),
            })
        
        return {"containers": result}
    
    def _tool_docker_inspect(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Inspect a specific container."""
        container_name = args["container"]
        include_logs = args.get("include_logs", False)
        log_lines = args.get("log_lines", 50)
        
        container = self.docker_client.containers.get(container_name)
        attrs = container.attrs or {}
        state = attrs.get("State", {})
        config = attrs.get("Config", {})
        
        result = {
            "name": container.name,
            "id": container.id[:12],
            "image": config.get("Image"),
            "status": state.get("Status"),
            "exit_code": state.get("ExitCode"),
            "error": state.get("Error"),
            "oom_killed": state.get("OOMKilled"),
            "restart_count": attrs.get("RestartCount", 0),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
        }
        
        # Add health check info if available
        health = state.get("Health", {})
        if health:
            result["health"] = {
                "status": health.get("Status"),
                "failing_streak": health.get("FailingStreak", 0),
            }
        
        # Add logs if requested
        if include_logs:
            try:
                logs = container.logs(tail=log_lines, timestamps=False).decode('utf-8', errors='ignore')
                result["logs"] = logs[-4000:]  # Last 4KB
            except Exception as e:
                result["logs_error"] = str(e)
        
        return result
    
    def _tool_docker_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get container resource usage."""
        container_name = args["container"]
        container = self.docker_client.containers.get(container_name)
        
        stats = container.stats(stream=False)
        
        # Calculate CPU percentage
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                   stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                      stats["precpu_stats"]["system_cpu_usage"]
        cpu_percent = 0.0
        if system_delta > 0 and cpu_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1])) * 100
        
        # Memory stats
        mem_usage = stats["memory_stats"].get("usage", 0)
        mem_limit = stats["memory_stats"].get("limit", 1)
        mem_percent = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0
        
        return {
            "container": container_name,
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(mem_usage / (1024 * 1024), 2),
            "memory_limit_mb": round(mem_limit / (1024 * 1024), 2),
            "memory_percent": round(mem_percent, 2),
        }
    
    def _tool_system_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get host system information."""
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load = psutil.getloadavg()
        
        return {
            "cpu_percent": cpu_percent,
            "memory": {
                "total_mb": round(mem.total / (1024 * 1024), 2),
                "available_mb": round(mem.available / (1024 * 1024), 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024 ** 3), 2),
                "used_gb": round(disk.used / (1024 ** 3), 2),
                "free_gb": round(disk.free / (1024 ** 3), 2),
                "percent": disk.percent,
            },
            "load_average": {
                "1min": load[0],
                "5min": load[1],
                "15min": load[2],
            }
        }
    
    def _tool_http_check(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Test HTTP endpoint."""
        url = args["url"]
        expected_status = args.get("expected_status", 200)
        headers = args.get("headers", {})
        
        start = time.time()
        try:
            response = requests.get(url, headers=headers, timeout=5)
            latency_ms = int((time.time() - start) * 1000)
            
            return {
                "url": url,
                "status_code": response.status_code,
                "expected_status": expected_status,
                "ok": response.status_code == expected_status,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            return {
                "url": url,
                "ok": False,
                "error": str(e),
            }
    
    # -------------------------- Action Tools ----------------------------------
    
    def _tool_restart_container(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Restart a container."""
        container_name = args["container"]
        reason = args["reason"]
        
        if not self.execute_mode:
            _log("info", "DRY RUN: Would restart container",
                 container=container_name, reason=reason)
            return {
                "dry_run": True,
                "container": container_name,
                "reason": reason,
                "message": "Restart skipped (AI_MONITOR_EXECUTE=false)"
            }
        
        container = self.docker_client.containers.get(container_name)
        container.restart(timeout=10)
        
        self.guardrails.record_restart(container_name)
        ACTIONS_TAKEN_TOTAL.labels(action_type="restart_container").inc()
        
        _log("warn", "Container restarted by agent",
             container=container_name, reason=reason)
        
        return {
            "container": container_name,
            "reason": reason,
            "restarted": True,
        }
    
    def _tool_create_alert(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create an alert."""
        severity = args["severity"]
        title = args["title"]
        message = args["message"]
        
        ACTIONS_TAKEN_TOTAL.labels(action_type="create_alert").inc()
        
        _log("warn", "Agent alert created",
             severity=severity, title=title, message=message)
        
        # TODO: Integrate with alerting system (Slack, PagerDuty, etc.)
        return {
            "alert_created": True,
            "severity": severity,
            "title": title,
        }
    
    def _tool_mark_resolved(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mark investigation resolved."""
        summary = args["summary"]
        outcome = args["outcome"]
        
        return {
            "resolved": True,
            "summary": summary,
            "outcome": outcome,
        }


# ============================= Trigger Detector ===============================

class TriggerDetector:
    """Detect state changes that warrant investigation."""
    
    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor
        self.last_state: Dict[str, Any] = {}
    
    def check_triggers(self) -> List[str]:
        """Return list of triggers for agent to investigate."""
        triggers = []
        
        # Get current container states
        current = self.tool_executor.execute("docker_list", {"all": True})
        if not current.get("success"):
            return triggers
        
        current_containers = {
            c["name"]: c for c in current["data"]["containers"]
        }
        prev_containers = self.last_state.get("containers", {})
        
        # Detect container state changes
        for name, state in current_containers.items():
            prev = prev_containers.get(name, {})
            
            # Health status change
            if state.get("health") != prev.get("health"):
                if state.get("health") == "unhealthy":
                    triggers.append(f"Container '{name}' became unhealthy")
            
            # Status change
            if state.get("status") != prev.get("status"):
                if state.get("status") == "exited":
                    triggers.append(f"Container '{name}' exited unexpectedly")
                elif state.get("status") == "running" and prev.get("status") == "exited":
                    _log("info", "Container recovered", container=name)
        
        # Update state for next iteration
        self.last_state["containers"] = current_containers
        
        return triggers


# ================================ Agent Monitor ===============================

class AgentMonitor:
    """LLM-driven monitoring agent with tool calling."""
    
    def __init__(self):
        # LLM setup
        self.claude_api_key = os.getenv("CLAUDE_API_KEY")
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        self.use_claude = bool(self.claude_api_key and ANTHROPIC_AVAILABLE)
        
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        self.use_gemini = bool(self.gemini_api_key and GEMINI_AVAILABLE and not self.use_claude)
        
        if self.use_claude:
            self._anthropic_client = Anthropic(api_key=self.claude_api_key)
        elif self.use_gemini:
            genai.configure(api_key=self.gemini_api_key)
            self._gemini_model = genai.GenerativeModel(self.gemini_model)
        
        # Components
        self.guardrails = GuardrailEnforcer()
        self.tool_executor = ToolExecutor(self.guardrails)
        self.trigger_detector = TriggerDetector(self.tool_executor)
        
        # Config
        self.interval_seconds = _env_int("AI_MONITOR_INTERVAL_SECONDS", 60)
        self.max_tool_calls = _env_int("AI_MONITOR_MAX_TOOL_CALLS", 20)
        self.max_investigation_time = _env_int("AI_MONITOR_MAX_INVESTIGATION_TIME_SECONDS", 300)
        self.incident_dir = os.getenv("AI_MONITOR_INCIDENT_REPORTS_DIR", "/app/incidents")
        
        _log("info", "Agent monitor initialized",
             llm_backend="claude" if self.use_claude else "gemini" if self.use_gemini else "none",
             max_tool_calls=self.max_tool_calls,
             execute_mode=self.tool_executor.execute_mode)
    
    def investigate(self, trigger: str) -> Investigation:
        """
        Investigate a trigger using LLM with tool calling.
        
        The LLM iteratively calls tools to understand the issue and take action.
        Returns complete investigation report with audit trail.
        """
        investigation = Investigation(
            trigger=trigger,
            start_time=time.time()
        )
        
        ACTIVE_INVESTIGATIONS.inc()
        
        try:
            if self.use_claude:
                self._investigate_claude(investigation)
            elif self.use_gemini:
                self._investigate_gemini(investigation)
            else:
                investigation.outcome = "error"
                investigation.findings = "No LLM backend configured"
        
        except Exception as e:
            investigation.outcome = "error"
            investigation.findings = f"Investigation failed: {str(e)}"
            _log("error", "Investigation failed", trigger=trigger, error=str(e))
        
        finally:
            investigation.end_time = time.time()
            duration = investigation.end_time - investigation.start_time
            
            ACTIVE_INVESTIGATIONS.dec()
            INVESTIGATION_DURATION.observe(duration)
            LLM_ITERATIONS.observe(investigation.llm_iterations)
            INVESTIGATIONS_TOTAL.labels(
                trigger_type=trigger.split()[0],  # First word as type
                outcome=investigation.outcome
            ).inc()
            
            _log("info", "Investigation complete",
                 trigger=trigger,
                 outcome=investigation.outcome,
                 duration_seconds=round(duration, 2),
                 tool_calls=len(investigation.tool_calls),
                 actions_taken=len(investigation.actions_taken))
            
            self._save_investigation_report(investigation)
        
        return investigation
    
    def _investigate_claude(self, investigation: Investigation) -> None:
        """Run investigation using Claude."""
        messages = [
            {
                "role": "user",
                "content": f"Investigate this trigger: {investigation.trigger}"
            }
        ]
        
        while investigation.llm_iterations < self.max_tool_calls:
            investigation.llm_iterations += 1
            
            # Check timeout
            if time.time() - investigation.start_time > self.max_investigation_time:
                investigation.outcome = "timeout"
                investigation.findings = f"Investigation timeout after {self.max_investigation_time}s"
                return
            
            # Call Claude with tools
            response = self._anthropic_client.messages.create(
                model=self.claude_model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=ALL_TOOLS,
            )
            
            # Check if Claude wants to use tools
            if response.stop_reason == "tool_use":
                # Execute tools and add results to messages
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_call = ToolCall(
                            id=content_block.id,
                            name=content_block.name,
                            arguments=content_block.input
                        )
                        
                        # Execute tool
                        result = self.tool_executor.execute(
                            content_block.name,
                            content_block.input
                        )
                        tool_call.result = result
                        investigation.tool_calls.append(tool_call)
                        
                        # Track actions
                        if content_block.name in ["restart_container", "create_alert"]:
                            investigation.actions_taken.append(
                                f"{content_block.name}({content_block.input})"
                            )
                        
                        # Check for mark_resolved
                        if content_block.name == "mark_resolved":
                            investigation.outcome = result.get("data", {}).get("outcome", "resolved")
                            investigation.findings = result.get("data", {}).get("summary", "")
                            return
                
                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": json.dumps(tc.result)
                        }
                        for tc in investigation.tool_calls
                        if tc.id in [b.id for b in response.content if hasattr(b, 'id')]
                    ]
                })
                continue
            
            # Claude concluded without mark_resolved
            investigation.outcome = "resolved"
            investigation.findings = response.content[0].text if response.content else "No findings"
            return
        
        # Max iterations reached
        investigation.outcome = "timeout"
        investigation.findings = f"Max tool calls ({self.max_tool_calls}) reached"
    
    def _investigate_gemini(self, investigation: Investigation) -> None:
        """Run investigation using Gemini (placeholder)."""
        # TODO: Implement Gemini function calling
        investigation.outcome = "error"
        investigation.findings = "Gemini integration not yet implemented"
    
    def _save_investigation_report(self, investigation: Investigation) -> None:
        """Save investigation report to file."""
        try:
            os.makedirs(self.incident_dir, exist_ok=True)
            
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{self.incident_dir}/investigation_{timestamp}.md"
            
            duration = (investigation.end_time or time.time()) - investigation.start_time
            
            report = f"""# Investigation Report
**Time:** {datetime.fromtimestamp(investigation.start_time, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Trigger:** {investigation.trigger}  
**Outcome:** {investigation.outcome}  
**Duration:** {duration:.1f}s  
**LLM Iterations:** {investigation.llm_iterations}  
**Tool Calls:** {len(investigation.tool_calls)}

## Findings
{investigation.findings}

## Actions Taken
"""
            if investigation.actions_taken:
                for action in investigation.actions_taken:
                    report += f"- {action}\n"
            else:
                report += "(none)\n"
            
            report += "\n## Tool Call Trace\n"
            for i, tc in enumerate(investigation.tool_calls, 1):
                report += f"\n### {i}. {tc.name}\n"
                report += f"**Arguments:**\n```json\n{json.dumps(tc.arguments, indent=2)}\n```\n"
                if tc.result:
                    report += f"**Result:**\n```json\n{json.dumps(tc.result, indent=2)}\n```\n"
            
            with open(filename, 'w') as f:
                f.write(report)
            
            _log("info", "Investigation report saved", filename=filename)
        
        except Exception as e:
            _log("error", "Failed to save investigation report", error=str(e))
    
    def run_once(self) -> None:
        """Execute one monitoring cycle."""
        triggers = self.trigger_detector.check_triggers()
        
        if not triggers:
            _log("debug", "No triggers detected")
            return
        
        _log("info", "Triggers detected", count=len(triggers), triggers=triggers)
        
        # Investigate each trigger
        for trigger in triggers:
            self.investigate(trigger)
    
    def run_forever(self) -> None:
        """Run monitoring loop forever."""
        # Start Prometheus metrics server
        metrics_port = _env_int("AI_MONITOR_METRICS_PORT", 8000)
        Thread(target=start_http_server, args=(metrics_port,), daemon=True).start()
        _log("info", "Prometheus metrics server started", port=metrics_port)
        
        _log("info", "Agent monitor starting",
             llm_backend="claude" if self.use_claude else "gemini" if self.use_gemini else "none",
             interval_seconds=self.interval_seconds)
        
        while True:
            try:
                self.run_once()
            except Exception as e:
                _log("error", "Monitor loop error", error=str(e))
            
            time.sleep(self.interval_seconds)


if __name__ == "__main__":
    AgentMonitor().run_forever()
