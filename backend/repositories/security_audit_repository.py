"""Security Audit Repository

Handles data access for security audit logging including:
- Security event storage and retrieval
- Rate limiting data persistence
- Security pattern tracking
- Compliance documentation
"""

import json
import logging
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

# Import types from service file temporarily until models are extracted
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional, Set

from backend.repositories.base import MonitoredRepository

if TYPE_CHECKING:
    from backend.services.security_audit_service import (
        RateLimitEntry,
        SecurityAuditEvent,
        SecurityEventSeverity,
        SecurityEventType,
    )

logger = logging.getLogger(__name__)


class SecurityAuditRepository(MonitoredRepository):
    """Repository for security audit data management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage (would be database tables in production)
        self._audit_events: list[Any] = []  # List[SecurityAuditEvent]
        self._max_audit_entries = 10000

        # Rate limiting storage
        self._rate_limits: dict[str, Any] = {}  # Dict[str, RateLimitEntry]

        # Security monitoring
        self._suspicious_patterns: dict[str, list[float]] = defaultdict(list)
        self._blocked_ips: set[str] = set()

        # Compliance tracking
        self._compliance_events: list[str] = []  # Event IDs requiring compliance review

    @MonitoredRepository._monitored_operation("store_audit_event")
    async def store_audit_event(self, event: Any) -> str:  # event: SecurityAuditEvent
        """Store a security audit event.

        Args:
            event: Security audit event to store

        Returns:
            Event ID
        """
        # Store event
        self._audit_events.append(event)

        # Track compliance requirements
        if event.compliance_required:
            self._compliance_events.append(event.event_id)

        # Trim if necessary
        if len(self._audit_events) > self._max_audit_entries:
            # Archive old events before trimming in production
            removed_events = self._audit_events[: len(self._audit_events) - self._max_audit_entries]

            # Remove compliance tracking for archived events
            archived_ids = {e.event_id for e in removed_events}
            self._compliance_events = [
                eid for eid in self._compliance_events if eid not in archived_ids
            ]

            self._audit_events = self._audit_events[-self._max_audit_entries :]

        return event.event_id

    @MonitoredRepository._monitored_operation("get_audit_events")
    async def get_audit_events(
        self,
        event_type: Any | None = None,  # Optional[SecurityEventType]
        severity: Any | None = None,  # Optional[SecurityEventSeverity]
        user_id: str | None = None,
        source_ip: str | None = None,
        hours: int = 24,
        limit: int = 100,
    ) -> list[Any]:  # List[SecurityAuditEvent]
        """Get filtered audit events.

        Args:
            event_type: Filter by event type
            severity: Filter by severity
            user_id: Filter by user
            source_ip: Filter by source IP
            hours: Time window in hours
            limit: Maximum events to return

        Returns:
            List of matching events
        """
        cutoff = time.time() - (hours * 3600)

        filtered_events = []
        for event in reversed(self._audit_events):  # Most recent first
            if event.timestamp < cutoff:
                break

            if event_type and event.event_type != event_type:
                continue
            if severity and event.severity != severity:
                continue
            if user_id and event.user_id != user_id:
                continue
            if source_ip and event.source_ip != source_ip:
                continue

            filtered_events.append(event)

            if len(filtered_events) >= limit:
                break

        return filtered_events

    @MonitoredRepository._monitored_operation("get_event_by_id")
    async def get_event_by_id(self, event_id: str) -> Any | None:  # Optional[SecurityAuditEvent]
        """Get a specific audit event by ID.

        Args:
            event_id: Event identifier

        Returns:
            Event if found
        """
        for event in self._audit_events:
            if event.event_id == event_id:
                return event
        return None

    @MonitoredRepository._monitored_operation("mark_event_reviewed")
    async def mark_event_reviewed(self, event_id: str) -> bool:
        """Mark an event as reviewed.

        Args:
            event_id: Event to mark as reviewed

        Returns:
            True if successful
        """
        for event in self._audit_events:
            if event.event_id == event_id:
                event.reviewed = True
                if event_id in self._compliance_events:
                    self._compliance_events.remove(event_id)
                return True
        return False

    @MonitoredRepository._monitored_operation("get_compliance_events")
    async def get_compliance_events(
        self, include_reviewed: bool = False
    ) -> list[Any]:  # List[SecurityAuditEvent]
        """Get events requiring compliance documentation.

        Args:
            include_reviewed: Include already reviewed events

        Returns:
            List of compliance events
        """
        events = []
        for event in self._audit_events:
            if event.compliance_required:
                if include_reviewed or not event.reviewed:
                    events.append(event)

        return sorted(events, key=lambda e: e.timestamp, reverse=True)

    @MonitoredRepository._monitored_operation("store_rate_limit")
    async def store_rate_limit(self, identifier: str, entry: Any) -> bool:  # entry: RateLimitEntry
        """Store or update rate limit entry.

        Args:
            identifier: IP or user identifier
            entry: Rate limit entry

        Returns:
            True if stored successfully
        """
        self._rate_limits[identifier] = entry
        return True

    @MonitoredRepository._monitored_operation("get_rate_limit")
    async def get_rate_limit(self, identifier: str) -> Any | None:  # Optional[RateLimitEntry]
        """Get rate limit entry for identifier.

        Args:
            identifier: IP or user identifier

        Returns:
            Rate limit entry if found
        """
        return self._rate_limits.get(identifier)

    @MonitoredRepository._monitored_operation("cleanup_rate_limits")
    async def cleanup_rate_limits(self, inactive_hours: int = 1) -> int:
        """Clean up expired rate limit entries.

        Args:
            inactive_hours: Hours of inactivity before cleanup

        Returns:
            Number of entries cleaned up
        """
        now = time.time()
        cutoff = now - (inactive_hours * 3600)
        expired_identifiers = []

        for identifier, entry in self._rate_limits.items():
            # Remove if no recent activity and not blocked
            if entry.blocked_until < now and (not entry.requests or entry.requests[-1] < cutoff):
                expired_identifiers.append(identifier)

        for identifier in expired_identifiers:
            del self._rate_limits[identifier]

        return len(expired_identifiers)

    @MonitoredRepository._monitored_operation("add_blocked_ip")
    async def add_blocked_ip(self, ip_address: str) -> bool:
        """Add IP to blocked list.

        Args:
            ip_address: IP to block

        Returns:
            True if added successfully
        """
        self._blocked_ips.add(ip_address)
        return True

    @MonitoredRepository._monitored_operation("remove_blocked_ip")
    async def remove_blocked_ip(self, ip_address: str) -> bool:
        """Remove IP from blocked list.

        Args:
            ip_address: IP to unblock

        Returns:
            True if removed successfully
        """
        self._blocked_ips.discard(ip_address)
        return True

    @MonitoredRepository._monitored_operation("get_blocked_ips")
    async def get_blocked_ips(self) -> set[str]:
        """Get all blocked IPs.

        Returns:
            Set of blocked IP addresses
        """
        return self._blocked_ips.copy()

    @MonitoredRepository._monitored_operation("cleanup_blocked_ips")
    async def cleanup_blocked_ips(self, hours: int = 1) -> int:
        """Clean up blocked IPs after timeout.

        Args:
            hours: Hours before unblocking

        Returns:
            Number of IPs unblocked
        """
        cutoff = time.time() - (hours * 3600)

        # Find IPs with no recent blocking events
        ips_to_unblock = set()
        for ip in self._blocked_ips:
            recent_blocks = [
                e
                for e in self._audit_events[-100:]
                if e.source_ip == ip
                and e.event_type == "brute_force_attempt"  # SecurityEventType.BRUTE_FORCE_ATTEMPT
                and e.timestamp > cutoff
            ]
            if not recent_blocks:
                ips_to_unblock.add(ip)

        for ip in ips_to_unblock:
            self._blocked_ips.discard(ip)

        return len(ips_to_unblock)

    @MonitoredRepository._monitored_operation("track_suspicious_pattern")
    async def track_suspicious_pattern(self, pattern_key: str, timestamp: float) -> None:
        """Track suspicious activity pattern.

        Args:
            pattern_key: Pattern identifier (e.g., "ip:event_type")
            timestamp: Event timestamp
        """
        self._suspicious_patterns[pattern_key].append(timestamp)

        # Keep only recent events (last hour)
        cutoff = time.time() - 3600
        self._suspicious_patterns[pattern_key] = [
            ts for ts in self._suspicious_patterns[pattern_key] if ts > cutoff
        ]

    @MonitoredRepository._monitored_operation("get_pattern_count")
    async def get_pattern_count(self, pattern_key: str, hours: float = 1.0) -> int:
        """Get count of pattern occurrences in time window.

        Args:
            pattern_key: Pattern identifier
            hours: Time window in hours

        Returns:
            Number of occurrences
        """
        cutoff = time.time() - (hours * 3600)
        return len([ts for ts in self._suspicious_patterns.get(pattern_key, []) if ts > cutoff])

    @MonitoredRepository._monitored_operation("get_security_summary")
    async def get_security_summary(self, hours: int = 24) -> dict[str, Any]:
        """Get security summary for time period.

        Args:
            hours: Time period in hours

        Returns:
            Security summary statistics
        """
        cutoff = time.time() - (hours * 3600)
        recent_events = [e for e in self._audit_events if e.timestamp > cutoff]

        # Event counts by type
        event_counts = defaultdict(int)
        severity_counts = defaultdict(int)

        for event in recent_events:
            event_counts[event.event_type] += 1
            severity_counts[event.severity] += 1

        # Rate limiting stats
        active_rate_limits = len(
            [entry for entry in self._rate_limits.values() if entry.blocked_until > time.time()]
        )

        total_blocked_requests = sum(entry.blocked_requests for entry in self._rate_limits.values())

        return {
            "time_period_hours": hours,
            "total_events": len(recent_events),
            "events_by_type": dict(event_counts),
            "events_by_severity": dict(severity_counts),
            "safety_critical_events": len(
                [e for e in recent_events if e.safety_impact or e.emergency_context]
            ),
            "compliance_events": len([e for e in recent_events if e.compliance_required]),
            "compliance_pending_review": len(
                [e for e in recent_events if e.compliance_required and not e.reviewed]
            ),
            "rate_limiting": {
                "active_blocks": active_rate_limits,
                "total_blocked_requests": total_blocked_requests,
                "blocked_ips": len(self._blocked_ips),
            },
        }

    @MonitoredRepository._monitored_operation("archive_old_events")
    async def archive_old_events(self, days: int = 30) -> int:
        """Archive events older than specified days.

        Args:
            days: Days to keep events

        Returns:
            Number of events archived
        """
        cutoff = time.time() - (days * 24 * 3600)

        # In production, these would be moved to archive storage
        events_to_archive = [e for e in self._audit_events if e.timestamp < cutoff]

        if events_to_archive:
            # Archive to file/database
            archive_data = {
                "archived_at": datetime.now(UTC).isoformat(),
                "event_count": len(events_to_archive),
                "events": [e.model_dump() for e in events_to_archive],
            }

            # Remove from active storage
            self._audit_events = [e for e in self._audit_events if e.timestamp >= cutoff]

            logger.info(f"Archived {len(events_to_archive)} security audit events")

        return len(events_to_archive)

    async def log_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Log a security event (convenience method).

        Args:
            event_type: Type of security event
            severity: Event severity level
            description: Event description
            user_id: User ID if applicable
            ip_address: Source IP address
            user_agent: User agent string
            metadata: Additional event metadata

        Returns:
            Event ID
        """
        # Create event object
        event_data = {
            "event_id": f"evt_{int(time.time() * 1000)}_{len(self._audit_events)}",
            "event_type": event_type,
            "severity": severity,
            "description": description,
            "timestamp": datetime.now(UTC),
            "user_id": user_id,
            "source_ip": ip_address,
            "user_agent": user_agent,
            "metadata": metadata or {},
            "compliance_required": severity in ["critical", "high"],
        }

        # Create a simple event object
        class SimpleEvent:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items()}

        event = SimpleEvent(**event_data)

        # Store using existing method
        return await self.store_audit_event(event)

    async def get_security_events(
        self,
        event_type_prefix: str | None = None,
        user_id: str | None = None,
        ip_address: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get security events with flexible filtering.

        Args:
            event_type_prefix: Filter by event type prefix
            user_id: Filter by user ID
            ip_address: Filter by IP address
            since: Filter events after this time
            limit: Maximum events to return

        Returns:
            List of event dictionaries
        """
        filtered_events = []

        for event in reversed(self._audit_events):  # Most recent first
            # Apply filters
            if since and event.timestamp < since:
                continue

            if event_type_prefix and not event.event_type.startswith(event_type_prefix):
                continue

            if user_id and event.user_id != user_id:
                continue

            if ip_address and getattr(event, "source_ip", None) != ip_address:
                continue

            # Convert to dict
            event_dict = (
                event.model_dump()
                if hasattr(event, "model_dump")
                else {
                    "event_id": getattr(event, "event_id", "unknown"),
                    "event_type": getattr(event, "event_type", "unknown"),
                    "severity": getattr(event, "severity", "info"),
                    "description": getattr(event, "description", ""),
                    "timestamp": getattr(event, "timestamp", datetime.now(UTC)),
                    "user_id": getattr(event, "user_id", None),
                    "ip_address": getattr(event, "source_ip", None),
                    "user_agent": getattr(event, "user_agent", None),
                    "metadata": getattr(event, "metadata", {}),
                }
            )

            filtered_events.append(event_dict)

            if len(filtered_events) >= limit:
                break

        return filtered_events

    @MonitoredRepository._monitored_operation("get_security_events_summary")
    async def get_security_events_summary(
        self,
        since: datetime | None = None,
        event_type_prefix: str | None = None,
        user_id: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Get aggregated summary of security events without fetching full records.

        Args:
            since: Filter events after this time
            event_type_prefix: Filter events by type prefix
            user_id: Filter by user ID
            ip_address: Filter by IP address

        Returns:
            Summary with counts by type, severity, unique users, and IPs
        """
        summary = {
            "total_events": 0,
            "by_type": {},
            "by_severity": {},
            "by_status": {},
            "unique_users": set(),
            "unique_ips": set(),
        }

        for event in reversed(self._audit_events):  # Most recent first
            # Apply filters
            if since and event.timestamp < since:
                continue

            if event_type_prefix and not event.event_type.startswith(event_type_prefix):
                continue

            if user_id and event.user_id != user_id:
                continue

            if ip_address and getattr(event, "source_ip", None) != ip_address:
                continue

            # Update summary
            summary["total_events"] += 1

            # Count by type
            evt_type = getattr(event, "event_type", "unknown")
            summary["by_type"][evt_type] = summary["by_type"].get(evt_type, 0) + 1

            # Count by severity
            severity = getattr(event, "severity", "info")
            summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1

            # Count by status if available
            if hasattr(event, "metadata") and event.metadata:
                status = event.metadata.get("status", "unknown")
                summary["by_status"][status] = summary["by_status"].get(status, 0) + 1

            # Track unique identifiers
            if event.user_id:
                summary["unique_users"].add(event.user_id)
            if hasattr(event, "source_ip") and event.source_ip:
                summary["unique_ips"].add(event.source_ip)

        # Convert sets to counts
        summary["unique_users"] = len(summary["unique_users"])
        summary["unique_ips"] = len(summary["unique_ips"])

        return summary
