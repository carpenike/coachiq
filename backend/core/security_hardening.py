"""
Security Hardening Configuration

Implements security hardening recommendations based on OWASP guidelines.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Based on OWASP security header recommendations.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # Add HSTS header for HTTPS connections
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Add CSP header
        # Note: 'unsafe-inline' is required for:
        # - Theme management script in index.html
        # - Dynamic inline styles in React components
        # 'unsafe-eval' has been removed as it's not needed
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  # Removed 'unsafe-eval'
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' wss: https:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "  # Added for additional security
            "form-action 'self'; "  # Added to restrict form submissions
            "object-src 'none'; "  # Added to block plugins
            "upgrade-insecure-requests;"  # Added to upgrade HTTP to HTTPS
        )

        return response


class SessionSecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enhances session security.

    Implements session binding to network/device fingerprints.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract session information
        session_id = getattr(request.state, "session_id", None)

        if session_id:
            # Verify session fingerprint
            stored_fingerprint = await self._get_session_fingerprint(session_id)
            current_fingerprint = self._calculate_fingerprint(request)

            if stored_fingerprint and stored_fingerprint != current_fingerprint:
                # Session hijacking detected
                logger.warning(
                    f"Session fingerprint mismatch for session {session_id}: "
                    f"stored={stored_fingerprint}, current={current_fingerprint}"
                )

                # Invalidate the session
                await self._invalidate_session(session_id)

                # Return unauthorized response
                return Response(
                    content="Session security violation",
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )

        response = await call_next(request)

        # Update session activity timestamp
        if session_id:
            await self._update_session_activity(session_id)

        return response

    def _calculate_fingerprint(self, request: Request) -> str:
        """Calculate a fingerprint based on request characteristics."""
        import hashlib

        # Include User-Agent and IP subnet in fingerprint
        user_agent = request.headers.get("User-Agent", "")
        client_ip = request.client.host if request.client else ""

        # Use IP subnet (first 3 octets) to allow for minor IP changes
        ip_parts = client_ip.split(".")
        ip_subnet = ".".join(ip_parts[:3]) if len(ip_parts) >= 3 else client_ip

        fingerprint_data = f"{user_agent}|{ip_subnet}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

    async def _get_session_fingerprint(self, session_id: str) -> str | None:
        """Get stored fingerprint for a session."""
        try:
            from backend.core.dependencies import get_service

            # Get session service to retrieve session data
            session_service = get_service("session_service")
            if not session_service:
                logger.warning("Session service not available for fingerprint validation")
                return None

            # For JWT-based sessions, we need to extract session data differently
            # Since we use stateless JWTs, we'll need to check against stored session data
            # This assumes the session_id is actually a refresh token or session identifier

            # Get the session repository directly for now
            session_repository = get_service("session_repository")
            if not session_repository:
                return None

            # Retrieve session data
            session_data = await session_repository.get_user_session(session_id)
            if session_data and isinstance(session_data, dict):
                # Extract fingerprint from device_info
                device_info = session_data.get("device_info", {})
                return device_info.get("fingerprint")

            return None

        except Exception as e:
            logger.error(f"Failed to retrieve session fingerprint for {session_id}: {e}")
            return None

    async def _invalidate_session(self, session_id: str) -> None:
        """Invalidate a compromised session."""
        try:
            from backend.core.dependencies import get_service

            # Get session repository to revoke the session
            session_repository = get_service("session_repository")
            if session_repository:
                await session_repository.revoke_user_session(session_id)
                logger.warning(f"Session {session_id} invalidated due to fingerprint mismatch")
            else:
                logger.error("Session repository not available to invalidate session")

        except Exception as e:
            logger.error(f"Failed to invalidate session {session_id}: {e}")

    async def _update_session_activity(self, session_id: str) -> None:
        """Update last activity timestamp for session."""
        # This would update the session's last activity time


def configure_security_hardening(app: FastAPI, settings: Any) -> None:
    """
    Configure security hardening for the application.

    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    # Add trusted host middleware
    if hasattr(settings, "allowed_hosts") and settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts,
        )
        logger.info(f"Configured trusted hosts: {settings.allowed_hosts}")

    # Add security headers middleware
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware configured")

    # Add session security middleware
    app.add_middleware(SessionSecurityMiddleware)
    logger.info("Session security middleware configured")


# Note: Rate limiting configuration has been moved to SecurityConfigService
# for centralized management. Use get_rate_limit_for_endpoint() from
# SecurityConfigService instead of local configuration.
