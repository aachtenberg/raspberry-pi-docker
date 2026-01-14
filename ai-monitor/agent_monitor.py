"""
AI Agent-Based Monitor with Tool Calling and Guardrails.

This module implements an LLM-driven monitoring agent that:
1. Detects state changes (triggers)
2. Investigates using observation tools (Prometheus, Docker APIs)
3. Takes remediation actions within guardrails
4. Verifies actions succeeded (closed-loop)
5. Stores learnings in knowledge base
6. Provides full audit trail of investigations
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from threading import Thread, Lock

import docker
import requests
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Import knowledge base
try:
    from knowledge_base import KnowledgeBase, SQLALCHEMY_AVAILABLE
    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False
    KnowledgeBase = None

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

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

try:
    import adbc_driver_flightsql.dbapi as flightsql
    INFLUXDB_AVAILABLE = True
except ImportError:
    INFLUXDB_AVAILABLE = False


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


# ============================= Tool Call History ==============================

# Global tool call history (last 500 calls)
TOOL_CALL_HISTORY: List[Dict[str, Any]] = []
TOOL_CALL_HISTORY_LOCK = Lock()
MAX_TOOL_CALL_HISTORY = 500


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
    duration_ms: Optional[float] = None
    success: bool = True


@dataclass
class ActionTaken:
    """Represents an action taken during investigation."""
    action_type: str
    target: Optional[str]
    parameters: Dict[str, Any]
    timestamp: float
    success: bool
    error: Optional[str] = None
    resolved_incident: bool = False


@dataclass
class VerificationCheck:
    """Represents a verification check after an action."""
    check_type: str
    description: str
    timestamp: float
    passed: bool
    details: Dict[str, Any]


@dataclass
class Investigation:
    """Complete investigation report."""
    trigger: str
    trigger_type: str
    start_time: float
    end_time: Optional[float] = None
    outcome: str = "in_progress"  # in_progress, resolved, escalated, timeout, error
    findings: str = ""
    root_cause: Optional[str] = None
    resolution_summary: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    actions_taken: List[ActionTaken] = field(default_factory=list)
    verifications: List[VerificationCheck] = field(default_factory=list)
    llm_iterations: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class GuardrailResult(BaseModel):
    """Result of guardrail check."""
    allowed: bool
    reason: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================== Tool Definitions ==============================

SYSTEM_PROMPT = """You are an autonomous SRE agent monitoring a Raspberry Pi Docker infrastructure.

MISSION:
- Figure out issues on your own using available data - no rigid rules
- Learn from past incidents to improve future resolutions
- Take confident action when historical data supports it
- Escalate only when truly uncertain

CRITICAL: CHECK KNOWLEDGE BASE FIRST
Before investigating manually, ALWAYS:
1. query_knowledge_base() - Have we seen this before?
2. get_runbook() - Is there a learned procedure?
3. check_action_confidence() - What's the success rate for proposed actions?

TOOLS AVAILABLE:

Knowledge tools (use FIRST):
- query_knowledge_base: Search past incidents for similar issues
- get_runbook: Get learned step-by-step procedures
- check_action_confidence: Check historical success rate for actions
- get_incident_trends: Analyze patterns over time

Observation tools (read-only):
- prom_query: Execute PromQL queries
- prom_list_metrics: List available Prometheus metrics
- docker_list: List all containers with status
- docker_inspect: Get detailed container info and logs
- docker_stats: Get real-time resource usage
- system_info: Get host system metrics
- http_check: Test HTTP endpoint availability
- mqtt_subscribe: Listen to MQTT topics
- mqtt_inspect: Get MQTT broker stats
- influxdb_query: Query InfluxDB data
- influxdb_list: List InfluxDB databases/tables

Action tools (guardrailed):
- restart_container: Restart a container (confidence-based execution)
- create_alert: Send alert to operators
- mark_resolved: Conclude investigation

AUTONOMOUS WORKFLOW:
1. ORIENT: query_knowledge_base() to check if we've seen this before
2. PLAN: If runbook exists, follow it. Otherwise, investigate.
3. DECIDE: check_action_confidence() before taking action
   - High confidence (>85%): Execute automatically
   - Medium confidence (50-85%): Proceed with caution
   - Low confidence (<50%): Consider escalating
4. ACT: Take action if confident, otherwise gather more data
5. VERIFY: System will auto-verify actions succeeded
6. LEARN: Your actions are recorded for future learning

GUARDRAILS (ENFORCED BY SYSTEM):
- Container allowlist enforced
- Restart cooldown: 10 minutes per container
- Max 3 restarts per hour globally
- Confidence-based execution thresholds

INVESTIGATION APPROACH:
- Don't follow rigid patterns - figure out what's actually wrong
- Use metrics, logs, and data to form hypotheses
- Test hypotheses with targeted queries
- Trust historical success rates for action decisions
- When evidence supports action, take it confidently

EXAMPLES:

Example 1 - Known issue (use knowledge base):
1. query_knowledge_base(query="influxdb unhealthy") → Found 3 similar resolved incidents
2. get_runbook(pattern="container_unhealthy") → Steps: inspect, check logs, restart
3. check_action_confidence(action="restart_container", target="influxdb3-core") → 92% success
4. restart_container(container="influxdb3-core", reason="Historical 92% success rate for this issue")
5. mark_resolved(summary="Applied learned resolution from knowledge base. 92% confidence.")

Example 2 - New issue (investigate fresh):
1. query_knowledge_base(query="telegraf memory") → No similar incidents found
2. docker_inspect(container="telegraf", include_logs=true) → Memory at 95%
3. prom_query(query='container_memory_usage_bytes{name="telegraf"}[1h]') → Gradual increase
4. check_action_confidence(action="restart_container", target="telegraf") → 50% (limited data)
5. restart_container(container="telegraf", reason="Memory exhaustion, restart to restore")
6. create_alert(severity="medium", title="Telegraf memory leak - needs investigation")
7. mark_resolved(summary="Restarted telegraf due to memory exhaustion. Alert created for root cause analysis.")

