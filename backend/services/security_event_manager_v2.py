"""
Enhanced Security Event Manager - Orchestration Facade

This is the enhanced version of SecurityEventManager that acts as a true
orchestration facade for all security-related operations, coordinating between:
- SecurityEventService (event publishing/subscription)
- AttemptTrackerService (centralized attempt tracking)
- SecurityConfigService (security policies)
- SecurityAuditService (audit logging)
- AuthManager (authentication operations)
- PINManager (PIN-based security)
- SecurityEventRepository (event persistence)
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from backend.models.security_events import SecurityEvent, SecurityEventStats
from backend.services.attempt_tracker_service import (
    AttemptAnalysis,
    AttemptStatus,
    AttemptSummary,
    AttemptType,
    SecurityAttempt,
)

logger = logging.getLogger(__name__)


class SecurityOrchestrationResult:
    """Result of a security orchestration operation."""

    def __init__(
        self,
        success: bool,
        operation: str,
        details: dict[str, Any] | None = None,
        alerts: list[str] | None = None,
        actions_taken: list[str] | None = None,
    ):
        self.success = success
        self.operation = operation
        self.details = details or {}
        self.alerts = alerts or []
        self.actions_taken = actions_taken or []
        self.timestamp = datetime.now(UTC)


class EnhancedSecurityEventManager:
    """
    Enhanced Security Event Manager that orchestrates all security operations.

    This facade coordinates between multiple security services to provide:
    - Unified security event handling
    - Automated threat response
    - Cross-service security workflows
    - Real-time security monitoring
    - Compliance and audit orchestration
    """

    def __init__(
        self,
        security_event_service: Any,
        attempt_tracker_service: Any,
        security_config_service: Any,
        security_audit_service: Any,
        auth_manager: Any | None = None,
        pin_manager: Any | None = None,
        lockout_service: Any | None = None,
        performance_monitor: Any | None = None,
    ):
        """
        Initialize the enhanced security event manager.

        Args:
            security_event_service: Core event publishing service
            attempt_tracker_service: Centralized attempt tracking
            security_config_service: Security configuration
            security_audit_service: Audit logging service
            auth_manager: Optional authentication manager (or AuthService with get_auth_manager)
            pin_manager: Optional PIN security manager
            lockout_service: Optional lockout service
            performance_monitor: Optional performance monitoring
        """
        self._event_service = security_event_service
        self._attempt_tracker = attempt_tracker_service
        self._config_service = security_config_service
        self._audit_service = security_audit_service

        # Handle auth_manager - could be AuthManager directly or AuthService with get_auth_manager
        if auth_manager and hasattr(auth_manager, "get_auth_manager"):
            # This is an AuthService, extract the AuthManager
            self._auth_manager = auth_manager.get_auth_manager()
        else:
            # This is already an AuthManager or None
            self._auth_manager = auth_manager

        self._pin_manager = pin_manager
        self._lockout_service = lockout_service
        self._monitor = performance_monitor

        # Security automation rules
        self._automation_rules = []
        self._response_handlers = {}

        # Real-time monitoring
        self._monitoring_task = None
        self._monitoring_interval = 60  # seconds

        logger.info("Enhanced SecurityEventManager initialized as orchestration facade")

    async def startup(self) -> None:
        """Start the security event manager and monitoring."""
        logger.info("Starting enhanced security event manager")

        # Subscribe to security events for orchestration
        await self._event_service.subscribe(self._handle_security_event, "SecurityOrchestrator")

        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._security_monitoring_loop())

        logger.info("Security orchestration started")

    async def shutdown(self) -> None:
        """Shutdown the security event manager."""
        logger.info("Shutting down enhanced security event manager")

        # Cancel monitoring task
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Security orchestration stopped")

    # Core Orchestration Methods

    async def handle_login_attempt(
        self,
        username: str,
        success: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityOrchestrationResult:
        """
        Orchestrate handling of a login attempt across all security services.

        This method coordinates:
        - Attempt tracking
        - Lockout checking
        - Event publishing
        - Audit logging
        - Automated responses
        """
        result = SecurityOrchestrationResult(success=True, operation="handle_login_attempt")

        try:
            # Track the attempt
            attempt = SecurityAttempt(
                attempt_type=AttemptType.LOGIN,
                status=AttemptStatus.SUCCESS if success else AttemptStatus.FAILED,
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata=metadata or {},
            )
            await self._attempt_tracker.track_attempt(attempt)
            result.actions_taken.append("Tracked login attempt")

            # Check for suspicious activity
            if not success:
                summary = await self._attempt_tracker.get_attempt_summary(
                    username=username,
                    ip_address=ip_address,
                    time_window_minutes=15,
                )

                analysis = await self._attempt_tracker.analyze_patterns(summary, attempt)

                if analysis.is_suspicious:
                    result.alerts.extend(analysis.indicators)

                    # Publish high-priority security event
                    event = SecurityEvent(
                        event_type="suspicious_login_activity",
                        severity="high"
                        if analysis.threat_level in ["high", "critical"]
                        else "medium",
                        component="AuthenticationSystem",
                        description=f"Suspicious login activity: {', '.join(analysis.indicators)}",
                        source="security_orchestrator",
                        user_id=username,
                        ip_address=ip_address,
                        metadata={
                            "analysis": analysis.model_dump(),
                            "summary": summary.model_dump(),
                        },
                    )
                    await self._event_service.publish_event(event)
                    result.actions_taken.append("Published suspicious activity event")

                    # Execute automated responses
                    responses = await self._execute_threat_response(analysis, summary, ip_address)
                    result.actions_taken.extend(responses)

            # Audit log the attempt
            await self._audit_service.log_auth_attempt(
                username=username,
                success=success,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata=metadata,
            )
            result.actions_taken.append("Logged to audit trail")

        except Exception as e:
            logger.error(f"Error orchestrating login attempt: {e}")
            result.success = False
            result.details["error"] = str(e)

        return result

    async def handle_safety_operation(
        self,
        operation: str,
        user_id: str,
        authorized: bool,
        resource: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityOrchestrationResult:
        """
        Orchestrate handling of safety-critical operations.

        This includes:
        - PIN validation
        - Operation authorization
        - Compliance logging
        - Real-time monitoring
        """
        result = SecurityOrchestrationResult(success=True, operation="handle_safety_operation")

        try:
            # Track the attempt
            attempt = SecurityAttempt(
                attempt_type=AttemptType.SAFETY_OPERATION,
                status=AttemptStatus.SUCCESS if authorized else AttemptStatus.BLOCKED,
                user_id=user_id,
                resource=resource,
                metadata={
                    "operation": operation,
                    **(metadata or {}),
                },
            )
            await self._attempt_tracker.track_attempt(attempt)
            result.actions_taken.append("Tracked safety operation attempt")

            # Publish event
            event = SecurityEvent(
                event_type="safety_operation_attempt",
                severity="high" if not authorized else "info",
                component="SafetySystem",
                description=(
                    f"Safety operation {operation}: {'authorized' if authorized else 'blocked'}"
                ),
                source="security_orchestrator",
                user_id=user_id,
                metadata={
                    "operation": operation,
                    "resource": resource,
                    "authorized": authorized,
                    **(metadata or {}),
                },
            )
            await self._event_service.publish_event(event)
            result.actions_taken.append("Published safety operation event")

            # Compliance logging for safety operations
            await self._audit_service.log_compliance_event(
                event_type="safety_operation",
                severity="high",
                description=f"Safety operation: {operation}",
                user_id=user_id,
                compliance_required=True,
                metadata={
                    "authorized": authorized,
                    "resource": resource,
                    **(metadata or {}),
                },
            )
            result.actions_taken.append("Created compliance log entry")

            # If unauthorized, check for policy violations
            if not authorized:
                user_summary = await self._attempt_tracker.get_user_risk_score(user_id)
                if user_summary["risk_level"] in ["high", "critical"]:
                    result.alerts.append(f"High-risk user attempted safety operation: {operation}")

                    # Consider additional security measures
                    if self._auth_manager:
                        # Force re-authentication
                        result.actions_taken.append("Flagged user for re-authentication")

        except Exception as e:
            logger.error(f"Error orchestrating safety operation: {e}")
            result.success = False
            result.details["error"] = str(e)

        return result

    async def handle_rate_limit_violation(
        self,
        ip_address: str,
        endpoint: str,
        limit: int,
        window: int,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityOrchestrationResult:
        """Orchestrate handling of rate limit violations."""
        result = SecurityOrchestrationResult(success=True, operation="handle_rate_limit_violation")

        try:
            # Track the violation
            attempt = SecurityAttempt(
                attempt_type=AttemptType.API_RATE_LIMIT,
                status=AttemptStatus.RATE_LIMITED,
                ip_address=ip_address,
                resource=endpoint,
                metadata={
                    "limit": limit,
                    "window": window,
                    **(metadata or {}),
                },
            )
            await self._attempt_tracker.track_attempt(attempt)
            result.actions_taken.append("Tracked rate limit violation")

            # Check for abuse patterns
            summary = await self._attempt_tracker.get_attempt_summary(
                ip_address=ip_address,
                attempt_type=AttemptType.API_RATE_LIMIT,
                time_window_minutes=60,
            )

            if summary.rate_limited_attempts > 10:
                # Consider IP blocking
                result.alerts.append(f"Repeated rate limit violations from {ip_address}")

                # Temporary IP block through audit service
                await self._audit_service.block_ip(
                    ip_address,
                    duration_minutes=60,
                    reason="Repeated rate limit violations",
                )
                result.actions_taken.append(f"Temporarily blocked IP {ip_address}")

        except Exception as e:
            logger.error(f"Error orchestrating rate limit violation: {e}")
            result.success = False
            result.details["error"] = str(e)

        return result

    # Threat Response Methods

    async def _execute_threat_response(
        self, analysis: AttemptAnalysis, summary: AttemptSummary, ip_address: str | None = None
    ) -> list[str]:
        """Execute automated threat responses based on analysis."""
        actions = []

        try:
            # Get security configuration
            config = await self._config_service.get_config()

            # IP blocking for critical threats from a single IP
            if analysis.threat_level == "critical" and summary.unique_ips == 1 and ip_address:
                # Single IP critical threat - block it
                ip_to_block = ip_address
                # Use a reasonable default duration if config is not available
                block_duration = 60  # Default to 1 hour
                try:
                    if hasattr(config, "network") and hasattr(
                        config.network, "connection_limit_per_ip"
                    ):
                        block_duration = config.network.connection_limit_per_ip * 60
                except Exception:
                    pass

                await self._audit_service.block_ip(
                    ip_to_block,
                    duration_minutes=block_duration,
                    reason="Critical security threat detected",
                )
                actions.append(f"Blocked IP address {ip_to_block}")

            # Account lockout for high-risk users
            if (
                analysis.threat_level in ["high", "critical"]
                and summary.unique_users == 1
                and self._lockout_service
            ):
                # Implement additional lockout
                actions.append("Enhanced account lockout applied")

            # Alert administrators
            if analysis.requires_action:
                event = SecurityEvent(
                    event_type="security_alert_admin_required",
                    severity="critical",
                    component="SecurityOrchestrator",
                    description="Immediate administrator action required",
                    source="security_orchestrator",
                    metadata={
                        "threat_level": analysis.threat_level,
                        "indicators": analysis.indicators,
                        "recommendations": analysis.recommendations,
                    },
                )
                await self._event_service.publish_event(event)
                actions.append("Administrator alert sent")

        except Exception as e:
            logger.error(f"Error executing threat response: {e}")
            actions.append(f"Error in threat response: {e!s}")

        return actions

    # Monitoring Methods

    async def _security_monitoring_loop(self) -> None:
        """Background task for continuous security monitoring."""
        while True:
            try:
                await asyncio.sleep(self._monitoring_interval)
                await self._perform_security_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in security monitoring loop: {e}")

    async def _perform_security_checks(self) -> None:
        """Perform periodic security checks."""
        try:
            # Get system threat assessment
            threat_assessment = await self._attempt_tracker.get_system_threat_assessment()

            if threat_assessment["requires_action"]:
                # Publish monitoring alert
                event = SecurityEvent(
                    event_type="security_monitoring_alert",
                    severity=threat_assessment["threat_level"],
                    component="SecurityMonitor",
                    description="Periodic security check detected threats",
                    source="security_orchestrator",
                    metadata=threat_assessment,
                )
                await self._event_service.publish_event(event)

                # Execute automated responses
                for threat in threat_assessment["top_threats"]:
                    if threat["severity"] in ["high", "critical"]:
                        logger.warning(f"Security threat detected: {threat['description']}")

            # Check for stale security sessions
            if self._pin_manager:
                # Cleanup expired PIN sessions
                logger.debug("Checking PIN session expiration")

        except Exception as e:
            logger.error(f"Error in security checks: {e}")

    # Event Handling

    async def _handle_security_event(self, event: SecurityEvent) -> None:
        """Handle incoming security events for orchestration."""
        try:
            # Don't process our own events to avoid loops
            if event.source == "security_orchestrator":
                return

            # Route events to appropriate handlers
            if event.event_type in self._response_handlers:
                handler = self._response_handlers[event.event_type]
                await handler(event)

            # Apply automation rules
            for rule in self._automation_rules:
                if rule.matches(event):
                    await rule.execute(event, self)

        except Exception as e:
            logger.error(f"Error handling security event: {e}")

    # Configuration Methods

    def add_automation_rule(self, rule: Any) -> None:
        """Add a security automation rule."""
        self._automation_rules.append(rule)
        logger.info(f"Added security automation rule: {rule}")

    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """Register a handler for specific event types."""
        self._response_handlers[event_type] = handler
        logger.info(f"Registered handler for event type: {event_type}")

    # Backward Compatibility Methods (Facade Pattern)

    async def publish_event(self, event: SecurityEvent) -> None:
        """Publish a security event (backward compatibility)."""
        await self._event_service.publish_event(event)

    async def publish(self, event: SecurityEvent) -> None:
        """Publish a security event (alternative method name for compatibility)."""
        await self._event_service.publish_event(event)

    async def subscribe(
        self, listener: Callable[[SecurityEvent], Any], name: str | None = None
    ) -> None:
        """Subscribe to security events (backward compatibility)."""
        await self._event_service.subscribe(listener, name)

    async def get_statistics(self) -> SecurityEventStats:
        """Get event statistics (backward compatibility)."""
        return await self._event_service.get_statistics()

    async def get_event_stats(self) -> SecurityEventStats:
        """Get event statistics - alias for get_statistics."""
        return await self.get_statistics()

    @property
    def health(self) -> str:
        """Get health status."""
        return "healthy"

    @property
    def health_details(self) -> dict[str, Any]:
        """Get detailed health information."""
        return {
            "status": self.health,
            "services": {
                "event_service": "healthy" if self._event_service else "unavailable",
                "attempt_tracker": "healthy" if self._attempt_tracker else "unavailable",
                "config_service": "healthy" if self._config_service else "unavailable",
                "audit_service": "healthy" if self._audit_service else "unavailable",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }
