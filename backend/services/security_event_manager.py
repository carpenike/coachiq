"""
Security Event Manager

Lightweight Observer pattern implementation for decoupled security event handling.
Integrates with FeatureManager and provides reliable event distribution to consumers.
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List

from backend.models.security_events import SecurityEvent, SecurityEventStats
from backend.services.feature_base import Feature

logger = logging.getLogger(__name__)


class SecurityEventManager(Feature):
    """
    Manages security event distribution using Observer pattern.

    This service acts as a central hub for security events, allowing
    producers to publish events and consumers to register for notifications.
    Uses asyncio.create_task for non-blocking, failure-isolated delivery.
    """

    def __init__(
        self,
        name: str = "security_event_manager",
        enabled: bool = True,
        core: bool = True,
        **kwargs
    ):
        """
        Initialize the security event manager.

        Args:
            name: Feature name
            enabled: Whether feature is enabled
            core: Whether this is a core feature
            **kwargs: Additional feature configuration
        """
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            **kwargs
        )

        # Observer pattern implementation
        self._listeners: List[Callable[[SecurityEvent], Any]] = []
        self._listener_names: Dict[Callable, str] = {}

        # Statistics tracking
        self._stats = {
            "events_published": 0,
            "events_delivered": 0,
            "delivery_failures": 0,
            "listeners_registered": 0,
            "start_time": time.time()
        }

        # Event rate tracking for monitoring
        self._event_counts: Dict[str, int] = defaultdict(int)
        self._recent_events: List[SecurityEvent] = []
        self._max_recent_events = 100

        # Performance metrics
        self._delivery_times: List[float] = []
        self._max_delivery_time_samples = 1000

        logger.info("SecurityEventManager initialized")

    async def startup(self) -> None:
        """Start the security event manager."""
        logger.info("SecurityEventManager starting up")
        self._stats["start_time"] = time.time()

    async def shutdown(self) -> None:
        """Shutdown the security event manager."""
        logger.info("SecurityEventManager shutting down")

        # Log final statistics
        uptime = time.time() - self._stats["start_time"]
        logger.info(
            f"SecurityEventManager final stats: "
            f"uptime={uptime:.1f}s, "
            f"events_published={self._stats['events_published']}, "
            f"events_delivered={self._stats['events_delivered']}, "
            f"delivery_failures={self._stats['delivery_failures']}, "
            f"listeners={self._stats['listeners_registered']}"
        )

    def register_listener(self, listener: Callable[[SecurityEvent], Any], name: str = None) -> None:
        """
        Register a consumer to receive security events.

        Args:
            listener: Async callable that accepts SecurityEvent
            name: Optional name for the listener (for logging/debugging)
        """
        if listener in self._listeners:
            logger.warning(f"Listener {name or 'unnamed'} already registered, skipping")
            return

        self._listeners.append(listener)
        self._listener_names[listener] = name or f"listener_{len(self._listeners)}"
        self._stats["listeners_registered"] += 1

        logger.info(f"Registered security event listener: {self._listener_names[listener]}")

    def unregister_listener(self, listener: Callable[[SecurityEvent], Any]) -> bool:
        """
        Unregister a consumer from receiving security events.

        Args:
            listener: The listener to remove

        Returns:
            True if listener was found and removed, False otherwise
        """
        if listener in self._listeners:
            name = self._listener_names.get(listener, "unknown")
            self._listeners.remove(listener)
            self._listener_names.pop(listener, None)
            logger.info(f"Unregistered security event listener: {name}")
            return True
        return False

    async def publish(self, event: SecurityEvent) -> None:
        """
        Publish a security event to all registered listeners.

        Events are delivered asynchronously and non-blocking. Failure in
        one listener does not affect delivery to other listeners.

        Args:
            event: The security event to publish
        """
        if not self.enabled:
            return

        start_time = time.time()

        # Update statistics
        self._stats["events_published"] += 1
        self._event_counts[event.event_type] += 1

        # Add to recent events (for dashboard)
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent_events:
            self._recent_events.pop(0)

        # Deliver to all listeners concurrently
        delivery_tasks = []
        for listener in self._listeners:
            task = asyncio.create_task(
                self._safe_deliver_event(listener, event),
                name=f"deliver_to_{self._listener_names.get(listener, 'unknown')}"
            )
            delivery_tasks.append(task)

        # Don't wait for delivery completion - fire and forget
        # This ensures publishing is non-blocking

        # Track delivery time for performance monitoring
        delivery_time = time.time() - start_time
        self._delivery_times.append(delivery_time)
        if len(self._delivery_times) > self._max_delivery_time_samples:
            self._delivery_times.pop(0)

        logger.debug(
            f"Published security event: {event.event_type} "
            f"(severity={event.severity}, component={event.source_component})"
        )

    async def _safe_deliver_event(self, listener: Callable, event: SecurityEvent) -> None:
        """
        Safely deliver an event to a listener with error isolation.

        Args:
            listener: The listener function to call
            event: The event to deliver
        """
        listener_name = self._listener_names.get(listener, "unknown")

        try:
            # Handle both sync and async listeners
            if asyncio.iscoroutinefunction(listener):
                await listener(event)
            else:
                listener(event)

            self._stats["events_delivered"] += 1

        except Exception as e:
            self._stats["delivery_failures"] += 1
            logger.error(
                f"Error delivering security event to listener '{listener_name}': {e}",
                exc_info=True
            )

            # For critical listeners, we might want to implement retry logic
            # For now, we just log and continue to prevent cascading failures

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get current statistics for monitoring and debugging.

        Returns:
            Dictionary of statistics and performance metrics
        """
        uptime = time.time() - self._stats["start_time"]

        # Calculate performance metrics
        avg_delivery_time = 0.0
        max_delivery_time = 0.0
        if self._delivery_times:
            avg_delivery_time = sum(self._delivery_times) / len(self._delivery_times)
            max_delivery_time = max(self._delivery_times)

        return {
            "uptime_seconds": uptime,
            "events_published": self._stats["events_published"],
            "events_delivered": self._stats["events_delivered"],
            "delivery_failures": self._stats["delivery_failures"],
            "listeners_registered": len(self._listeners),
            "event_types_seen": len(self._event_counts),
            "events_by_type": dict(self._event_counts),
            "recent_events_count": len(self._recent_events),
            "performance": {
                "avg_delivery_time_ms": avg_delivery_time * 1000,
                "max_delivery_time_ms": max_delivery_time * 1000,
                "delivery_success_rate": (
                    self._stats["events_delivered"] / max(1, self._stats["events_published"])
                )
            },
            "listeners": [
                self._listener_names.get(listener, "unknown")
                for listener in self._listeners
            ]
        }

    def get_recent_events(self, limit: int = 50) -> List[SecurityEvent]:
        """
        Get recently published events for dashboard display.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent SecurityEvent objects
        """
        return self._recent_events[-limit:] if self._recent_events else []

    def get_event_stats(self) -> SecurityEventStats:
        """
        Get aggregated event statistics for dashboard.

        Returns:
            SecurityEventStats with current statistics
        """
        current_time = time.time()
        hour_ago = current_time - 3600
        day_ago = current_time - 86400

        # Count recent events
        events_last_hour = len([
            e for e in self._recent_events
            if e.timestamp >= hour_ago
        ])

        events_last_24h = len([
            e for e in self._recent_events
            if e.timestamp >= day_ago
        ])

        # Count by severity
        events_by_severity = defaultdict(int)
        for event in self._recent_events:
            events_by_severity[event.severity] += 1

        # Count by component
        events_by_component = defaultdict(int)
        for event in self._recent_events:
            events_by_component[event.source_component] += 1

        return SecurityEventStats(
            total_events=self._stats["events_published"],
            events_by_severity=dict(events_by_severity),
            events_by_type=dict(self._event_counts),
            events_by_component=dict(events_by_component),
            events_last_hour=events_last_hour,
            events_last_24h=events_last_24h,
            # These would be populated by other services
            active_incidents=0,
            critical_alerts=len([
                e for e in self._recent_events
                if e.severity == "critical"
            ])
        )

    @property
    def health(self) -> str:
        """Return the health status of the feature."""
        if not self.enabled:
            return "healthy"  # Disabled is considered healthy

        # Check delivery success rate
        stats = self.get_statistics()
        success_rate = stats["performance"]["delivery_success_rate"]

        if success_rate < 0.95:  # Less than 95% delivery success
            return "degraded"
        elif success_rate < 0.90:  # Less than 90% delivery success
            return "failed"
        else:
            return "healthy"

    @property
    def health_details(self) -> Dict[str, Any]:
        """Return detailed health information for diagnostics."""
        if not self.enabled:
            return {"status": "disabled", "reason": "Feature not enabled"}

        stats = self.get_statistics()
        success_rate = stats["performance"]["delivery_success_rate"]

        return {
            "status": self.health,
            "uptime_seconds": stats["uptime_seconds"],
            "events_published": stats["events_published"],
            "delivery_success_rate": success_rate,
            "active_listeners": len(self._listeners),
            "recent_events": len(self._recent_events)
        }


