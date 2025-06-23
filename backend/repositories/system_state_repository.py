"""
System State Repository

Manages system-wide state and configuration that doesn't belong to specific domains.
Part of Phase 4A: App State Cleanup

This repository handles:
- Controller source address configuration
- System-wide broadcast functions
- Global system state not covered by other repositories
"""

import logging
from collections.abc import Callable
from typing import Any

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class SystemStateRepository:
    """
    Repository for system-wide state and configuration.

    This class encapsulates system-level state that doesn't belong to
    specific domain repositories but still needs to be accessible across
    the application.
    """

    def __init__(self):
        """Initialize the system state repository."""
        self._settings = get_settings()
        self._broadcast_functions: dict[str, Callable] = {}
        logger.info("SystemStateRepository initialized")

    def get_controller_source_addr(self) -> str:
        """
        Get the controller source address from configuration.

        Returns:
            Controller source address in hex format (e.g., "0xF9")
        """
        return self._settings.controller_source_addr

    def set_broadcast_function(self, name: str, func: Callable) -> None:
        """
        Register a broadcast function for system-wide use.

        Args:
            name: Name identifier for the broadcast function
            func: Callable function to broadcast data
        """
        self._broadcast_functions[name] = func
        logger.debug("Broadcast function '%s' registered", name)

    def get_broadcast_function(self, name: str) -> Callable | None:
        """
        Get a registered broadcast function.

        Args:
            name: Name identifier for the broadcast function

        Returns:
            The broadcast function or None if not found
        """
        return self._broadcast_functions.get(name)

    def remove_broadcast_function(self, name: str) -> None:
        """
        Remove a registered broadcast function.

        Args:
            name: Name identifier for the broadcast function
        """
        if name in self._broadcast_functions:
            del self._broadcast_functions[name]
            logger.debug("Broadcast function '%s' removed", name)

    def get_all_broadcast_functions(self) -> dict[str, Callable]:
        """
        Get all registered broadcast functions.

        Returns:
            Dictionary of broadcast function names to callables
        """
        return self._broadcast_functions.copy()

    def clear_broadcast_functions(self) -> None:
        """Clear all registered broadcast functions."""
        self._broadcast_functions.clear()
        logger.debug("All broadcast functions cleared")

    def get_health_status(self) -> dict[str, Any]:
        """
        Get repository health status.

        Returns:
            Health status information
        """
        return {
            "healthy": True,
            "controller_source_addr": self.get_controller_source_addr(),
            "broadcast_functions_registered": len(self._broadcast_functions),
            "settings_loaded": self._settings is not None,
        }

    def get_system_info(self) -> dict[str, Any]:
        """
        Get system information summary.

        Returns:
            System information dictionary
        """
        return {
            "controller_source_addr": self.get_controller_source_addr(),
            "environment": self._settings.environment,
            "app_name": self._settings.app_name,
            "broadcast_functions": list(self._broadcast_functions.keys()),
        }
