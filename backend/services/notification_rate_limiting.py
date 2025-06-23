"""
Rate Limiting and Debouncing for Notification System

This module implements token bucket rate limiting and notification debouncing
to protect against CAN bus message flooding attacks and prevent notification
spam in safety-critical RV-C environments.

Key Features:
- Token bucket algorithm for smooth rate limiting
- Notification debouncing with configurable time windows
- Per-channel rate limiting capabilities
- Comprehensive monitoring and statistics
- Thread-safe async implementation

Example:
    >>> rate_limiter = TokenBucketRateLimiter(max_tokens=100, refill_rate=10)
    >>> debouncer = NotificationDebouncer(suppress_window_minutes=15)
    >>>
    >>> if rate_limiter.allow("test message"):
    >>>     if debouncer.allow("test message", "info"):
    >>>         # Send notification
    >>>         pass
"""

import asyncio
import hashlib
import logging
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from backend.models.notification import RateLimitStatus


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter for smooth traffic control.

    Implements the token bucket algorithm to allow burst traffic while
    maintaining long-term rate limits. Designed for safety-critical
    environments where notification storms could impact vehicle systems.
    """

    def __init__(
        self,
        max_tokens: int = 100,
        refill_rate: float = 10.0,  # tokens per minute
        burst_allowance: float = 1.5,  # multiplier for burst detection
    ):
        """
        Initialize token bucket rate limiter.

        Args:
            max_tokens: Maximum tokens in bucket (burst capacity)
            refill_rate: Tokens refilled per minute
            burst_allowance: Multiplier for burst detection threshold
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate  # tokens per minute
        self.burst_threshold = int(max_tokens * burst_allowance)

        self.current_tokens = max_tokens
        self.last_refill = time.time()

        # Statistics tracking
        self.total_requests = 0
        self.blocked_requests = 0
        self.burst_events = 0
        self.last_reset = datetime.utcnow()

        # Request tracking for burst detection
        self.request_timestamps: deque = deque()
        self.burst_window = 60  # seconds

        self.logger = logging.getLogger(f"{__name__}.TokenBucketRateLimiter")
        self._lock = asyncio.Lock()

    async def allow(self, identifier: str | None = None) -> bool:
        """
        Check if request should be allowed.

        Args:
            identifier: Optional identifier for tracking (message content hash)

        Returns:
            bool: True if request is allowed
        """
        async with self._lock:
            self.total_requests += 1
            current_time = time.time()

            # Refill tokens based on elapsed time
            await self._refill_tokens(current_time)

            # Track request timestamp for burst detection
            self.request_timestamps.append(current_time)

            # Remove old timestamps outside burst window
            cutoff_time = current_time - self.burst_window
            while self.request_timestamps and self.request_timestamps[0] < cutoff_time:
                self.request_timestamps.popleft()

            # Check for burst activity
            if len(self.request_timestamps) > self.burst_threshold:
                self.burst_events += 1
                self.logger.warning(
                    f"Burst detected: {len(self.request_timestamps)} requests in {self.burst_window}s"
                )

            # Check if tokens available
            if self.current_tokens >= 1:
                self.current_tokens -= 1
                return True
            self.blocked_requests += 1
            if identifier:
                self.logger.debug(f"Rate limited request: {identifier[:50]}...")
            return False

    async def _refill_tokens(self, current_time: float) -> None:
        """Refill tokens based on elapsed time."""
        time_elapsed = current_time - self.last_refill
        tokens_to_add = (time_elapsed / 60.0) * self.refill_rate  # convert to per-minute rate

        if tokens_to_add >= 1:
            self.current_tokens = min(self.max_tokens, self.current_tokens + int(tokens_to_add))
            self.last_refill = current_time

    def get_status(self) -> RateLimitStatus:
        """Get current rate limiter status."""
        requests_last_minute = len([ts for ts in self.request_timestamps if time.time() - ts <= 60])

        return RateLimitStatus(
            current_tokens=int(self.current_tokens),
            max_tokens=self.max_tokens,
            refill_rate=self.refill_rate,
            requests_last_minute=requests_last_minute,
            requests_blocked=self.blocked_requests,
            active_debounces=0,  # Not tracked in rate limiter
            healthy=self.current_tokens > 0 or self.refill_rate > 0,
            last_reset=self.last_reset,
        )

    async def reset(self) -> None:
        """Reset rate limiter state."""
        async with self._lock:
            self.current_tokens = self.max_tokens
            self.last_refill = time.time()
            self.total_requests = 0
            self.blocked_requests = 0
            self.burst_events = 0
            self.last_reset = datetime.utcnow()
            self.request_timestamps.clear()

            self.logger.info("Rate limiter reset")


