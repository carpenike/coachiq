"""
Performance-optimized notification services with connection pooling and caching.

This module provides enhanced notification delivery with:
- Connection pooling for SMTP, webhook, and other channels
- Circuit breaker pattern for failing channels
- Efficient batch processing
- Performance monitoring and metrics
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import aiohttp
import aiosmtplib
import redis.asyncio as redis
from apprise import Apprise, NotifyFormat, NotifyType
from circuitbreaker import circuit

from backend.core.config import NotificationSettings
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationStatus,
)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ConnectionPool:
    """Base class for connection pooling."""

    def __init__(self, name: str, max_connections: int = 10):
        self.name = name
        self.max_connections = max_connections
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self._pool: list[Any] = []
        self._in_use: set[Any] = set()
        self._lock = asyncio.Lock()
        self._created_count = 0

    async def acquire(self) -> Any:
        """Acquire a connection from the pool."""
        async with self._lock:
            # Try to get an available connection
            while self._pool:
                conn = self._pool.pop()
                if await self._is_healthy(conn):
                    self._in_use.add(conn)
                    return conn
                await self._close_connection(conn)

            # Create new connection if under limit
            if self._created_count < self.max_connections:
                conn = await self._create_connection()
                self._created_count += 1
                self._in_use.add(conn)
                return conn

            # Wait for a connection to be released
            while not self._pool:
                await asyncio.sleep(0.1)
                async with self._lock:
                    if self._pool:
                        break

        return await self.acquire()

    async def release(self, conn: Any) -> None:
        """Release a connection back to the pool."""
        async with self._lock:
            if conn in self._in_use:
                self._in_use.remove(conn)
                if await self._is_healthy(conn):
                    self._pool.append(conn)
                else:
                    await self._close_connection(conn)
                    self._created_count -= 1

    async def close_all(self) -> None:
        """Close all connections in the pool."""
        async with self._lock:
            # Close pooled connections
            for conn in self._pool:
                await self._close_connection(conn)
            self._pool.clear()

            # Close in-use connections
            for conn in list(self._in_use):
                await self._close_connection(conn)
            self._in_use.clear()

            self._created_count = 0

    async def _create_connection(self) -> Any:
        """Create a new connection (must be implemented by subclasses)."""
        raise NotImplementedError

    async def _is_healthy(self, conn: Any) -> bool:
        """Check if connection is healthy (must be implemented by subclasses)."""
        raise NotImplementedError

    async def _close_connection(self, conn: Any) -> None:
        """Close a connection (must be implemented by subclasses)."""
        raise NotImplementedError


class SMTPConnectionPool(ConnectionPool):
    """Connection pool for SMTP connections."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        max_connections: int = 5,
    ):
        super().__init__("SMTPPool", max_connections)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    async def _create_connection(self) -> aiosmtplib.SMTP:
        """Create a new SMTP connection."""
        smtp = aiosmtplib.SMTP(
            hostname=self.host,
            port=self.port,
            use_tls=self.use_tls,
            timeout=30,
        )

        await smtp.connect()

        if self.username and self.password:
            await smtp.login(self.username, self.password)

        self.logger.debug(f"Created new SMTP connection to {self.host}:{self.port}")
        return smtp

    async def _is_healthy(self, conn: aiosmtplib.SMTP) -> bool:
        """Check if SMTP connection is healthy."""
        try:
            # Send NOOP command to check connection
            response = await conn.noop()
            return response[0] == 250
        except Exception:
            return False

    async def _close_connection(self, conn: aiosmtplib.SMTP) -> None:
        """Close SMTP connection."""
        try:
            await conn.quit()
        except Exception:
            pass


