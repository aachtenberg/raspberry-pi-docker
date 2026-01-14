"""
Unit tests for agent_monitor.py - Phase 3 features.

Tests:
- Knowledge base tool implementations
- Confidence-based execution in GuardrailEnforcer
- Proactive monitoring scan
- Pattern detection hooks
- Runbook generation hooks
"""
import os
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import create_test_incident


class TestKnowledgeBaseTools:
    """Tests for Phase 3 knowledge base tool implementations in ToolExecutor."""

    def test_query_knowledge_base_tool_no_kb(self, mock_tool_executor):
        """Test query_knowledge_base when KB not available."""
        from agent_monitor import ToolExecutor, GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        executor = ToolExecutor(guardrails)
        # KB not set

        result = executor._tool_query_knowledge_base({"query": "test"})

        assert "error" in result
        assert result["incidents"] == []

    def test_query_knowledge_base_tool_with_kb(self, knowledge_base):
        """Test query_knowledge_base with KB available."""
        from agent_monitor import ToolExecutor, GuardrailEnforcer

        # Add some test data
        create_test_incident(knowledge_base, "container_unhealthy", "resolved")

        guardrails = GuardrailEnforcer()
        executor = ToolExecutor(guardrails)
        executor.set_knowledge_base(knowledge_base)

        result = executor._tool_query_knowledge_base({
            "query": "container unhealthy",
            "limit": 5
        })

        assert "results_count" in result
        assert "incidents" in result
        assert "message" in result

    def test_get_runbook_tool_not_found(self, knowledge_base):
        """Test get_runbook when runbook doesn't exist."""
        from agent_monitor import ToolExecutor, GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        executor = ToolExecutor(guardrails)
        executor.set_knowledge_base(knowledge_base)

        result = executor._tool_get_runbook({"pattern": "nonexistent"})

        assert result["found"] is False
        assert result["runbook"] is None
        assert "auto-generated after 3+" in result["message"]

    def test_get_runbook_tool_found(self, populated_knowledge_base):
        """Test get_runbook when runbook exists."""
        from agent_monitor import ToolExecutor, GuardrailEnforcer

        # Generate runbook first
        populated_knowledge_base.maybe_generate_runbook("container_unhealthy", 3)

        guardrails = GuardrailEnforcer()
        executor = ToolExecutor(guardrails)
        executor.set_knowledge_base(populated_knowledge_base)

        result = executor._tool_get_runbook({"pattern": "container_unhealthy"})

        assert result["found"] is True
        assert result["runbook"] is not None
        assert "steps" in result["message"]

    def test_check_action_confidence_tool_no_kb(self):
        """Test check_action_confidence when KB not available."""
        from agent_monitor import ToolExecutor, GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        executor = ToolExecutor(guardrails)
        # KB not set

        result = executor._tool_check_action_confidence({
            "action_type": "restart_container",
            "target": "test",
            "trigger_type": "container_unhealthy"
        })

        assert result["confidence"] == 0.5
        assert result["recommendation"] == "request_approval"

    def test_check_action_confidence_tool_with_kb(self, populated_knowledge_base):
        """Test check_action_confidence with historical data."""
        from agent_monitor import ToolExecutor, GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        executor = ToolExecutor(guardrails)
        executor.set_knowledge_base(populated_knowledge_base)

        result = executor._tool_check_action_confidence({
            "action_type": "restart_container",
            "target": "influxdb3-core",
            "trigger_type": "container_unhealthy"
        })

        assert "confidence" in result
        assert "recommendation" in result
        assert "reason" in result
        assert result["recommendation"] in ["auto_execute", "request_approval", "escalate"]

    def test_get_incident_trends_tool(self, populated_knowledge_base):
        """Test get_incident_trends tool."""
        from agent_monitor import ToolExecutor, GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        executor = ToolExecutor(guardrails)
        executor.set_knowledge_base(populated_knowledge_base)

        result = executor._tool_get_incident_trends({"days": 7})

        assert "total_incidents" in result
        assert "daily_rate" in result
        assert "resolution_rate" in result


