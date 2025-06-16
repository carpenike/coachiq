"""
Security Event Models

Standardized data models for security monitoring events across all system components.
Supports CAN bus security, authentication events, and future security data sources.
"""

import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SecurityEventType(str, Enum):
    """Types of security events that can be generated."""

    # CAN Bus Security Events
    CAN_RATE_LIMIT_VIOLATION = "can_rate_limit_violation"
    CAN_PGN_SCANNING = "can_pgn_scanning"
    CAN_BROADCAST_STORM = "can_broadcast_storm"
    CAN_SOURCE_ACL_VIOLATION = "can_source_acl_violation"
    CAN_UNAUTHORIZED_MESSAGE = "can_unauthorized_message"
    CAN_MESSAGE_FLOOD = "can_message_flood"
    CAN_SUSPICIOUS_PATTERN = "can_suspicious_pattern"

    # Authentication & Authorization Events
    AUTH_LOGIN_SUCCESS = "auth_login_success"
    AUTH_LOGIN_FAILURE = "auth_login_failure"
    AUTH_SESSION_EXPIRED = "auth_session_expired"
    AUTH_PRIVILEGE_ESCALATION = "auth_privilege_escalation"
    AUTH_BRUTE_FORCE_ATTEMPT = "auth_brute_force_attempt"

    # System Security Events
    SYSTEM_EMERGENCY_STOP = "system_emergency_stop"
    SYSTEM_SAFETY_VIOLATION = "system_safety_violation"
    SYSTEM_CONFIG_CHANGE = "system_config_change"
    SYSTEM_SERVICE_FAILURE = "system_service_failure"

    # Network Security Events (Future)
    NETWORK_INTRUSION_ATTEMPT = "network_intrusion_attempt"
    NETWORK_DDoS_DETECTED = "network_ddos_detected"
    NETWORK_UNAUTHORIZED_ACCESS = "network_unauthorized_access"


class SecuritySeverity(str, Enum):
    """Security event severity levels following industry standards."""

    INFO = "info"        # Informational events, normal operation
    LOW = "low"          # Minor security concern, no immediate action needed
    MEDIUM = "medium"    # Security concern requiring monitoring
    HIGH = "high"        # Serious security issue requiring immediate attention
    CRITICAL = "critical"  # Critical security incident requiring emergency response


