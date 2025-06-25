"""
Contains custom FastAPI middleware for the CoachIQ application.

Middleware functions in this module are used to intercept HTTP requests
for purposes such as logging, metrics collection, or request modification.
"""

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

# CORS handling moved to Caddy edge layer - see config/Caddyfile.example
from backend.core.metrics import get_http_latency, get_http_requests


async def prometheus_http_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """
    FastAPI middleware to record Prometheus metrics for HTTP requests.
    It measures the latency of each request and increments a counter for
    requests, labeled by method, endpoint, and status code.
    Args:
        request: The incoming FastAPI Request object.
        call_next: A function to call to process the request and get the response.
    Returns:
        The response object from the next handler in the chain.
    """
    start = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start
    path = request.url.path
    method = request.method
    status = response.status_code

    # Get metrics and record values
    http_requests = get_http_requests()
    http_latency = get_http_latency()

    http_requests.labels(method=method, endpoint=path, status_code=status).inc()
    http_latency.labels(method=method, endpoint=path).observe(latency)

    return response


# CORS configuration removed - now handled by Caddy edge layer
# See config/Caddyfile.example for CORS configuration
#
# IMPORTANT: For production deployments:
# 1. Configure CORS in Caddyfile to match your frontend origin requirements
# 2. This provides better performance than application-layer CORS handling
# 3. For development without Caddy, CORS is handled by development servers
