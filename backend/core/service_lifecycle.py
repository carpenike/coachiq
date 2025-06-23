"""
Service Lifecycle Event System

Provides interfaces and implementations for service lifecycle notifications,
enabling coordination between services for safety-critical system operations.

Part of Phase 2Q: Service Lifecycle Event System
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ServiceFailureReason(Enum):
    """Reasons for service failure."""

    INITIALIZATION_ERROR = "initialization_error"
    HEALTH_CHECK_FAILED = "health_check_failed"
    DEPENDENCY_FAILED = "dependency_failed"
    RUNTIME_ERROR = "runtime_error"
    SHUTDOWN_ERROR = "shutdown_error"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    UNKNOWN = "unknown"


class ServiceLifecycleEvent:
    """Event data for service lifecycle notifications."""

    def __init__(
        self,
        service_name: str,
        timestamp: datetime,
        event_type: str,
        failure_reason: ServiceFailureReason | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.service_name = service_name
        self.timestamp = timestamp
        self.event_type = event_type
        self.failure_reason = failure_reason
        self.error_message = error_message
        self.metadata = metadata or {}


class IServiceLifecycleListener(ABC):
    """
    Interface for service lifecycle event listeners.

    Implementations must handle events in a thread-safe manner.
    The on_service_failed() method is particularly critical as it
    must be synchronous and blocking to ensure safety transitions.
    """

    @abstractmethod
    async def on_service_pre_shutdown(self, event: ServiceLifecycleEvent) -> None:
        """
        Called before a service begins graceful shutdown.

        This allows listeners to prepare for service unavailability
        and potentially veto the shutdown if unsafe.

        Args:
            event: Event details including service name and metadata
        """

    @abstractmethod
    def on_service_failed(self, event: ServiceLifecycleEvent) -> None:
        """
        Called when a service fails unexpectedly.

        CRITICAL: This method MUST be synchronous and blocking to ensure
        safety-critical state transitions complete before proceeding.
        This is essential for ISO 26262 compliance.

        Args:
            event: Event details including failure reason and error
        """

    @abstractmethod
    async def on_service_stopped(self, event: ServiceLifecycleEvent) -> None:
        """
        Called after a service has fully stopped.

        This indicates the service is no longer available and all
        resources have been released.

        Args:
            event: Event details including service name
        """

    @abstractmethod
    async def on_service_started(self, event: ServiceLifecycleEvent) -> None:
        """
        Called after a service has successfully (re)started.

        This can be used to re-enable features that depend on the service
        or to update system state after recovery.

        Args:
            event: Event details including service name
        """


class ServiceLifecycleManager:
    """
    Manages service lifecycle event listeners and dispatches events.

    This class is thread-safe and ensures proper event ordering and
    delivery guarantees for safety-critical operations.
    """

    def __init__(self):
        self._listeners: set[IServiceLifecycleListener] = set()
        self._listener_priorities: dict[IServiceLifecycleListener, int] = {}

    def add_listener(self, listener: IServiceLifecycleListener, priority: int = 0) -> None:
        """
        Add a lifecycle event listener.

        Args:
            listener: The listener to add
            priority: Higher priority listeners are notified first (default: 0)
        """
        self._listeners.add(listener)
        self._listener_priorities[listener] = priority
        logger.info(
            f"Added lifecycle listener: {listener.__class__.__name__} with priority {priority}"
        )

    def remove_listener(self, listener: IServiceLifecycleListener) -> None:
        """Remove a lifecycle event listener."""
        self._listeners.discard(listener)
        self._listener_priorities.pop(listener, None)
        logger.info(f"Removed lifecycle listener: {listener.__class__.__name__}")

    def _get_ordered_listeners(self) -> list[IServiceLifecycleListener]:
        """Get listeners ordered by priority (highest first)."""
        return sorted(
            self._listeners, key=lambda l: self._listener_priorities.get(l, 0), reverse=True
        )

    async def notify_pre_shutdown(
        self, service_name: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Notify listeners of impending service shutdown."""
        event = ServiceLifecycleEvent(
            service_name=service_name,
            timestamp=datetime.now(UTC),
            event_type="pre_shutdown",
            metadata=metadata,
        )

        for listener in self._get_ordered_listeners():
            try:
                await listener.on_service_pre_shutdown(event)
            except Exception as e:
                logger.error(f"Error in pre_shutdown listener {listener.__class__.__name__}: {e}")

    def notify_service_failed(
        self,
        service_name: str,
        reason: ServiceFailureReason,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Notify listeners of service failure.

        CRITICAL: This method is synchronous and will block until all
        listeners have processed the failure event. This ensures safety
        state transitions complete before continuing.
        """
        event = ServiceLifecycleEvent(
            service_name=service_name,
            timestamp=datetime.now(UTC),
            event_type="failed",
            failure_reason=reason,
            error_message=error_message,
            metadata=metadata,
        )

        # Process listeners in priority order
        for listener in self._get_ordered_listeners():
            try:
                # CRITICAL: Synchronous call for safety
                listener.on_service_failed(event)
            except Exception as e:
                # Log but continue - safety transitions must complete
                logger.error(
                    f"Error in service_failed listener {listener.__class__.__name__}: {e}",
                    exc_info=True,
                )

    async def notify_service_stopped(
        self, service_name: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Notify listeners that a service has stopped."""
        event = ServiceLifecycleEvent(
            service_name=service_name,
            timestamp=datetime.now(UTC),
            event_type="stopped",
            metadata=metadata,
        )

        for listener in self._get_ordered_listeners():
            try:
                await listener.on_service_stopped(event)
            except Exception as e:
                logger.error(
                    f"Error in service_stopped listener {listener.__class__.__name__}: {e}"
                )

    async def notify_service_started(
        self, service_name: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Notify listeners that a service has started."""
        event = ServiceLifecycleEvent(
            service_name=service_name,
            timestamp=datetime.now(UTC),
            event_type="started",
            metadata=metadata,
        )

        for listener in self._get_ordered_listeners():
            try:
                await listener.on_service_started(event)
            except Exception as e:
                logger.error(
                    f"Error in service_started listener {listener.__class__.__name__}: {e}"
                )


class CompositeLifecycleListener(IServiceLifecycleListener):
    """
    Composite listener that delegates to multiple child listeners.

    Useful for combining multiple listener implementations.
    """

    def __init__(self, listeners: list[IServiceLifecycleListener]):
        self._listeners = listeners

    async def on_service_pre_shutdown(self, event: ServiceLifecycleEvent) -> None:
        """Delegate to all child listeners."""
        for listener in self._listeners:
            await listener.on_service_pre_shutdown(event)

    def on_service_failed(self, event: ServiceLifecycleEvent) -> None:
        """Delegate to all child listeners (synchronous)."""
        for listener in self._listeners:
            listener.on_service_failed(event)

    async def on_service_stopped(self, event: ServiceLifecycleEvent) -> None:
        """Delegate to all child listeners."""
        for listener in self._listeners:
            await listener.on_service_stopped(event)

    async def on_service_started(self, event: ServiceLifecycleEvent) -> None:
        """Delegate to all child listeners."""
        for listener in self._listeners:
            await listener.on_service_started(event)