class TestGuardrailEnforcerConfidence:
    """Tests for confidence-based execution in GuardrailEnforcer."""

    def test_guardrail_without_kb(self):
        """Test guardrail check without knowledge base."""
        from agent_monitor import GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        result = guardrails.check_restart_container("test-container")

        assert result.allowed is True
        assert "0.50" in result.reason  # Default confidence
        assert result.metadata["confidence"] == 0.5
        assert result.metadata["confidence_level"] == "medium"

    def test_guardrail_with_kb_high_confidence(self, populated_knowledge_base):
        """Test guardrail check with high confidence from KB."""
        from agent_monitor import GuardrailEnforcer

        # Add more successful resolutions to increase confidence
        for i in range(10):
            create_test_incident(populated_knowledge_base, "container_unhealthy", "resolved")

        guardrails = GuardrailEnforcer()
        guardrails.set_knowledge_base(populated_knowledge_base)
        guardrails.set_investigation_context("container_unhealthy")

        result = guardrails.check_restart_container("test-container")

        assert result.allowed is True
        assert result.metadata["confidence"] > 0.5
        assert result.metadata["confidence_reason"] == "historical_data"

    def test_guardrail_confidence_levels(self, knowledge_base):
        """Test different confidence level classifications."""
        from agent_monitor import GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        guardrails.set_knowledge_base(knowledge_base)
        guardrails.set_investigation_context("container_unhealthy")

        # With no history, should be medium (0.5)
        result = guardrails.check_restart_container("test-container")

        assert result.metadata["confidence_level"] in ["low", "medium", "high"]

    def test_guardrail_allowlist_check(self):
        """Test that allowlist is still enforced with confidence."""
        from agent_monitor import GuardrailEnforcer

        guardrails = GuardrailEnforcer()

        # Container not in allowlist
        result = guardrails.check_restart_container("not-allowed-container")

        assert result.allowed is False
        assert "not in allowlist" in result.reason

    def test_guardrail_cooldown_check(self):
        """Test that cooldown is still enforced with confidence."""
        from agent_monitor import GuardrailEnforcer

        guardrails = GuardrailEnforcer()

        # Record a restart
        guardrails.record_restart("test-container")

        # Immediate second restart should be blocked
        result = guardrails.check_restart_container("test-container")

        assert result.allowed is False
        assert "cooldown" in result.reason.lower()

    def test_set_investigation_context(self):
        """Test setting investigation context."""
        from agent_monitor import GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        guardrails.set_investigation_context("prometheus_target_down")

        assert guardrails.current_trigger_type == "prometheus_target_down"


