"""
Pytest configuration and shared fixtures for AI Monitor tests.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ================================ Environment Setup ================================

@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("KNOWLEDGE_BASE_DB_TYPE", "sqlite")
    monkeypatch.setenv("AI_MONITOR_EXECUTE", "false")
    monkeypatch.setenv("AI_MONITOR_ALLOWED_CONTAINERS", "test-container,influxdb3-core,telegraf")
    monkeypatch.setenv("AI_MONITOR_GUARDRAIL_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("AI_MONITOR_GUARDRAIL_MAX_RESTARTS_PER_HOUR", "5")
    monkeypatch.setenv("AI_MONITOR_KNOWLEDGE_BASE_ENABLED", "true")
    monkeypatch.setenv("AI_MONITOR_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("AI_MONITOR_PROACTIVE_SCAN_INTERVAL", "900")


# ================================ Database Fixtures ================================

@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary SQLite database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def knowledge_base(temp_db_path, monkeypatch):
    """Create a KnowledgeBase instance with temporary database."""
    monkeypatch.setenv("KNOWLEDGE_BASE_SQLITE_PATH", temp_db_path)

    from knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    return kb


@pytest.fixture
def populated_knowledge_base(knowledge_base):
    """Knowledge base pre-populated with test incidents."""
    from datetime import timedelta

    # Add several incidents for testing
    incidents_data = [
        {
            "trigger": "Container 'influxdb3-core' is unhealthy",
            "trigger_type": "container_unhealthy",
            "outcome": "resolved",
            "findings": "Container health check failing due to high memory usage",
            "actions": [
                {
                    "type": "restart_container",
                    "target": "influxdb3-core",
                    "parameters": {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": True,
                    "resolved_incident": True
                }
            ],
            "tool_calls": [
                {
                    "name": "docker_inspect",
                    "arguments": {"container": "influxdb3-core"},
                    "result": {"health": "unhealthy"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": 50,
                    "success": True
                }
            ],
            "verifications": [
                {
                    "type": "docker_health",
                    "description": "Check container health",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "passed": True,
                    "details": {"health": "healthy"}
                }
            ],
            "root_cause": "Memory leak in InfluxDB",
            "resolution_summary": "Restarted container to restore service",
            "duration_seconds": 45.5
        },
        {
            "trigger": "Container 'influxdb3-core' is unhealthy",
            "trigger_type": "container_unhealthy",
            "outcome": "resolved",
            "findings": "Container crashed due to OOM",
            "actions": [
                {
                    "type": "restart_container",
                    "target": "influxdb3-core",
                    "parameters": {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": True,
                    "resolved_incident": True
                }
            ],
            "tool_calls": [],
            "verifications": [],
            "root_cause": "OOM killed",
            "resolution_summary": "Restarted to restore",
            "duration_seconds": 30.0
        },
        {
            "trigger": "Container 'influxdb3-core' is unhealthy",
            "trigger_type": "container_unhealthy",
            "outcome": "resolved",
            "findings": "Disk full causing health check failure",
            "actions": [
                {
                    "type": "restart_container",
                    "target": "influxdb3-core",
                    "parameters": {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": True,
                    "resolved_incident": True
                }
            ],
            "tool_calls": [],
            "verifications": [],
            "root_cause": "Disk space exhaustion",
            "resolution_summary": "Cleared logs and restarted",
            "duration_seconds": 60.0
        },
        {
            "trigger": "Prometheus target 'node-exporter' is down",
            "trigger_type": "prometheus_target_down",
            "outcome": "resolved",
            "findings": "Transient network issue",
            "actions": [],
            "tool_calls": [],
            "verifications": [],
            "root_cause": "Network blip",
            "resolution_summary": "Self-resolved, no action needed",
            "duration_seconds": 10.0
        },
        {
            "trigger": "Container 'telegraf' exited unexpectedly",
            "trigger_type": "container_exited",
            "outcome": "escalated",
            "findings": "Configuration error in telegraf.conf",
            "actions": [
                {
                    "type": "alert_created",
                    "target": "ops-team",
                    "parameters": {"severity": "high"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": True,
                    "resolved_incident": False
                }
            ],
            "tool_calls": [],
            "verifications": [],
            "root_cause": "Invalid configuration",
            "resolution_summary": "Escalated to ops team for config fix",
            "duration_seconds": 120.0
        }
    ]

    for incident_data in incidents_data:
        knowledge_base.record_incident(**incident_data)

    return knowledge_base


# ================================ Mock Fixtures ================================

@pytest.fixture
def mock_docker_client():
    """Mock Docker client for testing."""
    mock = MagicMock()
    mock.containers.list.return_value = [
        MagicMock(
            name="influxdb3-core",
            status="running",
            attrs={
                "State": {"Health": {"Status": "healthy"}},
                "Config": {"Image": "influxdb:3-core"}
            }
        ),
        MagicMock(
            name="telegraf",
            status="running",
            attrs={
                "State": {"Health": {"Status": "healthy"}},
                "Config": {"Image": "telegraf:latest"}
            }
        )
    ]
    return mock


@pytest.fixture
def mock_prometheus_response():
    """Mock Prometheus API response."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"job": "node-exporter"}, "value": [1234567890, "1"]}
            ]
        }
    }