class HTTPConnectionPool(ConnectionPool):
    """Connection pool for HTTP connections (webhooks)."""

    def __init__(self, max_connections: int = 20, connector_limit: int = 100):
        super().__init__("HTTPPool", max_connections)
        self.connector_limit = connector_limit

    async def _create_connection(self) -> aiohttp.ClientSession:
        """Create a new HTTP client session."""
        connector = aiohttp.TCPConnector(
            limit=self.connector_limit,
            limit_per_host=30,
            ttl_dns_cache=300,
        )

        session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "CoachIQ-Notifications/1.0"},
        )

        self.logger.debug("Created new HTTP client session")
        return session

    async def _is_healthy(self, conn: aiohttp.ClientSession) -> bool:
        """Check if HTTP session is healthy."""
        return not conn.closed

    async def _close_connection(self, conn: aiohttp.ClientSession) -> None:
        """Close HTTP session."""
        await conn.close()


class CircuitBreakerManager:
    """Manages circuit breakers for notification channels."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.circuits: dict[str, Any] = {}
        self.logger = logging.getLogger(f"{__name__}.CircuitBreaker")

        # Circuit state tracking
        self.state_history: dict[str, list[tuple[CircuitState, datetime]]] = defaultdict(list)
        self.failure_counts: dict[str, int] = defaultdict(int)
        self.last_failure_time: dict[str, datetime] = {}

    def get_circuit(self, channel: str) -> Any:
        """Get or create circuit breaker for channel."""
        if channel not in self.circuits:
            self.circuits[channel] = circuit(
                failure_threshold=self.failure_threshold,
                recovery_timeout=self.recovery_timeout,
                expected_exception=self.expected_exception,
                name=f"notification_{channel}",
            )
        return self.circuits[channel]

    def is_open(self, channel: str) -> bool:
        """Check if circuit is open (failing)."""
        cb = self.get_circuit(channel)
        return cb.current_state == "open"

    def record_success(self, channel: str) -> None:
        """Record successful delivery."""
        self.failure_counts[channel] = 0
        if channel in self.last_failure_time:
            del self.last_failure_time[channel]

    def record_failure(self, channel: str) -> None:
        """Record delivery failure."""
        self.failure_counts[channel] += 1
        self.last_failure_time[channel] = datetime.utcnow()

        # Record state change
        cb = self.get_circuit(channel)
        state = CircuitState(cb.current_state)
        self.state_history[channel].append((state, datetime.utcnow()))

        # Keep only last 100 state changes
        if len(self.state_history[channel]) > 100:
            self.state_history[channel] = self.state_history[channel][-100:]

    def get_channel_health(self, channel: str) -> dict[str, Any]:
        """Get health status for a channel."""
        cb = self.get_circuit(channel)

        return {
            "channel": channel,
            "state": cb.current_state,
            "failure_count": self.failure_counts[channel],
            "last_failure": self.last_failure_time.get(channel),
            "healthy": cb.current_state != "open",
            "recovery_timeout": self.recovery_timeout,
            "failure_threshold": self.failure_threshold,
        }

    def get_all_health(self) -> dict[str, Any]:
        """Get health status for all channels."""
        return {channel: self.get_channel_health(channel) for channel in self.circuits}


class PerformanceMetrics:
    """Tracks performance metrics for notification delivery."""

    def __init__(self):
        self.metrics: dict[str, Any] = defaultdict(
            lambda: {
                "total_sent": 0,
                "total_failed": 0,
                "total_time_ms": 0.0,
                "min_time_ms": float("inf"),
                "max_time_ms": 0.0,
                "last_success": None,
                "last_failure": None,
            }
        )
        self.batch_metrics = {
            "total_batches": 0,
            "total_notifications": 0,
            "avg_batch_size": 0.0,
            "total_batch_time_ms": 0.0,
        }

    def record_delivery(self, channel: str, success: bool, duration_ms: float) -> None:
        """Record a delivery attempt."""
        metric = self.metrics[channel]

        if success:
            metric["total_sent"] += 1
            metric["last_success"] = datetime.utcnow()
        else:
            metric["total_failed"] += 1
            metric["last_failure"] = datetime.utcnow()

        metric["total_time_ms"] += duration_ms
        metric["min_time_ms"] = min(metric["min_time_ms"], duration_ms)
        metric["max_time_ms"] = max(metric["max_time_ms"], duration_ms)

    def record_batch(self, batch_size: int, duration_ms: float) -> None:
        """Record batch processing metrics."""
        self.batch_metrics["total_batches"] += 1
        self.batch_metrics["total_notifications"] += batch_size
        self.batch_metrics["total_batch_time_ms"] += duration_ms

        # Update average batch size
        self.batch_metrics["avg_batch_size"] = (
            self.batch_metrics["total_notifications"] / self.batch_metrics["total_batches"]
        )

    def get_channel_metrics(self, channel: str) -> dict[str, Any]:
        """Get metrics for a specific channel."""
        metric = self.metrics[channel]
        total_attempts = metric["total_sent"] + metric["total_failed"]

        return {
            "channel": channel,
            "total_sent": metric["total_sent"],
            "total_failed": metric["total_failed"],
            "success_rate": metric["total_sent"] / total_attempts if total_attempts > 0 else 0.0,
            "avg_time_ms": metric["total_time_ms"] / total_attempts if total_attempts > 0 else 0.0,
            "min_time_ms": metric["min_time_ms"] if metric["min_time_ms"] != float("inf") else None,
            "max_time_ms": metric["max_time_ms"] if metric["max_time_ms"] > 0 else None,
            "last_success": metric["last_success"],
            "last_failure": metric["last_failure"],
        }

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all performance metrics."""
        return {
            "channels": {channel: self.get_channel_metrics(channel) for channel in self.metrics},
            "batch_processing": self.batch_metrics,
            "summary": self._get_summary_metrics(),
        }

    def _get_summary_metrics(self) -> dict[str, Any]:
        """Calculate summary metrics across all channels."""
        total_sent = sum(m["total_sent"] for m in self.metrics.values())
        total_failed = sum(m["total_failed"] for m in self.metrics.values())
        total_attempts = total_sent + total_failed

        return {
            "total_sent": total_sent,
            "total_failed": total_failed,
            "overall_success_rate": total_sent / total_attempts if total_attempts > 0 else 0.0,
            "channels_active": len(self.metrics),
        }


