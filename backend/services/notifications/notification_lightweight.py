"""
Lightweight notification service optimized for Raspberry Pi deployment.

This module provides a memory-efficient notification system suitable for
resource-constrained environments like Raspberry Pi in an RV with <5 users.

Key optimizations:
- Simple in-memory LRU caching with TTL
- Connection pooling with minimal overhead
- Lightweight batching using time windows
- Basic circuit breaker pattern
- Memory-efficient performance monitoring
- No external dependencies (Redis, etc.)
"""

import asyncio
import logging
import time
from collections import OrderedDict, defaultdict, deque
from datetime import datetime
from email.message import EmailMessage
from enum import Enum
from typing import Any

try:
    import aiohttp
    import aiosmtplib
    from jinja2 import Environment, FileSystemLoader

    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False

from backend.core.config import NotificationSettings
from backend.models.notification import (
    NotificationChannel,
    NotificationPayload,
    NotificationType,
)


class SimpleWebhookConfig:
    """Simple webhook configuration for lightweight notification system."""

    def __init__(self, url: str, secret: str | None = None):
        self.url = url
        self.secret = secret
        self.enabled = True


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class LightweightCache:
    """Simple LRU cache with TTL support for templates and configurations."""

    def __init__(self, max_size: int = 100, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Get item from cache if not expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                return value
            # Expired
            del self._cache[key]

        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set item in cache with TTL."""
        ttl = ttl or self.default_ttl
        expiry = time.time() + ttl

        # Remove oldest if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._cache.popitem(last=False)

        self._cache[key] = (value, expiry)
        self._cache.move_to_end(key)

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


class SimpleConnectionPool:
    """Lightweight connection pool for SMTP/HTTP connections."""

    def __init__(self, name: str, max_connections: int = 3, max_idle_time: int = 300):
        self.name = name
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.logger = logging.getLogger(f"{__name__}.{name}")

        self._pool: deque[tuple[Any, float]] = deque()
        self._active_count = 0
        self._lock = asyncio.Lock()
        self._total_created = 0
        self._total_reused = 0

    async def acquire(self) -> Any | None:
        """Acquire a connection from the pool."""
        async with self._lock:
            current_time = time.time()

            # Try to get a healthy connection from pool
            while self._pool:
                conn, last_used = self._pool.popleft()

                # Check if connection is still fresh
                if current_time - last_used < self.max_idle_time:
                    if await self._is_healthy(conn):
                        self._active_count += 1
                        self._total_reused += 1
                        return conn

                # Connection expired or unhealthy
                await self._close_connection(conn)

            # Create new connection if under limit
            if self._active_count < self.max_connections:
                try:
                    conn = await self._create_connection()
                    self._active_count += 1
                    self._total_created += 1
                    return conn
                except Exception as e:
                    self.logger.error(f"Failed to create connection: {e}")
                    return None

            # At capacity
            self.logger.warning(f"Connection pool {self.name} at capacity")
            return None

    async def release(self, conn: Any) -> None:
        """Release connection back to pool."""
        if conn is None:
            return

        async with self._lock:
            self._active_count = max(0, self._active_count - 1)

            if await self._is_healthy(conn):
                self._pool.append((conn, time.time()))
            else:
                await self._close_connection(conn)

    async def clear(self) -> None:
        """Clear all pooled connections."""
        async with self._lock:
            while self._pool:
                conn, _ = self._pool.popleft()
                await self._close_connection(conn)
            self._active_count = 0

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        return {
            "name": self.name,
            "pooled": len(self._pool),
            "active": self._active_count,
            "max_connections": self.max_connections,
            "total_created": self._total_created,
            "total_reused": self._total_reused,
            "reuse_rate": self._total_reused / (self._total_created + self._total_reused)
            if (self._total_created + self._total_reused) > 0
            else 0,
        }

    # Override these in subclasses
    async def _create_connection(self) -> Any:
        raise NotImplementedError

    async def _is_healthy(self, conn: Any) -> bool:
        raise NotImplementedError

    async def _close_connection(self, conn: Any) -> None:
        raise NotImplementedError


class SMTPConnectionPool(SimpleConnectionPool):
    """SMTP-specific connection pool."""

    def __init__(self, config: dict[str, Any], max_connections: int = 2):
        super().__init__("SMTP", max_connections)
        self.config = config

    async def _create_connection(self) -> aiosmtplib.SMTP:
        """Create new SMTP connection."""
        smtp = aiosmtplib.SMTP(
            hostname=self.config["host"],
            port=self.config["port"],
            use_tls=self.config.get("use_tls", True),
            timeout=30,
        )

        await smtp.connect()

        if self.config.get("username") and self.config.get("password"):
            await smtp.login(self.config["username"], self.config["password"])

        return smtp

    async def _is_healthy(self, conn: aiosmtplib.SMTP) -> bool:
        """Check SMTP connection health."""
        try:
            await asyncio.wait_for(conn.noop(), timeout=5)
            return True
        except:
            return False

    async def _close_connection(self, conn: aiosmtplib.SMTP) -> None:
        """Close SMTP connection."""
        try:
            await conn.quit()
        except:
            pass


class HTTPConnectionPool(SimpleConnectionPool):
    """HTTP session pool for webhooks."""

    def __init__(self, max_connections: int = 3):
        super().__init__("HTTP", max_connections)

    async def _create_connection(self) -> aiohttp.ClientSession:
        """Create new HTTP session."""
        connector = aiohttp.TCPConnector(
            limit=10,  # Low limit for Pi
            limit_per_host=5,
            ttl_dns_cache=300,
        )

        return aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "CoachIQ-Notifications/1.0"},
        )

    async def _is_healthy(self, conn: aiohttp.ClientSession) -> bool:
        """Check if session is healthy."""
        return not conn.closed

    async def _close_connection(self, conn: aiohttp.ClientSession) -> None:
        """Close HTTP session."""
        await conn.close()


class SimpleCircuitBreaker:
    """Lightweight circuit breaker for channel protection."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._states: dict[str, CircuitState] = defaultdict(lambda: CircuitState.CLOSED)
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._last_failure_time: dict[str, float] = {}
        self._success_counts: dict[str, int] = defaultdict(int)

    def is_open(self, channel: str) -> bool:
        """Check if circuit is open."""
        state = self._states[channel]

        if state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if channel in self._last_failure_time:
                if time.time() - self._last_failure_time[channel] > self.recovery_timeout:
                    self._states[channel] = CircuitState.HALF_OPEN
                    return False
            return True

        return False

    def record_success(self, channel: str) -> None:
        """Record successful operation."""
        self._success_counts[channel] += 1

        if self._states[channel] == CircuitState.HALF_OPEN:
            # Successful in half-open, close the circuit
            self._states[channel] = CircuitState.CLOSED
            self._failure_counts[channel] = 0

    def record_failure(self, channel: str) -> None:
        """Record failed operation."""
        self._failure_counts[channel] += 1
        self._last_failure_time[channel] = time.time()

        if self._states[channel] == CircuitState.HALF_OPEN:
            # Failed in half-open, reopen immediately
            self._states[channel] = CircuitState.OPEN
        elif self._failure_counts[channel] >= self.failure_threshold:
            # Threshold reached, open circuit
            self._states[channel] = CircuitState.OPEN

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        stats = {}
        for channel in set(list(self._states.keys()) + list(self._failure_counts.keys())):
            stats[channel] = {
                "state": self._states[channel].value,
                "failures": self._failure_counts[channel],
                "successes": self._success_counts[channel],
                "last_failure": datetime.fromtimestamp(self._last_failure_time[channel]).isoformat()
                if channel in self._last_failure_time
                else None,
            }
        return stats


class SimpleBatcher:
    """Lightweight notification batcher using time windows."""

    def __init__(self, window_seconds: int = 5, max_batch_size: int = 20):
        self.window_seconds = window_seconds
        self.max_batch_size = max_batch_size
        self._batches: dict[str, list[NotificationPayload]] = defaultdict(list)
        self._window_start: dict[str, float] = {}
        self._total_batched = 0
        self._total_sent = 0

    def add_notification(self, channel: str, notification: NotificationPayload) -> bool:
        """Add notification to batch. Returns True if batch is ready."""
        current_time = time.time()

        # Initialize window if needed
        if channel not in self._window_start:
            self._window_start[channel] = current_time

        # Add to batch
        self._batches[channel].append(notification)
        self._total_batched += 1

        # Check if batch is ready
        window_age = current_time - self._window_start[channel]
        batch_size = len(self._batches[channel])

        return (
            batch_size >= self.max_batch_size
            or window_age >= self.window_seconds
            or notification.level == NotificationType.CRITICAL
        )

    def get_batch(self, channel: str) -> list[NotificationPayload]:
        """Get and clear batch for channel."""
        batch = self._batches[channel].copy()
        self._batches[channel].clear()
        self._window_start[channel] = time.time()
        self._total_sent += len(batch)
        return batch

    def get_all_ready_batches(self) -> dict[str, list[NotificationPayload]]:
        """Get all batches that are ready to send."""
        current_time = time.time()
        ready = {}

        for channel, notifications in self._batches.items():
            if notifications:
                window_age = current_time - self._window_start[channel]
                if window_age >= self.window_seconds or len(notifications) >= self.max_batch_size:
                    ready[channel] = self.get_batch(channel)

        return ready

    def get_stats(self) -> dict[str, Any]:
        """Get batcher statistics."""
        return {
            "active_batches": len([b for b in self._batches.values() if b]),
            "total_batched": self._total_batched,
            "total_sent": self._total_sent,
            "efficiency": 1 - (self._total_sent / self._total_batched)
            if self._total_batched > 0
            else 0,
            "channels": {channel: len(batch) for channel, batch in self._batches.items() if batch},
        }


class SimpleMetrics:
    """Lightweight performance metrics without external dependencies."""

    def __init__(self, history_size: int = 100):
        self.history_size = history_size
        self._delivery_times: deque[float] = deque(maxlen=history_size)
        self._channel_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"sent": 0, "failed": 0}
        )
        self._memory_samples: deque[tuple[float, float]] = deque(maxlen=10)
        self._start_time = time.time()

    def record_delivery(self, channel: str, success: bool, duration_ms: float) -> None:
        """Record delivery attempt."""
        self._delivery_times.append(duration_ms)

        if success:
            self._channel_stats[channel]["sent"] += 1
        else:
            self._channel_stats[channel]["failed"] += 1

    def record_memory(self) -> None:
        """Record current memory usage."""
        try:
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self._memory_samples.append((time.time(), memory_mb))
        except ImportError:
            # psutil not available, skip memory tracking
            pass

    def get_stats(self) -> dict[str, Any]:
        """Get performance statistics."""
        total_sent = sum(s["sent"] for s in self._channel_stats.values())
        total_failed = sum(s["failed"] for s in self._channel_stats.values())

        # Calculate delivery time statistics
        if self._delivery_times:
            delivery_times = list(self._delivery_times)
            avg_time = sum(delivery_times) / len(delivery_times)
            min_time = min(delivery_times)
            max_time = max(delivery_times)
        else:
            avg_time = min_time = max_time = 0

        # Memory statistics
        memory_stats = {}
        if self._memory_samples:
            memory_values = [m[1] for m in self._memory_samples]
            memory_stats = {
                "current_mb": memory_values[-1],
                "avg_mb": sum(memory_values) / len(memory_values),
                "max_mb": max(memory_values),
            }

        return {
            "uptime_seconds": time.time() - self._start_time,
            "total_sent": total_sent,
            "total_failed": total_failed,
            "success_rate": total_sent / (total_sent + total_failed)
            if (total_sent + total_failed) > 0
            else 0,
            "delivery_time_ms": {
                "avg": avg_time,
                "min": min_time,
                "max": max_time,
            },
            "channels": dict(self._channel_stats),
            "memory": memory_stats,
        }


