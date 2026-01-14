"""
Unit tests for knowledge_base.py - Phase 2 and Phase 3 features.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import create_test_incident


class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    def test_sqlite_initialization(self, knowledge_base):
        """Test SQLite database initializes correctly."""
        assert knowledge_base.db.db_type == "sqlite"
        assert knowledge_base.db.engine is not None
        assert knowledge_base.db.SessionLocal is not None

    def test_health_check(self, knowledge_base):
        """Test database health check."""
        assert knowledge_base.db.health_check() is True

    def test_session_scope_commit(self, knowledge_base):
        """Test session scope commits successfully."""
        with knowledge_base.db.session_scope() as session:
            # Simple query that should succeed
            result = session.execute(
                knowledge_base.db.engine.dialect.name == "sqlite"
                and "SELECT 1" or "SELECT 1"
            )
            assert result is not None


class TestKnowledgeBaseRecording:
    """Tests for incident recording functionality."""

    def test_record_incident(self, knowledge_base):
        """Test basic incident recording."""
        incident_id = knowledge_base.record_incident(
            trigger="Test container unhealthy",
            trigger_type="container_unhealthy",
            outcome="resolved",
            findings="Test findings",
            actions=[],
            tool_calls=[],
            verifications=[],
            root_cause="Test cause",
            resolution_summary="Test resolution",
            duration_seconds=30.0
        )

        assert incident_id > 0

    def test_record_incident_with_actions(self, knowledge_base):
        """Test recording incident with actions."""
        incident_id = knowledge_base.record_incident(
            trigger="Container crash",
            trigger_type="container_exited",
            outcome="resolved",
            findings="Container OOM killed",
            actions=[
                {
                    "type": "restart_container",
                    "target": "test-container",
                    "parameters": {"force": True},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": True,
                    "resolved_incident": True
                }
            ],
            tool_calls=[
                {
                    "name": "docker_inspect",
                    "arguments": {"container": "test-container"},
                    "result": {"status": "exited"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": 45,
                    "success": True
                }
            ],
            verifications=[
                {
                    "type": "docker_health",
                    "description": "Verify container running",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "passed": True,
                    "details": {"status": "running"}
                }
            ],
            duration_seconds=60.0
        )

        assert incident_id > 0


class TestKnowledgeBaseStats:
    """Tests for knowledge base statistics."""

    def test_get_stats_empty(self, knowledge_base):
        """Test stats on empty database."""
        stats = knowledge_base.get_stats()

        assert stats["enabled"] is True
        assert stats["db_type"] == "sqlite"
        assert stats["total_incidents"] == 0
        assert stats["resolved_incidents"] == 0
        assert stats["resolution_rate"] == 0
        assert stats["health"] is True

    def test_get_stats_with_data(self, populated_knowledge_base):
        """Test stats with populated database."""
        stats = populated_knowledge_base.get_stats()

        assert stats["total_incidents"] == 5
        assert stats["resolved_incidents"] == 4
        assert stats["resolution_rate"] == 0.8


class TestQueryIncidents:
    """Tests for Phase 3 query_incidents functionality."""

    def test_query_incidents_by_text(self, populated_knowledge_base):
        """Test querying incidents by text."""
        results = populated_knowledge_base.query_incidents(
            query="influxdb unhealthy"
        )

        assert len(results) >= 1
        assert all("influxdb" in r["trigger"].lower() for r in results)

    def test_query_incidents_by_trigger_type(self, populated_knowledge_base):
        """Test filtering by trigger type."""
        results = populated_knowledge_base.query_incidents(
            query="container",
            trigger_type="container_unhealthy"
        )

        assert all(r["trigger_type"] == "container_unhealthy" for r in results)

    def test_query_incidents_by_outcome(self, populated_knowledge_base):
        """Test filtering by outcome."""
        results = populated_knowledge_base.query_incidents(
            query="container",
            outcome="resolved"
        )

        assert all(r["outcome"] == "resolved" for r in results)

    def test_query_incidents_limit(self, populated_knowledge_base):
        """Test result limiting."""
        results = populated_knowledge_base.query_incidents(
            query="container",
            limit=2
        )

        assert len(results) <= 2

    def test_query_incidents_includes_actions(self, populated_knowledge_base):
        """Test that query results include actions."""
        results = populated_knowledge_base.query_incidents(
            query="influxdb"
        )

        assert len(results) > 0
        # Check first result has actions array
        assert "actions" in results[0]

    def test_query_no_results(self, populated_knowledge_base):
        """Test query with no matching results."""
        results = populated_knowledge_base.query_incidents(
            query="nonexistent_xyz_123"
        )

        assert len(results) == 0


class TestSimilarIncidents:
    """Tests for find_similar_incidents functionality."""

    def test_find_similar_incidents(self, populated_knowledge_base):
        """Test finding similar incidents."""
        results = populated_knowledge_base.find_similar_incidents(
            trigger="Container 'influxdb3-core' is unhealthy",
            trigger_type="container_unhealthy"
        )

        assert len(results) >= 1

    def test_find_similar_prioritizes_resolved(self, populated_knowledge_base):
        """Test that resolved incidents are prioritized."""
        results = populated_knowledge_base.find_similar_incidents(
            trigger="Container unhealthy",
            limit=5
        )

        # Check resolved incidents come first
        resolved_indices = [i for i, r in enumerate(results) if r["outcome"] == "resolved"]
        escalated_indices = [i for i, r in enumerate(results) if r["outcome"] == "escalated"]

        if resolved_indices and escalated_indices:
            assert max(resolved_indices) < min(escalated_indices)


class TestRunbooks:
    """Tests for Phase 3 runbook functionality."""

    def test_get_runbook_not_found(self, knowledge_base):
        """Test getting runbook that doesn't exist."""
        result = knowledge_base.get_runbook("nonexistent_pattern")
        assert result is None

    def test_maybe_generate_runbook_insufficient_data(self, knowledge_base):
        """Test runbook generation with insufficient data."""
        # Add only 2 incidents (need 3)
        create_test_incident(knowledge_base, "test_type", "resolved")
        create_test_incident(knowledge_base, "test_type", "resolved")

        result = knowledge_base.maybe_generate_runbook("test_type", min_occurrences=3)
        assert result is None

    def test_maybe_generate_runbook_success(self, populated_knowledge_base):
        """Test successful runbook generation."""
        # populated_knowledge_base has 3+ resolved container_unhealthy incidents
        result = populated_knowledge_base.maybe_generate_runbook(
            "container_unhealthy",
            min_occurrences=3
        )

        assert result is not None
        assert result["pattern_type"] == "container_unhealthy"
        assert "steps" in result
        assert len(result["steps"]) > 0

    def test_get_runbook_after_generation(self, populated_knowledge_base):
        """Test retrieving generated runbook."""
        # Generate runbook first
        populated_knowledge_base.maybe_generate_runbook(
            "container_unhealthy",
            min_occurrences=3
        )

        # Now retrieve it
        runbook = populated_knowledge_base.get_runbook("container_unhealthy")

        assert runbook is not None
        assert runbook["pattern_type"] == "container_unhealthy"
        assert "success_rate" in runbook

    def test_runbook_not_regenerated(self, populated_knowledge_base):
        """Test that runbook is not regenerated if exists."""
        # Generate first time
        result1 = populated_knowledge_base.maybe_generate_runbook(
            "container_unhealthy",
            min_occurrences=3
        )
        assert result1 is not None

        # Try to generate again
        result2 = populated_knowledge_base.maybe_generate_runbook(
            "container_unhealthy",
            min_occurrences=3
        )
        assert result2 is None  # Should not regenerate

    def test_get_all_runbooks(self, populated_knowledge_base):
        """Test getting all runbooks."""
        # Generate a runbook first
        populated_knowledge_base.maybe_generate_runbook(
            "container_unhealthy",
            min_occurrences=3
        )

        runbooks = populated_knowledge_base.get_all_runbooks()
        assert len(runbooks) >= 1

    def test_update_runbook_usage(self, populated_knowledge_base):
        """Test updating runbook usage statistics."""
        # Generate runbook
        result = populated_knowledge_base.maybe_generate_runbook(
            "container_unhealthy",
            min_occurrences=3
        )
        runbook_id = result["id"]

        # Update usage
        populated_knowledge_base.update_runbook_usage(
            runbook_id=runbook_id,
            success=True,
            resolution_time=25.0
        )

        # Verify update
        runbook = populated_knowledge_base.get_runbook("container_unhealthy")
        assert runbook["times_used"] == 1
        assert runbook["success_count"] == 1


