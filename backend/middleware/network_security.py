"""
Network Security Middleware for RV-C Safety Operations

Provides comprehensive network-level security hardening including:
- HTTPS enforcement for safety endpoints
- Security headers (HSTS, CSP, X-Frame-Options)
- IP whitelist/blacklist filtering
- Request size limiting and DDoS protection
- Geographic blocking (optional)
- Rate limiting by network/IP

Designed for RV deployments with internet connectivity and safety-critical operations.
"""

import ipaddress
import logging
import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class NetworkSecurityConfig:
    """Network security configuration for RV deployments."""

    def __init__(
        self,
        # HTTPS Enforcement
        require_https: bool = True,
        https_redirect: bool = True,
        trusted_proxies: list[str] | None = None,
        # IP Filtering
        enable_ip_whitelist: bool = False,
        whitelist_networks: list[str] | None = None,
        blocked_networks: list[str] | None = None,
        # Geographic Filtering
        enable_geoip_blocking: bool = False,
        blocked_countries: list[str] | None = None,
        # DDoS Protection
        enable_ddos_protection: bool = True,
        max_connections_per_ip: int = 10,
        connection_window_seconds: int = 60,
        max_request_size_mb: int = 10,
        # Security Headers
        enable_security_headers: bool = True,
        enable_hsts: bool = True,
        hsts_max_age: int = 31536000,  # 1 year
        enable_csp: bool = True,
        csp_policy: str | None = None,
        # Safety-Specific Protection
        safety_endpoints: list[str] | None = None,
        safety_whitelist_only: bool = False,
        safety_require_client_cert: bool = False,
    ):
        """
        Initialize network security configuration.

        Args:
            require_https: Require HTTPS for all connections
            https_redirect: Redirect HTTP to HTTPS
            trusted_proxies: List of trusted proxy IP networks
            enable_ip_whitelist: Enable IP whitelist mode
            whitelist_networks: List of whitelisted IP networks (CIDR)
            blocked_networks: List of blocked IP networks (CIDR)
            enable_geoip_blocking: Enable geographic IP blocking
            blocked_countries: List of blocked country codes
            enable_ddos_protection: Enable DDoS protection
            max_connections_per_ip: Max concurrent connections per IP
            connection_window_seconds: Connection tracking window
            max_request_size_mb: Maximum request size in MB
            enable_security_headers: Enable security headers
            enable_hsts: Enable HTTP Strict Transport Security
            hsts_max_age: HSTS max age in seconds
            enable_csp: Enable Content Security Policy
            csp_policy: Custom CSP policy string
            safety_endpoints: List of safety-critical endpoint patterns
            safety_whitelist_only: Restrict safety endpoints to whitelist only
            safety_require_client_cert: Require client certificates for safety endpoints
        """
        self.require_https = require_https
        self.https_redirect = https_redirect
        self.trusted_proxies = self._parse_networks(trusted_proxies or [])

        self.enable_ip_whitelist = enable_ip_whitelist
        self.whitelist_networks = self._parse_networks(whitelist_networks or [])
        self.blocked_networks = self._parse_networks(blocked_networks or [])

        self.enable_geoip_blocking = enable_geoip_blocking
        self.blocked_countries = set(blocked_countries or [])

        self.enable_ddos_protection = enable_ddos_protection
        self.max_connections_per_ip = max_connections_per_ip
        self.connection_window_seconds = connection_window_seconds
        self.max_request_size_mb = max_request_size_mb

        self.enable_security_headers = enable_security_headers
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.enable_csp = enable_csp
        self.csp_policy = csp_policy or self._default_csp_policy()

        self.safety_endpoints = safety_endpoints or [
            "/api/safety/",
            "/api/pin/",
            "/api/security/",
            "/api/entities/control",
            "/api/v2/entities/control",
        ]
        self.safety_whitelist_only = safety_whitelist_only
        self.safety_require_client_cert = safety_require_client_cert

        logger.info("Network security configuration initialized for RV deployment")

    def _parse_networks(self, networks: list[str]) -> list[ipaddress.IPv4Network]:
        """Parse CIDR network strings into IPv4Network objects."""
        parsed = []
        for network_str in networks:
            try:
                network = ipaddress.IPv4Network(network_str, strict=False)
                parsed.append(network)
            except (ipaddress.AddressValueError, ValueError) as e:
                logger.warning(f"Invalid network address {network_str}: {e}")
        return parsed

    def _default_csp_policy(self) -> str:
        """Generate a secure Content Security Policy for RV applications."""
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'"
        )