class LightweightNotificationManager:
    """
    Memory-efficient notification manager optimized for Raspberry Pi.

    Features:
    - Simple LRU caching for templates
    - Lightweight connection pooling
    - Basic batching with time windows
    - Simple circuit breaker
    - Memory-efficient metrics
    - No external dependencies
    """

    def __init__(self, config: NotificationSettings):
        if not DEPENDENCIES_AVAILABLE:
            raise ImportError(
                "Required packages not available. Install with: "
                "pip install aiohttp aiosmtplib jinja2"
            )

        self.config = config
        self.logger = logging.getLogger(__name__)

        # Template cache
        self._template_cache = LightweightCache(max_size=20, default_ttl=3600)
        self._template_env: Environment | None = None
        self._setup_templates()

        # Connection pools (small for Pi)
        self._smtp_pool: SMTPConnectionPool | None = None
        self._http_pool = HTTPConnectionPool(max_connections=3)

        if config.smtp.enabled and config.smtp.host:
            smtp_config = {
                "host": config.smtp.host,
                "port": config.smtp.port,
                "username": config.smtp.username,
                "password": config.smtp.password,
                "use_tls": config.smtp.use_tls,
            }
            self._smtp_pool = SMTPConnectionPool(smtp_config, max_connections=2)

        # Circuit breaker
        self._circuit_breaker = SimpleCircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Batcher
        self._batcher = SimpleBatcher(window_seconds=5, max_batch_size=20)

        # Metrics
        self._metrics = SimpleMetrics(history_size=100)

        # Background tasks
        self._batch_processor_task: asyncio.Task | None = None
        self._metrics_task: asyncio.Task | None = None

        self.logger.info("Lightweight notification manager initialized")

    def _setup_templates(self) -> None:
        """Setup Jinja2 environment."""
        try:
            from pathlib import Path

            template_path = Path(self.config.template_path)

            if not template_path.exists():
                template_path.mkdir(parents=True, exist_ok=True)

            self._template_env = Environment(
                loader=FileSystemLoader(str(template_path)),
                autoescape=True,
                enable_async=True,
            )
        except Exception as e:
            self.logger.warning(f"Failed to setup templates: {e}")

    async def initialize(self) -> None:
        """Initialize background tasks."""
        self._batch_processor_task = asyncio.create_task(self._batch_processor())
        self._metrics_task = asyncio.create_task(self._metrics_collector())

    async def send_notification(
        self,
        message: str,
        title: str | None = None,
        level: str = "info",
        channels: list[str] | None = None,
        recipient: str | None = None,
        batch: bool = True,
    ) -> bool:
        """Send notification with optional batching."""
        if not self.config.enabled:
            return False

        # Create notification payload with all required fields
        notification = NotificationPayload(
            id=f"notif_{int(time.time() * 1000)}",
            message=message,
            title=title or "CoachIQ Notification",
            level=NotificationType(level),
            channels=[NotificationChannel(c) for c in (channels or ["webhook"])],
            recipient=recipient,
            created_at=datetime.utcnow(),
            tags=[],
            template=None,
            context={},
            status="pending",
            retry_count=0,
            max_retries=3,
            scheduled_for=None,
            priority=1,
            last_error=None,
            last_attempt=None,
            source_component="lightweight",
            correlation_id=None,
            pushover_priority=None,
            pushover_device=None,
        )

        # Check if batching is appropriate
        if batch and notification.level not in [NotificationType.CRITICAL, NotificationType.ERROR]:
            # Add to batch
            for channel in notification.channels:
                if self._batcher.add_notification(channel.value, notification):
                    # Batch is ready, process immediately
                    batch_notifications = self._batcher.get_batch(channel.value)
                    asyncio.create_task(self._send_batch(channel.value, batch_notifications))
            return True
        # Send immediately
        return await self._send_immediate(notification)

    async def _send_immediate(self, notification: NotificationPayload) -> bool:
        """Send notification immediately without batching."""
        success = False

        for channel in notification.channels:
            if self._circuit_breaker.is_open(channel.value):
                self.logger.warning(f"Circuit open for {channel.value}, skipping")
                continue

            start_time = time.time()
            try:
                if channel == NotificationChannel.SMTP and self._smtp_pool:
                    result = await self._send_smtp(notification)
                elif channel == NotificationChannel.WEBHOOK:
                    result = await self._send_webhook(notification)
                else:
                    result = False

                duration_ms = (time.time() - start_time) * 1000
                self._metrics.record_delivery(channel.value, result, duration_ms)

                if result:
                    self._circuit_breaker.record_success(channel.value)
                    success = True
                else:
                    self._circuit_breaker.record_failure(channel.value)

            except Exception as e:
                self.logger.error(f"Failed to send via {channel.value}: {e}")
                self._circuit_breaker.record_failure(channel.value)
                duration_ms = (time.time() - start_time) * 1000
                self._metrics.record_delivery(channel.value, False, duration_ms)

        return success

    async def _send_batch(self, channel: str, notifications: list[NotificationPayload]) -> None:
        """Send a batch of notifications."""
        if not notifications:
            return

        if self._circuit_breaker.is_open(channel):
            self.logger.warning(
                f"Circuit open for {channel}, dropping batch of {len(notifications)}"
            )
            return

        start_time = time.time()
        try:
            if channel == "smtp" and self._smtp_pool:
                success = await self._send_smtp_batch(notifications)
            elif channel == "webhook":
                success = await self._send_webhook_batch(notifications)
            else:
                success = False

            duration_ms = (time.time() - start_time) * 1000

            # Record metrics for each notification
            for _ in notifications:
                self._metrics.record_delivery(channel, success, duration_ms / len(notifications))

            if success:
                self._circuit_breaker.record_success(channel)
            else:
                self._circuit_breaker.record_failure(channel)

        except Exception as e:
            self.logger.error(f"Batch send failed for {channel}: {e}")
            self._circuit_breaker.record_failure(channel)

    async def _send_smtp(self, notification: NotificationPayload) -> bool:
        """Send single email."""
        if not self._smtp_pool or not notification.recipient:
            return False

        conn = None
        try:
            conn = await self._smtp_pool.acquire()
            if not conn:
                return False

            # Create email
            msg = EmailMessage()
            msg["Subject"] = notification.title
            msg["From"] = self.config.smtp.from_email
            msg["To"] = notification.recipient

            # Check cache for rendered template
            cache_key = f"email_{notification.level}_{hash(notification.message)}"
            content = self._template_cache.get(cache_key)

            if not content:
                content = self._render_email_content(notification)
                self._template_cache.set(cache_key, content, ttl=300)

            msg.set_content(content, subtype="html")

            # Send
            await conn.send_message(msg)
            return True

        except Exception as e:
            self.logger.error(f"SMTP send failed: {e}")
            return False
        finally:
            if conn:
                await self._smtp_pool.release(conn)

    async def _send_smtp_batch(self, notifications: list[NotificationPayload]) -> bool:
        """Send batch of emails efficiently."""
        if not self._smtp_pool:
            return False

        conn = None
        try:
            conn = await self._smtp_pool.acquire()
            if not conn:
                return False

            # Send all emails on single connection
            for notification in notifications:
                if notification.recipient:
                    msg = EmailMessage()
                    msg["Subject"] = notification.title
                    msg["From"] = self.config.smtp.from_email
                    msg["To"] = notification.recipient

                    content = self._render_email_content(notification)
                    msg.set_content(content, subtype="html")

                    await conn.send_message(msg)

            return True

        except Exception as e:
            self.logger.error(f"SMTP batch failed: {e}")
            return False
        finally:
            if conn:
                await self._smtp_pool.release(conn)

    async def _send_webhook(self, notification: NotificationPayload) -> bool:
        """Send single webhook."""
        # For lightweight version, check if there's a default webhook URL in targets
        if not self.config.webhook.enabled or not self.config.webhook.targets:
            return False

        # Get first available webhook target
        webhook_url = None
        webhook_secret = None
        for target_name, target_config in self.config.webhook.targets.items():
            if isinstance(target_config, dict) and target_config.get("url"):
                webhook_url = target_config["url"]
                webhook_secret = target_config.get("secret")
                break

        if not webhook_url:
            return False

        session = None
        try:
            session = await self._http_pool.acquire()
            if not session:
                return False

            payload = {
                "id": notification.id,
                "timestamp": notification.created_at.isoformat(),
                "level": notification.level.value,
                "title": notification.title,
                "message": notification.message,
                "source": notification.source_component,
            }

            headers = {}
            if webhook_secret:
                headers["Authorization"] = f"Bearer {webhook_secret}"

            async with session.post(
                webhook_url,
                json=payload,
                headers=headers,
            ) as response:
                return 200 <= response.status < 300

        except Exception as e:
            self.logger.error(f"Webhook failed: {e}")
            return False
        finally:
            if session:
                await self._http_pool.release(session)

    async def _send_webhook_batch(self, notifications: list[NotificationPayload]) -> bool:
        """Send batch webhook."""
        # For lightweight version, check if there's a default webhook URL in targets
        if not self.config.webhook.enabled or not self.config.webhook.targets:
            return False

        # Get first available webhook target
        webhook_url = None
        webhook_secret = None
        for target_name, target_config in self.config.webhook.targets.items():
            if isinstance(target_config, dict) and target_config.get("url"):
                webhook_url = target_config["url"]
                webhook_secret = target_config.get("secret")
                break

        if not webhook_url:
            return False

        session = None
        try:
            session = await self._http_pool.acquire()
            if not session:
                return False

            payload = {
                "batch_id": f"batch_{int(time.time())}",
                "notifications": [
                    {
                        "id": n.id,
                        "timestamp": n.created_at.isoformat(),
                        "level": n.level.value,
                        "title": n.title,
                        "message": n.message,
                    }
                    for n in notifications
                ],
            }

            headers = {}
            if webhook_secret:
                headers["Authorization"] = f"Bearer {webhook_secret}"

            async with session.post(
                webhook_url,
                json=payload,
                headers=headers,
            ) as response:
                return 200 <= response.status < 300

        except Exception as e:
            self.logger.error(f"Webhook batch failed: {e}")
            return False
        finally:
            if session:
                await self._http_pool.release(session)

    def _render_email_content(self, notification: NotificationPayload) -> str:
        """Render email content with caching."""
        # Simple HTML template
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{notification.title}</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #333;">{notification.title}</h2>
            <div style="padding: 20px; background: #f5f5f5; border-radius: 5px;">
                <p style="color: #666; margin: 0;">{notification.message}</p>
            </div>
            <p style="color: #999; font-size: 12px; margin-top: 20px;">
                Sent by CoachIQ at {notification.created_at.strftime("%Y-%m-%d %H:%M:%S")}
            </p>
        </body>
        </html>
        """

    async def _batch_processor(self) -> None:
        """Background task to process batches."""
        while True:
            try:
                await asyncio.sleep(1)

                # Get ready batches
                ready_batches = self._batcher.get_all_ready_batches()

                for channel, notifications in ready_batches.items():
                    if notifications:
                        asyncio.create_task(self._send_batch(channel, notifications))

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Batch processor error: {e}")

    async def _metrics_collector(self) -> None:
        """Background task to collect metrics."""
        while True:
            try:
                await asyncio.sleep(60)  # Collect every minute
                self._metrics.record_memory()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Metrics collector error: {e}")

    async def get_health(self) -> dict[str, Any]:
        """Get system health information."""
        return {
            "status": "healthy",
            "uptime": time.time() - self._metrics._start_time,
            "circuit_breakers": self._circuit_breaker.get_stats(),
            "pools": {
                "smtp": self._smtp_pool.get_stats() if self._smtp_pool else None,
                "http": self._http_pool.get_stats(),
            },
            "cache": self._template_cache.get_stats(),
            "batcher": self._batcher.get_stats(),
            "metrics": self._metrics.get_stats(),
        }

    async def close(self) -> None:
        """Clean shutdown."""
        self.logger.info("Shutting down lightweight notification manager")

        # Cancel background tasks
        if self._batch_processor_task:
            self._batch_processor_task.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()

        # Clear pools
        if self._smtp_pool:
            await self._smtp_pool.clear()
        await self._http_pool.clear()

        # Clear cache
        self._template_cache.clear()
