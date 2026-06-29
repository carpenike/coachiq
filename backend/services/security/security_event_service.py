"""Security Event Service

Core service for security event management, extracted from SecurityEventManager.
Handles event publishing, listener management, and statistics tracking.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from backend.core.performance import PerformanceMonitor
from backend.models.security_events import SecurityEvent, SecurityEventStats
from backend.repositories.security_event_repository import (
    SecurityEventRepository,
    SecurityListenerRepository,
)

logger = logging.getLogger(__name__)


class SecurityEventService:
    """
    Core service for security event management.

    Handles the business logic for security event publishing,
    listener management, and event distribution.
    """

    def __init__(
        self,
        event_repository: SecurityEventRepository,
        listener_repository: SecurityListenerRepository,
        performance_monitor: PerformanceMonitor,
    ):
        """
        Initialize the security event service.

        Args:
            event_repository: Repository for event storage
            listener_repository: Repository for listener management
            performance_monitor: Performance monitoring instance
        """
        self._event_repo = event_repository
        self._listener_repo = listener_repository
        self._monitor = performance_monitor

        # Active listeners (in-memory for performance)
        self._listeners: list[Callable[[SecurityEvent], Any]] = []
        self._listener_info: dict[Callable, dict[str, Any]] = {}

        # Statistics tracking
        self._stats = {
            "events_published": 0,
            "events_delivered": 0,
            "delivery_failures": 0,
            "listeners_registered": 0,
            "start_time": time.time(),
        }

        # Performance metrics
        self._delivery_times: list[float] = []
        self._max_delivery_time_samples = 1000

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("SecurityEventService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.publish_event = self._monitor.monitor_service_method(
            "SecurityEventService", "publish_event"
        )(self.publish_event)

        self.subscribe = self._monitor.monitor_service_method("SecurityEventService", "subscribe")(
            self.subscribe
        )

        self.get_statistics = self._monitor.monitor_service_method(
            "SecurityEventService", "get_statistics"
        )(self.get_statistics)

    async def publish_event(self, event: SecurityEvent) -> None:
        """
        Publish a security event to all registered listeners.

        Args:
            event: Security event to publish
        """
        # Store event in repository
        await self._event_repo.store_event(event)

        # Update statistics
        self._stats["events_published"] += 1

        # Distribute to listeners
        if self._listeners:
            await self._distribute_event(event)

        logger.debug(
            f"Published security event: type={event.event_type}, "
            f"component={event.component}, listeners={len(self._listeners)}"
        )

    async def _distribute_event(self, event: SecurityEvent) -> None:
        """
        Distribute event to all listeners with failure isolation.

        Args:
            event: Event to distribute
        """
        start_time = time.time()
        tasks = []

        for listener in self._listeners:
            # Create task for each listener (non-blocking)
            task = asyncio.create_task(self._deliver_to_listener(listener, event))
            tasks.append(task)

        # Wait for all deliveries to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Track delivery time
        delivery_time = (time.time() - start_time) * 1000  # ms
        self._delivery_times.append(delivery_time)

        # Trim delivery time samples
        if len(self._delivery_times) > self._max_delivery_time_samples:
            self._delivery_times = self._delivery_times[-self._max_delivery_time_samples :]

    async def _deliver_to_listener(
        self, listener: Callable[[SecurityEvent], Any], event: SecurityEvent
    ) -> None:
        """
        Deliver event to a single listener with error handling.

        Args:
            listener: Listener callback
            event: Event to deliver
        """
        listener_id = self._listener_info.get(listener, {}).get("id", "unknown")

        try:
            start_time = time.time()

            # Update listener stats
            await self._listener_repo.update_listener_stats(listener_id, {"events_received": 1})

            # Call listener
            result = listener(event)
            if asyncio.iscoroutine(result):
                await result

            # Update success stats
            processing_time = (time.time() - start_time) * 1000  # ms
            await self._listener_repo.update_listener_stats(
                listener_id,
                {
                    "events_processed": 1,
                    "processing_time_ms": processing_time,
                    "last_event_at": datetime.now(UTC).isoformat(),
                },
            )

            self._stats["events_delivered"] += 1

        except Exception as e:
            # Update error stats
            await self._listener_repo.update_listener_stats(listener_id, {"errors": 1})

            self._stats["delivery_failures"] += 1

            logger.error(
                f"Failed to deliver security event to listener {listener_id}: {e}", exc_info=True
            )

    async def subscribe(
        self, listener: Callable[[SecurityEvent], Any], name: str | None = None
    ) -> str:
        """
        Subscribe to security events.

        Args:
            listener: Callback function for events
            name: Optional listener name

        Returns:
            Listener ID
        """
        # Generate listener ID
        listener_id = f"listener_{id(listener)}_{int(time.time() * 1000)}"

        # Store listener info
        listener_info = {
            "id": listener_id,
            "name": name or f"SecurityListener_{len(self._listeners) + 1}",
            "component": getattr(listener, "__module__", "unknown"),
        }

        # Register in repository
        await self._listener_repo.register_listener(listener_id, listener_info)

        # Add to active listeners
        self._listeners.append(listener)
        self._listener_info[listener] = listener_info

        # Update stats
        self._stats["listeners_registered"] = len(self._listeners)

        logger.info(
            f"Registered security event listener: {listener_info['name']} (id={listener_id})"
        )

        return listener_id

    async def unsubscribe(self, listener_id: str) -> bool:
        """
        Unsubscribe from security events.

        Args:
            listener_id: ID of listener to remove

        Returns:
            True if unsubscribed successfully
        """
        # Find listener by ID
        listener_to_remove = None
        for listener, info in self._listener_info.items():
            if info.get("id") == listener_id:
                listener_to_remove = listener
                break

        if listener_to_remove:
            # Remove from active listeners
            self._listeners.remove(listener_to_remove)
            del self._listener_info[listener_to_remove]

            # Update repository
            await self._listener_repo.unregister_listener(listener_id)

            # Update stats
            self._stats["listeners_registered"] = len(self._listeners)

            logger.info(f"Unregistered security event listener: {listener_id}")
            return True

        return False

    async def get_statistics(self) -> SecurityEventStats:
        """
        Get comprehensive event statistics.

        Returns:
            Security event statistics
        """
        # Get repository statistics
        event_stats = await self._event_repo.get_event_statistics(hours=24)
        listener_health = await self._listener_repo.get_listener_health()

        # Calculate delivery metrics
        avg_delivery_time = (
            sum(self._delivery_times) / len(self._delivery_times) if self._delivery_times else 0.0
        )

        uptime = time.time() - self._stats["start_time"]

        return SecurityEventStats(
            events_published=self._stats["events_published"],
            events_delivered=self._stats["events_delivered"],
            delivery_failures=self._stats["delivery_failures"],
            listeners_registered=self._stats["listeners_registered"],
            event_types_count=len(event_stats.get("events_by_type", {})),
            uptime_seconds=uptime,
            average_delivery_time_ms=avg_delivery_time,
            events_per_minute=self._stats["events_published"] / (uptime / 60) if uptime > 0 else 0,
            # Additional stats from repositories
            total_events_24h=event_stats.get("total_events", 0),
            events_by_type=event_stats.get("events_by_type", {}),
            events_by_component=event_stats.get("events_by_component", {}),
            listener_health=listener_health,
        )

    async def get_recent_events(self, limit: int = 100) -> list[SecurityEvent]:
        """
        Get recent security events.

        Args:
            limit: Maximum number of events

        Returns:
            List of recent events
        """
        return await self._event_repo.get_recent_events(limit)

    async def cleanup_old_events(self, retention_days: int = 30) -> int:
        """
        Clean up old events.

        Args:
            retention_days: Days to retain events

        Returns:
            Number of events cleaned up
        """
        return await self._event_repo.cleanup_old_events(retention_days)