class SecurityEvent(BaseModel):
    """
    Standardized security event model for all security monitoring components.

    This model provides a consistent interface for security events across
    CAN bus monitoring, authentication, network security, and other sources.
    """

    # Core Identification
    event_id: str = Field(default_factory=lambda: f"sec_{uuid.uuid4().hex[:12]}")
    event_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Temporal Information
    timestamp: float = Field(default_factory=time.time)
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))

    # Event Classification
    source_component: str = Field(..., description="Component that generated the event")
    event_type: SecurityEventType = Field(..., description="Type of security event")
    severity: SecuritySeverity = Field(..., description="Severity level of the event")

    # Event Details
    title: str = Field(..., description="Human-readable event title")
    description: str = Field(..., description="Detailed event description")

    # Event-specific data (flexible JSON payload)
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific data")

    # Context and metadata
    event_metadata: dict[str, Any] | None = Field(default=None, description="Additional context", alias="metadata")

    # Correlation fields
    incident_id: str | None = Field(default=None, description="Associated incident ID")
    correlation_id: str | None = Field(default=None, description="Event correlation ID")

    # Response tracking
    acknowledged: bool = Field(default=False, description="Whether event has been acknowledged")
    acknowledged_by: str | None = Field(default=None, description="User who acknowledged event")
    acknowledged_at: float | None = Field(default=None, description="Acknowledgment timestamp")

    # Evidence and remediation
    evidence_data: dict[str, Any] | None = Field(default=None, description="Supporting evidence")
    remediation_action: str | None = Field(default=None, description="Suggested remediation")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    @classmethod
    def create_can_event(
        cls,
        event_type: SecurityEventType,
        severity: SecuritySeverity,
        title: str,
        description: str,
        source_address: int | None = None,
        pgn: int | None = None,
        **payload_data
    ) -> "SecurityEvent":
        """
        Factory method for creating CAN bus security events.

        Args:
            event_type: Type of CAN security event
            severity: Severity level
            title: Human-readable title
            description: Detailed description
            source_address: CAN source address (if applicable)
            pgn: Parameter Group Number (if applicable)
            **payload_data: Additional event-specific data

        Returns:
            SecurityEvent instance configured for CAN bus events
        """
        payload = {
            "source_address": source_address,
            "source_address_hex": f"0x{source_address:02X}" if source_address else None,
            "pgn": pgn,
            "pgn_hex": f"0x{pgn:05X}" if pgn else None,
            **payload_data
        }

        return cls(
            source_component="can_anomaly_detector",
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            payload=payload
        )

    @classmethod
    def create_auth_event(
        cls,
        event_type: SecurityEventType,
        severity: SecuritySeverity,
        title: str,
        description: str,
        user_id: str | None = None,
        ip_address: str | None = None,
        **payload_data
    ) -> "SecurityEvent":
        """
        Factory method for creating authentication security events.

        Args:
            event_type: Type of auth security event
            severity: Severity level
            title: Human-readable title
            description: Detailed description
            user_id: User identifier (if applicable)
            ip_address: Client IP address (if applicable)
            **payload_data: Additional event-specific data

        Returns:
            SecurityEvent instance configured for authentication events
        """
        payload = {
            "user_id": user_id,
            "ip_address": ip_address,
            **payload_data
        }

        return cls(
            source_component="auth_manager",
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            payload=payload
        )

    @classmethod
    def create_system_event(
        cls,
        event_type: SecurityEventType,
        severity: SecuritySeverity,
        title: str,
        description: str,
        component: str | None = None,
        **payload_data
    ) -> "SecurityEvent":
        """
        Factory method for creating system security events.

        Args:
            event_type: Type of system security event
            severity: Severity level
            title: Human-readable title
            description: Detailed description
            component: System component involved
            **payload_data: Additional event-specific data

        Returns:
            SecurityEvent instance configured for system events
        """
        payload = {
            "component": component,
            **payload_data
        }

        return cls(
            source_component="safety_service",
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            payload=payload
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.dict()

    def to_json_str(self) -> str:
        """Convert to JSON string."""
        return self.json()


class SecurityIncident(BaseModel):
    """
    Security incident model for grouping related security events.

    Incidents represent higher-level security situations that may
    involve multiple related events requiring investigation.
    """

    # Core Identification
    incident_id: str = Field(default_factory=lambda: f"inc_{uuid.uuid4().hex[:12]}")
    incident_uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Temporal Information
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    closed_at: float | None = Field(default=None)

    # Incident Details
    title: str = Field(..., description="Human-readable incident title")
    description: str = Field(..., description="Detailed incident description")
    status: str = Field(default="open", description="Incident status")

    # Severity and Classification
    severity: SecuritySeverity = Field(..., description="Incident severity level")
    category: str = Field(..., description="Incident category")

    # Investigation Details
    assigned_to: str | None = Field(default=None, description="Assigned investigator")
    investigation_notes: str | None = Field(default=None, description="Investigation notes")

    # Event Relationships
    event_count: int = Field(default=0, description="Number of associated events")
    primary_event_id: str | None = Field(default=None, description="Primary triggering event")

    # Resolution
    resolution: str | None = Field(default=None, description="Incident resolution")
    remediation_actions: list[str] | None = Field(default=None, description="Actions taken")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


# Event statistics and aggregation models
class SecurityEventStats(BaseModel):
    """Security event statistics for dashboard display."""

    total_events: int = 0
    events_by_severity: dict[str, int] = Field(default_factory=dict)
    events_by_type: dict[str, int] = Field(default_factory=dict)
    events_by_component: dict[str, int] = Field(default_factory=dict)
    events_last_hour: int = 0
    events_last_24h: int = 0
    active_incidents: int = 0
    critical_alerts: int = 0


class SecurityDashboardData(BaseModel):
    """Complete security dashboard data model."""

    current_time: float = Field(default_factory=time.time)
    stats: SecurityEventStats = Field(default_factory=SecurityEventStats)
    recent_events: list[SecurityEvent] = Field(default_factory=list)
    active_incidents: list[SecurityIncident] = Field(default_factory=list)
    system_status: str = "monitoring"
    threat_level: SecuritySeverity = SecuritySeverity.INFO
