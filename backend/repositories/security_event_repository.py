"""Security Event Repository

Handles data access for security event management including:
- Security event storage and retrieval
- Event filtering and querying
- Event statistics tracking
- Retention management
"""

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class SecurityEventRepository(MonitoredRepository):
    """Repository for security event data management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage (would be database table in production)
        self._events: list[Any] = []  # List[SecurityEvent]
        self._max_events = 10000

        # Indexes for efficient querying
        self._events_by_type: dict[str, list[int]] = defaultdict(list)  # event_type -> indices
        self._events_by_component: dict[str, list[int]] = defaultdict(list)  # component -> indices

    @MonitoredRepository._monitored_operation("store_event")
    async def store_event(self, event: Any) -> str:  # event: SecurityEvent
        """Store a security event.

        Args:
            event: Security event to store

        Returns:
            Event ID
        """
        # Add to main storage
        index = len(self._events)
        self._events.append(event)

        # Update indexes
        self._events_by_type[event.event_type].append(index)
        self._events_by_component[event.component].append(index)

        # Trim if necessary (in production, would archive old events)
        if len(self._events) > self._max_events:
            self._trim_old_events()

        logger.debug(f"Stored security event: {event.event_type} from {event.component}")
        return event.event_id

    @MonitoredRepository._monitored_operation("get_recent_events")
    async def get_recent_events(self, limit: int = 100) -> list[Any]:  # List[SecurityEvent]
        """Get most recent security events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent events, newest first
        """
        # Return events in reverse order (newest first)
        start_idx = max(0, len(self._events) - limit)
        return list(reversed(self._events[start_idx:]))

    @MonitoredRepository._monitored_operation("get_events_by_type")
    async def get_events_by_type(
        self, event_type: str, hours: int = 24
    ) -> list[Any]:  # List[SecurityEvent]
        """Get events by type within time window.

        Args:
            event_type: Type of events to retrieve
            hours: Time window in hours

        Returns:
            List of matching events
        """
        cutoff = time.time() - (hours * 3600)
        events = []

        # Use index for efficient lookup
        for idx in reversed(self._events_by_type.get(event_type, [])):
            event = self._events[idx]
            if hasattr(event, "timestamp") and event.timestamp < cutoff:
                break
            events.append(event)

        return events

    @MonitoredRepository._monitored_operation("get_events_by_component")
    async def get_events_by_component(
        self, component: str, hours: int = 24
    ) -> list[Any]:  # List[SecurityEvent]
        """Get events by component within time window.

        Args:
            component: Component that generated events
            hours: Time window in hours

        Returns:
            List of matching events
        """
        cutoff = time.time() - (hours * 3600)
        events = []

        # Use index for efficient lookup
        for idx in reversed(self._events_by_component.get(component, [])):
            event = self._events[idx]
            if hasattr(event, "timestamp") and event.timestamp < cutoff:
                break
            events.append(event)

        return events

    @MonitoredRepository._monitored_operation("cleanup_old_events")
    async def cleanup_old_events(self, retention_days: int = 30) -> int:
        """Clean up events older than retention period.

        Args:
            retention_days: Days to retain events

        Returns:
            Number of events cleaned up
        """
        cutoff = time.time() - (retention_days * 24 * 3600)
        original_count = len(self._events)

        # Filter events (in production, would archive before deletion)
        self._events = [
            event
            for event in self._events
            if hasattr(event, "timestamp") and event.timestamp > cutoff
        ]

        # Rebuild indexes
        self._rebuild_indexes()

        cleaned = original_count - len(self._events)
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old security events")

        return cleaned

    @MonitoredRepository._monitored_operation("get_event_statistics")
    async def get_event_statistics(self, hours: int = 24) -> dict[str, Any]:
        """Get event statistics for time period.

        Args:
            hours: Time window for statistics

        Returns:
            Statistics dictionary
        """
        cutoff = time.time() - (hours * 3600)

        # Count events by type and component
        type_counts = defaultdict(int)
        component_counts = defaultdict(int)
        total_events = 0

        for event in self._events:
            if hasattr(event, "timestamp") and event.timestamp > cutoff:
                total_events += 1
                type_counts[event.event_type] += 1
                component_counts[event.component] += 1

        return {
            "total_events": total_events,
            "events_by_type": dict(type_counts),
            "events_by_component": dict(component_counts),
            "time_window_hours": hours,
            "oldest_event_age_hours": self._get_oldest_event_age() / 3600 if self._events else 0,
        }

    def _trim_old_events(self) -> None:
        """Trim oldest events when at capacity."""
        # Keep most recent events
        trim_count = len(self._events) - self._max_events + 1000  # Keep some buffer

        if trim_count > 0:
            self._events = self._events[trim_count:]
            self._rebuild_indexes()
            logger.info(f"Trimmed {trim_count} old events to maintain capacity")

    def _rebuild_indexes(self) -> None:
        """Rebuild indexes after event list modification."""
        self._events_by_type.clear()
        self._events_by_component.clear()

        for idx, event in enumerate(self._events):
            self._events_by_type[event.event_type].append(idx)
            self._events_by_component[event.component].append(idx)

    def _get_oldest_event_age(self) -> float:
        """Get age of oldest event in seconds."""
        if not self._events:
            return 0.0

        oldest = self._events[0]
        if hasattr(oldest, "timestamp"):
            return time.time() - oldest.timestamp
        return 0.0


class SecurityListenerRepository(MonitoredRepository):
    """Repository for security event listener management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage
        self._listeners: dict[str, dict[str, Any]] = {}  # listener_id -> metadata
        self._listener_stats: dict[str, dict[str, Any]] = {}  # listener_id -> stats

    @MonitoredRepository._monitored_operation("register_listener")
    async def register_listener(self, listener_id: str, metadata: dict[str, Any]) -> bool:
        """Register a security event listener.

        Args:
            listener_id: Unique listener identifier
            metadata: Listener metadata (name, component, etc.)

        Returns:
            True if registered successfully
        """
        self._listeners[listener_id] = {
            **metadata,
            "registered_at": datetime.now(UTC).isoformat(),
            "active": True,
        }

        # Initialize stats
        self._listener_stats[listener_id] = {
            "events_received": 0,
            "events_processed": 0,
            "errors": 0,
            "last_event_at": None,
            "average_processing_time_ms": 0.0,
        }

        logger.info(f"Registered security listener: {listener_id}")
        return True

    @MonitoredRepository._monitored_operation("unregister_listener")
    async def unregister_listener(self, listener_id: str) -> bool:
        """Unregister a security event listener.

        Args:
            listener_id: Listener to unregister

        Returns:
            True if unregistered successfully
        """
        if listener_id in self._listeners:
            self._listeners[listener_id]["active"] = False
            self._listeners[listener_id]["unregistered_at"] = datetime.now(UTC).isoformat()
            logger.info(f"Unregistered security listener: {listener_id}")
            return True
        return False

    @MonitoredRepository._monitored_operation("get_active_listeners")
    async def get_active_listeners(self) -> list[dict[str, Any]]:
        """Get all active listeners.

        Returns:
            List of active listener info
        """
        active_listeners = []

        for listener_id, metadata in self._listeners.items():
            if metadata.get("active", False):
                listener_info = {
                    "listener_id": listener_id,
                    **metadata,
                    "stats": self._listener_stats.get(listener_id, {}),
                }
                active_listeners.append(listener_info)

        return active_listeners

    @MonitoredRepository._monitored_operation("update_listener_stats")
    async def update_listener_stats(self, listener_id: str, stats: dict[str, Any]) -> bool:
        """Update listener statistics.

        Args:
            listener_id: Listener to update
            stats: Statistics updates

        Returns:
            True if updated successfully
        """
        if listener_id not in self._listener_stats:
            self._listener_stats[listener_id] = {
                "events_received": 0,
                "events_processed": 0,
                "errors": 0,
                "last_event_at": None,
                "average_processing_time_ms": 0.0,
            }

        # Update stats
        current_stats = self._listener_stats[listener_id]

        if "events_received" in stats:
            current_stats["events_received"] += stats["events_received"]

        if "events_processed" in stats:
            current_stats["events_processed"] += stats["events_processed"]

        if "errors" in stats:
            current_stats["errors"] += stats["errors"]

        if "last_event_at" in stats:
            current_stats["last_event_at"] = stats["last_event_at"]

        if "processing_time_ms" in stats and stats.get("events_processed", 0) > 0:
            # Update rolling average
            total_events = current_stats["events_processed"]
            current_avg = current_stats["average_processing_time_ms"]
            new_time = stats["processing_time_ms"]

            if total_events > 0:
                current_stats["average_processing_time_ms"] = (
                    current_avg * (total_events - 1) + new_time
                ) / total_events
            else:
                current_stats["average_processing_time_ms"] = new_time

        return True

    @MonitoredRepository._monitored_operation("get_listener_health")
    async def get_listener_health(self) -> dict[str, Any]:
        """Get health status of all listeners.

        Returns:
            Health status summary
        """
        total_listeners = len(self._listeners)
        active_listeners = sum(1 for l in self._listeners.values() if l.get("active", False))

        # Calculate error rates
        listener_errors = {}
        for listener_id, stats in self._listener_stats.items():
            if stats["events_received"] > 0:
                error_rate = stats["errors"] / stats["events_received"]
                if error_rate > 0.01:  # More than 1% errors
                    listener_errors[listener_id] = error_rate

        # Find slow listeners
        slow_listeners = {}
        for listener_id, stats in self._listener_stats.items():
            avg_time = stats.get("average_processing_time_ms", 0)
            if avg_time > 100:  # More than 100ms average
                slow_listeners[listener_id] = avg_time

        return {
            "total_listeners": total_listeners,
            "active_listeners": active_listeners,
            "listeners_with_errors": listener_errors,
            "slow_listeners": slow_listeners,
            "health_status": "healthy"
            if not listener_errors and not slow_listeners
            else "degraded",
        }
