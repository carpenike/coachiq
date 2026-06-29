"""
Service for querying log history from journald.

Provides functions to retrieve structured log entries for API and WebSocket consumption.
"""

import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, cast


class ReaderProtocol(Protocol):
    """Protocol for the systemd.journal.Reader class."""

    def log_level(self, level: int) -> None: ...

    def seek_realtime(self, dt: datetime.datetime) -> None: ...

    def add_match(self, **kwargs: Any) -> None: ...

    def seek_cursor(self, cursor: str) -> None: ...

    def __iter__(self) -> "ReaderProtocol": ...

    def __next__(self) -> dict[str, Any]: ...


class JournalModuleProtocol(Protocol):
    """Protocol for the systemd.journal module with constants."""

    # Reader class
    Reader: ClassVar[type[ReaderProtocol]]

    # Log level constants
    LOG_EMERG: int
    LOG_ALERT: int
    LOG_CRIT: int
    LOG_ERR: int
    LOG_WARNING: int
    LOG_NOTICE: int
    LOG_INFO: int
    LOG_DEBUG: int


class SystemdJournalProtocol(Protocol):
    """Protocol for the systemd module with journal attribute."""

    journal: ClassVar[JournalModuleProtocol]


try:
    import systemd.journal  # type: ignore
except ImportError:
    systemd = None  # type: ignore
    if TYPE_CHECKING:
        systemd = cast("SystemdJournalProtocol", Any)  # type: ignore


def is_journald_available() -> bool:
    """Check if systemd.journal is available (Linux only)."""
    return systemd is not None and hasattr(systemd, "journal")


def query_journald_logs(
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    level: str | None = None,
    module: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """
    Query logs from journald with optional filters and pagination.

    Args:
        since: Start time for logs (UTC)
        until: End time for logs (UTC)
        level: Log level (e.g., 'INFO', 'ERROR')
        module: Logger name/module
        cursor: Journald cursor for pagination
        limit: Max number of log entries to return

    Returns:
        Dict with 'entries' (list of logs), 'next_cursor', and 'has_more'.
    """
    if not is_journald_available():
        msg = "systemd.journal is not available on this system."
        raise RuntimeError(msg)

    if systemd is not None and hasattr(systemd, "journal"):
        j = systemd.journal.Reader()
        j.log_level(systemd.journal.LOG_INFO)  # Default minimum level
        if since:
            j.seek_realtime(since)
        if until:
            j.add_match(_SOURCE_REALTIME_TIMESTAMP__lt=until.timestamp())
        if level:
            # Map level string to journald int
            level_map = {
                "CRITICAL": systemd.journal.LOG_CRIT,
                "ERROR": systemd.journal.LOG_ERR,
                "WARNING": systemd.journal.LOG_WARNING,
                "INFO": systemd.journal.LOG_INFO,
                "DEBUG": systemd.journal.LOG_DEBUG,
            }
            j.log_level(level_map.get(level.upper(), systemd.journal.LOG_INFO))
        if module:
            j.add_match(SYSLOG_IDENTIFIER=module)
        if cursor:
            j.seek_cursor(cursor)
            next(j)  # Skip the entry at the cursor

        entries = []
        next_cursor = None
        for count, entry in enumerate(j):
            # Convert journald entry to dict
            log_entry = {
                "timestamp": datetime.datetime.utcfromtimestamp(
                    entry["__REALTIME_TIMESTAMP"].timestamp()
                ).isoformat()
                + "Z",
                "level": entry.get("PRIORITY"),
                "message": entry.get("MESSAGE"),
                "module": entry.get("SYSLOG_IDENTIFIER"),
                "cursor": entry["__CURSOR"],
            }
            entries.append(log_entry)
            if count + 1 >= limit:
                next_cursor = entry["__CURSOR"]
                break
        has_more = next_cursor is not None
        return {"entries": entries, "next_cursor": next_cursor, "has_more": has_more}
    msg = "systemd.journal is not available or improperly configured."
    raise RuntimeError(msg)