class TestPatternDetection:
    """Tests for Phase 3 pattern detection functionality."""

    def test_detect_new_pattern(self, knowledge_base):
        """Test detecting a new pattern."""
        incident_id = create_test_incident(knowledge_base)

        result = knowledge_base.detect_and_record_pattern(
            trigger="Test trigger",
            trigger_type="container_unhealthy",
            incident_id=incident_id
        )

        # First occurrence shouldn't enable proactive (need 5+)
        assert result is None

    def test_pattern_occurrence_count(self, knowledge_base):
        """Test pattern occurrence counting."""
        # Create 4 incidents with same pattern
        for i in range(4):
            incident_id = create_test_incident(knowledge_base)
            knowledge_base.detect_and_record_pattern(
                trigger="Container 'test' unhealthy",
                trigger_type="container_unhealthy",
                incident_id=incident_id
            )

        # 5th should enable proactive
        incident_id = create_test_incident(knowledge_base)
        result = knowledge_base.detect_and_record_pattern(
            trigger="Container 'test' unhealthy",
            trigger_type="container_unhealthy",
            incident_id=incident_id
        )

        assert result is not None
        assert result["proactive_enabled"] is True
        assert result["occurrence_count"] == 5

    def test_pattern_signature_normalization(self, knowledge_base):
        """Test that pattern signatures are normalized."""
        sig1 = knowledge_base._generate_pattern_signature(
            "Container 'influxdb3-core' unhealthy at 2024-01-15",
            "container_unhealthy"
        )
        sig2 = knowledge_base._generate_pattern_signature(
            "Container 'telegraf' unhealthy at 2024-02-20",
            "container_unhealthy"
        )

        # Both should normalize to same pattern (container name and date removed)
        assert sig1 == sig2

    def test_get_proactive_checks_empty(self, knowledge_base):
        """Test getting proactive checks when none enabled."""
        checks = knowledge_base.get_proactive_checks()
        assert checks == []

    def test_get_proactive_checks_after_enabling(self, knowledge_base):
        """Test getting proactive checks after pattern threshold met."""
        # Create 5 incidents to enable proactive
        for i in range(5):
            incident_id = create_test_incident(knowledge_base)
            knowledge_base.detect_and_record_pattern(
                trigger="Container 'test' unhealthy",
                trigger_type="container_unhealthy",
                incident_id=incident_id
            )

        checks = knowledge_base.get_proactive_checks()
        assert len(checks) == 1
        assert "config" in checks[0]


