"""Journal repository for systemd journal access.

This repository manages access to systemd journal logs using the repository pattern.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.core.performance import PerformanceMonitor
from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class JournalRepository(MonitoredRepository):
    """Repository for systemd journal access."""

    def __init__(self, database_manager, performance_monitor: PerformanceMonitor):
        """Initialize journal repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)
        self._reader = None
        self._systemd_available = self._check_systemd_availability()

    def _check_systemd_availability(self) -> bool:
        """Check if systemd journal is available.

        Returns:
            True if systemd.journal module is available
        """
        try:
            import systemd.journal  # type: ignore

            return True
        except ImportError:
            logger.warning("systemd.journal module not available")
            return False

    @MonitoredRepository._monitored_operation("get_logs")
    async def get_logs(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        level: int | None = None,
        service: str | None = None,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Get logs from systemd journal.

        Args:
            since: Only return logs after this time
            until: Only return logs before this time
            level: Only return logs at this syslog priority or lower
            service: Only return logs for this systemd unit
            cursor: Journal cursor for pagination
            page_size: Number of log entries to return

        Returns:
            Tuple of (list of log entries, next cursor for pagination)
        """
        if not self._systemd_available:
            return [], None

        import systemd.journal  # type: ignore

        reader = systemd.journal.Reader()
        reader.this_boot()

        if since:
            reader.seek_realtime(since)
        if until:
            reader.add_match(__REALTIME_TIMESTAMP=f"..{until.isoformat()}")
        if level is not None:
            reader.add_match(PRIORITY=str(level))
        if service:
            reader.add_match(_SYSTEMD_UNIT=service)
        if cursor:
            reader.seek_cursor(cursor)
            next(reader)  # skip the entry at the cursor

        logs = []
        next_cursor = None

        for i, entry in enumerate(reader):
            logs.append(self._parse_entry(entry))
            if i + 1 >= page_size:
                next_cursor = reader.get_cursor()
                break

        return logs, next_cursor

    def _parse_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Parse a journal entry to a serializable format.

        Args:
            entry: Raw journal entry

        Returns:
            Parsed log entry
        """
        return {
            "timestamp": (
                datetime.fromtimestamp(entry["__REALTIME_TIMESTAMP"].timestamp()).isoformat()
                if "__REALTIME_TIMESTAMP" in entry
                else None
            ),
            "level": entry.get("PRIORITY"),
            "message": entry.get("MESSAGE"),
            "service_name": entry.get("_SYSTEMD_UNIT"),
            "logger": entry.get("SYSLOG_IDENTIFIER"),
            "pid": entry.get("_PID"),
            "extra": {
                k: v
                for k, v in entry.items()
                if k
                not in {
                    "__REALTIME_TIMESTAMP",
                    "PRIORITY",
                    "MESSAGE",
                    "_SYSTEMD_UNIT",
                    "SYSLOG_IDENTIFIER",
                    "_PID",
                }
            },
        }

    @MonitoredRepository._monitored_operation("get_services")
    async def get_services(self) -> list[str]:
        """Get list of available systemd services in journal.

        Returns:
            List of service names
        """
        if not self._systemd_available:
            return []

        import systemd.journal  # type: ignore

        reader = systemd.journal.Reader()
        reader.this_boot()

        services = set()
        # Sample recent entries to find services
        for i, entry in enumerate(reader):
            if i > 1000:  # Limit sampling
                break
            service = entry.get("_SYSTEMD_UNIT")
            if service:
                services.add(service)

        return sorted(list(services))

    @MonitoredRepository._monitored_operation("count_logs")
    async def count_logs(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        level: int | None = None,
        service: str | None = None,
    ) -> int:
        """Count logs matching criteria.

        Args:
            since: Only count logs after this time
            until: Only count logs before this time
            level: Only count logs at this syslog priority or lower
            service: Only count logs for this systemd unit

        Returns:
            Number of matching log entries
        """
        if not self._systemd_available:
            return 0

        import systemd.journal  # type: ignore

        reader = systemd.journal.Reader()
        reader.this_boot()

        if since:
            reader.seek_realtime(since)
        if until:
            reader.add_match(__REALTIME_TIMESTAMP=f"..{until.isoformat()}")
        if level is not None:
            reader.add_match(PRIORITY=str(level))
        if service:
            reader.add_match(_SYSTEMD_UNIT=service)

        count = 0
        for _ in reader:
            count += 1

        return count

    def is_available(self) -> bool:
        """Check if journal access is available.

        Returns:
            True if systemd journal is available
        """
        return self._systemd_available
