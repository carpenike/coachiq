"""Base Repository Pattern

Provides a base class for all repositories with common functionality
including performance monitoring integration.
"""

import asyncio
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MonitoredRepository:
    """Base repository class with performance monitoring integration."""

    def __init__(self, database_manager: Any, performance_monitor: Any):
        """Initialize the base repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        self._db_manager = database_manager
        self._monitor = performance_monitor
        self._repository_name = self.__class__.__name__

    @staticmethod
    def _monitored_operation(operation_name: str) -> Callable:
        """Decorator for monitoring repository operations.

        Args:
            operation_name: Name of the operation to monitor

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def async_wrapper(self: "MonitoredRepository", *args: Any, **kwargs: Any) -> T:
                """Async wrapper for monitoring."""
                # Use performance monitor if available
                if hasattr(self, "_monitor") and self._monitor:
                    monitored_func = self._monitor.monitor_repository_operation(
                        self._repository_name, operation_name
                    )(func)
                    return await monitored_func(self, *args, **kwargs)
                # No monitoring - just execute
                return await func(self, *args, **kwargs)

            @wraps(func)
            def sync_wrapper(self: "MonitoredRepository", *args: Any, **kwargs: Any) -> T:
                """Sync wrapper for monitoring."""
                # Use performance monitor if available
                if hasattr(self, "_monitor") and self._monitor:
                    monitored_func = self._monitor.monitor_repository_operation(
                        self._repository_name, operation_name
                    )(func)
                    return monitored_func(self, *args, **kwargs)
                # No monitoring - just execute
                return func(self, *args, **kwargs)

            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return cast("Callable[..., T]", async_wrapper)
            return cast("Callable[..., T]", sync_wrapper)

        return decorator

    async def initialize(self) -> None:
        """Initialize the repository.

        Override this method in subclasses if initialization is needed.
        """

    async def cleanup(self) -> None:
        """Clean up repository resources.

        Override this method in subclasses if cleanup is needed.
        """