class TestConfidenceScoring:
    """Tests for Phase 3 confidence-based execution."""

    def test_calculate_confidence_no_history(self, knowledge_base):
        """Test confidence calculation with no history."""
        confidence = knowledge_base.calculate_action_confidence(
            action_type="restart_container",
            target="unknown-container",
            trigger_type="unknown_type"
        )

        # Should return default (0.5) with no history
        assert confidence == 0.5

    def test_calculate_confidence_with_history(self, populated_knowledge_base):
        """Test confidence calculation with historical data."""
        confidence = populated_knowledge_base.calculate_action_confidence(
            action_type="restart_container",
            target="influxdb3-core",
            trigger_type="container_unhealthy"
        )

        # Should be higher than default due to successful history
        assert confidence > 0.5

    def test_get_action_recommendation_high(self, populated_knowledge_base):
        """Test action recommendation for high confidence."""
        # Force high confidence by adding more successful resolutions
        for i in range(5):
            create_test_incident(populated_knowledge_base, "container_unhealthy", "resolved")

        recommendation = populated_knowledge_base.get_action_recommendation(
            action_type="restart_container",
            target="test-container",
            trigger_type="container_unhealthy"
        )

        assert "confidence" in recommendation
        assert "recommendation" in recommendation
        assert recommendation["recommendation"] in ["auto_execute", "request_approval", "escalate"]

    def test_get_action_recommendation_structure(self, knowledge_base):
        """Test action recommendation response structure."""
        recommendation = knowledge_base.get_action_recommendation(
            action_type="restart_container",
            target="test-container",
            trigger_type="container_unhealthy"
        )

        assert "action_type" in recommendation
        assert "target" in recommendation
        assert "trigger_type" in recommendation
        assert "confidence" in recommendation
        assert "recommendation" in recommendation
        assert "reason" in recommendation
        assert "thresholds" in recommendation


class TestTrendAnalysis:
    """Tests for Phase 3 trend analysis functionality."""

    def test_get_trends_empty(self, knowledge_base):
        """Test trends on empty database."""
        trends = knowledge_base.get_incident_trends(days=7)

        assert trends["period_days"] == 7
        assert trends["total_incidents"] == 0

    def test_get_trends_with_data(self, populated_knowledge_base):
        """Test trends with populated database."""
        trends = populated_knowledge_base.get_incident_trends(days=7)

        assert trends["total_incidents"] == 5
        assert "daily_rate" in trends
        assert "resolution_rate" in trends
        assert "by_trigger_type" in trends

    def test_trends_by_trigger_type(self, populated_knowledge_base):
        """Test trends breakdown by trigger type."""
        trends = populated_knowledge_base.get_incident_trends(days=7)

        by_type = trends["by_trigger_type"]
        assert "container_unhealthy" in by_type
        assert by_type["container_unhealthy"]["count"] == 3

    def test_trending_issues_identification(self, populated_knowledge_base):
        """Test identification of trending issues."""
        trends = populated_knowledge_base.get_incident_trends(days=7)

        # container_unhealthy has 3 occurrences, should be in trending
        trending = trends["trending_issues"]
        trigger_types = [t["trigger_type"] for t in trending]
        assert "container_unhealthy" in trigger_types


class TestSuccessfulActions:
    """Tests for successful actions query."""

    def test_get_successful_actions_empty(self, knowledge_base):
        """Test with no successful actions."""
        actions = knowledge_base.get_successful_actions_for_trigger("nonexistent_type")
        assert actions == []

    def test_get_successful_actions_with_data(self, populated_knowledge_base):
        """Test getting successful actions."""
        actions = populated_knowledge_base.get_successful_actions_for_trigger(
            "container_unhealthy"
        )

        assert len(actions) > 0
        assert all("action_type" in a for a in actions)
        assert all("success_count" in a for a in actions)
