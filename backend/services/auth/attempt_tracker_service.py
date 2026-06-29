"""
Attempt Tracker Service - Centralized Security Attempt Tracking

Provides centralized tracking of all security-related attempts including:
- Authentication login attempts
- PIN validation attempts
- API rate limit violations
- Safety operation attempts
- Unauthorized access attempts

This service aggregates attempt data from multiple sources and provides
unified tracking and analysis capabilities for the Security Event Manager.
"""

import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.core.performance import PerformanceMonitor
from backend.models.security_events import SecurityEvent
from backend.repositories.auth_repository import AuthEventRepository
from backend.repositories.security_audit_repository import SecurityAuditRepository

logger = logging.getLogger(__name__)


class AttemptType(str, Enum):
    """Types of security attempts tracked."""

    LOGIN = "login"
    PIN_VALIDATION = "pin_validation"
    API_RATE_LIMIT = "api_rate_limit"
    SAFETY_OPERATION = "safety_operation"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    MFA = "mfa"
    TOKEN_REFRESH = "token_refresh"
    PERMISSION_CHECK = "permission_check"


class AttemptStatus(str, Enum):
    """Status of security attempts."""

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    EXPIRED = "expired"


class SecurityAttempt(BaseModel):
    """Model for a security attempt."""

    attempt_type: AttemptType = Field(..., description="Type of security attempt")
    status: AttemptStatus = Field(..., description="Status of the attempt")
    user_id: str | None = Field(None, description="User ID if authenticated")
    username: str | None = Field(None, description="Username for login attempts")
    ip_address: str | None = Field(None, description="IP address of attempt")
    user_agent: str | None = Field(None, description="User agent string")
    resource: str | None = Field(None, description="Resource being accessed")
    reason: str | None = Field(None, description="Reason for failure or blocking")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AttemptSummary(BaseModel):
    """Summary of attempts for a specific context."""

    total_attempts: int = Field(0, description="Total number of attempts")
    successful_attempts: int = Field(0, description="Number of successful attempts")
    failed_attempts: int = Field(0, description="Number of failed attempts")
    blocked_attempts: int = Field(0, description="Number of blocked attempts")
    rate_limited_attempts: int = Field(0, description="Number of rate limited attempts")
    unique_users: int = Field(0, description="Number of unique users")
    unique_ips: int = Field(0, description="Number of unique IP addresses")
    time_window_minutes: int = Field(0, description="Time window for the summary")
    by_type: dict[str, int] = Field(default_factory=dict, description="Attempts by type")
    by_status: dict[str, int] = Field(default_factory=dict, description="Attempts by status")


class AttemptAnalysis(BaseModel):
    """Analysis of attempt patterns."""

    is_suspicious: bool = Field(False, description="Whether pattern is suspicious")
    threat_level: str = Field("low", description="Threat level: low, medium, high, critical")
    indicators: list[str] = Field(default_factory=list, description="Suspicious indicators")
    recommendations: list[str] = Field(default_factory=list, description="Security recommendations")
    requires_action: bool = Field(False, description="Whether immediate action is required")


