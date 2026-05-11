"""
Type stubs for SecurityAuditService
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.repositories.security_audit_repository import SecurityAuditRepository

class SecurityAuditService:
    """
    Service for security audit logging and analysis.
    
    Provides comprehensive audit trail management for security events,
    compliance reporting, and threat detection.
    """

    _audit_repository: SecurityAuditRepository
    _running: bool

    def __init__(
        self,
        security_audit_repository: SecurityAuditRepository,
    ) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def log_event(
        self,
        event_type: str,
        user_id: str | None = None,
        resource: str | None = None,
        action: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> str: ...

    async def log_authentication_event(
        self,
        event_type: str,
        username: str,
        ip_address: str,
        success: bool,
        details: dict[str, Any] | None = None,
    ) -> str: ...

    async def log_authorization_event(
        self,
        user_id: str,
        resource: str,
        action: str,
        allowed: bool,
        reason: str | None = None,
    ) -> str: ...

    async def log_configuration_change(
        self,
        user_id: str,
        component: str,
        old_value: Any,
        new_value: Any,
        details: dict[str, Any] | None = None,
    ) -> str: ...

    async def log_data_access(
        self,
        user_id: str,
        resource: str,
        operation: str,
        data_classification: str,
        details: dict[str, Any] | None = None,
    ) -> str: ...

    async def get_events(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_type: str | None = None,
        user_id: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    async def get_user_activity(
        self,
        user_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]: ...

    async def get_failed_login_attempts(
        self,
        username: str | None = None,
        ip_address: str | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]: ...

    async def get_security_summary(
        self,
        hours: int = 24,
    ) -> dict[str, Any]: ...

    async def generate_compliance_report(
        self,
        start_date: datetime,
        end_date: datetime,
        compliance_standard: str = "SOC2",
    ) -> dict[str, Any]: ...

    async def detect_anomalies(
        self,
        hours: int = 24,
    ) -> list[dict[str, Any]]: ...

    async def cleanup_old_events(
        self,
        days_to_keep: int = 90,
    ) -> int: ...

    async def health_check(self) -> dict[str, Any]: ...