class NotificationDebouncer:
    """
    Notification debouncing to prevent spam and duplicate alerts.

    Tracks recent notifications by content hash and level to suppress
    duplicates within configurable time windows. Essential for RV-C
    environments where sensor fluctuations could cause notification storms.
    """

    def __init__(
        self,
        suppress_window_minutes: int = 15,
        max_tracked_items: int = 10000,
        cleanup_interval_minutes: int = 60,
    ):
        """
        Initialize notification debouncer.

        Args:
            suppress_window_minutes: Time window for suppressing duplicates
            max_tracked_items: Maximum items to track (memory protection)
            cleanup_interval_minutes: How often to clean up old entries
        """
        self.suppress_window = timedelta(minutes=suppress_window_minutes)
        self.max_tracked_items = max_tracked_items
        self.cleanup_interval = timedelta(minutes=cleanup_interval_minutes)

        # Track: {(content_hash, level): last_sent_time}
        self.suppressed_notifications: dict[tuple[str, str], datetime] = {}

        # Statistics
        self.total_checks = 0
        self.suppressed_count = 0
        self.last_cleanup = datetime.utcnow()

        self.logger = logging.getLogger(f"{__name__}.NotificationDebouncer")
        self._lock = asyncio.Lock()

        # Start background cleanup task
        asyncio.create_task(self._cleanup_loop())

    async def allow(self, message: str, level: str = "info", custom_key: str | None = None) -> bool:
        """
        Check if notification should be allowed (not suppressed).

        Args:
            message: Notification message content
            level: Notification level (info, warning, error, etc.)
            custom_key: Optional custom key for grouping

        Returns:
            bool: True if notification should be sent
        """
        async with self._lock:
            self.total_checks += 1

            # Create suppression key
            if custom_key:
                content_hash = custom_key
            else:
                # Hash message content for consistent key generation
                content_hash = hashlib.md5(
                    message.encode("utf-8"), usedforsecurity=False
                ).hexdigest()

            suppression_key = (content_hash, level.lower())
            current_time = datetime.utcnow()

            # Check if this notification was recently sent
            if suppression_key in self.suppressed_notifications:
                last_sent = self.suppressed_notifications[suppression_key]
                if current_time - last_sent < self.suppress_window:
                    self.suppressed_count += 1
                    self.logger.debug(
                        f"Suppressed duplicate notification: {message[:50]}... (level: {level})"
                    )
                    return False

            # Allow notification and update tracking
            self.suppressed_notifications[suppression_key] = current_time

            # Trigger cleanup if needed
            if len(self.suppressed_notifications) > self.max_tracked_items:
                await self._cleanup_old_entries()

            return True

    async def _cleanup_old_entries(self) -> None:
        """Clean up old suppression entries."""
        current_time = datetime.utcnow()
        cutoff_time = current_time - self.suppress_window

        # Remove entries older than suppression window
        old_keys = [
            key
            for key, timestamp in self.suppressed_notifications.items()
            if timestamp < cutoff_time
        ]

        for key in old_keys:
            del self.suppressed_notifications[key]

        if old_keys:
            self.logger.debug(f"Cleaned up {len(old_keys)} old debounce entries")

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval.total_seconds())

                async with self._lock:
                    await self._cleanup_old_entries()
                    self.last_cleanup = datetime.utcnow()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Cleanup loop error: {e}")

    def get_statistics(self) -> dict[str, Any]:
        """Get debouncer statistics."""
        return {
            "total_checks": self.total_checks,
            "suppressed_count": self.suppressed_count,
            "suppression_rate": self.suppressed_count / max(1, self.total_checks),
            "active_suppressions": len(self.suppressed_notifications),
            "suppress_window_minutes": self.suppress_window.total_seconds() / 60,
            "last_cleanup": self.last_cleanup.isoformat(),
            "memory_usage_items": len(self.suppressed_notifications),
        }

    async def clear_suppressions(self, pattern: str | None = None) -> int:
        """
        Clear suppression entries, optionally matching a pattern.

        Args:
            pattern: Optional pattern to match against message content

        Returns:
            int: Number of suppressions cleared
        """
        async with self._lock:
            if pattern is None:
                # Clear all
                count = len(self.suppressed_notifications)
                self.suppressed_notifications.clear()
                self.logger.info(f"Cleared all {count} debounce suppressions")
                return count
            # Clear matching pattern
            pattern_hash = hashlib.md5(pattern.encode("utf-8"), usedforsecurity=False).hexdigest()
            keys_to_remove = [
                key for key in self.suppressed_notifications if key[0] == pattern_hash
            ]

            for key in keys_to_remove:
                del self.suppressed_notifications[key]

            count = len(keys_to_remove)
            if count > 0:
                self.logger.info(f"Cleared {count} debounce suppressions matching pattern")

            return count


