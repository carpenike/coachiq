"""
CAN Tracking Repository

Manages real-time CAN message tracking with performance optimization.
Part of Phase 2R: AppState Repository Migration

This repository handles:
- CAN sniffer logs
- Pending commands tracking
- Command/response grouping
- Source address tracking
- Network map updates

Performance considerations:
- Lock-free data structures where possible
- Bounded collections to prevent memory growth
- Efficient lookups for real-time processing
"""

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class CANTrackingRepository:
    """
    Repository for real-time CAN message tracking.

    This class encapsulates all CAN message tracking operations with
    performance optimizations for high-frequency updates.
    """

    # Constants for bounded collections
    MAX_SNIFFER_LOG_SIZE = 1000
    MAX_GROUPED_ENTRIES = 500
    MAX_PENDING_COMMANDS = 100
    PENDING_COMMAND_TIMEOUT = 2.0  # seconds

    def __init__(self):
        """Initialize the CAN tracking repository."""
        # Use deque for efficient append/pop operations
        self._can_command_sniffer_log: deque = deque(maxlen=self.MAX_SNIFFER_LOG_SIZE)
        self._can_sniffer_grouped: deque = deque(maxlen=self.MAX_GROUPED_ENTRIES)
        self._pending_commands: list[dict[str, Any]] = []

        # Tracking data
        self._observed_source_addresses: set[int] = set()
        self._last_seen_by_source_addr: dict[int, dict[str, Any]] = {}

        # Background task management
        self._background_tasks: set[asyncio.Task] = set()
        self._broadcast_can_sniffer_group: Callable | None = None

        # Thread-safe lock for command grouping
        self._grouping_lock = asyncio.Lock()

        logger.info("CANTrackingRepository initialized with bounded collections")

    def set_broadcast_function(self, broadcast_func: Callable) -> None:
        """
        Set the function to broadcast CAN sniffer groups.

        Args:
            broadcast_func: Async function to broadcast grouped messages
        """
        self._broadcast_can_sniffer_group = broadcast_func

    def add_can_sniffer_entry(self, entry: dict[str, Any]) -> None:
        """
        Add a CAN command/control message entry to the sniffer log.

        Args:
            entry: CAN message entry
        """
        self._can_command_sniffer_log.append(entry)
        self._update_source_tracking(entry)

    def get_can_sniffer_log(self) -> list[dict[str, Any]]:
        """
        Get the current CAN command/control sniffer log.

        Returns:
            List of CAN message entries (newest last)
        """
        return list(self._can_command_sniffer_log)

    def add_pending_command(self, entry: dict[str, Any]) -> None:
        """
        Add a pending command and clean up old entries.

        Args:
            entry: Command entry with timestamp
        """
        self._pending_commands.append(entry)
        self._cleanup_old_pending_commands(entry["timestamp"])

    async def try_group_response(
        self, response_entry: dict[str, Any], known_pairs: dict[str, str]
    ) -> bool:
        """
        Try to group a response (RX) with a pending command (TX).

        Args:
            response_entry: Response message entry
            known_pairs: Known command/status DGN pairs

        Returns:
            True if successfully grouped, False otherwise
        """
        async with self._grouping_lock:
            now = response_entry["timestamp"]
            instance = response_entry.get("instance")
            dgn = response_entry.get("dgn_hex")

            # Try known command/status pairs first (high confidence)
            for cmd in self._pending_commands[:]:  # Iterate over copy
                cmd_dgn = cmd.get("dgn_hex")
                if (
                    cmd.get("instance") == instance
                    and isinstance(cmd_dgn, str)
                    and known_pairs.get(cmd_dgn) == dgn
                    and 0 <= now - cmd["timestamp"] < 1.0
                ):
                    await self._create_group(cmd, response_entry, "high", "mapping")
                    self._pending_commands.remove(cmd)
                    return True

            # Try heuristic matching (low confidence)
            for cmd in self._pending_commands[:]:
                if cmd.get("instance") == instance and 0 <= now - cmd["timestamp"] < 0.5:
                    await self._create_group(cmd, response_entry, "low", "heuristic")
                    self._pending_commands.remove(cmd)
                    return True

        return False

    def get_can_sniffer_grouped(self) -> list[dict[str, Any]]:
        """Get the list of grouped CAN sniffer entries."""
        return list(self._can_sniffer_grouped)

    def get_observed_source_addresses(self) -> list[int]:
        """Get a sorted list of all observed CAN source addresses."""
        return sorted(self._observed_source_addresses)

    def get_last_seen_by_source(self, source_addr: int) -> dict[str, Any] | None:
        """
        Get the last seen message from a source address.

        Args:
            source_addr: Source address

        Returns:
            Last message entry or None
        """
        return self._last_seen_by_source_addr.get(source_addr)

    def _update_source_tracking(self, entry: dict[str, Any]) -> None:
        """Update source address tracking."""
        src = entry.get("source_addr")
        if src is not None:
            self._observed_source_addresses.add(src)
            self._last_seen_by_source_addr[src] = entry

    def _cleanup_old_pending_commands(self, current_time: float) -> None:
        """Remove pending commands older than timeout."""
        self._pending_commands = [
            cmd
            for cmd in self._pending_commands
            if current_time - cmd["timestamp"] < self.PENDING_COMMAND_TIMEOUT
        ]

        # Enforce maximum size
        if len(self._pending_commands) > self.MAX_PENDING_COMMANDS:
            # Keep only the newest commands
            self._pending_commands = self._pending_commands[-self.MAX_PENDING_COMMANDS :]

    async def _create_group(
        self, command: dict[str, Any], response: dict[str, Any], confidence: str, reason: str
    ) -> None:
        """Create a command/response group and broadcast it."""
        group = {
            "command": command,
            "response": response,
            "confidence": confidence,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self._can_sniffer_grouped.append(group)

        # Broadcast if function is set
        if self._broadcast_can_sniffer_group:
            task = asyncio.create_task(self._broadcast_can_sniffer_group(group))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def cleanup_background_tasks(self) -> None:
        """Cancel and clean up background tasks."""
        for task in self._background_tasks:
            task.cancel()

        # Wait for all tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._background_tasks.clear()

    def get_health_status(self) -> dict[str, Any]:
        """
        Get repository health status.

        Returns:
            Health status information
        """
        return {
            "healthy": True,
            "sniffer_log_size": len(self._can_command_sniffer_log),
            "grouped_entries": len(self._can_sniffer_grouped),
            "pending_commands": len(self._pending_commands),
            "observed_sources": len(self._observed_source_addresses),
            "background_tasks": len(self._background_tasks),
            "memory_bounded": True,  # Collections have size limits
        }

    def get_statistics(self) -> dict[str, Any]:
        """
        Get tracking statistics.

        Returns:
            Statistical information
        """
        return {
            "total_messages": len(self._can_command_sniffer_log),
            "grouped_messages": len(self._can_sniffer_grouped),
            "pending_commands": len(self._pending_commands),
            "unique_sources": len(self._observed_source_addresses),
            "active_tasks": len(self._background_tasks),
            "max_log_size": self.MAX_SNIFFER_LOG_SIZE,
            "max_grouped_size": self.MAX_GROUPED_ENTRIES,
        }
