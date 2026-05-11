"""
Logging Middleware for Request/Response Tracking

Provides comprehensive request/response logging with:
- Automatic request ID generation/consumption
- Request/response timing
- User context tracking
- Error logging with full context
- Performance metrics
"""

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.core.structured_logging import (
    clear_request_context,
    get_logger,
    set_request_context,
)

logger = get_logger(__name__, "logging_middleware")


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for comprehensive request/response logging.

    Features:
    - Automatic request ID handling (consume from header or generate)
    - Request/response timing and performance tracking
    - User context extraction from authentication
    - Structured logging with full context
    - Error tracking and reporting
    """

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] | None = None,
        log_request_body: bool = False,
        log_response_body: bool = False,
        slow_request_threshold_ms: float = 1000,
    ):
        """
        Initialize logging middleware.

        Args:
            app: ASGI application
            exclude_paths: Paths to exclude from logging (e.g., health checks)
            log_request_body: Whether to log request bodies (careful with sensitive data)
            log_response_body: Whether to log response bodies (careful with large responses)
            slow_request_threshold_ms: Threshold for slow request warnings
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/healthz", "/api/healthz", "/metrics"]
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.slow_request_threshold_ms = slow_request_threshold_ms

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with comprehensive logging."""
        # Check if path should be excluded
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Start timing
        start_time = time.perf_counter()

        # Extract or generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Extract user context if available
        user_id = None
        session_id = None

        # Try to get user info from request state (set by auth middleware)
        if hasattr(request.state, "user"):
            user = request.state.user
            if hasattr(user, "id"):
                user_id = str(user.id)
            elif isinstance(user, dict):
                user_id = user.get("id") or user.get("user_id")

        if hasattr(request.state, "session_id"):
            session_id = request.state.session_id

        # Set logging context
        set_request_context(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            client_ip=request.client.host if request.client else None,
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params) if request.query_params else None,
        )

        # Log request
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            user_agent=request.headers.get("User-Agent"),
            content_length=request.headers.get("Content-Length"),
        )

        # Log request body if enabled and present
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Note: This consumes the request body, so we need to be careful
                # In production, consider using a custom Request class that caches the body
                content_type = request.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    logger.debug("Request body logged", body_preview="[JSON body]")
            except Exception as e:
                logger.warning(f"Failed to log request body: {e}")

        response = None
        error_occurred = False
        error_details = None

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log response
            log_level = "info"
            if response.status_code >= 500:
                log_level = "error"
                error_occurred = True
            elif response.status_code >= 400 or duration_ms > self.slow_request_threshold_ms:
                log_level = "warning"

            log_data = {
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "slow_request": duration_ms > self.slow_request_threshold_ms,
            }

            # Add response size if available
            if hasattr(response, "headers") and "Content-Length" in response.headers:
                log_data["response_size"] = response.headers["Content-Length"]

            getattr(logger, log_level)(
                f"Request completed: {request.method} {request.url.path} -> {response.status_code}",
                **log_data,
            )

            # Log performance metrics for slow requests
            if duration_ms > self.slow_request_threshold_ms:
                logger.performance(
                    f"{request.method} {request.url.path}",
                    duration_ms,
                    status_code=response.status_code,
                )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Log exception
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_occurred = True
            error_details = str(e)

            logger.exception(
                f"Request failed: {request.method} {request.url.path}",
                duration_ms=round(duration_ms, 2),
                error_type=type(e).__name__,
            )

            # Return error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred",
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )

        finally:
            # Audit log for security-sensitive endpoints
            if any(path in request.url.path for path in ["/auth", "/login", "/api/auth"]):
                logger.audit(
                    event_type="api_access",
                    message=f"{request.method} {request.url.path}",
                    success=not error_occurred,
                    status_code=response.status_code if response else 500,
                    error=error_details,
                )

            # Clear request context
            clear_request_context()


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware focused only on performance logging.

    Use this when you already have request logging but want to add
    performance tracking without duplicating logs.
    """

    def __init__(
        self,
        app: ASGIApp,
        slow_request_threshold_ms: float = 1000,
        exclude_paths: list[str] | None = None,
    ):
        """
        Initialize performance logging middleware.

        Args:
            app: ASGI application
            slow_request_threshold_ms: Threshold for slow request warnings
            exclude_paths: Paths to exclude from performance logging
        """
        super().__init__(app)
        self.slow_request_threshold_ms = slow_request_threshold_ms
        self.exclude_paths = exclude_paths or ["/healthz", "/api/healthz", "/metrics"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track request performance."""
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000

            if duration_ms > self.slow_request_threshold_ms:
                # Extract request ID if available
                request_id = request.headers.get("X-Request-ID")

                logger.performance(
                    f"{request.method} {request.url.path}",
                    duration_ms,
                    request_id=request_id,
                    slow_ratio=duration_ms / self.slow_request_threshold_ms,
                )
