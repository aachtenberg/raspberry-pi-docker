"""
Knowledge Base for Agentic SRE - Persistent Learning and Memory.

Supports both SQLite (local/dev) and PostgreSQL (production) via abstraction layer.
Stores incidents, runbooks, actions, and learnings for continuous improvement.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum

# Try to import database libraries
try:
    from sqlalchemy import (
        create_engine, Column, Integer, String, Float, Text, JSON, 
        DateTime, ForeignKey, Index, Boolean, Table, MetaData, text
    )
    from sqlalchemy.orm import declarative_base, sessionmaker, relationship
    from sqlalchemy.pool import StaticPool, QueuePool
    SQLALCHEMY_AVAILABLE = True
    Base = declarative_base()
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    Base = None


def _log(level: str, msg: str, **fields: Any) -> None:
    """Structured logging."""
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "msg": msg,
        **fields
    }
    print(json.dumps(payload, ensure_ascii=False))


# ============================= Schema Models ==================================

class OutcomeType(str, Enum):
    """Investigation outcome types."""
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"
    ERROR = "error"
    IN_PROGRESS = "in_progress"


class ActionType(str, Enum):
    """Action types taken during investigation."""
    RESTART_CONTAINER = "restart_container"
    SCALE_SERVICE = "scale_service"
    UPDATE_CONFIG = "update_config"
    ROLLBACK = "rollback"
    ALERT_CREATED = "alert_created"
    NONE = "none"


if SQLALCHEMY_AVAILABLE:
    class Incident(Base):
        """Incident record - one per investigation."""
        __tablename__ = 'incidents'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        trigger = Column(String(500), nullable=False, index=True)
        trigger_type = Column(String(100), index=True)  # metric_anomaly, container_failure, etc
        
        # Timestamps
        detected_at = Column(DateTime(timezone=True), nullable=False, index=True)
        started_at = Column(DateTime(timezone=True), nullable=False)
        completed_at = Column(DateTime(timezone=True))
        
        # Investigation details
        outcome = Column(String(50), nullable=False, index=True)
        duration_seconds = Column(Float)
        llm_iterations = Column(Integer, default=0)
        
        # Results
        findings = Column(Text)
        root_cause = Column(Text)
        resolution_summary = Column(Text)
        
        # Metadata
        extra_metadata = Column(JSON)  # Flexible field for extra context
        
        # Relationships
        actions = relationship("Action", back_populates="incident", cascade="all, delete-orphan")
        tool_calls = relationship("ToolCall", back_populates="incident", cascade="all, delete-orphan")
        verifications = relationship("Verification", back_populates="incident", cascade="all, delete-orphan")
        
        # Indexes
        __table_args__ = (
            Index('idx_trigger_outcome', 'trigger_type', 'outcome'),
            Index('idx_detected_at', 'detected_at'),
        )
    
    
    class Action(Base):
        """Actions taken during an incident."""
        __tablename__ = 'actions'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        incident_id = Column(Integer, ForeignKey('incidents.id'), nullable=False, index=True)
        
        action_type = Column(String(100), nullable=False, index=True)
        target = Column(String(200))  # Container name, service, etc
        parameters = Column(JSON)
        
        executed_at = Column(DateTime(timezone=True), nullable=False)
        success = Column(Boolean, nullable=False)
        error_message = Column(Text)
        
        # Did this action resolve the issue?
        resolved_incident = Column(Boolean, default=False)
        
        incident = relationship("Incident", back_populates="actions")
        
        __table_args__ = (
            Index('idx_action_type_success', 'action_type', 'success'),
        )
    
    
    class ToolCall(Base):
        """Tool calls made during investigation."""
        __tablename__ = 'tool_calls'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        incident_id = Column(Integer, ForeignKey('incidents.id'), nullable=False, index=True)
        
        tool_name = Column(String(100), nullable=False, index=True)
        arguments = Column(JSON)
        result = Column(JSON)
        error_message = Column(Text)
        
        called_at = Column(DateTime(timezone=True), nullable=False)
        duration_ms = Column(Float)
        success = Column(Boolean, nullable=False)
        
        incident = relationship("Incident", back_populates="tool_calls")
    
    
    class Verification(Base):
        """Verification checks after actions."""
        __tablename__ = 'verifications'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        incident_id = Column(Integer, ForeignKey('incidents.id'), nullable=False, index=True)
        
        check_type = Column(String(100), nullable=False)  # metric_check, log_check, health_check
        check_description = Column(Text)
        
        verified_at = Column(DateTime(timezone=True), nullable=False)
        passed = Column(Boolean, nullable=False)
        details = Column(JSON)
        
        incident = relationship("Incident", back_populates="verifications")
    
    
    class Runbook(Base):
        """Learned procedures for common issues."""
        __tablename__ = 'runbooks'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        
        pattern = Column(String(500), nullable=False, unique=True, index=True)
        pattern_type = Column(String(100), index=True)
        
        # Steps (ordered JSON array)
        steps = Column(JSON, nullable=False)
        
        # Success metrics
        times_used = Column(Integer, default=0)
        success_count = Column(Integer, default=0)
        avg_resolution_time_seconds = Column(Float)
        
        # Learned from which incidents
        learned_from_incident_ids = Column(JSON)  # Array of incident IDs
        
        created_at = Column(DateTime(timezone=True), nullable=False)
        updated_at = Column(DateTime(timezone=True), nullable=False)
        
        extra_metadata = Column(JSON)
    
    
    class Pattern(Base):
        """Detected patterns across incidents."""
        __tablename__ = 'patterns'
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        
        pattern_signature = Column(String(500), nullable=False, unique=True, index=True)
        description = Column(Text)
        
        # Frequency and recency
        occurrence_count = Column(Integer, default=1)
        first_seen = Column(DateTime(timezone=True), nullable=False)
        last_seen = Column(DateTime(timezone=True), nullable=False)
        
        # Related incidents
        related_incident_ids = Column(JSON)
        
        # Should we create proactive check?
        proactive_check_enabled = Column(Boolean, default=False)
        proactive_check_config = Column(JSON)
        
        extra_metadata = Column(JSON)


# ============================== Database Manager ==============================

class DatabaseManager:
    """
    Abstraction layer for database operations.
    Supports both SQLite (local/dev) and PostgreSQL (production).
    """
    
    def __init__(self):
        self.db_type = os.getenv("KNOWLEDGE_BASE_DB_TYPE", "sqlite").lower()
        self.engine = None
        self.SessionLocal = None
        
        if not SQLALCHEMY_AVAILABLE:
            _log("error", "SQLAlchemy not available - knowledge base disabled")
            return
        
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Initialize database connection based on configuration."""
        if self.db_type == "postgresql":
            # PostgreSQL connection (production on raspberrypi2)
            host = os.getenv("KNOWLEDGE_BASE_PG_HOST", "raspberrypi2.local")
            port = os.getenv("KNOWLEDGE_BASE_PG_PORT", "5432")
            database = os.getenv("KNOWLEDGE_BASE_PG_DATABASE", "sre_knowledge")
            user = os.getenv("KNOWLEDGE_BASE_PG_USER", "sre_agent")
            password = os.getenv("KNOWLEDGE_BASE_PG_PASSWORD", "")
            
            if not password:
                _log("error", "PostgreSQL password not configured", 
                     env_var="KNOWLEDGE_BASE_PG_PASSWORD")
                raise ValueError("KNOWLEDGE_BASE_PG_PASSWORD required for PostgreSQL")
            
            connection_string = (
                f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
            )
            
            self.engine = create_engine(
                connection_string,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # Verify connections before using
                echo=False
            )
            
            _log("info", "PostgreSQL connection initialized",
                 host=host, database=database, pool_size=5)
        
        else:
            # SQLite connection (local development)
            db_path = os.getenv("KNOWLEDGE_BASE_SQLITE_PATH", 
                               "/app/incidents/knowledge.db")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            connection_string = f"sqlite:///{db_path}"
            
            self.engine = create_engine(
                connection_string,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
                echo=False
            )
            
            _log("info", "SQLite connection initialized", path=db_path)
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        # Create tables if they don't exist
        Base.metadata.create_all(bind=self.engine)
        _log("info", "Database schema initialized")
    
    @contextmanager
    def session_scope(self):
        """Provide a transactional scope for database operations."""
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized")
        
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            _log("error", "Database transaction failed", error=str(e))
            raise
        finally:
            session.close()
    
    def health_check(self) -> bool:
        """Check database connection health."""
        try:
            with self.session_scope() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            _log("error", "Database health check failed", error=str(e))
            return False