class ChannelSpecificRateLimiter:
    """
    Per-channel rate limiting for fine-grained control.

    Allows different rate limits for different notification channels
    (e.g., stricter limits for SMS, more relaxed for logs).
    """

    def __init__(self, default_config: dict[str, Any] | None = None):
        """
        Initialize channel-specific rate limiter.

        Args:
            default_config: Default rate limiting configuration
        """
        self.default_config = default_config or {"max_tokens": 100, "refill_rate": 10.0}

        # Per-channel rate limiters
        self.channel_limiters: dict[str, TokenBucketRateLimiter] = {}

        # Channel-specific configurations
        self.channel_configs = {
            "smtp": {"max_tokens": 50, "refill_rate": 5.0},  # Email is expensive
            "slack": {"max_tokens": 100, "refill_rate": 10.0},  # Slack handles bursts well
            "discord": {"max_tokens": 100, "refill_rate": 10.0},  # Similar to Slack
            "pushover": {"max_tokens": 200, "refill_rate": 20.0},  # Pushover is lightweight
            "system": {"max_tokens": 1000, "refill_rate": 100.0},  # Local logs unrestricted
        }

        self.logger = logging.getLogger(f"{__name__}.ChannelSpecificRateLimiter")

    async def allow(self, channel: str, identifier: str | None = None) -> bool:
        """
        Check if request is allowed for specific channel.

        Args:
            channel: Notification channel name
            identifier: Optional identifier for tracking

        Returns:
            bool: True if request is allowed
        """
        # Get or create rate limiter for channel
        if channel not in self.channel_limiters:
            config = self.channel_configs.get(channel, self.default_config)
            self.channel_limiters[channel] = TokenBucketRateLimiter(
                max_tokens=config["max_tokens"], refill_rate=config["refill_rate"]
            )

        return await self.channel_limiters[channel].allow(identifier)

    def get_channel_status(self, channel: str) -> RateLimitStatus | None:
        """Get rate limiting status for specific channel."""
        if channel in self.channel_limiters:
            return self.channel_limiters[channel].get_status()
        return None

    def get_all_channel_status(self) -> dict[str, RateLimitStatus]:
        """Get rate limiting status for all channels."""
        return {channel: limiter.get_status() for channel, limiter in self.channel_limiters.items()}

    async def reset_channel(self, channel: str) -> bool:
        """Reset rate limiter for specific channel."""
        if channel in self.channel_limiters:
            await self.channel_limiters[channel].reset()
            self.logger.info(f"Reset rate limiter for channel: {channel}")
            return True
        return False

    async def reset_all(self) -> None:
        """Reset all channel rate limiters."""
        for limiter in self.channel_limiters.values():
            await limiter.reset()
        self.logger.info("Reset all channel rate limiters")


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts limits based on system health.

    Monitors system metrics and automatically tightens rate limits when
    the system is under stress (high queue depth, processing delays, etc.).
    """

    def __init__(
        self,
        base_rate_limiter: TokenBucketRateLimiter,
        health_check_interval: int = 30,  # seconds
    ):
        """
        Initialize adaptive rate limiter.

        Args:
            base_rate_limiter: Base rate limiter to adapt
            health_check_interval: How often to check system health
        """
        self.base_limiter = base_rate_limiter
        self.health_check_interval = health_check_interval

        # Adaptation factors
        self.current_factor = 1.0  # 1.0 = normal, 0.5 = half rate, 2.0 = double rate
        self.min_factor = 0.1  # Minimum rate (10% of normal)
        self.max_factor = 2.0  # Maximum rate (200% of normal)

        # Health thresholds
        self.health_thresholds = {
            "queue_depth_warning": 1000,
            "queue_depth_critical": 5000,
            "success_rate_warning": 0.9,
            "success_rate_critical": 0.7,
            "processing_time_warning": 30.0,  # seconds
            "processing_time_critical": 120.0,
        }

        self.logger = logging.getLogger(f"{__name__}.AdaptiveRateLimiter")

        # Start health monitoring
        asyncio.create_task(self._health_monitoring_loop())

    async def allow(self, identifier: str | None = None) -> bool:
        """Check if request is allowed with adaptive limiting."""
        return await self.base_limiter.allow(identifier)

    async def update_health_metrics(self, metrics: dict[str, Any]) -> None:
        """Update system health metrics and adjust rate limiting."""
        try:
            health_score = self._calculate_health_score(metrics)
            new_factor = self._calculate_adaptation_factor(health_score)

            if abs(new_factor - self.current_factor) > 0.1:  # Significant change
                await self._apply_adaptation_factor(new_factor)
                self.current_factor = new_factor

                self.logger.info(
                    f"Adapted rate limiting: factor={new_factor:.2f}, "
                    f"health_score={health_score:.2f}"
                )

        except Exception as e:
            self.logger.error(f"Failed to update adaptive rate limiting: {e}")

    def _calculate_health_score(self, metrics: dict[str, Any]) -> float:
        """Calculate overall system health score (0.0 = unhealthy, 1.0 = healthy)."""
        score = 1.0

        # Queue depth impact
        queue_depth = metrics.get("queue_depth", 0)
        if queue_depth > self.health_thresholds["queue_depth_critical"]:
            score *= 0.2
        elif queue_depth > self.health_thresholds["queue_depth_warning"]:
            score *= 0.7

        # Success rate impact
        success_rate = metrics.get("success_rate", 1.0)
        if success_rate < self.health_thresholds["success_rate_critical"]:
            score *= 0.3
        elif success_rate < self.health_thresholds["success_rate_warning"]:
            score *= 0.8

        # Processing time impact
        processing_time = metrics.get("avg_processing_time", 0)
        if processing_time > self.health_thresholds["processing_time_critical"]:
            score *= 0.4
        elif processing_time > self.health_thresholds["processing_time_warning"]:
            score *= 0.8

        return max(0.0, min(1.0, score))

    def _calculate_adaptation_factor(self, health_score: float) -> float:
        """Calculate rate limiting adaptation factor based on health score."""
        if health_score < 0.3:
            # System under severe stress - drastically reduce rate
            return self.min_factor
        if health_score < 0.7:
            # System under moderate stress - reduce rate proportionally
            return self.min_factor + (health_score - 0.3) / 0.4 * (1.0 - self.min_factor)
        if health_score > 0.95:
            # System very healthy - can increase rate slightly
            return min(
                self.max_factor, 1.0 + (health_score - 0.95) / 0.05 * (self.max_factor - 1.0)
            )
        # Normal operation
        return 1.0

    async def _apply_adaptation_factor(self, factor: float) -> None:
        """Apply adaptation factor to base rate limiter."""
        # Adjust refill rate based on factor
        original_rate = getattr(self.base_limiter, "_original_refill_rate", None)
        if original_rate is None:
            # Store original rate as private attribute
            self.base_limiter._original_refill_rate = self.base_limiter.refill_rate
            original_rate = self.base_limiter.refill_rate

        self.base_limiter.refill_rate = original_rate * factor

    async def _health_monitoring_loop(self) -> None:
        """Background health monitoring loop."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                # Health metrics would be provided by the notification system
                # This is a placeholder for the monitoring integration

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Health monitoring loop error: {e}")


# Utility functions


def create_message_hash(message: str, context: dict[str, Any] | None = None) -> str:
    """
    Create consistent hash for message content and context.

    Args:
        message: Notification message
        context: Optional context data

    Returns:
        str: Consistent hash for deduplication
    """
    content = message
    if context:
        # Include relevant context in hash (exclude timestamps, IDs)
        stable_context = {
            k: v
            for k, v in context.items()
            if k not in ["timestamp", "id", "created_at", "correlation_id"]
        }
        content += str(sorted(stable_context.items()))

    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def calculate_backoff_delay(
    attempt: int, base_delay: float = 30.0, max_delay: float = 300.0
) -> float:
    """
    Calculate exponential backoff delay for retries.

    Args:
        attempt: Retry attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        float: Delay in seconds
    """
    delay = base_delay * (2**attempt)
    return min(delay, max_delay)