@pytest.fixture
def mock_tool_executor(mock_docker_client, mock_prometheus_response):
    """Mock ToolExecutor for testing."""
    mock = MagicMock()

    def execute_side_effect(tool_name, args):
        if tool_name == "docker_list":
            return {
                "success": True,
                "data": {
                    "containers": [
                        {"name": "influxdb3-core", "status": "running", "health": "healthy"},
                        {"name": "telegraf", "status": "running", "health": "healthy"}
                    ]
                }
            }
        elif tool_name == "docker_inspect":
            return {
                "success": True,
                "data": {
                    "name": args.get("container", "unknown"),
                    "status": "running",
                    "health": "healthy"
                }
            }
        elif tool_name == "prom_query":
            return {
                "success": True,
                "data": mock_prometheus_response["data"]
            }
        elif tool_name == "system_info":
            return {
                "success": True,
                "data": {
                    "cpu": {"percent": 25.0},
                    "memory": {"percent": 45.0},
                    "disk": {"percent": 60.0}
                }
            }
        else:
            return {"success": True, "data": {}}

    mock.execute.side_effect = execute_side_effect
    return mock


# ================================ Investigation Fixtures ================================

@pytest.fixture
def sample_investigation():
    """Create a sample Investigation object for testing."""
    from agent_monitor import Investigation

    return Investigation(
        trigger="Container 'influxdb3-core' is unhealthy",
        trigger_type="container_unhealthy",
        start_time=datetime.now(timezone.utc).timestamp()
    )


@pytest.fixture
def sample_trigger_types():
    """Sample trigger types for testing."""
    return [
        ("Container 'influxdb3-core' is unhealthy", "container_unhealthy"),
        ("Container 'telegraf' exited unexpectedly", "container_exited"),
        ("Prometheus target 'node-exporter' is down", "prometheus_target_down"),
        ("Scrape quality degraded for job 'cadvisor'", "scrape_quality_degraded"),
        ("Unknown issue detected", "unknown")
    ]


# ================================ Helper Functions ================================

def create_test_incident(knowledge_base, trigger_type="container_unhealthy", outcome="resolved"):
    """Helper to create a test incident."""
    return knowledge_base.record_incident(
        trigger=f"Test trigger for {trigger_type}",
        trigger_type=trigger_type,
        outcome=outcome,
        findings="Test findings",
        actions=[
            {
                "type": "restart_container",
                "target": "test-container",
                "parameters": {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
                "resolved_incident": outcome == "resolved"
            }
        ] if outcome == "resolved" else [],
        tool_calls=[],
        verifications=[],
        root_cause="Test root cause",
        resolution_summary="Test resolution",
        duration_seconds=30.0
    )
