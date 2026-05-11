"""
Structured Logging Module for RV-C Control System

Provides context-aware, structured logging with support for:
- Request context tracking (request_id, user_id, session_id)
- Performance metrics tracking
- Security audit logging
- Service-specific logging contexts
- Automatic log level management based on criticality
"""

import contextvars
import functools
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from backend.core.custom_exceptions import SafetyException

# Context variables for request tracking
request_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("request_context")

F = TypeVar("F", bound=Callable[..., Any])


class StructuredLogger:
    """Enhanced logger with structured logging capabilities."""

    def __init__(self, name: str, service_name: str | None = None):
        """
        Initialize structured logger.

        Args:
            name: Logger name (typically __name__)
            service_name: Optional service name for additional context
        """
        self.logger = logging.getLogger(name)
        self.service_name = service_name or name.split(".")[-1]

    def _get_context(self) -> dict[str, Any]:
        """Get current request context."""
        try:
            return request_context.get().copy()
        except LookupError:
            return {}

    def _add_common_fields(self, extra: dict[str, Any]) -> dict[str, Any]:
        """Add common fields to log data."""
        context = self._get_context()

        # Merge with provided extra data
        extra_combined = {
            "service": self.service_name,
            "timestamp": datetime.now(UTC).isoformat(),
            **context,
            **extra,
        }

        return extra_combined

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message with context."""
        extra = self._add_common_fields(kwargs)
        self.logger.debug(message, *args, extra=extra)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log info message with context."""
        extra = self._add_common_fields(kwargs)
        self.logger.info(message, *args, extra=extra)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message with context."""
        extra = self._add_common_fields(kwargs)
        self.logger.warning(message, *args, extra=extra)

    def error(
        self,
        message: str,
        *args: Any,
        exc_info: bool | None = None,
        **kwargs: Any,
    ) -> None:
        """Log error message with context."""
        extra = self._add_common_fields(kwargs)
        self.logger.error(message, *args, exc_info=exc_info, extra=extra)

    def critical(
        self,
        message: str,
        *args: Any,
        exc_info: bool | None = None,
        **kwargs: Any,
    ) -> None:
        """Log critical message with context."""
        extra = self._add_common_fields(kwargs)
        self.logger.critical(message, *args, exc_info=exc_info, extra=extra)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log exception with context and traceback."""
        extra = self._add_common_fields(kwargs)
        self.logger.exception(message, *args, extra=extra)

    def audit(self, event_type: str, message: str, success: bool = True, **kwargs: Any) -> None:
        """
        Log security audit event.

        Args:
            event_type: Type of audit event (e.g., "login", "access_denied")
            message: Audit message
            success: Whether the audited action was successful
            **kwargs: Additional audit context
        """
        extra = self._add_common_fields(
            {
                "audit_event": event_type,
                "audit_success": success,
                "audit_timestamp": datetime.now(UTC).isoformat(),
                **kwargs,
            }
        )

        level = logging.INFO if success else logging.WARNING
        self.logger.log(level, f"AUDIT [{event_type}]: {message}", extra=extra)

    def performance(self, operation: str, duration_ms: float, **kwargs: Any) -> None:
        """
        Log performance metrics.

        Args:
            operation: Name of the operation
            duration_ms: Duration in milliseconds
            **kwargs: Additional performance context
        """
        extra = self._add_common_fields(
            {
                "performance_operation": operation,
                "performance_duration_ms": duration_ms,
                "performance_slow": duration_ms > 1000,  # Flag slow operations
                **kwargs,
            }
        )

        level = logging.WARNING if duration_ms > 1000 else logging.DEBUG
        self.logger.log(level, f"PERFORMANCE [{operation}]: {duration_ms:.2f}ms", extra=extra)

    def safety(self, safety_level: str, message: str, **kwargs: Any) -> None:
        """
        Log safety-critical events.

        Args:
            safety_level: Safety level (CRITICAL, HIGH, MEDIUM, LOW)
            message: Safety message
            **kwargs: Additional safety context
        """
        extra = self._add_common_fields(
            {
                "safety_level": safety_level,
                "safety_event": True,
                **kwargs,
            }
        )

        # Map safety levels to log levels
        level_map = {
            "CRITICAL": logging.CRITICAL,
            "HIGH": logging.ERROR,
            "MEDIUM": logging.WARNING,
            "LOW": logging.INFO,
        }

        level = level_map.get(safety_level, logging.WARNING)
        self.logger.log(level, f"SAFETY [{safety_level}]: {message}", extra=extra)