class NetworkSecurityMiddleware(BaseHTTPMiddleware):
    """
    Network security middleware for RV-C safety operations.

    Provides comprehensive network-level security hardening including HTTPS enforcement,
    security headers, IP filtering, and DDoS protection.
    """

    def __init__(self, app, config: NetworkSecurityConfig | None = None):
        """
        Initialize network security middleware.

        Args:
            app: FastAPI application
            config: Network security configuration
        """
        super().__init__(app)
        self.config = config or NetworkSecurityConfig()

        # Connection tracking for DDoS protection
        self.connection_counts: dict[str, list[float]] = defaultdict(list)
        self.blocked_ips: dict[str, float] = {}  # IP -> block_until_timestamp

        logger.info("Network Security Middleware initialized for RV safety operations")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through network security checks.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response
        """
        start_time = time.time()

        try:
            # Get client IP address (handle proxy scenarios)
            client_ip = self._get_client_ip(request)

            # 1. Check if IP is temporarily blocked
            if self._is_ip_blocked(client_ip):
                logger.warning(f"Blocked IP {client_ip} attempted connection")
                return self._create_security_response(
                    "IP_BLOCKED",
                    "IP address temporarily blocked due to security policy",
                    status_code=429,
                )

            # 2. HTTPS enforcement
            if self.config.require_https and not self._is_https_request(request):
                if self.config.https_redirect:
                    return self._redirect_to_https(request)
                logger.warning(f"HTTP request rejected from {client_ip}: HTTPS required")
                return self._create_security_response(
                    "HTTPS_REQUIRED", "HTTPS is required for security", status_code=426
                )

            # 3. IP filtering
            if not self._is_ip_allowed(client_ip, request):
                logger.warning(f"IP {client_ip} blocked by filtering policy")
                return self._create_security_response(
                    "IP_FILTERED", "IP address not allowed by security policy", status_code=403
                )

            # 4. Request size limiting
            if not self._check_request_size(request):
                logger.warning(f"Request from {client_ip} exceeds size limit")
                return self._create_security_response(
                    "REQUEST_TOO_LARGE", "Request size exceeds security limits", status_code=413
                )

            # 5. DDoS protection
            if self.config.enable_ddos_protection:
                if not self._check_ddos_protection(client_ip):
                    logger.warning(f"DDoS protection triggered for {client_ip}")
                    return self._create_security_response(
                        "RATE_LIMITED", "Too many connections from your IP address", status_code=429
                    )

            # 6. Safety endpoint additional protection
            if self._is_safety_endpoint(request):
                safety_check = self._check_safety_endpoint_access(client_ip, request)
                if safety_check is not None:
                    return safety_check

            # Process the request
            response = await call_next(request)

            # Add security headers to response
            if self.config.enable_security_headers:
                self._add_security_headers(response, request)

            # Log successful request processing
            processing_time = time.time() - start_time
            logger.debug(
                f"Network security processed request from {client_ip} in {processing_time:.3f}s"
            )

            return response

        except Exception as e:
            logger.error(f"Network security middleware error: {e}", exc_info=True)
            return self._create_security_response(
                "SECURITY_ERROR", "Network security check failed", status_code=500
            )

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address handling proxies and load balancers.

        Args:
            request: HTTP request

        Returns:
            Client IP address string
        """
        # Check for forwarded headers (common in RV gateway setups)
        headers = getattr(request, "headers", {})
        forwarded_for = headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            # Check other common proxy headers
            client_ip = headers.get("X-Real-IP") or headers.get("CF-Connecting-IP")  # Cloudflare

            # Fall back to request.client if no proxy headers
            if not client_ip:
                # Access client address information
                # Using getattr to avoid type checking issues with Starlette's Request.client
                client = getattr(request, "client", None)
                if client is not None:
                    # client is a tuple of (host, port) or an Address object
                    if hasattr(client, "host"):
                        client_ip = getattr(client, "host", "unknown")
                    elif isinstance(client, tuple) and len(client) >= 1:
                        client_ip = client[0]
                    else:
                        client_ip = "unknown"
                else:
                    client_ip = "unknown"

        return client_ip

    def _is_https_request(self, request: Request) -> bool:
        """
        Check if request is using HTTPS.

        Args:
            request: HTTP request

        Returns:
            True if HTTPS, False otherwise
        """
        # Direct HTTPS check
        if str(request.url).startswith("https://"):
            return True

        # Check proxy headers (common in RV setups with reverse proxies)
        headers = getattr(request, "headers", {})
        forwarded_proto = headers.get("X-Forwarded-Proto", "").lower()
        return forwarded_proto == "https"

    def _redirect_to_https(self, request: Request) -> Response:
        """
        Redirect HTTP request to HTTPS.

        Args:
            request: HTTP request

        Returns:
            Redirect response
        """
        https_url = str(request.url).replace("http://", "https://")
        return Response(
            status_code=301,
            content=f'{{"message": "Redirecting to HTTPS", "location": "{https_url}"}}',
            media_type="application/json",
            headers={"Location": https_url},
        )

    def _is_ip_allowed(self, client_ip: str, request: Request) -> bool:
        """
        Check if IP address is allowed by filtering policies.

        Args:
            client_ip: Client IP address
            request: HTTP request

        Returns:
            True if IP is allowed, False otherwise
        """
        try:
            ip_addr = ipaddress.IPv4Address(client_ip)
        except ipaddress.AddressValueError:
            logger.warning(f"Invalid IP address: {client_ip}")
            return False

        # Check blocked networks first
        for blocked_network in self.config.blocked_networks:
            if ip_addr in blocked_network:
                return False

        # If whitelist is enabled, check whitelist
        if self.config.enable_ip_whitelist:
            for allowed_network in self.config.whitelist_networks:
                if ip_addr in allowed_network:
                    return True
            return False  # Not in whitelist

        # Safety endpoints may have stricter requirements
        if self._is_safety_endpoint(request) and self.config.safety_whitelist_only:
            for allowed_network in self.config.whitelist_networks:
                if ip_addr in allowed_network:
                    return True
            return False  # Safety endpoint requires whitelist

        return True  # Default allow

    def _check_request_size(self, request: Request) -> bool:
        """
        Check if request size is within limits.

        Args:
            request: HTTP request

        Returns:
            True if size is acceptable, False otherwise
        """
        headers = getattr(request, "headers", {})
        content_length = headers.get("content-length")
        if content_length:
            try:
                size_bytes = int(content_length)
                max_size_bytes = self.config.max_request_size_mb * 1024 * 1024
                return size_bytes <= max_size_bytes
            except ValueError:
                logger.warning(f"Invalid Content-Length header: {content_length}")
                return False

        return True  # No content-length header, assume OK

    def _check_ddos_protection(self, client_ip: str) -> bool:
        """
        Check DDoS protection limits for client IP.

        Args:
            client_ip: Client IP address

        Returns:
            True if connection is allowed, False if rate limited
        """
        now = time.time()
        window_start = now - self.config.connection_window_seconds

        # Clean old connections
        self.connection_counts[client_ip] = [
            conn_time for conn_time in self.connection_counts[client_ip] if conn_time > window_start
        ]

        # Check current connection count
        current_connections = len(self.connection_counts[client_ip])
        if current_connections >= self.config.max_connections_per_ip:
            # Block IP temporarily
            self.blocked_ips[client_ip] = now + 300  # 5 minute block
            return False

        # Record this connection
        self.connection_counts[client_ip].append(now)
        return True

    def _is_ip_blocked(self, client_ip: str) -> bool:
        """
        Check if IP is currently blocked.

        Args:
            client_ip: Client IP address

        Returns:
            True if IP is blocked, False otherwise
        """
        now = time.time()
        if client_ip in self.blocked_ips:
            if self.blocked_ips[client_ip] > now:
                return True
            # Block expired, remove it
            del self.blocked_ips[client_ip]
        return False

    def _is_safety_endpoint(self, request: Request) -> bool:
        """
        Check if request is for a safety-critical endpoint.

        Args:
            request: HTTP request

        Returns:
            True if safety endpoint, False otherwise
        """
        path = str(request.url.path)
        return any(safety_pattern in path for safety_pattern in self.config.safety_endpoints)

    def _check_safety_endpoint_access(self, client_ip: str, request: Request) -> Response | None:
        """
        Perform additional security checks for safety endpoints.

        Args:
            client_ip: Client IP address
            request: HTTP request

        Returns:
            Security response if access denied, None if allowed
        """
        # Additional safety endpoint restrictions
        if self.config.safety_require_client_cert:
            # Check for client certificate (in RV deployments with PKI)
            client_cert = getattr(request, "headers", {}).get("X-Client-Cert-Subject")
            if not client_cert:
                logger.warning(f"Safety endpoint access without client cert from {client_ip}")
                return self._create_security_response(
                    "CLIENT_CERT_REQUIRED",
                    "Client certificate required for safety operations",
                    status_code=403,
                )

        return None  # Access allowed

    def _add_security_headers(self, response: Response, request: Request) -> None:
        """
        Add security headers to response.

        Args:
            response: HTTP response
            request: HTTP request
        """
        # Get response headers or create if not exists
        if not hasattr(response, "headers"):
            return

        headers = getattr(response, "headers", {})

        # HSTS (HTTP Strict Transport Security)
        if self.config.enable_hsts and self._is_https_request(request):
            headers["Strict-Transport-Security"] = (
                f"max-age={self.config.hsts_max_age}; includeSubDomains; preload"
            )

        # Content Security Policy
        if self.config.enable_csp:
            headers["Content-Security-Policy"] = self.config.csp_policy

        # Additional security headers
        headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Permissions-Policy": (
                    "geolocation=(), microphone=(), camera=(), "
                    "payment=(), usb=(), serial=(), bluetooth=()"
                ),
            }
        )

        # RV-specific security headers
        if self._is_safety_endpoint(request):
            headers.update(
                {
                    "X-Safety-Critical": "true",
                    "X-RVC-Security": "enhanced",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                }
            )

    def _create_security_response(
        self, error_code: str, message: str, status_code: int = 403
    ) -> Response:
        """
        Create a standardized security error response.

        Args:
            error_code: Security error code
            message: Human-readable error message
            status_code: HTTP status code

        Returns:
            JSON error response
        """
        import json

        content = {
            "error": "network_security_violation",
            "code": error_code,
            "message": message,
            "timestamp": time.time(),
            "security_policy": "rv_deployment",
        }

        return Response(
            status_code=status_code,
            content=json.dumps(content),
            media_type="application/json",
            headers={
                "X-Security-Violation": error_code,
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    def get_security_stats(self) -> dict:
        """
        Get network security statistics for monitoring.

        Returns:
            Dictionary with security statistics
        """
        now = time.time()
        active_connections = 0
        for connections in self.connection_counts.values():
            # Count connections in last 60 seconds
            recent_connections = [conn for conn in connections if conn > now - 60]
            active_connections += len(recent_connections)

        blocked_ips_count = len(
            [ip for ip, block_until in self.blocked_ips.items() if block_until > now]
        )

        return {
            "active_connections": active_connections,
            "blocked_ips": blocked_ips_count,
            "connection_tracking_entries": len(self.connection_counts),
            "config": {
                "https_required": self.config.require_https,
                "ip_whitelist_enabled": self.config.enable_ip_whitelist,
                "ddos_protection_enabled": self.config.enable_ddos_protection,
                "safety_whitelist_only": self.config.safety_whitelist_only,
            },
        }
