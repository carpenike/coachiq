"""
Audit Decorators for Automatic Security Logging

Provides decorators that automatically log security-critical operations
following OWASP ASVS V7 guidelines.
"""

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any, Optional

from backend.core.dependencies import get_security_audit_service
from backend.core.request_context import get_request_context
from backend.core.sensitive_data_filter import SensitiveDataFilter
from backend.models.audit_events import (
    AuditAction,
    AuditActor,
    AuditEventType,
    AuditOutcome,
    AuditSeverity,
    AuditTarget,
    StructuredAuditEvent,
)

logger = logging.getLogger(__name__)

# Initialize sensitive data filter
_sensitive_filter = SensitiveDataFilter()


def audit_event(
    event_type: AuditEventType,
    severity: AuditSeverity = AuditSeverity.INFO,
    target_type: str | None = None,
    target_arg: str | None = None,
    extract_actor: bool = True,
    compliance_required: bool = False,
    safety_critical: bool = False,
):
    """
    Decorator for automatic audit logging of security-critical operations.

    Args:
        event_type: Type of audit event
        severity: Default severity level
        target_type: Type of target resource
        target_arg: Function argument name containing target ID
        extract_actor: Whether to extract actor from request context
        compliance_required: Whether this requires compliance review
        safety_critical: Whether this is a safety-critical operation

    Example:
        @audit_event(
            event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
            severity=AuditSeverity.INFO,
            target_type="user_account",
            target_arg="username"
        )
        async def login(username: str, password: str):
            # ... login logic ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            outcome = AuditOutcome.SUCCESS
            reason = None
            result = None
            error = None

            # Extract context and actor information
            context = get_request_context()
            actor = _extract_actor(context, extract_actor)
            correlation_id = context.get("correlation_id") if context else None

            # Extract target information
            target = _extract_target(func, args, kwargs, target_type, target_arg)

            try:
                # Execute the wrapped function
                result = await func(*args, **kwargs)

                # Check if result indicates failure
                if isinstance(result, dict) and not result.get("success", True):
                    outcome = AuditOutcome.FAILURE
                    reason = result.get("error", "Operation failed")

                return result

            except TimeoutError:
                outcome = AuditOutcome.TIMEOUT
                reason = "Operation timed out"
                error = "TimeoutError"
                raise

            except PermissionError as e:
                outcome = AuditOutcome.BLOCKED
                reason = str(e)
                error = "PermissionError"
                raise

            except Exception as e:
                outcome = AuditOutcome.ERROR
                reason = str(e)
                error = type(e).__name__
                raise

            finally:
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Determine final severity
                final_severity = severity
                if outcome in [AuditOutcome.BLOCKED, AuditOutcome.ERROR]:
                    final_severity = AuditSeverity.WARNING
                if safety_critical and outcome != AuditOutcome.SUCCESS:
                    final_severity = AuditSeverity.HIGH

                # Create audit event
                audit_svc = await get_security_audit_service()
                if audit_svc:
                    await _log_audit_event(
                        audit_svc,
                        event_type=event_type,
                        severity=final_severity,
                        actor=actor,
                        action=AuditAction(
                            method=func.__name__,
                            service=func.__module__.split(".")[-1],
                            endpoint=context.get("endpoint") if context else None,
                            outcome=outcome,
                            reason=reason,
                            duration_ms=duration_ms,
                        ),
                        target=target,
                        correlation_id=correlation_id,
                        details={
                            "function": f"{func.__module__}.{func.__name__}",
                            "error": error,
                            # Filter sensitive data from kwargs before logging
                            **(
                                _sensitive_filter.filter_dict(kwargs)
                                if kwargs and len(str(kwargs)) < 1000
                                else {}
                            ),
                        },
                        compliance_required=compliance_required,
                        safety_critical=safety_critical,
                    )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous functions, we need to run in event loop
            return asyncio.run(async_wrapper(*args, **kwargs))

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def audit_access_control(
    resource_type: str,
    permission: str,
    resource_arg: str = "resource_id",
):
    """
    Specialized decorator for access control decisions.

    Args:
        resource_type: Type of resource being accessed
        permission: Required permission
        resource_arg: Function argument containing resource ID
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # This will be called for both granted and denied access
            event_type = AuditEventType.AUTHZ_ACCESS_GRANTED
            severity = AuditSeverity.INFO

            try:
                result = await func(*args, **kwargs)
                return result
            except PermissionError:
                event_type = AuditEventType.AUTHZ_ACCESS_DENIED
                severity = AuditSeverity.WARNING
                raise

        # Apply the audit_event decorator with appropriate parameters
        return audit_event(
            event_type=event_type,
            severity=severity,
            target_type=resource_type,
            target_arg=resource_arg,
        )(wrapper)

    return decorator