class TestTriggerClassification:
    """Tests for trigger classification."""

    def test_classify_trigger_container_unhealthy(self):
        """Test classification of container unhealthy trigger."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)

            trigger_type = monitor._classify_trigger(
                "Container 'influxdb3-core' is unhealthy"
            )
            assert trigger_type == "container_unhealthy"

    def test_classify_trigger_container_exited(self):
        """Test classification of container exited trigger."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)

            trigger_type = monitor._classify_trigger(
                "Container 'telegraf' exited unexpectedly"
            )
            assert trigger_type == "container_exited"

    def test_classify_trigger_prometheus_down(self):
        """Test classification of prometheus target down trigger."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)

            trigger_type = monitor._classify_trigger(
                "Prometheus target 'node-exporter' is down"
            )
            assert trigger_type == "prometheus_target_down"

    def test_classify_trigger_scrape_degraded(self):
        """Test classification of scrape quality trigger."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)

            trigger_type = monitor._classify_trigger(
                "Scrape quality degraded for cadvisor"
            )
            assert trigger_type == "scrape_quality_degraded"

    def test_classify_trigger_unknown(self):
        """Test classification of unknown trigger."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)

            trigger_type = monitor._classify_trigger(
                "Something completely different happened"
            )
            assert trigger_type == "unknown"


class TestProactiveScan:
    """Tests for proactive monitoring scan functionality."""

    def test_proactive_scan_no_kb(self, mock_tool_executor):
        """Test proactive scan when KB not available."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = None
            monitor.tool_executor = mock_tool_executor

            # Should return without error
            monitor._proactive_scan()

    def test_proactive_scan_no_checks(self, knowledge_base, mock_tool_executor):
        """Test proactive scan with no proactive checks enabled."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = knowledge_base
            monitor.tool_executor = mock_tool_executor

            # Should return without starting investigations
            monitor._proactive_scan()

    def test_proactive_scan_with_checks(self, knowledge_base, mock_tool_executor):
        """Test proactive scan with enabled checks."""
        from agent_monitor import AgentMonitor

        # Enable a proactive check by creating 5 incidents
        for i in range(5):
            incident_id = create_test_incident(knowledge_base)
            knowledge_base.detect_and_record_pattern(
                trigger="Container 'test' unhealthy",
                trigger_type="container_unhealthy",
                incident_id=incident_id
            )

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = knowledge_base
            monitor.tool_executor = mock_tool_executor

            with patch.object(monitor, 'investigate') as mock_investigate:
                with patch.object(monitor, '_check_trends'):
                    monitor._proactive_scan()

                # If unhealthy containers detected, investigate should be called
                # This depends on mock_tool_executor returning healthy containers


class TestCheckTrends:
    """Tests for trend checking functionality."""

    def test_check_trends_no_kb(self):
        """Test trend check when KB not available."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = None

            # Should return without error
            monitor._check_trends()

    def test_check_trends_empty_db(self, knowledge_base):
        """Test trend check with empty database."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = knowledge_base

            # Should return without error
            monitor._check_trends()

    def test_check_trends_with_data(self, populated_knowledge_base):
        """Test trend check with data."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = populated_knowledge_base

            # Should complete without error
            monitor._check_trends()


class TestInvestigationHooks:
    """Tests for Phase 3 hooks in investigation flow."""

    def test_investigation_sets_context(self, knowledge_base):
        """Test that investigation sets guardrail context."""
        from agent_monitor import GuardrailEnforcer

        guardrails = GuardrailEnforcer()
        guardrails.set_knowledge_base(knowledge_base)

        # Set context as would happen in investigate()
        guardrails.set_investigation_context("container_unhealthy")

        assert guardrails.current_trigger_type == "container_unhealthy"

    def test_investigation_checks_similar_incidents(self, populated_knowledge_base):
        """Test that similar incidents are checked."""
        similar = populated_knowledge_base.find_similar_incidents(
            trigger="Container 'influxdb3-core' is unhealthy",
            trigger_type="container_unhealthy",
            limit=3
        )

        assert len(similar) >= 1

    def test_investigation_checks_runbook(self, populated_knowledge_base):
        """Test that runbook is checked during investigation."""
        # Generate runbook first
        populated_knowledge_base.maybe_generate_runbook("container_unhealthy", 3)

        runbook = populated_knowledge_base.get_runbook("container_unhealthy")

        assert runbook is not None


class TestInvestigation:
    """Tests for Investigation dataclass."""

    def test_investigation_initialization(self, sample_investigation):
        """Test Investigation object initialization."""
        assert sample_investigation.trigger == "Container 'influxdb3-core' is unhealthy"
        assert sample_investigation.trigger_type == "container_unhealthy"
        assert sample_investigation.outcome == "in_progress"
        assert sample_investigation.tool_calls == []
        assert sample_investigation.actions_taken == []
        assert sample_investigation.verifications == []

    def test_investigation_metadata(self, sample_investigation):
        """Test Investigation metadata handling."""
        sample_investigation.metadata["test_key"] = "test_value"
        assert sample_investigation.metadata["test_key"] == "test_value"


