"""
Security Events Database Models

SQLAlchemy models for storing security events and incidents in the database.
These models correspond to the Pydantic models in security_events.py but are
optimized for database storage and querying.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base


class SecurityEventDB(Base):
    """
    Database model for security events.

    Stores security events from all system components with proper indexing
    for efficient querying by time, severity, type, and component.
    """

    __tablename__ = "security_events"

    # Primary key
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Auto-incrementing primary key"
    )

    # Core event identification
    event_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, comment="Unique event identifier"
    )

    event_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, comment="UUID for event"
    )

    # Temporal information
    timestamp: Mapped[float] = mapped_column(
        Float, nullable=False, index=True, comment="Event timestamp (Unix timestamp)"
    )

    timestamp_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="Event timestamp in milliseconds"
    )

    # Event classification
    source_component: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Component that generated the event"
    )

    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Type of security event"
    )

    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="Event severity level"
    )

    # Event details
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Human-readable event title"
    )

    description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Detailed event description"
    )

    # Event-specific data (flexible JSON payload)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Event-specific data payload"
    )

    # Context and metadata
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Additional context and metadata"
    )

    # Correlation fields
    incident_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Associated incident ID"
    )

    correlation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Event correlation ID"
    )

    # Response tracking
    acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether event has been acknowledged",
    )

    acknowledged_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="User who acknowledged event"
    )

    acknowledged_at: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Acknowledgment timestamp"
    )

    # Evidence and remediation
    evidence_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Supporting evidence"
    )

    remediation_action: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Suggested remediation"
    )

    # Database timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), comment="Database record creation timestamp"
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Database record last update timestamp",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert database model to dictionary."""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "event_uuid": self.event_uuid,
            "timestamp": self.timestamp,
            "timestamp_ms": self.timestamp_ms,
            "source_component": self.source_component,
            "event_type": self.event_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "payload": self.payload,
            "metadata": self.event_metadata,
            "incident_id": self.incident_id,
            "correlation_id": self.correlation_id,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at,
            "evidence_data": self.evidence_data,
            "remediation_action": self.remediation_action,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SecurityIncidentDB(Base):
    """
    Database model for security incidents.

    Groups related security events into incidents for investigation and tracking.
    """

    __tablename__ = "security_incidents"

    # Primary key
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="Auto-incrementing primary key"
    )

    # Core incident identification
    incident_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, comment="Unique incident identifier"
    )

    incident_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, comment="UUID for incident"
    )

    # Temporal information
    created_at: Mapped[float] = mapped_column(
        Float, nullable=False, index=True, comment="Incident creation timestamp"
    )

    updated_at: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Last update timestamp"
    )

    closed_at: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Incident closure timestamp"
    )

    # Incident details
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Human-readable incident title"
    )

    description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Detailed incident description"
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="open", index=True, comment="Incident status"
    )

    # Severity and classification
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="Incident severity level"
    )

    category: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Incident category"
    )

    # Investigation details
    assigned_to: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Assigned investigator"
    )

    investigation_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Investigation notes"
    )

    # Event relationships
    event_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of associated events"
    )

    primary_event_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Primary triggering event"
    )

    # Resolution
    resolution: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Incident resolution"
    )

    remediation_actions: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="Actions taken"
    )

    # Database timestamps
    db_created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), comment="Database record creation timestamp"
    )

    db_updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Database record last update timestamp",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert database model to dictionary."""
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "incident_uuid": self.incident_uuid,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "severity": self.severity,
            "category": self.category,
            "assigned_to": self.assigned_to,
            "investigation_notes": self.investigation_notes,
            "event_count": self.event_count,
            "primary_event_id": self.primary_event_id,
            "resolution": self.resolution,
            "remediation_actions": self.remediation_actions,
            "db_created_at": self.db_created_at.isoformat() if self.db_created_at else None,
            "db_updated_at": self.db_updated_at.isoformat() if self.db_updated_at else None,
        }