# Global instance management
_security_event_manager: SecurityEventManager | None = None


def get_security_event_manager() -> SecurityEventManager:
    """
    Get the security event manager instance.

    This function is deprecated. Use dependency injection instead:
    - For API endpoints: Use Depends(get_security_event_manager) from backend.core.dependencies
    - For WebSocket/Background services: Use ServiceProxy from backend.core.service_patterns

    Returns:
        The SecurityEventManager instance

    Raises:
        RuntimeError: If manager has not been initialized
    """
    # Try to get from app.state first
    try:
        from backend.main import app
        if hasattr(app.state, 'security_event_manager') and app.state.security_event_manager is not None:
            return app.state.security_event_manager
    except (ImportError, AttributeError, RuntimeError):
        # App not initialized yet
        pass

    # Try ServiceRegistry if available
    try:
        if hasattr(app.state, 'service_registry') and app.state.service_registry is not None:
            service = app.state.service_registry.get_service('security_event_manager')
            if service:
                return service
    except:
        pass

    # Fall back to global instance for backward compatibility
    global _security_event_manager
    if _security_event_manager is None:
        raise RuntimeError(
            "SecurityEventManager has not been initialized. "
            "Use dependency injection or ensure it's registered with ServiceRegistry."
        )
    return _security_event_manager