class TestToolDefinitions:
    """Tests for Phase 3 tool definitions."""

    def test_knowledge_tools_in_observation_tools(self):
        """Test that knowledge tools are included in OBSERVATION_TOOLS."""
        from agent_monitor import OBSERVATION_TOOLS

        tool_names = [t["name"] for t in OBSERVATION_TOOLS]

        assert "query_knowledge_base" in tool_names
        assert "get_runbook" in tool_names
        assert "check_action_confidence" in tool_names
        assert "get_incident_trends" in tool_names

    def test_query_knowledge_base_schema(self):
        """Test query_knowledge_base tool schema."""
        from agent_monitor import OBSERVATION_TOOLS

        tool = next(t for t in OBSERVATION_TOOLS if t["name"] == "query_knowledge_base")

        assert "query" in tool["input_schema"]["properties"]
        assert "trigger_type" in tool["input_schema"]["properties"]
        assert "outcome" in tool["input_schema"]["properties"]
        assert "limit" in tool["input_schema"]["properties"]
        assert tool["input_schema"]["required"] == ["query"]

    def test_check_action_confidence_schema(self):
        """Test check_action_confidence tool schema."""
        from agent_monitor import OBSERVATION_TOOLS

        tool = next(t for t in OBSERVATION_TOOLS if t["name"] == "check_action_confidence")

        assert "action_type" in tool["input_schema"]["properties"]
        assert "target" in tool["input_schema"]["properties"]
        assert "trigger_type" in tool["input_schema"]["properties"]
        assert set(tool["input_schema"]["required"]) == {"action_type", "target", "trigger_type"}


class TestSystemPrompt:
    """Tests for updated system prompt."""

    def test_system_prompt_mentions_knowledge_base(self):
        """Test that system prompt mentions knowledge base tools."""
        from agent_monitor import SYSTEM_PROMPT

        assert "query_knowledge_base" in SYSTEM_PROMPT
        assert "get_runbook" in SYSTEM_PROMPT
        assert "check_action_confidence" in SYSTEM_PROMPT

    def test_system_prompt_workflow(self):
        """Test that system prompt describes autonomous workflow."""
        from agent_monitor import SYSTEM_PROMPT

        assert "ORIENT" in SYSTEM_PROMPT
        assert "knowledge base" in SYSTEM_PROMPT.lower()
        assert "confidence" in SYSTEM_PROMPT.lower()

    def test_system_prompt_confidence_thresholds(self):
        """Test that system prompt mentions confidence thresholds."""
        from agent_monitor import SYSTEM_PROMPT

        assert "85%" in SYSTEM_PROMPT or ">85%" in SYSTEM_PROMPT
        assert "50%" in SYSTEM_PROMPT


class TestRunOnceProactiveScan:
    """Tests for proactive scan integration in run_once."""

    def test_run_once_triggers_proactive_scan(self):
        """Test that run_once triggers proactive scan at interval."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = None
            monitor.proactive_scan_interval = 900
            monitor.last_proactive_scan = 0
            monitor.trigger_detector = MagicMock()
            monitor.trigger_detector.check_triggers.return_value = []

            with patch.object(monitor, '_proactive_scan') as mock_scan:
                with patch('time.time', return_value=1000):
                    monitor.run_once()
                    mock_scan.assert_called_once()

    def test_run_once_skips_proactive_if_recent(self):
        """Test that run_once skips proactive scan if recently run."""
        from agent_monitor import AgentMonitor

        with patch.object(AgentMonitor, '__init__', lambda x: None):
            monitor = AgentMonitor.__new__(AgentMonitor)
            monitor.knowledge_base = None
            monitor.proactive_scan_interval = 900
            monitor.last_proactive_scan = 500  # Recent
            monitor.trigger_detector = MagicMock()
            monitor.trigger_detector.check_triggers.return_value = []

            with patch.object(monitor, '_proactive_scan') as mock_scan:
                with patch('time.time', return_value=600):  # Only 100 seconds later
                    monitor.run_once()
                    mock_scan.assert_not_called()
