"""
Diagnostics Repository

This repository manages diagnostic data that used to live in the
removed ``AppState`` monolith, including unmapped entries and unknown
PGNs.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DiagnosticsRepository:
    """
    Repository for diagnostic and debugging data.

    This repository consolidates diagnostic data that used to live
    in the removed ``AppState`` monolith:
    - Unmapped entries: Entity configs that couldn't be mapped
    - Unknown PGNs: RV-C messages with unrecognized PGNs
    - Other diagnostic counters and metrics
    """

    def __init__(self):
        """Initialize the diagnostics repository."""
        # Unmapped entries: configs that couldn't be matched to entities
        self._unmapped_entries: dict[str, Any] = {}

        # Unknown PGNs: messages with unrecognized PGNs
        self._unknown_pgns: dict[str, Any] = {}

        # Diagnostic counters
        self._message_count = 0
        self._error_count = 0
        self._last_error: str | None = None
        self._last_error_time: datetime | None = None

        logger.info("DiagnosticsRepository initialized")

    # Unmapped entries management
    def add_unmapped_entry(self, key: str, entry: Any) -> None:
        """Add an unmapped entry."""
        self._unmapped_entries[key] = entry
        logger.debug(f"Added unmapped entry: {key}")

    def remove_unmapped_entry(self, key: str) -> None:
        """Remove an unmapped entry."""
        if key in self._unmapped_entries:
            del self._unmapped_entries[key]
            logger.debug(f"Removed unmapped entry: {key}")

    def get_unmapped_entries(self) -> dict[str, Any]:
        """Get all unmapped entries."""
        return self._unmapped_entries.copy()

    def clear_unmapped_entries(self) -> None:
        """Clear all unmapped entries."""
        count = len(self._unmapped_entries)
        self._unmapped_entries.clear()
        logger.info(f"Cleared {count} unmapped entries")

    def upsert_unmapped_entry(self, key: str, entry: dict[str, Any]) -> dict[str, Any]:
        """Insert or update an unmapped entry, preserving first-seen and counting hits.

        On first sight the entry is stored with ``count`` = 1. On subsequent
        upserts the incoming fields overwrite the stored ones, except
        ``first_seen_timestamp`` (kept from the original entry) and ``count``
        (incremented).
        """
        merged = self._merge_upsert(self._unmapped_entries, key, entry)
        logger.debug("Upserted unmapped entry: %s (count=%s)", key, merged["count"])
        return merged

    # Unknown PGNs management
    def add_unknown_pgn(self, pgn: str, data: Any) -> None:
        """Add an unknown PGN."""
        self._unknown_pgns[pgn] = data
        logger.debug(f"Added unknown PGN: {pgn}")

    def remove_unknown_pgn(self, pgn: str) -> None:
        """Remove an unknown PGN."""
        if pgn in self._unknown_pgns:
            del self._unknown_pgns[pgn]
            logger.debug(f"Removed unknown PGN: {pgn}")

    def get_unknown_pgns(self) -> dict[str, Any]:
        """Get all unknown PGNs."""
        return self._unknown_pgns.copy()

    def clear_unknown_pgns(self) -> None:
        """Clear all unknown PGNs."""
        count = len(self._unknown_pgns)
        self._unknown_pgns.clear()
        logger.info(f"Cleared {count} unknown PGNs")

    def upsert_unknown_pgn(self, pgn: str, entry: dict[str, Any]) -> dict[str, Any]:
        """Insert or update an unknown PGN entry, preserving first-seen and counting hits.

        Same merge semantics as :meth:`upsert_unmapped_entry`.
        """
        merged = self._merge_upsert(self._unknown_pgns, pgn, entry)
        logger.debug("Upserted unknown PGN: %s (count=%s)", pgn, merged["count"])
        return merged

    @staticmethod
    def _merge_upsert(
        store: dict[str, Any], key: str, entry: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge an entry into a keyed store with first-seen/count upsert semantics."""
        existing = store.get(key)
        if isinstance(existing, dict):
            merged = {**existing, **entry}
            if "first_seen_timestamp" in existing:
                merged["first_seen_timestamp"] = existing["first_seen_timestamp"]
            merged["count"] = int(existing.get("count", 0)) + 1
        else:
            merged = {**entry, "count": 1}
        store[key] = merged
        return merged

    # Diagnostic counters
    def increment_message_count(self) -> None:
        """Increment the message counter."""
        self._message_count += 1

    def increment_error_count(self, error_message: str | None = None) -> None:
        """Increment the error counter and optionally record error details."""
        self._error_count += 1
        if error_message:
            self._last_error = error_message
            self._last_error_time = datetime.now(UTC)

    def get_diagnostics_summary(self) -> dict[str, Any]:
        """
        Get a summary of diagnostic information.

        Returns:
            Dictionary containing diagnostic metrics
        """
        return {
            "unmapped_entries_count": len(self._unmapped_entries),
            "unknown_pgns_count": len(self._unknown_pgns),
            "total_messages_processed": self._message_count,
            "total_errors": self._error_count,
            "last_error": self._last_error,
            "last_error_time": self._last_error_time.isoformat() if self._last_error_time else None,
        }

    def get_health_status(self) -> dict[str, Any]:
        """
        Get repository health status.

        Returns:
            Health status information
        """
        error_rate = (
            (self._error_count / self._message_count * 100) if self._message_count > 0 else 0
        )

        return {
            "repository": "DiagnosticsRepository",
            "healthy": error_rate < 5.0,  # Healthy if error rate < 5%
            "unmapped_entries": len(self._unmapped_entries),
            "unknown_pgns": len(self._unknown_pgns),
            "message_count": self._message_count,
            "error_count": self._error_count,
            "error_rate_percent": round(error_rate, 2),
            "last_error": self._last_error,
            "last_error_time": self._last_error_time.isoformat() if self._last_error_time else None,
        }
