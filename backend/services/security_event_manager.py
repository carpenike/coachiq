"""
Security Event Manager

Facade over SecurityEventService for backward compatibility.
"""

import logging
from collections.abc import Callable
from typing import Any, Optional

from backend.models.security_events import SecurityEvent, SecurityEventStats

logger = logging.getLogger(__name__)


class SecurityEventManager:
    """
    Security event manager facade.

    This is a clean facade that delegates to SecurityEventService.
    """

    def __init__(
        self,
        security_event_service: Any,
        **kwargs,  # Ignore all legacy parameters
    ):
        """Initialize with the modern SecurityEventService."""
        self._service = security_event_service
        logger.info("SecurityEventManager initialized as facade over SecurityEventService")

    async def startup(self) -> None:
        """Start the security event manager (no-op for facade)."""
        logger.info("SecurityEventManager startup (delegating to service)")

    async def shutdown(self) -> None:
        """Shutdown the security event manager (no-op for facade)."""
        logger.info("SecurityEventManager shutdown (delegating to service)")

    @property
    def health(self) -> str:
        """Get health status."""
        return "healthy"

    # Event publishing methods - direct delegation

    async def publish_event(self, event: SecurityEvent) -> None:
        """Publish a security event."""
        await self._service.publish_event(event)

    async def publish(self, event: SecurityEvent) -> None:
        """Publish a security event (alternative method name for compatibility)."""
        await self._service.publish_event(event)

    # Listener management - direct delegation

    async def subscribe(
        self, listener: Callable[[SecurityEvent], Any], name: str | None = None
    ) -> None:
        """Subscribe to security events."""
        await self._service.subscribe(listener, name)

    async def unsubscribe(self, listener: Callable[[SecurityEvent], Any]) -> None:
        """Unsubscribe from security events."""
        await self._service.unsubscribe(listener)

    # Statistics and monitoring

    async def get_statistics(self) -> SecurityEventStats:
        """Get event statistics."""
        return await self._service.get_statistics()

    async def get_listener_count(self) -> int:
        """Get number of registered listeners."""
        return await self._service.get_listener_count()

    async def get_recent_events(self, limit: int = 10) -> list[SecurityEvent]:
        """Get recent events."""
        return await self._service.get_recent_events(limit)

    async def clear_statistics(self) -> None:
        """Clear statistics."""
        await self._service.clear_statistics()
