"""Journal Service (Refactored with Repository Pattern)

Service for accessing systemd journal logs with repository pattern.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.core.performance import PerformanceMonitor
from backend.repositories.journal_repository import JournalRepository

logger = logging.getLogger(__name__)


class JournalService:
    """Service for managing systemd journal access with performance monitoring."""

    def __init__(
        self, journal_repository: JournalRepository, performance_monitor: PerformanceMonitor
    ):
        """Initialize journal service with repository.

        Args:
            journal_repository: Repository for journal access
            performance_monitor: Performance monitoring instance
        """
        self._repository = journal_repository
        self._monitor = performance_monitor

        # Apply performance monitoring
        self._apply_monitoring()

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        # Wrap methods with performance monitoring
        self.get_journal_logs = self._monitor.monitor_service_method(
            "JournalService", "get_journal_logs"
        )(self.get_journal_logs)

        self.get_available_services = self._monitor.monitor_service_method(
            "JournalService", "get_available_services"
        )(self.get_available_services)

        self.get_log_statistics = self._monitor.monitor_service_method(
            "JournalService", "get_log_statistics"
        )(self.get_log_statistics)

    async def get_journal_logs(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        level: int | None = None,
        service: str | None = None,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Retrieve logs from journald with optional filtering and pagination.

        Args:
            since: Only return logs after this time
            until: Only return logs before this time
            level: Only return logs at this syslog priority or lower (lower is more severe)
            service: Only return logs for this systemd unit
            cursor: Journal cursor for pagination
            page_size: Number of log entries to return

        Returns:
            A tuple of (list of log entries, next cursor for pagination)

        Raises:
            RuntimeError: If systemd journal is not available
        """
        if not self._repository.is_available():
            msg = "systemd.journal module is not available. Install systemd-python."
            raise RuntimeError(msg)

        return await self._repository.get_logs(
            since=since,
            until=until,
            level=level,
            service=service,
            cursor=cursor,
            page_size=page_size,
        )

    async def get_available_services(self) -> list[str]:
        """
        Get list of available systemd services in journal.

        Returns:
            List of service names
        """
        return await self._repository.get_services()

    async def get_log_statistics(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        service: str | None = None,
    ) -> dict[str, Any]:
        """
        Get statistics about journal logs.

        Args:
            since: Count logs after this time
            until: Count logs before this time
            service: Only count logs for this systemd unit

        Returns:
            Dictionary with log statistics
        """
        stats = {}

        # Count logs by level
        for level in range(8):  # Syslog levels 0-7
            count = await self._repository.count_logs(
                since=since, until=until, level=level, service=service
            )
            stats[f"level_{level}"] = count

        # Total count
        total = await self._repository.count_logs(since=since, until=until, service=service)

        return {
            "total": total,
            "by_level": stats,
            "time_range": {
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
            },
            "service": service,
        }

    def is_available(self) -> bool:
        """
        Check if journal access is available.

        Returns:
            True if systemd journal is available
        """
        return self._repository.is_available()