# ============================== Knowledge Base ================================

class KnowledgeBase:
    """
    High-level interface for storing and querying SRE knowledge.
    """
    
    def __init__(self):
        self.db = DatabaseManager()
    
    def record_incident(
        self,
        trigger: str,
        trigger_type: str,
        outcome: str,
        findings: str,
        actions: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        verifications: List[Dict[str, Any]],
        root_cause: Optional[str] = None,
        resolution_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        duration_seconds: Optional[float] = None,
        llm_iterations: int = 0
    ) -> int:
        """
        Record a completed incident investigation.
        Returns incident ID.
        """
        if not SQLALCHEMY_AVAILABLE:
            return -1
        
        now = datetime.now(timezone.utc)
        
        with self.db.session_scope() as session:
            incident = Incident(
                trigger=trigger,
                trigger_type=trigger_type,
                detected_at=now,
                started_at=now,
                completed_at=now,
                outcome=outcome,
                duration_seconds=duration_seconds,
                llm_iterations=llm_iterations,
                findings=findings,
                root_cause=root_cause,
                resolution_summary=resolution_summary,
                extra_metadata=metadata or {}
            )
            
            session.add(incident)
            session.flush()  # Get incident ID
            
            # Add actions
            for action_data in actions:
                action = Action(
                    incident_id=incident.id,
                    action_type=action_data.get("type"),
                    target=action_data.get("target"),
                    parameters=action_data.get("parameters"),
                    executed_at=datetime.fromisoformat(action_data.get("timestamp")),
                    success=action_data.get("success", True),
                    error_message=action_data.get("error"),
                    resolved_incident=action_data.get("resolved_incident", False)
                )
                session.add(action)
            
            # Add tool calls
            for tool_data in tool_calls:
                tool_call = ToolCall(
                    incident_id=incident.id,
                    tool_name=tool_data.get("name"),
                    arguments=tool_data.get("arguments"),
                    result=tool_data.get("result"),
                    error_message=tool_data.get("error"),
                    called_at=datetime.fromisoformat(tool_data.get("timestamp")),
                    duration_ms=tool_data.get("duration_ms"),
                    success=tool_data.get("success", True)
                )
                session.add(tool_call)
            
            # Add verifications
            for verification_data in verifications:
                verification = Verification(
                    incident_id=incident.id,
                    check_type=verification_data.get("type"),
                    check_description=verification_data.get("description"),
                    verified_at=datetime.fromisoformat(verification_data.get("timestamp")),
                    passed=verification_data.get("passed"),
                    details=verification_data.get("details")
                )
                session.add(verification)
            
            _log("info", "Incident recorded", 
                 incident_id=incident.id, 
                 trigger=trigger[:100],
                 outcome=outcome)
            
            return incident.id
    
    def find_similar_incidents(
        self,
        trigger: str,
        trigger_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find similar past incidents based on trigger text.
        Uses simple text matching for now - can be enhanced with embeddings.
        """
        if not SQLALCHEMY_AVAILABLE:
            return []
        
        with self.db.session_scope() as session:
            query = session.query(Incident).filter(
                Incident.trigger.contains(trigger[:50])  # Partial match
            )
            
            if trigger_type:
                query = query.filter(Incident.trigger_type == trigger_type)
            
            # Prioritize resolved incidents
            query = query.order_by(
                (Incident.outcome == OutcomeType.RESOLVED.value).desc(),
                Incident.detected_at.desc()
            ).limit(limit)
            
            incidents = query.all()
            
            return [
                {
                    "id": inc.id,
                    "trigger": inc.trigger,
                    "trigger_type": inc.trigger_type,
                    "outcome": inc.outcome,
                    "findings": inc.findings,
                    "root_cause": inc.root_cause,
                    "resolution_summary": inc.resolution_summary,
                    "detected_at": inc.detected_at.isoformat(),
                    "duration_seconds": inc.duration_seconds
                }
                for inc in incidents
            ]
    
    def get_successful_actions_for_trigger(
        self,
        trigger_type: str
    ) -> List[Dict[str, Any]]:
        """
        Get actions that successfully resolved similar incidents.
        Used for confidence scoring.
        """
        if not SQLALCHEMY_AVAILABLE:
            return []
        
        with self.db.session_scope() as session:
            actions = session.query(Action).join(Incident).filter(
                Incident.trigger_type == trigger_type,
                Incident.outcome == OutcomeType.RESOLVED.value,
                Action.success == True,
                Action.resolved_incident == True
            ).all()
            
            action_stats = {}
            for action in actions:
                key = f"{action.action_type}:{action.target}"
                if key not in action_stats:
                    action_stats[key] = {
                        "action_type": action.action_type,
                        "target": action.target,
                        "success_count": 0,
                        "total_count": 0
                    }
                action_stats[key]["success_count"] += 1
                action_stats[key]["total_count"] += 1
            
            return list(action_stats.values())
    
    def calculate_action_confidence(
        self,
        action_type: str,
        target: str,
        trigger_type: str
    ) -> float:
        """
        Calculate confidence score (0-1) for an action based on historical success.
        """
        if not SQLALCHEMY_AVAILABLE:
            return 0.5  # Default medium confidence
        
        with self.db.session_scope() as session:
            # Get all past uses of this action for this trigger type
            total = session.query(Action).join(Incident).filter(
                Action.action_type == action_type,
                Action.target == target,
                Incident.trigger_type == trigger_type
            ).count()
            
            if total == 0:
                return 0.5  # No history, medium confidence
            
            # Get successful uses
            successes = session.query(Action).join(Incident).filter(
                Action.action_type == action_type,
                Action.target == target,
                Incident.trigger_type == trigger_type,
                Action.success == True,
                Incident.outcome == OutcomeType.RESOLVED.value
            ).count()
            
            # Calculate confidence with Laplace smoothing
            # (successes + 1) / (total + 2) to avoid 0 or 1 extremes
            confidence = (successes + 1) / (total + 2)
            
            _log("debug", "Calculated action confidence",
                 action_type=action_type,
                 target=target,
                 trigger_type=trigger_type,
                 successes=successes,
                 total=total,
                 confidence=confidence)
            
            return confidence
    
    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics."""
        if not SQLALCHEMY_AVAILABLE:
            return {"enabled": False}

        with self.db.session_scope() as session:
            total_incidents = session.query(Incident).count()
            resolved = session.query(Incident).filter(
                Incident.outcome == OutcomeType.RESOLVED.value
            ).count()
            total_runbooks = session.query(Runbook).count()
            total_patterns = session.query(Pattern).count()

            return {
                "enabled": True,
                "db_type": self.db.db_type,
                "total_incidents": total_incidents,
                "resolved_incidents": resolved,
                "resolution_rate": resolved / total_incidents if total_incidents > 0 else 0,
                "total_runbooks": total_runbooks,
                "total_patterns": total_patterns,
                "health": self.db.health_check()
            }

    # ========================= Phase 3: Knowledge Query Methods =========================

    def query_incidents(
        self,
        query: str,
        trigger_type: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search past incidents using natural language query.
        Searches trigger, findings, root_cause, and resolution_summary fields.
        """
        if not SQLALCHEMY_AVAILABLE:
            return []

        with self.db.session_scope() as session:
            # Build query with text search across multiple fields
            base_query = session.query(Incident)

            # Apply text search (simple LIKE for now, can be enhanced with full-text search)
            search_terms = query.lower().split()
            for term in search_terms[:5]:  # Limit to 5 terms
                term_pattern = f"%{term}%"
                base_query = base_query.filter(
                    (Incident.trigger.ilike(term_pattern)) |
                    (Incident.findings.ilike(term_pattern)) |
                    (Incident.root_cause.ilike(term_pattern)) |
                    (Incident.resolution_summary.ilike(term_pattern))
                )

            if trigger_type:
                base_query = base_query.filter(Incident.trigger_type == trigger_type)

            if outcome:
                base_query = base_query.filter(Incident.outcome == outcome)

            # Order by relevance (resolved first, then recent)
            base_query = base_query.order_by(
                (Incident.outcome == OutcomeType.RESOLVED.value).desc(),
                Incident.detected_at.desc()
            ).limit(limit)

            incidents = base_query.all()

            results = []
            for inc in incidents:
                # Get actions for this incident
                actions = [
                    {
                        "type": a.action_type,
                        "target": a.target,
                        "success": a.success,
                        "resolved_incident": a.resolved_incident
                    }
                    for a in inc.actions
                ]

                results.append({
                    "id": inc.id,
                    "trigger": inc.trigger,
                    "trigger_type": inc.trigger_type,
                    "outcome": inc.outcome,
                    "findings": inc.findings,
                    "root_cause": inc.root_cause,
                    "resolution_summary": inc.resolution_summary,
                    "detected_at": inc.detected_at.isoformat(),
                    "duration_seconds": inc.duration_seconds,
                    "actions": actions
                })

            _log("info", "Knowledge base query completed",
                 query=query[:100], results_count=len(results))

            return results

    def get_runbook(self, pattern: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a runbook for a given pattern.
        Returns None if no runbook exists.
        """
        if not SQLALCHEMY_AVAILABLE:
            return None

        with self.db.session_scope() as session:
            # Try exact match first
            runbook = session.query(Runbook).filter(
                Runbook.pattern == pattern
            ).first()

            # Try partial match if no exact match
            if not runbook:
                runbook = session.query(Runbook).filter(
                    Runbook.pattern.ilike(f"%{pattern}%")
                ).first()

            if not runbook:
                return None

            success_rate = (runbook.success_count / runbook.times_used
                          if runbook.times_used > 0 else 0)

            return {
                "id": runbook.id,
                "pattern": runbook.pattern,
                "pattern_type": runbook.pattern_type,
                "steps": runbook.steps,
                "times_used": runbook.times_used,
                "success_count": runbook.success_count,
                "success_rate": success_rate,
                "avg_resolution_time_seconds": runbook.avg_resolution_time_seconds,
                "created_at": runbook.created_at.isoformat(),
                "updated_at": runbook.updated_at.isoformat()
            }

    def get_all_runbooks(self) -> List[Dict[str, Any]]:
        """Get all runbooks ordered by success rate."""
        if not SQLALCHEMY_AVAILABLE:
            return []

        with self.db.session_scope() as session:
            runbooks = session.query(Runbook).order_by(
                Runbook.success_count.desc()
            ).all()

            return [
                {
                    "id": rb.id,
                    "pattern": rb.pattern,
                    "pattern_type": rb.pattern_type,
                    "times_used": rb.times_used,
                    "success_rate": rb.success_count / rb.times_used if rb.times_used > 0 else 0,
                    "avg_resolution_time_seconds": rb.avg_resolution_time_seconds
                }
                for rb in runbooks
            ]

    def update_runbook_usage(self, runbook_id: int, success: bool, resolution_time: float) -> None:
        """Update runbook statistics after use."""
        if not SQLALCHEMY_AVAILABLE:
            return

        with self.db.session_scope() as session:
            runbook = session.query(Runbook).filter(Runbook.id == runbook_id).first()
            if runbook:
                runbook.times_used += 1
                if success:
                    runbook.success_count += 1

                # Update average resolution time (running average)
                if runbook.avg_resolution_time_seconds:
                    total_time = runbook.avg_resolution_time_seconds * (runbook.times_used - 1)
                    runbook.avg_resolution_time_seconds = (total_time + resolution_time) / runbook.times_used
                else:
                    runbook.avg_resolution_time_seconds = resolution_time

                runbook.updated_at = datetime.now(timezone.utc)

    # ========================= Phase 3: Runbook Auto-Generation =========================

    def maybe_generate_runbook(self, trigger_type: str, min_occurrences: int = 3) -> Optional[Dict[str, Any]]:
        """
        Auto-generate a runbook if we have enough successful resolutions.
        Called after each successful incident resolution.
        Returns the new runbook if created, None otherwise.
        """
        if not SQLALCHEMY_AVAILABLE:
            return None

        with self.db.session_scope() as session:
            # Check if runbook already exists for this trigger type
            existing = session.query(Runbook).filter(
                Runbook.pattern_type == trigger_type
            ).first()

            if existing:
                return None  # Already have a runbook

            # Find all resolved incidents of this type
            resolved_incidents = session.query(Incident).filter(
                Incident.trigger_type == trigger_type,
                Incident.outcome == OutcomeType.RESOLVED.value
            ).order_by(Incident.detected_at.desc()).limit(10).all()

            if len(resolved_incidents) < min_occurrences:
                return None  # Not enough data

            # Extract common patterns from successful resolutions
            action_sequence = self._extract_common_action_sequence(
                session, [inc.id for inc in resolved_incidents]
            )

            if not action_sequence:
                return None  # No consistent pattern found

            # Calculate average resolution time
            avg_time = sum(
                inc.duration_seconds or 0 for inc in resolved_incidents
            ) / len(resolved_incidents)

            # Create runbook
            now = datetime.now(timezone.utc)
            runbook = Runbook(
                pattern=f"auto:{trigger_type}",
                pattern_type=trigger_type,
                steps=action_sequence,
                times_used=0,
                success_count=0,
                avg_resolution_time_seconds=avg_time,
                learned_from_incident_ids=[inc.id for inc in resolved_incidents],
                created_at=now,
                updated_at=now,
                extra_metadata={
                    "auto_generated": True,
                    "source_incidents_count": len(resolved_incidents)
                }
            )

            session.add(runbook)
            session.flush()

            _log("info", "Auto-generated runbook",
                 pattern_type=trigger_type,
                 steps_count=len(action_sequence),
                 source_incidents=len(resolved_incidents))

            return {
                "id": runbook.id,
                "pattern": runbook.pattern,
                "pattern_type": runbook.pattern_type,
                "steps": runbook.steps,
                "avg_resolution_time_seconds": avg_time
            }

    def _extract_common_action_sequence(
        self,
        session,
        incident_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Extract common action patterns from successful incidents.
        Returns ordered list of steps that appear in most incidents.
        """
        from collections import Counter

        # Get all successful actions from these incidents
        actions = session.query(Action).filter(
            Action.incident_id.in_(incident_ids),
            Action.success == True
        ).order_by(Action.executed_at).all()

        if not actions:
            return []

        # Count action types and targets
        action_counts = Counter()
        for action in actions:
            key = (action.action_type, action.target)
            action_counts[key] += 1

        # Keep actions that appear in at least 50% of incidents
        threshold = len(incident_ids) * 0.5
        common_actions = [
            {"action": action_type, "target": target, "frequency": count}
            for (action_type, target), count in action_counts.items()
            if count >= threshold
        ]

        # Build step sequence
        steps = []
        for i, action_info in enumerate(common_actions, 1):
            steps.append({
                "step": i,
                "action": action_info["action"],
                "target": action_info["target"],
                "description": f"{action_info['action']} on {action_info['target']}",
                "confidence": action_info["frequency"] / len(incident_ids)
            })

        return steps

    # ========================= Phase 3: Pattern Detection =========================

    def detect_and_record_pattern(
        self,
        trigger: str,
        trigger_type: str,
        incident_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if this trigger matches an existing pattern or creates a new one.
        Called after each incident recording.
        Returns pattern info if pattern threshold met.
        """
        if not SQLALCHEMY_AVAILABLE:
            return None

        # Generate pattern signature from trigger
        signature = self._generate_pattern_signature(trigger, trigger_type)

        with self.db.session_scope() as session:
            # Check for existing pattern
            pattern = session.query(Pattern).filter(
                Pattern.pattern_signature == signature
            ).first()

            now = datetime.now(timezone.utc)

            if pattern:
                # Update existing pattern
                pattern.occurrence_count += 1
                pattern.last_seen = now

                # Add incident ID to related list
                related_ids = pattern.related_incident_ids or []
                related_ids.append(incident_id)
                pattern.related_incident_ids = related_ids[-20:]  # Keep last 20

                _log("info", "Pattern occurrence recorded",
                     signature=signature,
                     occurrence_count=pattern.occurrence_count)

                # Check if we should enable proactive monitoring
                if pattern.occurrence_count >= 5 and not pattern.proactive_check_enabled:
                    pattern.proactive_check_enabled = True
                    pattern.proactive_check_config = self._generate_proactive_config(
                        trigger_type, signature
                    )

                    _log("info", "Proactive monitoring enabled for pattern",
                         signature=signature,
                         config=pattern.proactive_check_config)

                    return {
                        "pattern_id": pattern.id,
                        "signature": signature,
                        "occurrence_count": pattern.occurrence_count,
                        "proactive_enabled": True,
                        "proactive_config": pattern.proactive_check_config
                    }
            else:
                # Create new pattern
                pattern = Pattern(
                    pattern_signature=signature,
                    description=f"Pattern for {trigger_type}: {trigger[:100]}",
                    occurrence_count=1,
                    first_seen=now,
                    last_seen=now,
                    related_incident_ids=[incident_id],
                    proactive_check_enabled=False,
                    extra_metadata={"trigger_type": trigger_type}
                )
                session.add(pattern)

                _log("info", "New pattern created", signature=signature)

            return None

    def _generate_pattern_signature(self, trigger: str, trigger_type: str) -> str:
        """Generate a consistent signature for pattern matching."""
        import re

        # Normalize the trigger text
        normalized = trigger.lower()

        # Remove specific container names but keep structure
        normalized = re.sub(r"'[^']+'" , "'<container>'", normalized)

        # Remove timestamps and IDs
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}', '<date>', normalized)
        normalized = re.sub(r'\d+\.\d+\.\d+\.\d+', '<ip>', normalized)
        normalized = re.sub(r'[a-f0-9]{12,}', '<id>', normalized)

        # Create signature
        return f"{trigger_type}:{normalized[:200]}"

    def _generate_proactive_config(self, trigger_type: str, signature: str) -> Dict[str, Any]:
        """Generate proactive monitoring configuration based on pattern type."""
        configs = {
            "container_unhealthy": {
                "check_type": "docker_health",
                "interval_seconds": 300,
                "threshold": "health != 'healthy'",
                "action": "alert"
            },
            "container_exited": {
                "check_type": "docker_status",
                "interval_seconds": 60,
                "threshold": "status == 'exited'",
                "action": "investigate"
            },
            "prometheus_target_down": {
                "check_type": "prometheus_query",
                "interval_seconds": 60,
                "query": "up == 0",
                "threshold": "result_count > 0",
                "action": "investigate"
            },
            "scrape_quality_degraded": {
                "check_type": "prometheus_query",
                "interval_seconds": 120,
                "query": "scrape_samples_scraped < 5",
                "threshold": "result_count > 0",
                "action": "alert"
            }
        }

        return configs.get(trigger_type, {
            "check_type": "generic",
            "interval_seconds": 300,
            "action": "alert"
        })

    def get_proactive_checks(self) -> List[Dict[str, Any]]:
        """Get all enabled proactive checks from patterns."""
        if not SQLALCHEMY_AVAILABLE:
            return []

        with self.db.session_scope() as session:
            patterns = session.query(Pattern).filter(
                Pattern.proactive_check_enabled == True
            ).all()

            return [
                {
                    "pattern_id": p.id,
                    "signature": p.pattern_signature,
                    "occurrence_count": p.occurrence_count,
                    "config": p.proactive_check_config,
                    "last_seen": p.last_seen.isoformat()
                }
                for p in patterns
            ]

    # ========================= Phase 3: Confidence-Based Execution =========================

    def get_action_recommendation(
        self,
        action_type: str,
        target: str,
        trigger_type: str
    ) -> Dict[str, Any]:
        """
        Get recommendation for whether to execute an action.
        Returns confidence score and execution recommendation.
        """
        confidence = self.calculate_action_confidence(action_type, target, trigger_type)

        # Thresholds for autonomous execution
        HIGH_CONFIDENCE = 0.85
        MEDIUM_CONFIDENCE = 0.5

        if confidence >= HIGH_CONFIDENCE:
            recommendation = "auto_execute"
            reason = f"High confidence ({confidence:.2f}) based on historical success"
        elif confidence >= MEDIUM_CONFIDENCE:
            recommendation = "request_approval"
            reason = f"Medium confidence ({confidence:.2f}) - human approval recommended"
        else:
            recommendation = "escalate"
            reason = f"Low confidence ({confidence:.2f}) - escalate to human operator"

        return {
            "action_type": action_type,
            "target": target,
            "trigger_type": trigger_type,
            "confidence": confidence,
            "recommendation": recommendation,
            "reason": reason,
            "thresholds": {
                "auto_execute": HIGH_CONFIDENCE,
                "request_approval": MEDIUM_CONFIDENCE
            }
        }

    # ========================= Phase 3: Trend Analysis =========================

    def get_incident_trends(self, days: int = 7) -> Dict[str, Any]:
        """
        Analyze incident trends over the specified period.
        Used for proactive monitoring decisions.
        """
        if not SQLALCHEMY_AVAILABLE:
            return {}

        from datetime import timedelta

        with self.db.session_scope() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Get incidents in period
            incidents = session.query(Incident).filter(
                Incident.detected_at >= cutoff
            ).all()

            if not incidents:
                return {"period_days": days, "total_incidents": 0}

            # Aggregate by trigger type
            by_type = {}
            for inc in incidents:
                t = inc.trigger_type or "unknown"
                if t not in by_type:
                    by_type[t] = {"count": 0, "resolved": 0, "escalated": 0}
                by_type[t]["count"] += 1
                if inc.outcome == "resolved":
                    by_type[t]["resolved"] += 1
                elif inc.outcome == "escalated":
                    by_type[t]["escalated"] += 1

            # Calculate daily rate
            daily_rate = len(incidents) / days

            # Identify trending issues (increasing frequency)
            trending = []
            for trigger_type, stats in by_type.items():
                if stats["count"] >= 3:  # At least 3 occurrences
                    trending.append({
                        "trigger_type": trigger_type,
                        "count": stats["count"],
                        "resolution_rate": stats["resolved"] / stats["count"],
                        "daily_rate": stats["count"] / days
                    })

            trending.sort(key=lambda x: x["count"], reverse=True)

            return {
                "period_days": days,
                "total_incidents": len(incidents),
                "daily_rate": daily_rate,
                "by_trigger_type": by_type,
                "trending_issues": trending[:5],
                "resolution_rate": sum(
                    1 for i in incidents if i.outcome == "resolved"
                ) / len(incidents)
            }
