"""Context management for request tracing across services.

This module provides context variables for tracking requests through the system,
enabling end-to-end performance monitoring and debugging.
"""

import uuid
from contextvars import ContextVar
from typing import Optional

# ContextVar for request tracing - persists across async boundaries
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def generate_request_id() -> str:
    """Generate a unique request ID for tracing.

    Returns:
        A UUID string for request identification
    """
    return str(uuid.uuid4())


def get_request_id() -> str | None:
    """Get the current request ID from context.

    Returns:
        The current request ID or None if not in a request context
    """
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID in the current context.

    Args:
        request_id: The request ID to set
    """
    request_id_var.set(request_id)
