"""
Security Audit Service for RV Safety Operations

Provides comprehensive security audit logging and monitoring for safety-critical
operations in internet-connected RV systems, focusing on:

- Safety operation audit trails
- Security event detection and alerting
- Rate limiting for safety endpoints
- Attack pattern recognition
- Compliance logging for safety regulations

For RV-C vehicle control systems with enhanced security requirements.
"""

import json
import logging
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from enum import Enum
from ipaddress import ip_address, ip_network
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from backend.core.performance import PerformanceMonitor
from backend.models.audit_events import AuditEventType as EnhancedAuditEventType
from backend.models.audit_events import StructuredAuditEvent
from backend.repositories.security_audit_repository import SecurityAuditRepository

logger = logging.getLogger(__name__)


class SecurityEventType(str, Enum):
    """Types of security events to audit."""

    # Authentication Events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    AUTH_LOCKED = "auth_locked"
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"

    # PIN-based Authorization Events
    PIN_VALIDATION_SUCCESS = "pin_validation_success"
    PIN_VALIDATION_FAILURE = "pin_validation_failure"
    PIN_LOCKOUT = "pin_lockout"
    PIN_ROTATION = "pin_rotation"

    # Safety Operation Events
    EMERGENCY_STOP_TRIGGERED = "emergency_stop_triggered"
    EMERGENCY_STOP_RESET = "emergency_stop_reset"
    SAFETY_INTERLOCK_VIOLATED = "safety_interlock_violated"
    SAFETY_OVERRIDE_USED = "safety_override_used"

    # Entity Control Events
    ENTITY_CONTROL_SUCCESS = "entity_control_success"
    ENTITY_CONTROL_FAILURE = "entity_control_failure"
    BULK_OPERATION_STARTED = "bulk_operation_started"
    BULK_OPERATION_COMPLETED = "bulk_operation_completed"

    # Security Threats
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"

    # System Events
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"
    CONFIGURATION_CHANGED = "configuration_changed"


