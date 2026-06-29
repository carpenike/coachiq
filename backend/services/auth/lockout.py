"""Account lockout protection.

Extracted from the historical ``backend/services/auth_services.py`` in
audit cycle 2026-05-13 PR A9. The :class:`LockoutService` body is moved
verbatim; only the surrounding imports and module docstring are new.
"""

# ruff: noqa: G004, PLR0913, SIM102
# Pre-existing patterns from the moved code (lifted from auth_services.py
# in audit cycle 2026-05-13 PR A9). Cleanup is intentionally out of scope.

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.performance import PerformanceMonitor
from backend.repositories.auth_repository import AuthEventRepository

logger = logging.getLogger(__name__)


class LockoutService:
    """Service for account lockout protection."""

    def __init__(
        self,
        auth_event_repository: AuthEventRepository,
        performance_monitor: PerformanceMonitor,
        max_failed_attempts: int,
        lockout_window_minutes: int,
        lockout_duration_minutes: int,
        attempt_tracker_service: Any | None = None,
    ):
        """Initialize the lockout service.

        Args:
            auth_event_repository: Repository for auth events
            performance_monitor: Performance monitoring instance
            max_failed_attempts: Maximum failed attempts before lockout
            lockout_window_minutes: Time window for counting attempts
            lockout_duration_minutes: How long to lock account
            attempt_tracker_service: Optional centralized attempt tracking service
        """
        self._auth_event_repo = auth_event_repository
        self._monitor = performance_monitor
        self._max_attempts = max_failed_attempts
        self._window_minutes = lockout_window_minutes
        self._lockout_minutes = lockout_duration_minutes
        self._attempt_tracker = attempt_tracker_service

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("LockoutService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.check_lockout = self._monitor.monitor_service_method(
            "LockoutService", "check_lockout"
        )(self.check_lockout)

        self.record_failed_attempt = self._monitor.monitor_service_method(
            "LockoutService", "record_failed_attempt"
        )(self.record_failed_attempt)

    async def check_lockout(self, username: str) -> tuple[bool, datetime | None]:
        """Check if user is locked out.

        Args:
            username: Username to check

        Returns:
            Tuple of (is_locked, unlock_time)
        """
        # Get recent failed attempts
        failed_count = await self._auth_event_repo.get_failed_attempts_count(
            username, self._window_minutes
        )

        if failed_count >= self._max_attempts:
            # Calculate unlock time
            events = await self._auth_event_repo.get_auth_events_for_user(
                username, datetime.now(UTC) - timedelta(minutes=self._window_minutes)
            )

            # Find the most recent failed attempt
            failed_events = [e for e in events if e["event_type"] == "login" and not e["success"]]

            if failed_events:
                latest_fail = max(failed_events, key=lambda e: e["timestamp"])
                fail_time = datetime.fromisoformat(latest_fail["timestamp"].replace("Z", "+00:00"))
                unlock_time = fail_time + timedelta(minutes=self._lockout_minutes)

                if unlock_time > datetime.now(UTC):
                    logger.warning(f"User {username} is locked out until {unlock_time}")
                    return True, unlock_time

        return False, None

    async def record_failed_attempt(
        self, username: str, metadata: dict[str, Any] | None = None
    ) -> int:
        """Record a failed login attempt.

        Args:
            username: Username that failed
            metadata: Additional event metadata

        Returns:
            Current failed attempt count
        """
        # Record the event
        await self._auth_event_repo.create_auth_event(username, "login", False, metadata)

        # Also track in centralized service if available
        if self._attempt_tracker:
            try:
                # Import here to avoid circular dependency
                from backend.services.auth.attempt_tracker_service import (
                    AttemptStatus,
                    AttemptType,
                    SecurityAttempt,
                )

                attempt = SecurityAttempt(
                    attempt_type=AttemptType.LOGIN,
                    status=AttemptStatus.FAILED,
                    username=username,
                    ip_address=metadata.get("ip_address") if metadata else None,
                    user_agent=metadata.get("user_agent") if metadata else None,
                    metadata=metadata or {},
                )
                await self._attempt_tracker.track_attempt(attempt)
            except Exception as e:
                logger.error(f"Failed to track attempt in AttemptTrackerService: {e}")

        # Get current count
        failed_count = await self._auth_event_repo.get_failed_attempts_count(
            username, self._window_minutes
        )

        if failed_count >= self._max_attempts:
            logger.warning(f"User {username} reached max failed attempts ({failed_count})")

        return failed_count

    async def record_successful_login(
        self, username: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Record a successful login and clear failed attempts.

        Args:
            username: Username that succeeded
            metadata: Additional event metadata
        """
        # Record success
        await self._auth_event_repo.create_auth_event(username, "login", True, metadata)

        # Also track in centralized service if available
        if self._attempt_tracker:
            try:
                # Import here to avoid circular dependency
                from backend.services.auth.attempt_tracker_service import (
                    AttemptStatus,
                    AttemptType,
                    SecurityAttempt,
                )

                attempt = SecurityAttempt(
                    attempt_type=AttemptType.LOGIN,
                    status=AttemptStatus.SUCCESS,
                    username=username,
                    ip_address=metadata.get("ip_address") if metadata else None,
                    user_agent=metadata.get("user_agent") if metadata else None,
                    metadata=metadata or {},
                )
                await self._attempt_tracker.track_attempt(attempt)
            except Exception as e:
                logger.error(f"Failed to track attempt in AttemptTrackerService: {e}")

        # Clear failed attempts
        await self._auth_event_repo.clear_failed_attempts(username)

        logger.info(f"Successful login recorded for {username}")

    async def get_lockout_info(self, username: str) -> dict[str, Any]:
        """Get detailed lockout information for a user.

        Args:
            username: Username to check

        Returns:
            Lockout status and details
        """
        is_locked, unlock_time = await self.check_lockout(username)
        failed_count = await self._auth_event_repo.get_failed_attempts_count(
            username, self._window_minutes
        )

        return {
            "is_locked": is_locked,
            "unlock_time": unlock_time.isoformat() if unlock_time else None,
            "failed_attempts": failed_count,
            "max_attempts": self._max_attempts,
            "attempts_remaining": max(0, self._max_attempts - failed_count),
        }