class PerformanceOptimizedNotificationManager:
    """
    Enhanced notification manager with performance optimizations.

    Features:
    - Connection pooling for SMTP and HTTP
    - Circuit breaker pattern for failing channels
    - Performance metrics tracking
    - Efficient batch processing
    """

    def __init__(self, config: NotificationSettings):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.PerformanceNotificationManager")

        # Connection pools
        self.smtp_pool: SMTPConnectionPool | None = None
        self.http_pool = HTTPConnectionPool()

        # Circuit breaker manager
        self.circuit_breaker = CircuitBreakerManager(
            failure_threshold=5,
            recovery_timeout=60,
        )

        # Performance metrics
        self.metrics = PerformanceMetrics()

        # Apprise instance for other channels
        self.apprise_obj = Apprise()

        # Initialize pools if SMTP is configured
        if config.smtp.enabled and config.smtp.host:
            self.smtp_pool = SMTPConnectionPool(
                host=config.smtp.host,
                port=config.smtp.port,
                username=config.smtp.username,
                password=config.smtp.password,
                use_tls=config.smtp.use_tls,
                max_connections=5,
            )

    async def initialize(self) -> None:
        """Initialize the performance-optimized notification manager."""
        self.logger.info("Initializing performance-optimized notification manager")

        # Setup non-pooled channels in Apprise
        enabled_channels = self.config.get_enabled_channels()
        for channel_name, channel_url in enabled_channels:
            if channel_name not in ["smtp", "webhook"] and channel_url != "dynamic":
                try:
                    self.apprise_obj.add(channel_url, tag=channel_name)
                    self.logger.debug(f"Added {channel_name} notification channel")
                except Exception as e:
                    self.logger.error(f"Failed to add {channel_name} channel: {e}")

    async def send_notification(
        self, notification: NotificationPayload
    ) -> tuple[bool, dict[str, Any]]:
        """
        Send a notification with performance optimization.

        Returns:
            Tuple of (success, delivery_details)
        """
        start_time = time.time()
        delivery_results = {}
        overall_success = False

        try:
            # Check circuit breakers for requested channels
            available_channels = []
            for channel in notification.channels:
                if not self.circuit_breaker.is_open(channel.value):
                    available_channels.append(channel)
                else:
                    self.logger.warning(f"Circuit breaker open for {channel.value}")
                    delivery_results[channel.value] = {
                        "success": False,
                        "error": "Circuit breaker open",
                        "duration_ms": 0,
                    }

            if not available_channels:
                return False, delivery_results

            # Send to available channels
            tasks = []
            for channel in available_channels:
                if channel == NotificationChannel.SMTP and self.smtp_pool:
                    tasks.append(self._send_smtp_optimized(notification))
                elif channel == NotificationChannel.WEBHOOK:
                    tasks.append(self._send_webhook_optimized(notification))
                else:
                    tasks.append(self._send_via_apprise(notification, channel))

            # Execute all sends concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, (channel, result) in enumerate(zip(available_channels, results, strict=False)):
                channel_start = time.time()

                if isinstance(result, Exception):
                    success = False
                    error = str(result)
                    self.circuit_breaker.record_failure(channel.value)
                else:
                    success, error = result
                    if success:
                        self.circuit_breaker.record_success(channel.value)
                    else:
                        self.circuit_breaker.record_failure(channel.value)

                duration_ms = (time.time() - channel_start) * 1000
                self.metrics.record_delivery(channel.value, success, duration_ms)

                delivery_results[channel.value] = {
                    "success": success,
                    "error": error if not success else None,
                    "duration_ms": duration_ms,
                }

                if success:
                    overall_success = True

            total_duration = (time.time() - start_time) * 1000
            self.logger.info(
                f"Notification {notification.id} sent to {len(available_channels)} channels "
                f"in {total_duration:.2f}ms (success: {overall_success})"
            )

            return overall_success, delivery_results

        except Exception as e:
            self.logger.error(f"Failed to send notification {notification.id}: {e}")
            return False, {"error": str(e)}

    async def send_batch(self, notifications: list[NotificationPayload]) -> dict[str, Any]:
        """
        Send a batch of notifications efficiently.

        Returns:
            Batch processing results
        """
        start_time = time.time()
        batch_results = {
            "total": len(notifications),
            "successful": 0,
            "failed": 0,
            "results": [],
        }

        try:
            # Group notifications by channel for efficient processing
            channel_groups: dict[str, list[NotificationPayload]] = defaultdict(list)
            for notification in notifications:
                for channel in notification.channels:
                    if not self.circuit_breaker.is_open(channel.value):
                        channel_groups[channel.value].append(notification)

            # Process each channel group concurrently
            tasks = []
            for channel, channel_notifications in channel_groups.items():
                if channel == "smtp" and self.smtp_pool:
                    tasks.append(self._send_smtp_batch(channel_notifications))
                elif channel == "webhook":
                    tasks.append(self._send_webhook_batch(channel_notifications))
                else:
                    # For other channels, process individually
                    for notif in channel_notifications:
                        tasks.append(self._send_via_apprise(notif, NotificationChannel(channel)))

            # Execute all batch sends
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    batch_results["failed"] += 1
                elif isinstance(result, list):
                    # Batch result
                    for success, _ in result:
                        if success:
                            batch_results["successful"] += 1
                        else:
                            batch_results["failed"] += 1
                else:
                    # Individual result
                    success, _ = result
                    if success:
                        batch_results["successful"] += 1
                    else:
                        batch_results["failed"] += 1

            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_batch(len(notifications), duration_ms)

            batch_results["duration_ms"] = duration_ms
            batch_results["notifications_per_second"] = (
                len(notifications) / (duration_ms / 1000) if duration_ms > 0 else 0
            )

            self.logger.info(
                f"Batch of {len(notifications)} notifications processed in {duration_ms:.2f}ms "
                f"(success: {batch_results['successful']}, failed: {batch_results['failed']})"
            )

            return batch_results

        except Exception as e:
            self.logger.error(f"Batch processing failed: {e}")
            batch_results["error"] = str(e)
            return batch_results

    async def _send_smtp_optimized(
        self, notification: NotificationPayload
    ) -> tuple[bool, str | None]:
        """Send notification via SMTP with connection pooling."""
        if not self.smtp_pool or not notification.recipient:
            return False, "SMTP not configured or no recipient"

        conn = None
        try:
            # Acquire connection from pool
            conn = await self.smtp_pool.acquire()

            # Create email message
            message = self._create_email_message(notification)

            # Send email
            await conn.send_message(message)

            return True, None

        except Exception as e:
            self.logger.error(f"SMTP send failed: {e}")
            return False, str(e)
        finally:
            if conn:
                await self.smtp_pool.release(conn)

    async def _send_webhook_optimized(
        self, notification: NotificationPayload
    ) -> tuple[bool, str | None]:
        """Send notification via webhook with connection pooling."""
        if not self.config.webhook.url:
            return False, "Webhook not configured"

        session = None
        try:
            # Acquire HTTP session from pool
            session = await self.http_pool.acquire()

            # Prepare webhook payload
            payload = {
                "id": notification.id,
                "timestamp": notification.created_at.isoformat(),
                "level": notification.level.value,
                "title": notification.title,
                "message": notification.message,
                "tags": notification.tags,
                "source": notification.source_component,
            }

            # Add auth headers if configured
            headers = {}
            if self.config.webhook.secret:
                headers["Authorization"] = f"Bearer {self.config.webhook.secret}"

            # Send webhook
            async with session.post(
                self.config.webhook.url,
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 200 and response.status < 300:
                    return True, None
                error = f"Webhook returned {response.status}"
                return False, error

        except Exception as e:
            self.logger.error(f"Webhook send failed: {e}")
            return False, str(e)
        finally:
            if session:
                await self.http_pool.release(session)

    async def _send_via_apprise(
        self, notification: NotificationPayload, channel: NotificationChannel
    ) -> tuple[bool, str | None]:
        """Send notification via Apprise for non-pooled channels."""
        try:
            # Map notification level to Apprise type
            notify_type = {
                "info": NotifyType.INFO,
                "success": NotifyType.SUCCESS,
                "warning": NotifyType.WARNING,
                "error": NotifyType.FAILURE,
                "critical": NotifyType.FAILURE,
            }.get(notification.level.value, NotifyType.INFO)

            # Send via Apprise
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.apprise_obj.notify(
                    body=notification.message,
                    title=notification.title,
                    notify_type=notify_type,
                    tag=[channel.value],
                ),
            )

            return (True, None) if result else (False, "Apprise delivery failed")

        except Exception as e:
            self.logger.error(f"Apprise send failed for {channel.value}: {e}")
            return False, str(e)

    async def _send_smtp_batch(
        self, notifications: list[NotificationPayload]
    ) -> list[tuple[bool, str | None]]:
        """Send batch of emails efficiently."""
        if not self.smtp_pool:
            return [(False, "SMTP not configured")] * len(notifications)

        results = []
        conn = None

        try:
            # Acquire single connection for batch
            conn = await self.smtp_pool.acquire()

            for notification in notifications:
                try:
                    if notification.recipient:
                        message = self._create_email_message(notification)
                        await conn.send_message(message)
                        results.append((True, None))
                    else:
                        results.append((False, "No recipient"))
                except Exception as e:
                    results.append((False, str(e)))

            return results

        except Exception as e:
            self.logger.error(f"SMTP batch send failed: {e}")
            return [(False, str(e))] * len(notifications)
        finally:
            if conn:
                await self.smtp_pool.release(conn)

    async def _send_webhook_batch(
        self, notifications: list[NotificationPayload]
    ) -> list[tuple[bool, str | None]]:
        """Send batch of webhooks efficiently."""
        if not self.config.webhook.url:
            return [(False, "Webhook not configured")] * len(notifications)

        session = None
        try:
            # Acquire HTTP session
            session = await self.http_pool.acquire()

            # Prepare batch payload
            batch_payload = {
                "batch_id": f"batch_{int(time.time())}",
                "notifications": [
                    {
                        "id": n.id,
                        "timestamp": n.created_at.isoformat(),
                        "level": n.level.value,
                        "title": n.title,
                        "message": n.message,
                        "tags": n.tags,
                        "source": n.source_component,
                    }
                    for n in notifications
                ],
            }

            # Add auth headers if configured
            headers = {}
            if self.config.webhook.secret:
                headers["Authorization"] = f"Bearer {self.config.webhook.secret}"

            # Send batch webhook
            async with session.post(
                self.config.webhook.url,
                json=batch_payload,
                headers=headers,
            ) as response:
                if response.status >= 200 and response.status < 300:
                    return [(True, None)] * len(notifications)
                error = f"Webhook returned {response.status}"
                return [(False, error)] * len(notifications)

        except Exception as e:
            self.logger.error(f"Webhook batch send failed: {e}")
            return [(False, str(e))] * len(notifications)
        finally:
            if session:
                await self.http_pool.release(session)

    def _create_email_message(self, notification: NotificationPayload) -> dict[str, Any]:
        """Create email message from notification."""
        return {
            "To": notification.recipient,
            "From": self.config.smtp.from_email,
            "Subject": notification.title or "CoachIQ Notification",
            "Body": notification.message,
        }

    async def get_performance_metrics(self) -> dict[str, Any]:
        """Get current performance metrics."""
        return {
            "metrics": self.metrics.get_all_metrics(),
            "circuit_breakers": self.circuit_breaker.get_all_health(),
            "pools": {
                "smtp": {
                    "active": self.smtp_pool is not None,
                    "connections": self.smtp_pool._created_count if self.smtp_pool else 0,
                    "in_use": len(self.smtp_pool._in_use) if self.smtp_pool else 0,
                    "available": len(self.smtp_pool._pool) if self.smtp_pool else 0,
                }
                if self.smtp_pool
                else None,
                "http": {
                    "active": True,
                    "connections": self.http_pool._created_count,
                    "in_use": len(self.http_pool._in_use),
                    "available": len(self.http_pool._pool),
                },
            },
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on all channels."""
        health_results = {}

        # Check SMTP
        if self.smtp_pool:
            try:
                conn = await self.smtp_pool.acquire()
                healthy = await self.smtp_pool._is_healthy(conn)
                await self.smtp_pool.release(conn)
                health_results["smtp"] = {"healthy": healthy}
            except Exception as e:
                health_results["smtp"] = {"healthy": False, "error": str(e)}

        # Check webhook
        if self.config.webhook.url:
            try:
                session = await self.http_pool.acquire()
                async with session.head(self.config.webhook.url) as response:
                    healthy = response.status < 500
                await self.http_pool.release(session)
                health_results["webhook"] = {"healthy": healthy}
            except Exception as e:
                health_results["webhook"] = {"healthy": False, "error": str(e)}

        # Check other channels via circuit breaker status
        for channel in NotificationChannel:
            if channel.value not in health_results:
                cb_health = self.circuit_breaker.get_channel_health(channel.value)
                health_results[channel.value] = {
                    "healthy": cb_health["healthy"],
                    "circuit_state": cb_health["state"],
                }

        return health_results

    async def close(self) -> None:
        """Clean shutdown of performance-optimized manager."""
        self.logger.info("Shutting down performance-optimized notification manager")

        # Close connection pools
        if self.smtp_pool:
            await self.smtp_pool.close_all()
        await self.http_pool.close_all()