def audit_safety_operation(
    operation_name: str,
    emergency: bool = False,
):
    """
    Specialized decorator for safety-critical operations.

    Args:
        operation_name: Name of the safety operation
        emergency: Whether this is an emergency operation
    """

    def decorator(func: Callable) -> Callable:
        event_type = (
            AuditEventType.SAFETY_EMERGENCY_STOP
            if emergency
            else AuditEventType.SAFETY_CRITICAL_OPERATION
        )

        return audit_event(
            event_type=event_type,
            severity=AuditSeverity.HIGH if emergency else AuditSeverity.WARNING,
            target_type="safety_system",
            compliance_required=True,
            safety_critical=True,
        )(func)

    return decorator


# Helper functions


def _extract_actor(
    context: dict[str, Any] | None,
    extract_actor: bool,
) -> AuditActor:
    """Extract actor information from request context."""
    if not extract_actor or not context:
        return AuditActor(service="system")

    # Extract IP address and optionally mask for privacy
    ip_address = context.get("client_ip")
    if ip_address and ip_address.startswith(("192.168.", "10.", "172.")):
        # Keep private IPs as-is for internal tracking
        pass
    elif ip_address:
        # Mask last octet of public IPs for privacy
        parts = ip_address.split(".")
        if len(parts) == 4:
            ip_address = f"{'.'.join(parts[:3])}.***"

    return AuditActor(
        id=context.get("user_id"),
        username=context.get("username"),
        ip_address=ip_address,
        user_agent=context.get("user_agent"),
        service=context.get("service_name"),
    )


def _extract_target(
    func: Callable,
    args: tuple,
    kwargs: dict,
    target_type: str | None,
    target_arg: str | None,
) -> AuditTarget | None:
    """Extract target information from function arguments."""
    if not target_type:
        return None

    target_id = None
    target_name = None

    if target_arg:
        # Try to get from kwargs first
        if target_arg in kwargs:
            target_value = kwargs[target_arg]
            # Don't expose sensitive target IDs
            if _sensitive_filter.is_sensitive_key(target_arg):
                target_id = _sensitive_filter.mask_value(target_value)
            else:
                target_id = str(target_value)
        else:
            # Try to get from positional args
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if target_arg in params:
                idx = params.index(target_arg)
                if idx < len(args):
                    target_value = args[idx]
                    if _sensitive_filter.is_sensitive_key(target_arg):
                        target_id = _sensitive_filter.mask_value(target_value)
                    else:
                        target_id = str(target_value)

    return AuditTarget(
        type=target_type,
        id=target_id,
        name=target_name,
    )


async def _log_audit_event(
    audit_service: Any,
    event_type: AuditEventType,
    severity: AuditSeverity,
    actor: AuditActor,
    action: AuditAction,
    target: AuditTarget | None,
    correlation_id: str | None,
    details: dict[str, Any],
    compliance_required: bool,
    safety_critical: bool,
) -> None:
    """Log the audit event through the audit service."""
    try:
        event = StructuredAuditEvent(
            correlation_id=correlation_id,
            event_type=event_type,
            severity=severity,
            actor=actor,
            action=action,
            target=target,
            details=details,
            compliance_required=compliance_required,
            safety_impact="critical" if safety_critical else None,
            tags=_generate_tags(event_type, actor, target),
        )

        # Log through enhanced audit service
        await audit_service.log_structured_event(event)

    except Exception as e:
        # Audit logging should never break the application
        logger.error(f"Failed to log audit event: {e}")


def _generate_tags(
    event_type: AuditEventType,
    actor: AuditActor,
    target: AuditTarget | None,
) -> list[str]:
    """Generate searchable tags for the audit event."""
    tags = []

    # Add event category tags
    if event_type.startswith("auth."):
        tags.append("authentication")
    elif event_type.startswith("authz."):
        tags.append("authorization")
    elif event_type.startswith("safety."):
        tags.append("safety")
    elif event_type.startswith("config."):
        tags.append("configuration")

    # Add outcome tags
    if "failure" in event_type or "denied" in event_type:
        tags.append("security_failure")

    # Add target tags
    if target:
        tags.append(f"target:{target.type}")

    return tags