Example 3 - False alarm:
1. query_knowledge_base(query="prometheus target down") → Similar: 5 transient failures, all self-resolved
2. prom_query(query='up{job="node-exporter"}') → Target is up now
3. mark_resolved(summary="Transient scrape failure matching known pattern. Self-resolved, no action needed.")

REMEMBER:
- The knowledge base is your memory - use it!
- Historical success rates should guide your confidence
- Be efficient (max 20 tool calls) but thorough
- Every investigation improves the knowledge base for next time
"""

OBSERVATION_TOOLS = [
    # ====================== Knowledge Base Tools (Phase 3) ======================
    {
        "name": "query_knowledge_base",
        "description": "Search past incidents and resolutions. Use this FIRST to check if we've seen this issue before. Returns matching incidents with their outcomes, root causes, and what actions resolved them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search (e.g., 'influxdb authentication error', 'container OOM killed', 'prometheus scrape failures')"
                },
                "trigger_type": {
                    "type": "string",
                    "description": "Optional filter by trigger type (container_unhealthy, container_exited, prometheus_target_down, scrape_quality_degraded)"
                },
                "outcome": {
                    "type": "string",
                    "enum": ["resolved", "escalated", "timeout", "error"],
                    "description": "Optional filter by outcome"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default: 5)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_runbook",
        "description": "Retrieve a learned runbook for a pattern. Runbooks are auto-generated from successful incident resolutions and contain step-by-step procedures.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Pattern to look up (e.g., 'container_unhealthy', 'influxdb', 'prometheus_target_down')"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "check_action_confidence",
        "description": "Check confidence score for a proposed action based on historical success. Returns recommendation on whether to auto-execute, request approval, or escalate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "The action type (e.g., 'restart_container')"
                },
                "target": {
                    "type": "string",
                    "description": "Target of the action (e.g., container name)"
                },
                "trigger_type": {
                    "type": "string",
                    "description": "The trigger type for this investigation"
                }
            },
            "required": ["action_type", "target", "trigger_type"]
        }
    },
    {
        "name": "get_incident_trends",
        "description": "Get incident trends and statistics over a time period. Useful for understanding if issues are recurring or getting worse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default: 7)"
                }
            }
        }
    },
    # ====================== Prometheus Tools ======================
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
    },
    {
        "name": "mqtt_subscribe",
        "description": "Subscribe to MQTT topic(s) and receive messages. Use this to inspect live data from sensors, check message formats, or diagnose publishing issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "MQTT topics to subscribe to (supports wildcards: # for multi-level, + for single-level)"
                },
                "duration_seconds": {
                    "type": "integer",
                    "description": "How long to listen for messages (default: 5, max: 30)"
                },
                "max_messages": {
                    "type": "integer",
                    "description": "Maximum messages to collect (default: 20)"
                }
            },
            "required": ["topics"]
        }
    },
    {
        "name": "mqtt_inspect",
        "description": "Get MQTT broker statistics and connection info. Use this to check broker health, client connections, and message throughput.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "influxdb_query",
        "description": "Execute FlightSQL query against InfluxDB 3 Core. Use this to check data freshness, validate schemas, investigate missing data, or analyze time-series patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name to query"
                },
                "query": {
                    "type": "string",
                    "description": "SQL query to execute (e.g., 'SELECT * FROM temperature LIMIT 10')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Row limit to prevent overwhelming context (default: 50, max: 200)"
                }
            },
            "required": ["database", "query"]
        }
    },
    {
        "name": "influxdb_list",
        "description": "List databases, tables, or schema information from InfluxDB 3 Core. Use this to discover what data exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "show": {
                    "type": "string",
                    "enum": ["databases", "tables", "columns"],
                    "description": "What to list (databases, tables in a database, or columns in a table)"
                },
                "database": {
                    "type": "string",
                    "description": "Database name (required for 'tables' and 'columns')"
                },
                "table": {
                    "type": "string",
                    "description": "Table name (required for 'columns')"
                }
            },
            "required": ["show"]
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
    """Enforce safety guardrails on agent actions with confidence-based execution."""

    # Confidence thresholds for autonomous execution
    HIGH_CONFIDENCE_THRESHOLD = 0.85  # Auto-execute
    MEDIUM_CONFIDENCE_THRESHOLD = 0.5  # Proceed with caution
    # Below MEDIUM = escalate/alert

    def __init__(self):
        self.allowed_containers = {
            c.strip() for c in os.getenv("AI_MONITOR_ALLOWED_CONTAINERS", "").split(",") if c.strip()
        }
        self.cooldown_seconds = _env_int("AI_MONITOR_GUARDRAIL_COOLDOWN_SECONDS", 600)
        self.max_restarts_per_hour = _env_int("AI_MONITOR_GUARDRAIL_MAX_RESTARTS_PER_HOUR", 3)
        self.restart_history: Dict[str, float] = {}
        self.restart_lock = Lock()

        # Knowledge base reference for confidence checks
        self.knowledge_base = None

        # Current investigation context (set during investigation)
        self.current_trigger_type: Optional[str] = None

        _log("info", "Guardrail enforcer initialized",
             allowed_containers=sorted(self.allowed_containers),
             cooldown_seconds=self.cooldown_seconds,
             max_restarts_per_hour=self.max_restarts_per_hour,
             high_confidence_threshold=self.HIGH_CONFIDENCE_THRESHOLD,
             medium_confidence_threshold=self.MEDIUM_CONFIDENCE_THRESHOLD)

    def set_knowledge_base(self, kb) -> None:
        """Set knowledge base reference for confidence calculations."""
        self.knowledge_base = kb

    def set_investigation_context(self, trigger_type: str) -> None:
        """Set current investigation context for confidence calculations."""
        self.current_trigger_type = trigger_type

    def check_restart_container(self, container: str) -> GuardrailResult:
        """Check if container restart is allowed with confidence-based execution."""
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

            # Calculate confidence score if knowledge base available
            confidence = 0.5  # Default medium confidence
            confidence_reason = "default"

            if self.knowledge_base and self.current_trigger_type:
                confidence = self.knowledge_base.calculate_action_confidence(
                    action_type="restart_container",
                    target=container,
                    trigger_type=self.current_trigger_type
                )
                confidence_reason = "historical_data"

            # Log confidence level
            if confidence >= self.HIGH_CONFIDENCE_THRESHOLD:
                confidence_level = "high"
            elif confidence >= self.MEDIUM_CONFIDENCE_THRESHOLD:
                confidence_level = "medium"
            else:
                confidence_level = "low"

            _log("info", "Restart confidence calculated",
                 container=container,
                 confidence=confidence,
                 confidence_level=confidence_level,
                 trigger_type=self.current_trigger_type)

            return GuardrailResult(
                allowed=True,
                reason=f"All guardrails passed. Confidence: {confidence:.2f} ({confidence_level})",
                metadata={
                    "confidence": confidence,
                    "confidence_level": confidence_level,
                    "confidence_reason": confidence_reason
                }
            )

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
        start_time = time.time()
        success = False
        result_data = None
        error_msg = None
        
        try:
            # Check guardrails for action tools
            if tool_name in ["restart_container", "create_alert", "mark_resolved"]:
                check = self.guardrails.check_action(tool_name, arguments)
                if not check.allowed:
                    error_msg = f"Guardrail blocked: {check.reason}"
                    return {
                        "success": False,
                        "error": error_msg,
                        "metadata": check.metadata
                    }
            
            # Route to appropriate handler
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                error_msg = f"Unknown tool: {tool_name}"
                return {"success": False, "error": error_msg}
            
            result_data = handler(arguments)
            success = True
            TOOL_CALLS_TOTAL.labels(tool_name=tool_name, success="true").inc()
            return {"success": True, "data": result_data}
        
        except Exception as e:
            error_msg = str(e)
            TOOL_CALLS_TOTAL.labels(tool_name=tool_name, success="false").inc()
            _log("error", "Tool execution failed", tool=tool_name, error=error_msg)
            return {"success": False, "error": error_msg}
        
        finally:
            # Record tool call in history
            duration_ms = int((time.time() - start_time) * 1000)
            self._record_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                success=success,
                result=result_data,
                error=error_msg,
                duration_ms=duration_ms
            )
    
    def _record_tool_call(self, tool_name: str, arguments: Dict[str, Any], 
                          success: bool, result: Any, error: Optional[str], 
                          duration_ms: int) -> None:
        """Record tool call in global history."""
        global TOOL_CALL_HISTORY
        
        # Truncate large results/errors for history
        result_preview = None
        if result:
            result_str = json.dumps(result, default=str)
            result_preview = result_str[:500] + "..." if len(result_str) > 500 else result_str
        
        error_preview = error[:200] if error else None
        
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
            "result_preview": result_preview,
            "error": error_preview,
            "duration_ms": duration_ms
        }
        
        with TOOL_CALL_HISTORY_LOCK:
            TOOL_CALL_HISTORY.append(record)
            # Keep only last MAX_TOOL_CALL_HISTORY calls
            if len(TOOL_CALL_HISTORY) > MAX_TOOL_CALL_HISTORY:
                TOOL_CALL_HISTORY.pop(0)
    
    # Reference to knowledge base (set by AgentMonitor)
    knowledge_base = None

    def set_knowledge_base(self, kb) -> None:
        """Set reference to knowledge base for knowledge tools."""
        self.knowledge_base = kb

    # ----------------------- Knowledge Base Tools (Phase 3) ------------------

    def _tool_query_knowledge_base(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search past incidents in knowledge base."""
        if not self.knowledge_base:
            return {"error": "Knowledge base not available", "incidents": []}

        query = args["query"]
        trigger_type = args.get("trigger_type")
        outcome = args.get("outcome")
        limit = args.get("limit", 5)

        incidents = self.knowledge_base.query_incidents(
            query=query,
            trigger_type=trigger_type,
            outcome=outcome,
            limit=limit
        )

        return {
            "query": query,
            "results_count": len(incidents),
            "incidents": incidents,
            "message": f"Found {len(incidents)} matching incidents" if incidents else "No similar incidents found - this may be a new issue type"
        }

    def _tool_get_runbook(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve runbook for a pattern."""
        if not self.knowledge_base:
            return {"error": "Knowledge base not available", "runbook": None}

        pattern = args["pattern"]
        runbook = self.knowledge_base.get_runbook(pattern)

        if runbook:
            return {
                "found": True,
                "runbook": runbook,
                "message": f"Found runbook with {len(runbook.get('steps', []))} steps, {runbook.get('success_rate', 0)*100:.0f}% success rate"
            }
        else:
            return {
                "found": False,
                "runbook": None,
                "message": f"No runbook found for pattern '{pattern}'. Investigate manually and a runbook will be auto-generated after 3+ successful resolutions."
            }

    def _tool_check_action_confidence(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Check confidence for proposed action."""
        if not self.knowledge_base:
            return {
                "confidence": 0.5,
                "recommendation": "request_approval",
                "reason": "Knowledge base not available - defaulting to medium confidence"
            }

        action_type = args["action_type"]
        target = args["target"]
        trigger_type = args["trigger_type"]

        recommendation = self.knowledge_base.get_action_recommendation(
            action_type=action_type,
            target=target,
            trigger_type=trigger_type
        )

        return recommendation

    def _tool_get_incident_trends(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get incident trends over time period."""
        if not self.knowledge_base:
            return {"error": "Knowledge base not available"}

        days = args.get("days", 7)
        trends = self.knowledge_base.get_incident_trends(days=days)

        return trends

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
    
    def _tool_mqtt_subscribe(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Subscribe to MQTT topics and collect messages."""
        if not MQTT_AVAILABLE:
            return {"error": "MQTT client not available (paho-mqtt not installed)"}
        
        topics = args["topics"]
        duration = min(args.get("duration_seconds", 5), 30)
        max_messages = min(args.get("max_messages", 20), 100)
        
        mqtt_host = os.getenv("MQTT_HOST", "mosquitto")
        mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
        
        messages = []
        received_event = Lock()
        
        def on_message(client, userdata, msg):
            if len(messages) < max_messages:
                try:
                    payload = msg.payload.decode('utf-8')
                    messages.append({
                        "topic": msg.topic,
                        "payload": payload,
                        "qos": msg.qos,
                        "retain": msg.retain,
                        "timestamp": time.time()
                    })
                except Exception as e:
                    messages.append({
                        "topic": msg.topic,
                        "error": f"Failed to decode: {e}",
                        "payload_hex": msg.payload.hex()[:200]
                    })
        
        try:
            client = mqtt.Client()
            client.on_message = on_message
            client.connect(mqtt_host, mqtt_port, 60)
            
            for topic in topics:
                client.subscribe(topic)
            
            client.loop_start()
            time.sleep(duration)
            client.loop_stop()
            client.disconnect()
            
            return {
                "topics": topics,
                "duration_seconds": duration,
                "messages_received": len(messages),
                "messages": messages
            }
        except Exception as e:
            return {"error": f"MQTT connection failed: {e}"}
    
    def _tool_mqtt_inspect(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get MQTT broker stats via $SYS topics."""
        if not MQTT_AVAILABLE:
            return {"error": "MQTT client not available"}
        
        mqtt_host = os.getenv("MQTT_HOST", "mosquitto")
        mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
        
        stats = {}
        
        def on_message(client, userdata, msg):
            try:
                stats[msg.topic] = msg.payload.decode('utf-8')
            except:
                pass
        
        try:
            client = mqtt.Client()
            client.on_message = on_message
            client.connect(mqtt_host, mqtt_port, 60)
            client.subscribe("$SYS/#")
            
            client.loop_start()
            time.sleep(2)
            client.loop_stop()
            client.disconnect()
            
            # Parse key metrics
            result = {
                "broker": mqtt_host,
                "uptime": stats.get("$SYS/broker/uptime"),
                "clients_connected": stats.get("$SYS/broker/clients/connected"),
                "clients_total": stats.get("$SYS/broker/clients/total"),
                "messages_received": stats.get("$SYS/broker/messages/received"),
                "messages_sent": stats.get("$SYS/broker/messages/sent"),
                "subscriptions": stats.get("$SYS/broker/subscriptions/count"),
                "retained_messages": stats.get("$SYS/broker/retained messages/count"),
                "all_stats": stats
            }
            return result
        except Exception as e:
            return {"error": f"Failed to inspect broker: {e}"}
    
    def _tool_influxdb_query(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute FlightSQL query against InfluxDB 3."""
        if not INFLUXDB_AVAILABLE:
            return {"error": "InfluxDB FlightSQL driver not available"}
        
        database = args["database"]
        query = args["query"]
        limit = min(args.get("limit", 50), 200)
        
        influxdb_host = os.getenv("INFLUXDB3_HOST", "influxdb3-core")
        influxdb_port = int(os.getenv("INFLUXDB3_GRPC_PORT", "8182"))
        token = os.getenv("INFLUXDB3_ADMIN_TOKEN", "")
        
        if not token:
            return {"error": "INFLUXDB3_ADMIN_TOKEN not set"}
        
        # Add LIMIT if not present
        query_lower = query.lower()
        if "limit" not in query_lower:
            query = f"{query} LIMIT {limit}"
        
        try:
            uri = f"grpc://{influxdb_host}:{influxdb_port}"
            conn = flightsql.connect(
                uri,
                db_kwargs={
                    "username": "ignored",
                    "password": token,
                    "adbc.flight.sql.rpc.call_header.database": database
                }
            )
            
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Convert rows to dicts
            results = []
            for row in rows[:limit]:
                results.append(dict(zip(columns, row)))
            
            cursor.close()
            conn.close()
            
            return {
                "database": database,
                "query": query,
                "rows_returned": len(results),
                "columns": columns,
                "data": results
            }
        except Exception as e:
            return {"error": f"Query failed: {e}"}
    
    def _tool_influxdb_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List InfluxDB databases, tables, or schema."""
        if not INFLUXDB_AVAILABLE:
            return {"error": "InfluxDB FlightSQL driver not available"}
        
        show = args["show"]
        database = args.get("database")
        table = args.get("table")
        
        influxdb_host = os.getenv("INFLUXDB3_HOST", "influxdb3-core")
        influxdb_port = int(os.getenv("INFLUXDB3_GRPC_PORT", "8182"))
        token = os.getenv("INFLUXDB3_ADMIN_TOKEN", "")
        
        if not token:
            return {"error": "INFLUXDB3_ADMIN_TOKEN not set"}
        
        try:
            uri = f"grpc://{influxdb_host}:{influxdb_port}"
            conn = flightsql.connect(
                uri,
                db_kwargs={
                    "username": "ignored",
                    "password": token
                }
            )
            
            cursor = conn.cursor()
            
            if show == "databases":
                cursor.execute("SHOW DATABASES")
                rows = cursor.fetchall()
                result = {"databases": [row[0] for row in rows]}
            
            elif show == "tables":
                if not database:
                    return {"error": "database parameter required for show=tables"}
                cursor.adbc_connection.set_options(**{"adbc.flight.sql.rpc.call_header.database": database})
                cursor.execute("SHOW TABLES")
                rows = cursor.fetchall()
                result = {"database": database, "tables": [row[0] for row in rows]}
            
            elif show == "columns":
                if not database or not table:
                    return {"error": "database and table parameters required for show=columns"}
                cursor.adbc_connection.set_options(**{"adbc.flight.sql.rpc.call_header.database": database})
                cursor.execute(f"DESCRIBE {table}")
                rows = cursor.fetchall()
                columns = []
                for row in rows:
                    columns.append({
                        "name": row[0],
                        "type": row[1] if len(row) > 1 else None
                    })
                result = {"database": database, "table": table, "columns": columns}
            
            else:
                result = {"error": f"Unknown show option: {show}"}
            
            cursor.close()
            conn.close()
            
            return result
        except Exception as e:
            return {"error": f"List operation failed: {e}"}
    
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
        
        # Check Prometheus metrics for degraded services
        triggers.extend(self._check_prometheus_triggers())
        
        # Update state for next iteration
        self.last_state["containers"] = current_containers
        
        return triggers
    
    def _check_prometheus_triggers(self) -> List[str]:
        """Check Prometheus metrics for issues that warrant investigation."""
        triggers = []
        
        try:
            # 1. Scrape failures: target is "up" but scraping is broken
            scrape_result = self.tool_executor.execute("prom_query", {
                "query": "up{job!=\"\"} == 1 and (scrape_samples_scraped < 5 or scrape_duration_seconds > 5)"
            })
            if scrape_result.get("success") and scrape_result["data"].get("result"):
                for series in scrape_result["data"]["result"]:
                    job = series.get("metric", {}).get("job", "unknown")
                    instance = series.get("metric", {}).get("instance", "unknown")
                    triggers.append(f"Scrape quality degraded for {job} ({instance})")
            
            # 2. Targets completely down
            down_result = self.tool_executor.execute("prom_query", {
                "query": "up == 0"
            })
            if down_result.get("success") and down_result["data"].get("result"):
                for series in down_result["data"]["result"]:
                    job = series.get("metric", {}).get("job", "unknown")
                    instance = series.get("metric", {}).get("instance", "unknown")
                    prev_key = f"down_{job}_{instance}"
                    
                    # Only trigger if this is a new failure (not already down)
                    if not self.last_state.get(prev_key):
                        triggers.append(f"Target down: {job} ({instance})")
                        self.last_state[prev_key] = time.time()
                    # Clear state if target recovered
                    elif prev_key in self.last_state:
                        del self.last_state[prev_key]
            
            # 3. Recent container restarts
            restart_result = self.tool_executor.execute("prom_query", {
                "query": "changes(container_last_seen[5m]) > 0"
            })
            if restart_result.get("success") and restart_result["data"].get("result"):
                for series in restart_result["data"]["result"]:
                    container = series.get("metric", {}).get("name", "unknown")
                    triggers.append(f"Container '{container}' restarted recently")
        
        except Exception as e:
            _log("error", "Failed to check Prometheus triggers", error=str(e))
        
        return triggers


# ================================ Agent Monitor ===============================

class AgentMonitor:
    """LLM-driven monitoring agent with tool calling."""
    
    def __init__(self):
        # Load user preference from state file
        incident_dir = os.getenv("AI_MONITOR_INCIDENT_REPORTS_DIR", "/app/incidents")
        state_file = Path(incident_dir) / "incidents_state.json"
        preferred_backend = "auto"
        
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                preferred_backend = state.get("_preferences", {}).get("llm_backend", "auto")
                _log("info", "Loaded LLM preference from state", preference=preferred_backend)
            except Exception as e:
                _log("warn", "Failed to load state file", error=str(e))
        
        # LLM setup
        self.claude_api_key = os.getenv("CLAUDE_API_KEY")
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        claude_available = bool(self.claude_api_key and ANTHROPIC_AVAILABLE)
        
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        gemini_available = bool(self.gemini_api_key and GEMINI_AVAILABLE)
        
        # Respect user preference
        if preferred_backend == "claude" and claude_available:
            self.use_claude = True
            self.use_gemini = False
        elif preferred_backend == "gemini" and gemini_available:
            self.use_claude = False
            self.use_gemini = True
        elif preferred_backend == "auto":
            # Default: Claude priority if both available
            self.use_claude = claude_available
            self.use_gemini = gemini_available and not claude_available
        else:
            self.use_claude = False
            self.use_gemini = False
        
        if self.use_claude:
            self._anthropic_client = Anthropic(api_key=self.claude_api_key)
        elif self.use_gemini:
            genai.configure(api_key=self.gemini_api_key)
            self._gemini_model = genai.GenerativeModel(self.gemini_model)
        
        # Components
        self.guardrails = GuardrailEnforcer()
        self.tool_executor = ToolExecutor(self.guardrails)
        self.trigger_detector = TriggerDetector(self.tool_executor)

        # Knowledge base
        self.knowledge_base = None
        if KNOWLEDGE_BASE_AVAILABLE and _env_bool("AI_MONITOR_KNOWLEDGE_BASE_ENABLED", True):
            try:
                self.knowledge_base = KnowledgeBase()
                # Wire up knowledge base to components for Phase 3 features
                self.tool_executor.set_knowledge_base(self.knowledge_base)
                self.guardrails.set_knowledge_base(self.knowledge_base)
                _log("info", "Knowledge base initialized",
                     stats=self.knowledge_base.get_stats())
            except Exception as e:
                _log("error", "Failed to initialize knowledge base", error=str(e))

        # Proactive monitoring config
        self.proactive_scan_interval = _env_int("AI_MONITOR_PROACTIVE_SCAN_INTERVAL", 900)  # 15 min
        self.last_proactive_scan = 0
        
        # Config
        self.interval_seconds = _env_int("AI_MONITOR_INTERVAL_SECONDS", 60)
        self.max_tool_calls = _env_int("AI_MONITOR_MAX_TOOL_CALLS", 20)
        self.max_investigation_time = _env_int("AI_MONITOR_MAX_INVESTIGATION_TIME_SECONDS", 300)
        self.incident_dir = incident_dir
        self.verification_enabled = _env_bool("AI_MONITOR_VERIFICATION_ENABLED", True)
        
        _log("info", "Agent monitor initialized",
             llm_backend="claude" if self.use_claude else "gemini" if self.use_gemini else "none",
             preferred=preferred_backend,
             max_tool_calls=self.max_tool_calls,
             execute_mode=self.tool_executor.execute_mode,
             knowledge_base_enabled=self.knowledge_base is not None,
             verification_enabled=self.verification_enabled)
    
    def investigate(self, trigger: str) -> Investigation:
        """
        Investigate a trigger using LLM with tool calling.

        The LLM iteratively calls tools to understand the issue and take action.
        After actions, verifies they succeeded (closed-loop).
        Stores learnings in knowledge base and triggers learning hooks.
        Returns complete investigation report with audit trail.
        """
        # Classify trigger type for similarity matching
        trigger_type = self._classify_trigger(trigger)

        investigation = Investigation(
            trigger=trigger,
            trigger_type=trigger_type,
            start_time=time.time()
        )

        ACTIVE_INVESTIGATIONS.inc()

        # Set investigation context for confidence-based execution
        self.guardrails.set_investigation_context(trigger_type)

        # Check knowledge base for similar incidents and runbooks
        if self.knowledge_base:
            similar = self.knowledge_base.find_similar_incidents(
                trigger=trigger,
                trigger_type=trigger_type,
                limit=3
            )
            if similar:
                _log("info", "Found similar past incidents", count=len(similar))
                investigation.metadata["similar_incidents"] = similar

            # Check for existing runbook
            runbook = self.knowledge_base.get_runbook(trigger_type)
            if runbook:
                _log("info", "Found runbook for trigger type",
                     trigger_type=trigger_type,
                     steps=len(runbook.get("steps", [])))
                investigation.metadata["runbook"] = runbook
        
        try:
            if self.use_claude:
                self._investigate_claude(investigation)
            elif self.use_gemini:
                self._investigate_gemini(investigation)
            else:
                investigation.outcome = "error"
                investigation.findings = "No LLM backend configured"
            
            # After investigation completes, run verification if actions were taken
            if self.verification_enabled and investigation.actions_taken:
                self._verify_resolution(investigation)
        
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
                trigger_type=trigger_type,
                outcome=investigation.outcome
            ).inc()
            
            _log("info", "Investigation complete",
                 trigger=trigger,
                 outcome=investigation.outcome,
                 duration_seconds=round(duration, 2),
                 tool_calls=len(investigation.tool_calls),
                 actions_taken=len(investigation.actions_taken),
                 verifications=len(investigation.verifications))
            
            # Store in knowledge base and trigger learning hooks
            if self.knowledge_base:
                try:
                    incident_id = self._record_to_knowledge_base(investigation)
                    investigation.metadata["incident_id"] = incident_id

                    # Phase 3: Pattern detection - track recurring issues
                    pattern_result = self.knowledge_base.detect_and_record_pattern(
                        trigger=investigation.trigger,
                        trigger_type=investigation.trigger_type,
                        incident_id=incident_id
                    )
                    if pattern_result and pattern_result.get("proactive_enabled"):
                        _log("info", "Proactive monitoring enabled for pattern",
                             pattern_id=pattern_result["pattern_id"],
                             occurrence_count=pattern_result["occurrence_count"])

                    # Phase 3: Auto-generate runbook after successful resolutions
                    if investigation.outcome == "resolved":
                        runbook_result = self.knowledge_base.maybe_generate_runbook(
                            trigger_type=investigation.trigger_type,
                            min_occurrences=3
                        )
                        if runbook_result:
                            _log("info", "Auto-generated runbook from successful resolutions",
                                 pattern_type=runbook_result["pattern_type"],
                                 steps_count=len(runbook_result.get("steps", [])))

                except Exception as e:
                    _log("error", "Failed to record to knowledge base", error=str(e))

            self._save_investigation_report(investigation)
        
        return investigation
    
    def _classify_trigger(self, trigger: str) -> str:
        """Extract trigger type from trigger string."""
        trigger_lower = trigger.lower()
        
        if "unhealthy" in trigger_lower:
            return "container_unhealthy"
        elif "exited" in trigger_lower:
            return "container_exited"
        elif "down" in trigger_lower and "target" in trigger_lower:
            return "prometheus_target_down"
        elif "scrape" in trigger_lower and "degraded" in trigger_lower:
            return "scrape_quality_degraded"
        elif "restart" in trigger_lower:
            return "container_restarted"
        else:
            return "unknown"
    
    def _verify_resolution(self, investigation: Investigation) -> None:
        """
        Verify that actions taken actually resolved the issue.
        This is the critical closed-loop verification.
        """
        _log("info", "Running verification checks", trigger=investigation.trigger)
        
        # Wait for system to stabilize after actions
        time.sleep(5)
        
        # Generate verification plan based on trigger type
        checks = self._generate_verification_checks(investigation)
        
        for check in checks:
            try:
                result = self.tool_executor.execute(check["tool"], check["arguments"])
                
                verification = VerificationCheck(
                    check_type=check["type"],
                    description=check["description"],
                    timestamp=time.time(),
                    passed=check["validator"](result),
                    details=result
                )
                
                investigation.verifications.append(verification)
                
                _log("info", "Verification check complete",
                     check_type=check["type"],
                     passed=verification.passed)
            
            except Exception as e:
                verification = VerificationCheck(
                    check_type=check["type"],
                    description=check["description"],
                    timestamp=time.time(),
                    passed=False,
                    details={"error": str(e)}
                )
                investigation.verifications.append(verification)
                _log("error", "Verification check failed", 
                     check_type=check["type"], error=str(e))
        
        # Update outcome based on verifications
        if investigation.verifications:
            all_passed = all(v.passed for v in investigation.verifications)
            if all_passed and investigation.outcome == "resolved":
                investigation.resolution_summary = "Actions verified successful"
                # Mark the successful action
                if investigation.actions_taken:
                    investigation.actions_taken[-1].resolved_incident = True
            elif not all_passed:
                investigation.outcome = "escalated"
                investigation.resolution_summary = "Verification failed - manual intervention needed"
    
    def _generate_verification_checks(self, investigation: Investigation) -> List[Dict[str, Any]]:
        """Generate verification checks based on trigger type and actions taken."""
        checks = []
        
        if investigation.trigger_type == "container_unhealthy":
            # Check if container is now healthy
            container_name = self._extract_container_name(investigation.trigger)
            if container_name:
                checks.append({
                    "type": "docker_health",
                    "description": f"Verify {container_name} is healthy",
                    "tool": "docker_inspect",
                    "arguments": {"container": container_name},
                    "validator": lambda r: r.get("success") and r.get("data", {}).get("health") == "healthy"
                })
        
        elif investigation.trigger_type == "prometheus_target_down":
            # Check if target is now up
            checks.append({
                "type": "prometheus_target",
                "description": "Verify Prometheus targets are up",
                "tool": "prom_query",
                "arguments": {"query": "up == 0"},
                "validator": lambda r: r.get("success") and len(r.get("data", {}).get("result", [])) == 0
            })
        
        elif investigation.trigger_type == "scrape_quality_degraded":
            # Check if scrape quality improved
            checks.append({
                "type": "scrape_quality",
                "description": "Verify scrape quality improved",
                "tool": "prom_query",
                "arguments": {"query": "scrape_samples_scraped > 5"},
                "validator": lambda r: r.get("success") and len(r.get("data", {}).get("result", [])) > 0
            })
        
        # Always add generic health check
        checks.append({
            "type": "overall_health",
            "description": "Check overall system health",
            "tool": "docker_list",
            "arguments": {"all": True},
            "validator": lambda r: r.get("success") and not any(
                c.get("health") == "unhealthy" or c.get("status") == "exited" 
                for c in r.get("data", {}).get("containers", [])
            )
        })
        
        return checks
    
    def _extract_container_name(self, trigger: str) -> Optional[str]:
        """Extract container name from trigger string."""
        import re
        match = re.search(r"Container '([^']+)'", trigger)
        return match.group(1) if match else None
    
    def _record_to_knowledge_base(self, investigation: Investigation) -> int:
        """Store investigation in knowledge base for future learning."""
        return self.knowledge_base.record_incident(
            trigger=investigation.trigger,
            trigger_type=investigation.trigger_type,
            outcome=investigation.outcome,
            findings=investigation.findings,
            root_cause=investigation.root_cause,
            resolution_summary=investigation.resolution_summary,
            actions=[
                {
                    "type": a.action_type,
                    "target": a.target,
                    "parameters": a.parameters,
                    "timestamp": datetime.fromtimestamp(a.timestamp, tz=timezone.utc).isoformat(),
                    "success": a.success,
                    "error": a.error,
                    "resolved_incident": a.resolved_incident
                }
                for a in investigation.actions_taken
            ],
            tool_calls=[
                {
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": tc.result,
                    "error": tc.error,
                    "timestamp": datetime.fromtimestamp(tc.timestamp, tz=timezone.utc).isoformat(),
                    "duration_ms": tc.duration_ms,
                    "success": tc.success
                }
                for tc in investigation.tool_calls
            ],
            verifications=[
                {
                    "type": v.check_type,
                    "description": v.description,
                    "timestamp": datetime.fromtimestamp(v.timestamp, tz=timezone.utc).isoformat(),
                    "passed": v.passed,
                    "details": v.details
                }
                for v in investigation.verifications
            ],
            metadata=investigation.metadata,
            duration_seconds=investigation.end_time - investigation.start_time if investigation.end_time else None,
            llm_iterations=investigation.llm_iterations
        )
    
    def _investigate_claude(self, investigation: Investigation) -> None:
        """Run investigation using Claude."""
        # Add similar incidents to context if available
        context_msg = f"Investigate this trigger: {investigation.trigger}"
        if investigation.metadata.get("similar_incidents"):
            context_msg += f"\n\nSimilar past incidents found:\n{json.dumps(investigation.metadata['similar_incidents'], indent=2)}"
        
        messages = [
            {
                "role": "user",
                "content": context_msg
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
            start_time = time.time()
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
                tool_results = []
                
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_start = time.time()
                        
                        tool_call = ToolCall(
                            id=content_block.id,
                            name=content_block.name,
                            arguments=content_block.input,
                            timestamp=tool_start
                        )
                        
                        # Execute tool
                        result = self.tool_executor.execute(
                            content_block.name,
                            content_block.input
                        )
                        
                        tool_call.result = result
                        tool_call.duration_ms = (time.time() - tool_start) * 1000
                        tool_call.success = result.get("success", False)
                        tool_call.error = result.get("error")
                        
                        investigation.tool_calls.append(tool_call)
                        
                        # Track actions with full details
                        if content_block.name in ["restart_container", "create_alert", "mark_resolved"]:
                            action = ActionTaken(
                                action_type=content_block.name,
                                target=content_block.input.get("container") or content_block.input.get("target"),
                                parameters=content_block.input,
                                timestamp=tool_start,
                                success=result.get("success", False),
                                error=result.get("error")
                            )
                            investigation.actions_taken.append(action)
                        
                        # Check for mark_resolved
                        if content_block.name == "mark_resolved":
                            investigation.outcome = result.get("data", {}).get("outcome", "resolved")
                            investigation.findings = result.get("data", {}).get("summary", "")
                            return
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": content_block.id,
                            "content": json.dumps(result)
                        })
                
                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": tool_results
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
        # Run proactive scan periodically
        now = time.time()
        if now - self.last_proactive_scan >= self.proactive_scan_interval:
            self._proactive_scan()
            self.last_proactive_scan = now

        triggers = self.trigger_detector.check_triggers()

        if not triggers:
            _log("debug", "No triggers detected")
            return

        _log("info", "Triggers detected", count=len(triggers), triggers=triggers)

        # Investigate each trigger
        for trigger in triggers:
            self.investigate(trigger)

    def _proactive_scan(self) -> None:
        """
        Phase 3: Proactive monitoring scan.
        Check for patterns with proactive monitoring enabled and run their checks.
        """
        if not self.knowledge_base:
            return

        _log("info", "Running proactive monitoring scan")

        # Get all enabled proactive checks
        proactive_checks = self.knowledge_base.get_proactive_checks()
        if not proactive_checks:
            _log("debug", "No proactive checks configured")
            return

        _log("info", "Found proactive checks", count=len(proactive_checks))

        triggers_found = []

        for check in proactive_checks:
            config = check.get("config", {})
            check_type = config.get("check_type", "generic")

            try:
                issue_detected = False
                issue_details = None

                if check_type == "docker_health":
                    # Check all containers for unhealthy status
                    result = self.tool_executor.execute("docker_list", {"all": True})
                    if result.get("success"):
                        unhealthy = [
                            c for c in result["data"].get("containers", [])
                            if c.get("health") == "unhealthy"
                        ]
                        if unhealthy:
                            issue_detected = True
                            issue_details = f"Unhealthy containers: {[c['name'] for c in unhealthy]}"

                elif check_type == "docker_status":
                    # Check for exited containers
                    result = self.tool_executor.execute("docker_list", {"all": True})
                    if result.get("success"):
                        exited = [
                            c for c in result["data"].get("containers", [])
                            if c.get("status") == "exited"
                        ]
                        if exited:
                            issue_detected = True
                            issue_details = f"Exited containers: {[c['name'] for c in exited]}"

                elif check_type == "prometheus_query":
                    # Run the configured query
                    query = config.get("query", "up == 0")
                    result = self.tool_executor.execute("prom_query", {"query": query})
                    if result.get("success"):
                        results = result["data"].get("result", [])
                        if results:
                            issue_detected = True
                            issue_details = f"Prometheus query '{query}' returned {len(results)} results"

                elif check_type == "resource_forecast":
                    # Basic resource trend analysis
                    result = self.tool_executor.execute("system_info", {})
                    if result.get("success"):
                        disk_percent = result["data"].get("disk", {}).get("percent", 0)
                        mem_percent = result["data"].get("memory", {}).get("percent", 0)

                        if disk_percent > 85:
                            issue_detected = True
                            issue_details = f"Disk usage at {disk_percent}% - may exhaust soon"
                        elif mem_percent > 90:
                            issue_detected = True
                            issue_details = f"Memory usage at {mem_percent}% - may exhaust soon"

                if issue_detected:
                    _log("warn", "Proactive check detected issue",
                         pattern_id=check.get("pattern_id"),
                         signature=check.get("signature"),
                         issue=issue_details)

                    # Create trigger for investigation
                    triggers_found.append(
                        f"[PROACTIVE] {check.get('signature', 'unknown')}: {issue_details}"
                    )

            except Exception as e:
                _log("error", "Proactive check failed",
                     pattern_id=check.get("pattern_id"),
                     error=str(e))

        # Run trend analysis
        self._check_trends()

        # Investigate any proactive triggers found
        for trigger in triggers_found:
            _log("info", "Investigating proactive trigger", trigger=trigger)
            self.investigate(trigger)

    def _check_trends(self) -> None:
        """
        Analyze incident trends and alert on concerning patterns.
        """
        if not self.knowledge_base:
            return

        try:
            trends = self.knowledge_base.get_incident_trends(days=7)
            if not trends.get("total_incidents"):
                return

            # Check for concerning trends
            daily_rate = trends.get("daily_rate", 0)
            resolution_rate = trends.get("resolution_rate", 1.0)

            # Alert if daily incident rate is high
            if daily_rate > 10:
                _log("warn", "High incident rate detected",
                     daily_rate=daily_rate,
                     period_days=7)

            # Alert if resolution rate is low
            if resolution_rate < 0.7 and trends.get("total_incidents", 0) > 5:
                _log("warn", "Low resolution rate detected",
                     resolution_rate=resolution_rate,
                     total_incidents=trends.get("total_incidents"))

            # Log trending issues
            trending = trends.get("trending_issues", [])
            if trending:
                _log("info", "Trending issues identified",
                     trending=[t["trigger_type"] for t in trending[:3]])

        except Exception as e:
            _log("error", "Trend analysis failed", error=str(e))
    
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