def get_logger(name: str, service_name: str | None = None) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)
        service_name: Optional service name for additional context

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name, service_name)


def set_request_context(**kwargs: Any) -> None:
    """
    Set request context for structured logging.

    Common fields:
    - request_id: Unique request identifier
    - user_id: Authenticated user ID
    - session_id: Session identifier
    - client_ip: Client IP address
    - method: HTTP method
    - path: Request path
    """
    try:
        current = request_context.get()
    except LookupError:
        current = {}
    current.update(kwargs)
    request_context.set(current)


def clear_request_context() -> None:
    """Clear request context."""
    request_context.set({})


def log_execution_time(
    logger: StructuredLogger | None = None,
    operation: str | None = None,
    threshold_ms: float = 1000,
) -> Callable[[F], F]:
    """
    Decorator to log function execution time.

    Args:
        logger: Logger instance (will create one if not provided)
        operation: Operation name (defaults to function name)
        threshold_ms: Only log if execution time exceeds this threshold

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        nonlocal logger, operation

        if logger is None:
            logger = get_logger(func.__module__)

        if operation is None:
            operation = func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                if duration_ms >= threshold_ms:
                    logger.performance(operation, duration_ms)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                if duration_ms >= threshold_ms:
                    logger.performance(operation, duration_ms)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def log_safety_critical(
    logger: StructuredLogger | None = None,
    safety_level: str = "HIGH",
) -> Callable[[F], F]:
    """
    Decorator for safety-critical operations.

    Args:
        logger: Logger instance
        safety_level: Safety level for the operation

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        nonlocal logger

        if logger is None:
            logger = get_logger(func.__module__)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            operation = func.__name__
            logger.safety(safety_level, f"Starting safety-critical operation: {operation}")

            try:
                result = await func(*args, **kwargs)
                logger.safety(safety_level, f"Completed safety-critical operation: {operation}")
                return result
            except SafetyException as e:
                logger.safety(
                    e.safety_level,
                    f"Safety exception in {operation}: {e!s}",
                    error_code=e.error_code,
                    details=e.details,
                )
                raise
            except Exception as e:
                logger.safety(
                    "CRITICAL",
                    f"Unexpected exception in safety-critical operation {operation}: {e!s}",
                    exc_info=True,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            operation = func.__name__
            logger.safety(safety_level, f"Starting safety-critical operation: {operation}")

            try:
                result = func(*args, **kwargs)
                logger.safety(safety_level, f"Completed safety-critical operation: {operation}")
                return result
            except SafetyException as e:
                logger.safety(
                    e.safety_level,
                    f"Safety exception in {operation}: {e!s}",
                    error_code=e.error_code,
                    details=e.details,
                )
                raise
            except Exception as e:
                logger.safety(
                    "CRITICAL",
                    f"Unexpected exception in safety-critical operation {operation}: {e!s}",
                    exc_info=True,
                )
                raise

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


class LogContext:
    """Context manager for temporary logging context."""

    def __init__(self, **kwargs: Any):
        """Initialize with context values."""
        self.context = kwargs
        self.previous_context: dict[str, Any] = {}

    def __enter__(self) -> "LogContext":
        """Enter context and save previous values."""
        try:
            current = request_context.get()
        except LookupError:
            current = {}
        self.previous_context = current.copy()
        current.update(self.context)
        request_context.set(current)
        return self

    def __exit__(self, *args: Any) -> None:
        """Restore previous context."""
        request_context.set(self.previous_context)


# Convenience function for service-specific loggers
def get_service_logger(service_class: type) -> StructuredLogger:
    """
    Get a logger for a service class.

    Args:
        service_class: Service class

    Returns:
        StructuredLogger configured for the service
    """
    return get_logger(
        f"{service_class.__module__}.{service_class.__name__}", service_name=service_class.__name__
    )
