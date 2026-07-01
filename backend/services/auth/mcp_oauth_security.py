"""Security helpers for MCP OAuth protocol endpoints."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class McpOAuthRateLimiter:
    """Simple in-memory fixed-window rate limiter for OAuth protocol endpoints."""

    limit: int
    window_seconds: int
    _events: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        """Return whether the key is allowed in the current fixed window."""
        now = time.monotonic()
        window_start = now - self.window_seconds
        events = [event for event in self._events.get(key, []) if event > window_start]
        if len(events) >= self.limit:
            self._events[key] = events
            return False
        events.append(now)
        self._events[key] = events
        return True


def audit_mcp_oauth_event(event_type: str, **fields: Any) -> None:
    """Log a non-secret MCP OAuth audit event."""
    redacted = {
        key: ("[REDACTED]" if "secret" in key or "token" in key or "code" in key else value)
        for key, value in fields.items()
    }
    logger.info("MCP OAuth event: %s", event_type, extra={"mcp_oauth": redacted})
