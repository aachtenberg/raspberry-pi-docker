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
            
            return {
                "enabled": True,
                "db_type": self.db.db_type,
                "total_incidents": total_incidents,
                "resolved_incidents": resolved,
                "resolution_rate": resolved / total_incidents if total_incidents > 0 else 0,
                "health": self.db.health_check()
            }
