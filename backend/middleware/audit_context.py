"""
Audit Context Middleware

Provides request context tracking for correlation IDs and audit logging.
"""

import logging
import time
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.request_context import clear_request_context, set_request_context

logger = logging.getLogger(__name__)


class AuditContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that sets up request context for audit logging.

    Extracts and tracks:
    - Correlation ID (from header or generates new one)
    - User information from JWT
    - Client IP address
    - User agent
    - Request endpoint
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract correlation ID
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or f"req_{uuid4().hex[:12]}"
        )

        # Extract user info from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        username = getattr(request.state, "username", None)

        # Extract client information
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

        # Build request context
        context = {
            "correlation_id": correlation_id,
            "user_id": user_id,
            "username": username,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "endpoint": f"{request.method} {request.url.path}",
            "request_time": time.time(),
        }

        # Set context for the request
        set_request_context(context)

        try:
            # Add correlation ID to response headers
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response

        finally:
            # Clean up context
            clear_request_context()


def configure_audit_context_middleware(app) -> None:
    """Configure audit context middleware for the application."""
    app.add_middleware(AuditContextMiddleware)
    logger.info("Audit context middleware configured")
