"""
Request Context Management

Provides context tracking for audit logging and correlation.
"""

import contextvars
from typing import Any, Optional

# Context variable for storing request-specific data
_request_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "_request_context", default=None
)


def set_request_context(context: dict[str, Any]) -> None:
    """Set the request context for the current async context."""
    _request_context.set(context)


def get_request_context() -> dict[str, Any] | None:
    """Get the current request context."""
    return _request_context.get()


def clear_request_context() -> None:
    """Clear the current request context."""
    _request_context.set(None)


class RequestContext:
    """Context manager for request context."""

    def __init__(
        self,
        correlation_id: str | None = None,
        user_id: str | None = None,
        username: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        endpoint: str | None = None,
        service_name: str | None = None,
        **kwargs,
    ):
        self.context = {
            "correlation_id": correlation_id,
            "user_id": user_id,
            "username": username,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "endpoint": endpoint,
            "service_name": service_name,
            **kwargs,
        }

    def __enter__(self):
        set_request_context(self.context)
        return self.context

    def __exit__(self, exc_type, exc_val, exc_tb):
        clear_request_context()