class AttemptTrackerService:
    """
    Centralized service for tracking all security-related attempts.

    This service aggregates attempt data from multiple sources and provides
    unified tracking, analysis, and alerting capabilities.
    """

    def __init__(
        self,
        auth_event_repository: AuthEventRepository,
        security_audit_repository: SecurityAuditRepository,
        performance_monitor: PerformanceMonitor,
        security_event_service: Any | None = None,  # For publishing events
    ):
        """
        Initialize the attempt tracker service.

        Args:
            auth_event_repository: Repository for auth events
            security_audit_repository: Repository for security audits
            performance_monitor: Performance monitoring instance
            security_event_service: Optional security event service for alerts
        """
        self._auth_event_repo = auth_event_repository
        self._audit_repo = security_audit_repository
        self._monitor = performance_monitor
        self._event_service = security_event_service

        # Thresholds for suspicious activity detection
        self._thresholds = {
            "failed_login_threshold": 5,
            "failed_pin_threshold": 3,
            "rate_limit_threshold": 10,
            "unique_ip_threshold": 5,
            "time_window_minutes": 15,
        }

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("AttemptTrackerService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.track_attempt = self._monitor.monitor_service_method(
            "AttemptTrackerService", "track_attempt"
        )(self.track_attempt)

        self.get_attempt_summary = self._monitor.monitor_service_method(
            "AttemptTrackerService", "get_attempt_summary"
        )(self.get_attempt_summary)

        self.analyze_patterns = self._monitor.monitor_service_method(
            "AttemptTrackerService", "analyze_patterns"
        )(self.analyze_patterns)

    async def track_attempt(self, attempt: SecurityAttempt) -> None:
        """
        Track a security attempt.

        Args:
            attempt: Security attempt to track
        """
        # Store in appropriate repository based on type
        if attempt.attempt_type in [AttemptType.LOGIN, AttemptType.TOKEN_REFRESH, AttemptType.MFA]:
            # Store in auth event repository
            success = attempt.status == AttemptStatus.SUCCESS
            await self._auth_event_repo.create_auth_event(
                username=attempt.username or attempt.user_id or "unknown",
                event_type=attempt.attempt_type.value,
                success=success,
                metadata={
                    "ip_address": attempt.ip_address,
                    "user_agent": attempt.user_agent,
                    "reason": attempt.reason,
                    "status": attempt.status.value,
                    **attempt.metadata,
                },
            )

        # Always store in security audit
        await self._audit_repo.log_security_event(
            event_type=f"attempt_{attempt.attempt_type.value}",
            severity="info" if attempt.status == AttemptStatus.SUCCESS else "warning",
            description=f"{attempt.attempt_type.value} attempt: {attempt.status.value}",
            user_id=attempt.user_id,
            ip_address=attempt.ip_address,
            user_agent=attempt.user_agent,
            metadata={
                "username": attempt.username,
                "resource": attempt.resource,
                "reason": attempt.reason,
                "status": attempt.status.value,
                **attempt.metadata,
            },
        )

        # Analyze for suspicious patterns
        if attempt.status in [
            AttemptStatus.FAILED,
            AttemptStatus.BLOCKED,
            AttemptStatus.RATE_LIMITED,
        ]:
            await self._check_suspicious_activity(attempt)

        logger.debug(
            f"Tracked {attempt.attempt_type.value} attempt: "
            f"status={attempt.status.value}, user={attempt.user_id or attempt.username}"
        )

    async def _check_suspicious_activity(self, attempt: SecurityAttempt) -> None:
        """Check if the attempt is part of suspicious activity."""
        # Get recent summary
        summary = await self.get_attempt_summary(
            user_id=attempt.user_id,
            username=attempt.username,
            ip_address=attempt.ip_address,
            time_window_minutes=self._thresholds["time_window_minutes"],
        )

        # Analyze patterns
        analysis = await self.analyze_patterns(summary, attempt)

        # Publish security event if suspicious
        if analysis.is_suspicious and self._event_service:
            event = SecurityEvent(
                event_type="suspicious_activity_detected",
                severity="high" if analysis.threat_level in ["high", "critical"] else "medium",
                component="AttemptTrackerService",
                description=f"Suspicious activity detected: {', '.join(analysis.indicators)}",
                source="attempt_tracker",
                user_id=attempt.user_id,
                ip_address=attempt.ip_address,
                metadata={
                    "threat_level": analysis.threat_level,
                    "indicators": analysis.indicators,
                    "recommendations": analysis.recommendations,
                    "attempt_type": attempt.attempt_type.value,
                    "summary": summary.model_dump(),
                },
            )

            await self._event_service.publish_event(event)

            # Log critical audit entry
            await self._audit_repo.log_security_event(
                event_type="suspicious_activity",
                severity=analysis.threat_level,
                description=f"Suspicious activity: {', '.join(analysis.indicators)}",
                user_id=attempt.user_id,
                ip_address=attempt.ip_address,
                metadata={
                    "analysis": analysis.model_dump(),
                    "attempt": attempt.model_dump(),
                },
            )

    async def get_attempt_summary(
        self,
        user_id: str | None = None,
        username: str | None = None,
        ip_address: str | None = None,
        attempt_type: AttemptType | None = None,
        time_window_minutes: int = 60,
    ) -> AttemptSummary:
        """
        Get summary of attempts for specified criteria.

        Args:
            user_id: Filter by user ID
            username: Filter by username
            ip_address: Filter by IP address
            attempt_type: Filter by attempt type
            time_window_minutes: Time window to analyze

        Returns:
            Summary of attempts
        """
        since = datetime.now(UTC) - timedelta(minutes=time_window_minutes)

        # Use aggregation methods for efficient summary
        summary = AttemptSummary(time_window_minutes=time_window_minutes)

        # Get auth events summary if relevant
        if not attempt_type or attempt_type in [
            AttemptType.LOGIN,
            AttemptType.TOKEN_REFRESH,
            AttemptType.MFA,
        ]:
            auth_summary = await self._auth_event_repo.get_auth_events_summary(
                user_id=user_id,
                username=username,
                event_type=attempt_type.value if attempt_type else None,
                since=since,
            )

            # Merge auth summary into main summary
            summary.total_attempts += auth_summary["total_attempts"]
            summary.successful_attempts += auth_summary["successful_attempts"]
            summary.failed_attempts += auth_summary["failed_attempts"]

            for evt_type, count in auth_summary["by_type"].items():
                summary.by_type[evt_type] = summary.by_type.get(evt_type, 0) + count

            for status, count in auth_summary["by_status"].items():
                summary.by_status[status] = summary.by_status.get(status, 0) + count

            summary.unique_users = auth_summary["unique_users"]
            summary.unique_ips = auth_summary["unique_ips"]

        # Get security audit events summary
        audit_summary = await self._audit_repo.get_security_events_summary(
            since=since,
            event_type_prefix=f"attempt_{attempt_type.value}" if attempt_type else "attempt_",
            user_id=user_id,
            ip_address=ip_address,
        )

        # Merge audit summary into main summary
        # Note: Don't double-count auth events that might also be in audit log
        for evt_type, count in audit_summary["by_type"].items():
            if not evt_type.startswith("attempt_login"):  # Avoid double counting login attempts
                summary.total_attempts += count
                clean_type = evt_type.replace("attempt_", "")
                summary.by_type[clean_type] = summary.by_type.get(clean_type, 0) + count

        # Extract status counts from audit events
        for status, count in audit_summary["by_status"].items():
            if status == "blocked":
                summary.blocked_attempts += count
            elif status == "rate_limited":
                summary.rate_limited_attempts += count
            summary.by_status[status] = summary.by_status.get(status, 0) + count

        # Combine unique counts (max of auth and audit counts)
        summary.unique_users = max(summary.unique_users, audit_summary["unique_users"])
        summary.unique_ips = max(summary.unique_ips, audit_summary["unique_ips"])

        return summary

    async def analyze_patterns(
        self,
        summary: AttemptSummary,
        current_attempt: SecurityAttempt | None = None,
    ) -> AttemptAnalysis:
        """
        Analyze attempt patterns for suspicious activity.

        Args:
            summary: Attempt summary to analyze
            current_attempt: Current attempt for context

        Returns:
            Analysis results
        """
        analysis = AttemptAnalysis()

        # Check failed login attempts
        failed_logins = summary.by_type.get("login", 0) - summary.successful_attempts
        if failed_logins >= self._thresholds["failed_login_threshold"]:
            analysis.is_suspicious = True
            analysis.indicators.append(f"Excessive failed login attempts: {failed_logins}")
            analysis.recommendations.append("Consider temporary account lockout")

        # Check failed PIN attempts
        failed_pins = summary.by_type.get("pin_validation", 0) - summary.successful_attempts
        if failed_pins >= self._thresholds["failed_pin_threshold"]:
            analysis.is_suspicious = True
            analysis.indicators.append(f"Excessive failed PIN attempts: {failed_pins}")
            analysis.recommendations.append("Review PIN security policies")

        # Check rate limit violations
        rate_limited = summary.rate_limited_attempts
        if rate_limited >= self._thresholds["rate_limit_threshold"]:
            analysis.is_suspicious = True
            analysis.indicators.append(f"Excessive rate limit violations: {rate_limited}")
            analysis.recommendations.append("Consider IP-based blocking")

        # Check for distributed attack pattern
        if summary.unique_ips >= self._thresholds["unique_ip_threshold"]:
            analysis.is_suspicious = True
            analysis.indicators.append(f"Multiple IP addresses: {summary.unique_ips}")
            analysis.recommendations.append("Possible distributed attack pattern")

        # Check for credential stuffing
        if summary.unique_users > 10 and summary.failed_attempts > summary.successful_attempts * 2:
            analysis.is_suspicious = True
            analysis.indicators.append("Potential credential stuffing attack")
            analysis.recommendations.append("Enable additional authentication factors")

        # Determine threat level
        if len(analysis.indicators) >= 3:
            analysis.threat_level = "critical"
            analysis.requires_action = True
        elif len(analysis.indicators) >= 2:
            analysis.threat_level = "high"
            analysis.requires_action = True
        elif len(analysis.indicators) >= 1:
            analysis.threat_level = "medium"

        # Add context-specific recommendations
        if current_attempt:
            if current_attempt.attempt_type == AttemptType.SAFETY_OPERATION:
                analysis.recommendations.append("Review safety operation permissions")
                analysis.threat_level = "high"  # Safety operations are always high priority

            if current_attempt.status == AttemptStatus.BLOCKED:
                analysis.recommendations.append("Review blocking rules effectiveness")

        return analysis

    async def get_user_risk_score(self, user_id: str) -> dict[str, Any]:
        """
        Calculate risk score for a specific user.

        Args:
            user_id: User to analyze

        Returns:
            Risk score and details
        """
        # Get summaries for different time windows in parallel for better performance
        import asyncio

        hour_task = self.get_attempt_summary(user_id=user_id, time_window_minutes=60)
        day_task = self.get_attempt_summary(user_id=user_id, time_window_minutes=1440)
        week_task = self.get_attempt_summary(user_id=user_id, time_window_minutes=10080)

        # Execute in parallel
        hour_summary, day_summary, week_summary = await asyncio.gather(
            hour_task, day_task, week_task
        )

        # Calculate risk factors
        risk_score = 0
        risk_factors = []

        # Recent failures
        if hour_summary.failed_attempts > 0:
            risk_score += hour_summary.failed_attempts * 10
            risk_factors.append(f"Recent failures: {hour_summary.failed_attempts}")

        # Blocked attempts
        if day_summary.blocked_attempts > 0:
            risk_score += day_summary.blocked_attempts * 20
            risk_factors.append(f"Blocked attempts: {day_summary.blocked_attempts}")

        # Rate limiting
        if day_summary.rate_limited_attempts > 0:
            risk_score += day_summary.rate_limited_attempts * 5
            risk_factors.append(f"Rate limited: {day_summary.rate_limited_attempts}")

        # Multiple IPs
        if day_summary.unique_ips > 3:
            risk_score += (day_summary.unique_ips - 3) * 15
            risk_factors.append(f"Multiple IPs: {day_summary.unique_ips}")

        # Determine risk level
        if risk_score >= 100:
            risk_level = "critical"
        elif risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "user_id": user_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "hour_summary": hour_summary.model_dump(),
            "day_summary": day_summary.model_dump(),
            "recommendations": await self._get_risk_recommendations(risk_level, risk_factors),
        }

    async def _get_risk_recommendations(
        self, risk_level: str, risk_factors: list[str]
    ) -> list[str]:
        """Get recommendations based on risk level and factors."""
        recommendations = []

        if risk_level in ["high", "critical"]:
            recommendations.append("Consider forcing password reset")
            recommendations.append("Enable multi-factor authentication")

        if risk_level == "critical":
            recommendations.append("Review account for compromise")
            recommendations.append("Consider temporary account suspension")

        if any("Multiple IPs" in factor for factor in risk_factors):
            recommendations.append("Review login locations for anomalies")

        if any("Rate limited" in factor for factor in risk_factors):
            recommendations.append("Review API usage patterns")

        return recommendations

    async def get_system_threat_assessment(self) -> dict[str, Any]:
        """
        Get overall system threat assessment.

        Returns:
            System-wide threat analysis
        """
        # Get system-wide summary in parallel
        import asyncio

        hour_task = self.get_attempt_summary(time_window_minutes=60)
        day_task = self.get_attempt_summary(time_window_minutes=1440)

        hour_summary, day_summary = await asyncio.gather(hour_task, day_task)

        # Analyze patterns
        hour_analysis = await self.analyze_patterns(hour_summary)
        day_analysis = await self.analyze_patterns(day_summary)

        # Determine overall threat level
        if hour_analysis.threat_level == "critical" or day_analysis.threat_level == "critical":
            overall_threat = "critical"
        elif hour_analysis.threat_level == "high" or day_analysis.threat_level == "high":
            overall_threat = "high"
        elif hour_analysis.threat_level == "medium" or day_analysis.threat_level == "medium":
            overall_threat = "medium"
        else:
            overall_threat = "low"

        return {
            "threat_level": overall_threat,
            "requires_action": hour_analysis.requires_action or day_analysis.requires_action,
            "hour_analysis": {
                "summary": hour_summary.model_dump(),
                "analysis": hour_analysis.model_dump(),
            },
            "day_analysis": {
                "summary": day_summary.model_dump(),
                "analysis": day_analysis.model_dump(),
            },
            "top_threats": self._identify_top_threats(hour_analysis, day_analysis),
            "recommendations": list(
                set(hour_analysis.recommendations + day_analysis.recommendations)
            ),
        }

    def _identify_top_threats(
        self, hour_analysis: AttemptAnalysis, day_analysis: AttemptAnalysis
    ) -> list[dict[str, Any]]:
        """Identify top threats from analyses."""
        threats = []

        # Combine indicators
        all_indicators = hour_analysis.indicators + day_analysis.indicators

        # Categorize threats
        if any("credential stuffing" in ind.lower() for ind in all_indicators):
            threats.append(
                {
                    "type": "credential_stuffing",
                    "severity": "high",
                    "description": "Potential credential stuffing attack detected",
                }
            )

        if any("distributed attack" in ind.lower() for ind in all_indicators):
            threats.append(
                {
                    "type": "distributed_attack",
                    "severity": "critical",
                    "description": "Distributed attack pattern detected",
                }
            )

        if any("failed login" in ind.lower() for ind in all_indicators):
            threats.append(
                {
                    "type": "brute_force",
                    "severity": "medium",
                    "description": "Brute force login attempts detected",
                }
            )

        return threats[:3]  # Return top 3 threats
