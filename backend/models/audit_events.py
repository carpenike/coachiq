"""
Enhanced Audit Event Models

Structured audit event models based on OWASP ASVS V7 guidelines.
Provides standardized, machine-readable audit logging for security operations.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Standardized audit event types for consistent logging."""

    # Authentication Events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH_SUCCESS = "auth.token.refresh.success"
    AUTH_TOKEN_REFRESH_FAILURE = "auth.token.refresh.failure"
    AUTH_SESSION_TIMEOUT = "auth.session.timeout"
    AUTH_LOCKOUT_TRIGGERED = "auth.lockout.triggered"
    AUTH_LOCKOUT_RELEASED = "auth.lockout.released"

    # Authorization Events
    AUTHZ_ACCESS_GRANTED = "authz.access.granted"
    AUTHZ_ACCESS_DENIED = "authz.access.denied"
    AUTHZ_PERMISSION_CHANGE = "authz.permission.change"
    AUTHZ_ROLE_ASSIGNMENT = "authz.role.assignment"

    # PIN Security Events
    PIN_VALIDATION_SUCCESS = "pin.validation.success"
    PIN_VALIDATION_FAILURE = "pin.validation.failure"
    PIN_CREATED = "pin.created"
    PIN_CHANGED = "pin.changed"
    PIN_LOCKOUT = "pin.lockout"

    # Safety Operation Events
    SAFETY_EMERGENCY_STOP = "safety.emergency_stop"
    SAFETY_EMERGENCY_RESET = "safety.emergency_reset"
    SAFETY_INTERLOCK_VIOLATION = "safety.interlock.violation"
    SAFETY_OVERRIDE_USED = "safety.override.used"
    SAFETY_CRITICAL_OPERATION = "safety.critical_operation"

    # Configuration Events
    CONFIG_SECURITY_CHANGED = "config.security.changed"
    CONFIG_SAFETY_CHANGED = "config.safety.changed"
    CONFIG_SYSTEM_CHANGED = "config.system.changed"

    # Data Access Events
    DATA_ACCESS_SENSITIVE = "data.access.sensitive"
    DATA_EXPORT = "data.export"
    DATA_DELETION = "data.deletion"

    # System Security Events
    SYSTEM_RATE_LIMIT_EXCEEDED = "system.rate_limit.exceeded"
    SYSTEM_INTRUSION_DETECTED = "system.intrusion.detected"
    SYSTEM_ANOMALY_DETECTED = "system.anomaly.detected"
    SYSTEM_SECURITY_SCAN = "system.security.scan"


class AuditSeverity(str, Enum):
    """Audit event severity levels."""

    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class AuditOutcome(str, Enum):
    """Standardized audit event outcomes."""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"


class AuditActor(BaseModel):
    """Information about who performed the action."""

    id: str | None = Field(None, description="User or system ID")
    username: str | None = Field(None, description="Username if available")
    ip_address: str | None = Field(None, description="IP address of the actor")
    user_agent: str | None = Field(None, description="User agent string")
    service: str | None = Field(None, description="Service or system component")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "user-123",
                "username": "admin",
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0...",
                "service": None,
            }
        }


class AuditAction(BaseModel):
    """Information about the action performed."""

    method: str = Field(..., description="Action method or operation")
    service: str = Field(..., description="Service handling the action")
    endpoint: str | None = Field(None, description="API endpoint if applicable")
    outcome: AuditOutcome = Field(..., description="Action outcome")
    reason: str | None = Field(None, description="Reason for outcome")
    duration_ms: float | None = Field(None, description="Action duration in milliseconds")

    class Config:
        json_schema_extra = {
            "example": {
                "method": "login",
                "service": "AuthenticationService",
                "endpoint": "/api/auth/login",
                "outcome": "failure",
                "reason": "invalid_credentials",
                "duration_ms": 125.5,
            }
        }


class AuditTarget(BaseModel):
    """Information about the resource acted upon."""

    type: str = Field(..., description="Type of target resource")
    id: str | None = Field(None, description="Target resource ID")
    name: str | None = Field(None, description="Human-readable name")
    attributes: dict[str, Any] | None = Field(None, description="Additional attributes")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "user_account",
                "id": "user-123",
                "name": "admin",
                "attributes": {"role": "administrator"},
            }
        }


class StructuredAuditEvent(BaseModel):
    """
    Structured audit event following OWASP ASVS V7 guidelines.

    Provides machine-readable, context-rich audit logging for security operations.
    """

    # Core identification
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    correlation_id: str | None = Field(None, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Event classification
    event_type: AuditEventType = Field(..., description="Standardized event type")
    severity: AuditSeverity = Field(..., description="Event severity level")

    # Context
    actor: AuditActor = Field(..., description="Who performed the action")
    action: AuditAction = Field(..., description="What action was performed")
    target: AuditTarget | None = Field(None, description="Resource acted upon")

    # Additional details
    details: dict[str, Any] = Field(default_factory=dict, description="Event-specific details")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")

    # Compliance and safety
    compliance_required: bool = Field(False, description="Requires compliance review")
    safety_impact: str | None = Field(None, description="Safety impact assessment")
    emergency_context: bool = Field(False, description="Emergency operation context")

    def to_log_entry(self) -> str:
        """Convert to a structured log entry string."""
        return (
            f"[{self.severity.upper()}] {self.event_type}: "
            f"actor={self.actor.username or self.actor.id or 'system'} "
            f"outcome={self.action.outcome} "
            f"target={self.target.type if self.target else 'none'} "
            f"correlation_id={self.correlation_id or 'none'}"
        )

    def to_json_log(self) -> dict[str, Any]:
        """Convert to JSON format for structured logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "actor": self.actor.model_dump(exclude_none=True),
            "action": self.action.model_dump(exclude_none=True),
            "target": self.target.model_dump(exclude_none=True) if self.target else None,
            "details": self.details,
            "tags": self.tags,
            "compliance_required": self.compliance_required,
            "safety_impact": self.safety_impact,
            "emergency_context": self.emergency_context,
        }

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "evt_a1b2c3d4e5f6",
                "correlation_id": "req_x9y8z7w6v5u4",
                "timestamp": "2024-01-01T10:00:00.123Z",
                "event_type": "auth.login.failure",
                "severity": "warning",
                "actor": {
                    "id": None,
                    "username": "testuser",
                    "ip_address": "192.168.1.100",
                    "user_agent": "Mozilla/5.0...",
                },
                "action": {
                    "method": "login",
                    "service": "AuthenticationService",
                    "endpoint": "/api/auth/login",
                    "outcome": "failure",
                    "reason": "invalid_credentials",
                    "duration_ms": 125.5,
                },
                "target": {"type": "user_account", "id": None, "name": "testuser"},
                "details": {"attempt_number": 3, "lockout_remaining": 2},
                "tags": ["authentication", "failed_login"],
                "compliance_required": False,
                "safety_impact": None,
                "emergency_context": False,
            }
        }