class SecurityEventSeverity(str, Enum):
    """Severity levels for security events."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityAuditEvent(BaseModel):
    """Security audit event record."""

    event_id: str = Field(..., description="Unique event identifier")
    event_type: SecurityEventType = Field(..., description="Type of security event")
    severity: SecurityEventSeverity = Field(..., description="Event severity level")
    timestamp: float = Field(..., description="Event timestamp (Unix time)")
    user_id: str | None = Field(None, description="User associated with event")
    source_ip: str | None = Field(None, description="Source IP address")
    endpoint: str | None = Field(None, description="API endpoint involved")
    details: dict[str, Any] = Field(default_factory=dict, description="Event-specific details")

    # Safety-specific fields
    entity_id: str | None = Field(None, description="Entity involved in operation")
    safety_impact: str | None = Field(None, description="Safety impact assessment")
    emergency_context: bool = Field(False, description="Whether event occurred during emergency")

    # Compliance fields
    compliance_required: bool = Field(
        False, description="Whether event requires compliance documentation"
    )
    reviewed: bool = Field(False, description="Whether event has been reviewed")

    def to_log_entry(self) -> str:
        """Convert to structured log entry."""
        return json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "severity": self.severity,
                "timestamp": self.timestamp,
                "iso_timestamp": datetime.fromtimestamp(self.timestamp, tz=UTC).isoformat(),
                "user_id": self.user_id,
                "source_ip": self.source_ip,
                "endpoint": self.endpoint,
                "entity_id": self.entity_id,
                "safety_impact": self.safety_impact,
                "emergency_context": self.emergency_context,
                "details": self.details,
            }
        )


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    # General API limits
    requests_per_minute: int = Field(60, description="General requests per minute per IP")
    burst_limit: int = Field(10, description="Burst request limit")

    # Safety-specific limits (more restrictive)
    safety_operations_per_minute: int = Field(
        5, description="Safety operations per minute per user"
    )
    emergency_operations_per_hour: int = Field(
        3, description="Emergency operations per hour per user"
    )
    pin_attempts_per_minute: int = Field(3, description="PIN attempts per minute per IP")

    # Protection limits
    max_failed_operations_per_hour: int = Field(
        10, description="Max failed operations before investigation"
    )

    # Exemptions
    trusted_networks: list[str] = Field(
        default_factory=list, description="Trusted IP networks (CIDR)"
    )
    admin_multiplier: float = Field(2.0, description="Rate limit multiplier for admin users")


class RateLimitEntry(BaseModel):
    """Rate limit tracking entry."""

    identifier: str = Field(..., description="IP address or user ID")
    endpoint_category: str = Field(..., description="Category of endpoint")
    requests: deque = Field(default_factory=deque, description="Request timestamps")
    blocked_until: float = Field(0, description="Blocked until timestamp")
    total_requests: int = Field(0, description="Total request count")
    blocked_requests: int = Field(0, description="Total blocked requests")


class SecurityAuditService:
    """
    Comprehensive security audit service for RV safety operations.

    Provides audit logging, rate limiting, and security monitoring
    specifically designed for safety-critical RV control systems.
    """

    def __init__(
        self,
        security_audit_repository: SecurityAuditRepository,
        performance_monitor: PerformanceMonitor,
        config: RateLimitConfig | None = None,
    ):
        """
        Initialize security audit service.

        Args:
            security_audit_repository: Repository for security audit data
            performance_monitor: Performance monitoring instance
            config: Rate limiting configuration
        """
        self._repository = security_audit_repository
        self._monitor = performance_monitor
        self.config = config or RateLimitConfig()

        # Cached data for performance
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.time()
        self._trusted_networks = [ip_network(net) for net in self.config.trusted_networks]

        # Alert thresholds
        self._alert_thresholds = {
            SecurityEventType.AUTH_FAILURE: 5,  # 5 failures in 10 minutes
            SecurityEventType.PIN_VALIDATION_FAILURE: 3,  # 3 failures in 5 minutes
            SecurityEventType.UNAUTHORIZED_ACCESS: 1,  # Immediate alert
            SecurityEventType.EMERGENCY_STOP_TRIGGERED: 1,  # Immediate alert
        }

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("Security Audit Service initialized for RV safety monitoring")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.log_security_event = self._monitor.monitor_service_method(
            "SecurityAuditService", "log_security_event"
        )(self.log_security_event)

        self.check_rate_limit = self._monitor.monitor_service_method(
            "SecurityAuditService", "check_rate_limit"
        )(self.check_rate_limit)

    async def log_security_event(
        self,
        event_type: SecurityEventType,
        severity: SecurityEventSeverity,
        user_id: str | None = None,
        source_ip: str | None = None,
        endpoint: str | None = None,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
        emergency_context: bool = False,
    ) -> str:
        """
        Log a security audit event.

        Args:
            event_type: Type of security event
            severity: Event severity level
            user_id: User associated with event
            source_ip: Source IP address
            endpoint: API endpoint involved
            entity_id: Entity involved in operation
            details: Event-specific details
            emergency_context: Whether event occurred during emergency

        Returns:
            str: Event ID
        """
        import secrets

        event_id = secrets.token_urlsafe(16)

        # Determine safety impact
        safety_impact = await self._assess_safety_impact(event_type, details or {})

        # Determine compliance requirements
        compliance_required = event_type in [
            SecurityEventType.EMERGENCY_STOP_TRIGGERED,
            SecurityEventType.EMERGENCY_STOP_RESET,
            SecurityEventType.SAFETY_INTERLOCK_VIOLATED,
            SecurityEventType.SAFETY_OVERRIDE_USED,
        ]

        event = SecurityAuditEvent(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            timestamp=time.time(),
            user_id=user_id,
            source_ip=source_ip,
            endpoint=endpoint,
            entity_id=entity_id,
            details=details or {},
            safety_impact=safety_impact,
            emergency_context=emergency_context,
            compliance_required=compliance_required,
            reviewed=False,  # Add default value for reviewed field
        )

        # Store event in repository
        await self._repository.store_audit_event(event)

        # Log to standard logger with structured format
        log_level = self._get_log_level(severity)
        logger.log(log_level, f"SECURITY_AUDIT: {event.to_log_entry()}")

        # Check for suspicious patterns
        await self._analyze_security_pattern(event)

        # Send alerts if needed
        await self._check_alert_thresholds(event_type, source_ip)

        return event_id

    async def log_structured_event(self, event: StructuredAuditEvent) -> str:
        """
        Log a structured audit event following OWASP ASVS V7 guidelines.

        Args:
            event: Pre-built structured audit event

        Returns:
            Event ID for tracking
        """
        # Convert to legacy format for repository storage
        # In future, update repository to store structured events directly
        legacy_event_type = self._map_enhanced_event_type(event.event_type)
        legacy_severity = self._map_enhanced_severity(event.severity)

        # Create legacy event
        audit_event = SecurityAuditEvent(
            event_id=event.event_id,
            event_type=legacy_event_type,
            severity=legacy_severity,
            timestamp=event.timestamp.timestamp(),
            user_id=event.actor.id or event.actor.username,
            source_ip=event.actor.ip_address,
            endpoint=event.action.endpoint,
            entity_id=event.target.id if event.target else None,
            details=event.to_json_log(),  # Store full structured event in details
            safety_impact=event.safety_impact,
            emergency_context=event.emergency_context,
            compliance_required=event.compliance_required,
            reviewed=False,
        )

        # Store in repository
        await self._repository.store_audit_event(audit_event)

        # Log to structured logger
        logger.info("STRUCTURED_AUDIT", extra={"audit_event": event.to_json_log()})

        # Analyze patterns if needed
        if event.severity in ["high", "critical"]:
            await self._analyze_security_pattern(audit_event)

        # Check alert thresholds
        if event.actor.ip_address:
            await self._check_alert_thresholds(legacy_event_type, event.actor.ip_address)

        return event.event_id

    def _map_enhanced_event_type(self, event_type: EnhancedAuditEventType) -> SecurityEventType:
        """Map enhanced event types to legacy types."""
        mapping = {
            EnhancedAuditEventType.AUTH_LOGIN_SUCCESS: SecurityEventType.AUTH_SUCCESS,
            EnhancedAuditEventType.AUTH_LOGIN_FAILURE: SecurityEventType.AUTH_FAILURE,
            EnhancedAuditEventType.AUTH_LOCKOUT_TRIGGERED: SecurityEventType.AUTH_LOCKED,
            EnhancedAuditEventType.PIN_VALIDATION_SUCCESS: SecurityEventType.PIN_VALIDATION_SUCCESS,
            EnhancedAuditEventType.PIN_VALIDATION_FAILURE: SecurityEventType.PIN_VALIDATION_FAILURE,
            EnhancedAuditEventType.SAFETY_EMERGENCY_STOP: SecurityEventType.EMERGENCY_STOP_TRIGGERED,
            # Add more mappings as needed
        }

        # Default to a generic event type if no mapping exists
        return mapping.get(event_type, SecurityEventType.ACCESS_GRANTED)

    def _map_enhanced_severity(self, severity: str) -> SecurityEventSeverity:
        """Map enhanced severity to legacy severity."""
        mapping = {
            "info": SecurityEventSeverity.LOW,
            "warning": SecurityEventSeverity.MEDIUM,
            "high": SecurityEventSeverity.HIGH,
            "critical": SecurityEventSeverity.CRITICAL,
        }
        return mapping.get(severity, SecurityEventSeverity.MEDIUM)

    async def _assess_safety_impact(
        self, event_type: SecurityEventType, details: dict[str, Any]
    ) -> str | None:
        """Assess the safety impact of a security event."""

        if event_type == SecurityEventType.EMERGENCY_STOP_TRIGGERED:
            return "critical_safety_action"
        if event_type == SecurityEventType.SAFETY_INTERLOCK_VIOLATED:
            return "safety_constraint_violated"
        if event_type in [
            SecurityEventType.ENTITY_CONTROL_SUCCESS,
            SecurityEventType.ENTITY_CONTROL_FAILURE,
        ]:
            # Check if controlling safety-critical entities
            entity_type = details.get("entity_type", "")
            if entity_type in ["slide_room", "awning", "leveling_jack", "brake"]:
                return "position_critical_operation"
        elif event_type == SecurityEventType.UNAUTHORIZED_ACCESS:
            return "potential_safety_compromise"

        return None

    def _get_log_level(self, severity: SecurityEventSeverity) -> int:
        """Convert severity to logging level."""
        mapping = {
            SecurityEventSeverity.LOW: logging.INFO,
            SecurityEventSeverity.MEDIUM: logging.WARNING,
            SecurityEventSeverity.HIGH: logging.ERROR,
            SecurityEventSeverity.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(severity, logging.INFO)

    async def _analyze_security_pattern(self, event: SecurityAuditEvent) -> None:
        """Analyze event for suspicious security patterns."""

        if not event.source_ip:
            return

        pattern_key = f"{event.source_ip}:{event.event_type}"
        await self._repository.track_suspicious_pattern(pattern_key, event.timestamp)

        # Check for brute force patterns
        if event.event_type in [
            SecurityEventType.AUTH_FAILURE,
            SecurityEventType.PIN_VALIDATION_FAILURE,
        ]:
            recent_failures = await self._repository.get_pattern_count(pattern_key, hours=1.0)
            if recent_failures >= 5:  # 5 failures in an hour
                await self.log_security_event(
                    SecurityEventType.BRUTE_FORCE_ATTEMPT,
                    SecurityEventSeverity.HIGH,
                    source_ip=event.source_ip,
                    details={
                        "failure_count": recent_failures,
                        "pattern_type": event.event_type,
                        "time_window_hours": 1,
                    },
                )

                # Block IP temporarily
                await self._repository.add_blocked_ip(event.source_ip)
                logger.warning(f"Blocked IP {event.source_ip} due to brute force pattern")

    async def _check_alert_thresholds(
        self, event_type: SecurityEventType, source_ip: str | None
    ) -> None:
        """Check if event type exceeds alert thresholds."""

        if event_type not in self._alert_thresholds:
            return

        threshold = self._alert_thresholds[event_type]

        # Count recent events of this type
        recent_events = await self._repository.get_audit_events(
            event_type=event_type,
            hours=0.167,  # 10 minutes
            limit=threshold + 1,
        )

        if len(recent_events) >= threshold:
            await self.log_security_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                SecurityEventSeverity.HIGH,
                source_ip=source_ip,
                details={
                    "triggered_by": event_type,
                    "event_count": len(recent_events),
                    "threshold": threshold,
                    "time_window_minutes": 10,
                },
            )

    async def check_rate_limit(
        self,
        identifier: str,  # IP address or user ID
        endpoint_category: str,  # "general", "safety", "emergency", "pin_auth"
        is_admin: bool = False,
        source_ip: str | None = None,
    ) -> bool:
        """
        Check if request exceeds rate limits.

        Args:
            identifier: IP address or user ID for rate limiting
            endpoint_category: Category of endpoint being accessed
            is_admin: Whether user has admin privileges
            source_ip: Source IP for logging

        Returns:
            bool: True if request is allowed, False if rate limited
        """

        # Clean up old entries periodically
        if time.time() - self._last_cleanup > self._cleanup_interval:
            await self._cleanup_rate_limits()

        # Check if IP is blocked
        blocked_ips = await self._repository.get_blocked_ips()
        if source_ip and source_ip in blocked_ips:
            await self.log_security_event(
                SecurityEventType.RATE_LIMIT_EXCEEDED,
                SecurityEventSeverity.MEDIUM,
                source_ip=source_ip,
                details={"reason": "ip_blocked", "category": endpoint_category},
            )
            return False

        # Check if IP is in trusted networks
        if source_ip and self._is_trusted_ip(source_ip):
            return True

        # Get rate limit for category
        limit = self._get_rate_limit(endpoint_category, is_admin)
        time_window = self._get_time_window(endpoint_category)

        # Get or create rate limit entry
        entry = await self._repository.get_rate_limit(identifier)
        if not entry:
            entry = RateLimitEntry(
                identifier=identifier,
                endpoint_category=endpoint_category,
                requests=deque(),
                blocked_until=0,
                total_requests=0,
                blocked_requests=0,
            )

        now = time.time()

        # Check if currently blocked
        if entry.blocked_until > now:
            entry.blocked_requests += 1
            await self._repository.store_rate_limit(identifier, entry)
            await self.log_security_event(
                SecurityEventType.RATE_LIMIT_EXCEEDED,
                SecurityEventSeverity.MEDIUM,
                source_ip=source_ip,
                details={
                    "identifier": identifier,
                    "category": endpoint_category,
                    "blocked_until": entry.blocked_until,
                },
            )
            return False

        # Clean old requests
        cutoff = now - time_window
        while entry.requests and entry.requests[0] < cutoff:
            entry.requests.popleft()

        # Check if limit exceeded
        if len(entry.requests) >= limit:
            # Block for time window
            entry.blocked_until = now + time_window
            entry.blocked_requests += 1

            await self._repository.store_rate_limit(identifier, entry)
            await self.log_security_event(
                SecurityEventType.RATE_LIMIT_EXCEEDED,
                SecurityEventSeverity.HIGH,
                source_ip=source_ip,
                details={
                    "identifier": identifier,
                    "category": endpoint_category,
                    "limit": limit,
                    "time_window_seconds": time_window,
                    "request_count": len(entry.requests),
                },
            )
            return False

        # Allow request
        entry.requests.append(now)
        entry.total_requests += 1
        await self._repository.store_rate_limit(identifier, entry)
        return True

    def _is_trusted_ip(self, ip_str: str) -> bool:
        """Check if IP is in trusted networks."""
        try:
            ip = ip_address(ip_str)
            return any(ip in network for network in self._trusted_networks)
        except ValueError:
            return False

    def _get_rate_limit(self, category: str, is_admin: bool) -> int:
        """Get rate limit for endpoint category."""
        limits = {
            "general": self.config.requests_per_minute,
            "safety": self.config.safety_operations_per_minute,
            "emergency": self.config.emergency_operations_per_hour,
            "pin_auth": self.config.pin_attempts_per_minute,
        }

        base_limit = limits.get(category, self.config.requests_per_minute)

        if is_admin:
            return int(base_limit * self.config.admin_multiplier)

        return base_limit

    def _get_time_window(self, category: str) -> int:
        """Get time window for rate limiting in seconds."""
        windows = {
            "general": 60,  # 1 minute
            "safety": 60,  # 1 minute
            "emergency": 3600,  # 1 hour
            "pin_auth": 60,  # 1 minute
        }

        return windows.get(category, 60)

    async def _cleanup_rate_limits(self) -> None:
        """Clean up expired rate limit entries."""
        # Clean up rate limits
        cleaned_count = await self._repository.cleanup_rate_limits(inactive_hours=1)

        # Clean up blocked IPs
        unblocked_count = await self._repository.cleanup_blocked_ips(hours=1)

        self._last_cleanup = time.time()

        if cleaned_count > 0:
            logger.debug(f"Cleaned up {cleaned_count} expired rate limit entries")
        if unblocked_count > 0:
            logger.debug(f"Unblocked {unblocked_count} IP addresses")

    async def get_security_summary(self, hours: int = 24) -> dict[str, Any]:
        """Get security summary for the specified time period."""
        summary = await self._repository.get_security_summary(hours)

        # Add additional pattern information
        recent_events = await self._repository.get_audit_events(hours=hours, limit=1000)

        summary["security_patterns"] = {
            "suspicious_activity_detected": len(
                [e for e in recent_events if e.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY]
            ),
            "brute_force_attempts": len(
                [e for e in recent_events if e.event_type == SecurityEventType.BRUTE_FORCE_ATTEMPT]
            ),
        }

        return summary

    async def get_audit_events(
        self,
        event_type: SecurityEventType | None = None,
        severity: SecurityEventSeverity | None = None,
        user_id: str | None = None,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get filtered audit events."""
        events = await self._repository.get_audit_events(
            event_type=event_type, severity=severity, user_id=user_id, hours=hours, limit=limit
        )

        return [event.model_dump() for event in events]

    async def get_rate_limit_status(self, identifier: str) -> dict[str, Any] | None:
        """Get rate limit status for identifier."""
        entry = await self._repository.get_rate_limit(identifier)
        if not entry:
            return None

        now = time.time()

        return {
            "identifier": entry.identifier,
            "endpoint_category": entry.endpoint_category,
            "is_blocked": entry.blocked_until > now,
            "blocked_until": entry.blocked_until,
            "current_requests": len(entry.requests),
            "total_requests": entry.total_requests,
            "blocked_requests": entry.blocked_requests,
            "requests_in_window": len(
                [
                    req
                    for req in entry.requests
                    if req > now - self._get_time_window(entry.endpoint_category)
                ]
            ),
        }
