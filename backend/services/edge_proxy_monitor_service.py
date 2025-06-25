"""
Edge Proxy Monitor Service

Monitors the health and status of the edge proxy (Caddy) for integration
with the ServiceRegistry health monitoring system. This service provides
a bridge between infrastructure-layer (Caddy) and application-layer
(ServiceRegistry) health monitoring.
"""

import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class EdgeProxyMonitorService:
    """
    Service to monitor edge proxy (Caddy) health and integrate with ServiceRegistry.

    This service periodically checks the Caddy Admin API to ensure the reverse proxy
    is operational and properly configured. It provides health status that can be
    consumed by other services through the ServiceRegistry dependency system.
    """

    def __init__(
        self,
        admin_api_url: str = "http://127.0.0.1:2019",
        timeout_seconds: float = 5.0,
        check_interval_seconds: int = 30,
    ):
        """
        Initialize the edge proxy monitor service.

        Args:
            admin_api_url: URL of the Caddy Admin API (default: http://127.0.0.1:2019)
            timeout_seconds: HTTP request timeout for health checks
            check_interval_seconds: Interval between health checks
        """
        self.admin_api_url = admin_api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.check_interval_seconds = check_interval_seconds

        # Health status tracking
        self._last_check_time: float | None = None
        self._last_health_status: bool = False
        self._last_error: str | None = None
        self._consecutive_failures: int = 0

        # HTTP client for admin API calls
        self._client = httpx.Client(timeout=self.timeout_seconds)

        logger.info(f"EdgeProxyMonitorService initialized with admin API: {self.admin_api_url}")

    async def health_check(self) -> dict[str, Any]:
        """
        Perform health check of the edge proxy.

        Returns:
            Health status dictionary compatible with ServiceRegistry
        """
        current_time = time.time()

        try:
            # Check if Caddy Admin API is responsive
            response = self._client.get(f"{self.admin_api_url}/config/")

            if response.status_code == 200:
                # Successful response indicates Caddy is running and configured
                self._last_health_status = True
                self._last_error = None
                self._consecutive_failures = 0

                # Try to get additional metrics if available
                config_data = response.json()
                app_count = len(config_data.get("apps", {}))

                logger.debug(f"Edge proxy health check successful, {app_count} apps configured")

                return {
                    "healthy": True,
                    "status": "operational",
                    "admin_api_responsive": True,
                    "configured_apps": app_count,
                    "last_check": current_time,
                    "consecutive_failures": 0,
                    "uptime_estimate": "available",  # Could be enhanced with more detailed metrics
                }
            # Non-200 response indicates configuration or operational issues
            error_msg = f"Admin API returned status {response.status_code}"
            return self._handle_health_failure(current_time, error_msg)

        except httpx.TimeoutException:
            error_msg = f"Admin API timeout after {self.timeout_seconds}s"
            return self._handle_health_failure(current_time, error_msg)

        except httpx.ConnectError:
            error_msg = "Cannot connect to Admin API (Caddy may not be running)"
            return self._handle_health_failure(current_time, error_msg)

        except Exception as e:
            error_msg = f"Unexpected error during health check: {e!s}"
            return self._handle_health_failure(current_time, error_msg)

        finally:
            self._last_check_time = current_time

    def _handle_health_failure(self, current_time: float, error_msg: str) -> dict[str, Any]:
        """Handle health check failure and update internal state."""
        self._last_health_status = False
        self._last_error = error_msg
        self._consecutive_failures += 1

        logger.warning(
            f"Edge proxy health check failed: {error_msg} "
            f"(consecutive failures: {self._consecutive_failures})"
        )

        return {
            "healthy": False,
            "status": "failed",
            "admin_api_responsive": False,
            "error": error_msg,
            "last_check": current_time,
            "consecutive_failures": self._consecutive_failures,
            "critical": self._consecutive_failures >= 3,  # Mark as critical after 3 failures
        }

    def get_proxy_config(self) -> dict[str, Any] | None:
        """
        Retrieve current proxy configuration from Caddy Admin API.

        Returns:
            Configuration dictionary or None if unavailable
        """
        try:
            response = self._client.get(f"{self.admin_api_url}/config/")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"Failed to retrieve proxy configuration: {e}")

        return None

    def get_rate_limit_stats(self) -> dict[str, Any] | None:
        """
        Retrieve rate limiting statistics if available.

        Note: This depends on the specific rate limiting module and may not
        be available in all Caddy configurations.

        Returns:
            Rate limit statistics or None if unavailable
        """
        try:
            # Try to get rate limiting metrics (module-specific endpoint)
            response = self._client.get(f"{self.admin_api_url}/metrics")
            if response.status_code == 200:
                metrics = response.text
                # Parse rate limiting metrics from Prometheus format
                # This is a simplified implementation - real implementation would
                # need proper Prometheus metrics parsing
                return {"raw_metrics": metrics}
        except Exception as e:
            logger.debug(f"Rate limit stats not available: {e}")

        return None

    def is_healthy(self) -> bool:
        """
        Quick health status check without performing new API call.

        Returns:
            True if last health check was successful
        """
        return self._last_health_status

    def get_last_error(self) -> str | None:
        """
        Get the last recorded error message.

        Returns:
            Last error message or None if no errors
        """
        return self._last_error

    def get_status_summary(self) -> dict[str, Any]:
        """
        Get comprehensive status summary for monitoring dashboards.

        Returns:
            Status summary dictionary
        """
        return {
            "service_name": "EdgeProxyMonitorService",
            "healthy": self._last_health_status,
            "last_check": self._last_check_time,
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
            "admin_api_url": self.admin_api_url,
            "check_interval": self.check_interval_seconds,
        }

    def close(self):
        """Clean up resources."""
        if hasattr(self, "_client"):
            self._client.close()

    def __del__(self):
        """Ensure resources are cleaned up."""
        self.close()
