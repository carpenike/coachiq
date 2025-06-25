"""ASGI middleware for performance monitoring with request tracing.

This middleware tracks request performance and sets up request context
for distributed tracing across services.
"""

import time
from typing import Optional

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.core.context import generate_request_id, request_id_var
from backend.core.performance import PerformanceMonitor


class PerformanceMiddleware:
    """ASGI middleware for performance monitoring with request tracing."""

    def __init__(self, app: ASGIApp, performance_monitor: PerformanceMonitor | None = None):
        self.app = app
        self._monitor = performance_monitor

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip health checks to avoid noise in metrics
        path = scope.get("path", "")
        if path in ["/api/health", "/api/health/ready", "/api/health/startup"]:
            await self.app(scope, receive, send)
            return

        # Extract request ID from Caddy or generate fallback for development
        # Production: Caddy generates X-Request-ID using {http.request.uuid}
        # Development: Generate locally if header not present
        headers = Headers(scope=scope)
        request_id = headers.get("X-Request-ID") or generate_request_id()

        # Set request ID in context for downstream services
        token = request_id_var.set(request_id)

        start_time = time.perf_counter()

        # Capture response status
        status_code = None

        async def send_wrapper(message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                # Add request ID to response headers
                headers = dict(message.get("headers", []))
                headers[b"x-request-id"] = request_id.encode()
                headers[b"x-response-time-ms"] = str(
                    int((time.perf_counter() - start_time) * 1000)
                ).encode()

                # Convert headers back to list of tuples
                message["headers"] = [(k, v) for k, v in headers.items()]

            await send(message)

        try:
            # Process request
            await self.app(scope, receive, send_wrapper)

            # Record metrics if monitor is available
            if self._monitor:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                self._monitor.record_api_latency(
                    method=scope.get("method", "UNKNOWN"),
                    path=path,
                    latency_ms=elapsed_ms,
                    request_id=request_id,
                    status_code=status_code,
                )

        finally:
            # Reset context
            request_id_var.reset(token)
