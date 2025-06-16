"""
Safety service for RV-C vehicle control systems.

Implements ISO 26262-inspired safety patterns including:
- Safety interlocks for position-critical features
- Emergency stop capabilities
- Watchdog monitoring
- Audit logging for safety-critical operations
- Enhanced security audit logging and rate limiting
"""

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from backend.services.feature_models import (
    FeatureState,
    SafeStateAction,
    SafetyClassification,
)

logger = logging.getLogger(__name__)


class SystemOperationalMode(str, Enum):
    """
    Operational modes for the safety system.

    Follows ISO 26262 operational mode patterns:
    - NORMAL: System functions as intended
    - MAINTENANCE: Service mode with relaxed interlocks
    - DIAGNOSTIC: Test mode for troubleshooting
    """

    NORMAL = "normal"
    MAINTENANCE = "maintenance"
    DIAGNOSTIC = "diagnostic"


@dataclass
class ModeSession:
    """Tracks an active operational mode session."""

    mode: SystemOperationalMode
    pin_session_id: str
    entered_by: str
    entered_at: datetime
    expires_at: datetime
    active_overrides: dict[str, datetime]  # interlock_name -> override_expiry


class SafetyInterlock:
    """
    Safety interlock for position-critical features.

    Prevents unsafe operations and enforces safety constraints
    for physical positioning systems like slides, awnings, leveling jacks.
    """

    def __init__(
        self,
        name: str,
        feature_name: str,
        interlock_conditions: list[str],
        safe_state_action: SafeStateAction = SafeStateAction.MAINTAIN_POSITION,
    ):
        """
        Initialize safety interlock.

        Args:
            name: Unique identifier for this interlock
            feature_name: Name of the feature this interlock protects
            interlock_conditions: List of conditions that must be met
            safe_state_action: Action to take when interlock is triggered
        """
        self.name = name
        self.feature_name = feature_name
        self.interlock_conditions = interlock_conditions
        self.safe_state_action = safe_state_action
        self.is_engaged = False
        self.engagement_time: datetime | None = None
        self.engagement_reason = ""
        # Override support for maintenance mode
        self._is_overridden = False
        self._override_session_id: str | None = None
        self._override_reason: str | None = None
        self._override_expires_at: datetime | None = None
        self._override_by: str | None = None

    async def check_conditions(self, system_state: dict[str, Any]) -> tuple[bool, str]:
        """
        Check if interlock conditions are satisfied.

        Args:
            system_state: Current system state information

        Returns:
            Tuple of (conditions_met, reason_if_not_met)
        """
        # Check if interlock is overridden
        if self._is_overridden:
            if self._override_expires_at and datetime.now(UTC) > self._override_expires_at:
                # Override has expired, clear it
                self._is_overridden = False
                self._override_session_id = None
                self._override_reason = None
                self._override_expires_at = None
                self._override_by = None
                logger.warning(
                    "Interlock '%s' override expired, reverting to normal operation", self.name
                )
            else:
                # Override is still valid
                return True, f"Overridden by {self._override_by}: {self._override_reason}"

        # Normal condition checking
        for condition in self.interlock_conditions:
            if not await self._evaluate_condition(condition, system_state):
                return False, f"Interlock condition not met: {condition}"
        return True, "All conditions satisfied"

    async def _evaluate_condition(self, condition: str, system_state: dict[str, Any]) -> bool:
        """
        Evaluate a single interlock condition.

        Args:
            condition: Condition string to evaluate
            system_state: Current system state

        Returns:
            True if condition is met
        """
        # Parse condition (simplified implementation)
        if condition == "vehicle_not_moving":
            vehicle_speed_threshold = 0.5  # mph
            return system_state.get("vehicle_speed", 0) < vehicle_speed_threshold
        if condition == "parking_brake_engaged":
            return system_state.get("parking_brake", False)
        if condition == "leveling_jacks_deployed":
            return system_state.get("leveling_jacks_down", False)
        if condition == "engine_not_running":
            return not system_state.get("engine_running", False)
        if condition == "transmission_in_park":
            return system_state.get("transmission_gear", "") == "PARK"
        if condition == "slide_rooms_retracted":
            return system_state.get("all_slides_retracted", True)
        # Unknown condition - fail safe
        logger.warning("Unknown interlock condition: %s", condition)
        return False

    async def engage(self, reason: str) -> None:
        """
        Engage the safety interlock.

        Args:
            reason: Reason for engaging the interlock
        """
        if not self.is_engaged:
            self.is_engaged = True
            self.engagement_time = datetime.now(UTC)
            self.engagement_reason = reason

            logger.warning(
                "Safety interlock '%s' ENGAGED for feature '%s': %s",
                self.name,
                self.feature_name,
                reason,
            )

    async def disengage(self, reason: str = "Manual override") -> None:
        """
        Disengage the safety interlock.

        Args:
            reason: Reason for disengaging the interlock
        """
        if self.is_engaged:
            duration = 0.0
            if self.engagement_time:
                duration = (datetime.now(UTC) - self.engagement_time).total_seconds()
            self.is_engaged = False
            self.engagement_time = None
            self.engagement_reason = ""

            logger.info(
                "Safety interlock '%s' DISENGAGED for feature '%s' after %.1fs: %s",
                self.name,
                self.feature_name,
                duration,
                reason,
            )

    async def override(
        self,
        session_id: str,
        reason: str,
        expires_at: datetime,
        overridden_by: str,
    ) -> None:
        """
        Override the safety interlock temporarily.

        Args:
            session_id: PIN session ID authorizing the override
            reason: Reason for overriding the interlock
            expires_at: When the override expires
            overridden_by: User who authorized the override
        """
        self._is_overridden = True
        self._override_session_id = session_id
        self._override_reason = reason
        self._override_expires_at = expires_at
        self._override_by = overridden_by

        logger.warning(
            "Safety interlock '%s' OVERRIDDEN for feature '%s' by %s: %s (expires: %s)",
            self.name,
            self.feature_name,
            overridden_by,
            reason,
            expires_at.isoformat(),
        )

    def clear_override(self) -> None:
        """Clear any active override on this interlock."""
        if self._is_overridden:
            logger.info(
                "Safety interlock '%s' override CLEARED for feature '%s'",
                self.name,
                self.feature_name,
            )
            self._is_overridden = False
            self._override_session_id = None
            self._override_reason = None
            self._override_expires_at = None
            self._override_by = None

    def get_override_info(self) -> dict[str, Any] | None:
        """Get information about the current override if any.

        Returns:
            Dictionary with override details or None if not overridden
        """
        if not self._is_overridden:
            return None

        return {
            "is_overridden": self._is_overridden,
            "session_id": self._override_session_id,
            "reason": self._override_reason,
            "expires_at": self._override_expires_at,
            "overridden_by": self._override_by,
        }


class SafetyService:
    """
    Comprehensive safety service for RV-C vehicle control systems.

    Implements ISO 26262-inspired safety patterns including interlocks,
    emergency stop, watchdog monitoring, and audit logging.

    The service initializes with a safe default system state representing
    a parked and stabilized RV with parking brake engaged, leveling jacks
    deployed, and transmission in park to prevent false safety violations
    at startup.
    """

    # Constants
    MULTIPLE_VIOLATION_THRESHOLD = 3  # Number of violations to trigger emergency stop

    def __init__(
        self,
        feature_manager,
        health_check_interval: float = 5.0,
        watchdog_timeout: float = 15.0,
        pin_manager=None,
        security_audit_service=None,
    ):
        """
        Initialize safety service.

        Args:
            feature_manager: FeatureManager instance to monitor
            health_check_interval: Interval between health checks (seconds)
            watchdog_timeout: Watchdog timeout threshold (seconds)
            pin_manager: Optional PIN manager for enhanced authorization
            security_audit_service: Optional security audit service for enhanced logging
        """
        self.feature_manager = feature_manager
        self.health_check_interval = health_check_interval
        self.watchdog_timeout = watchdog_timeout
        self.pin_manager = pin_manager
        self.security_audit_service = security_audit_service

        # Safety state tracking
        self._in_safe_state = False
        self._emergency_stop_active = False
        self._operational_mode = SystemOperationalMode.NORMAL
        self._mode_session_id: str | None = None
        self._mode_entered_by: str | None = None
        self._mode_entered_at: datetime | None = None
        self._mode_expires_at: datetime | None = None
        self._active_overrides: dict[str, datetime] = {}  # interlock_name -> expiry
        self._last_watchdog_kick = 0.0
        self._watchdog_task: asyncio.Task | None = None
        self._health_monitor_task: asyncio.Task | None = None

        # Interlocks management
        self._interlocks: dict[str, SafetyInterlock] = {}
        # Initialize system state with safe defaults (parked and stabilized RV)
        self._system_state: dict[str, Any] = {
            "vehicle_speed": 0.0,  # Vehicle not moving
            "parking_brake": True,  # Parking brake engaged
            "leveling_jacks_down": True,  # Jacks deployed for stability
            "engine_running": False,  # Engine off
            "transmission_gear": "PARK",  # Transmission in park
            "all_slides_retracted": True,  # All slides in safe position
        }

        # Audit logging
        self._audit_log: list[dict[str, Any]] = []
        self._max_audit_entries = 1000

        # Emergency stop tracking
        self._emergency_stop_reason: str | None = None
        self._emergency_stop_triggered_by: str | None = None
        self._emergency_stop_time: datetime | None = None
        self._active_safety_actions: list[str] = []
        self._last_health_check: datetime | None = None

        # Initialize default interlocks
        self._setup_default_interlocks()

        logger.info("SafetyService initialized with default system state: %s", self._system_state)

    def _setup_default_interlocks(self) -> None:
        """Set up default safety interlocks for common RV systems."""

        # Slide room safety interlocks
        slide_interlocks = [
            "vehicle_not_moving",
            "parking_brake_engaged",
            "leveling_jacks_deployed",
            "transmission_in_park",
        ]

        self.add_interlock(
            SafetyInterlock(
                name="slide_room_safety",
                feature_name="firefly",  # Firefly controls slide rooms
                interlock_conditions=slide_interlocks,
                safe_state_action=SafeStateAction.MAINTAIN_POSITION,
            )
        )

        # Awning safety interlocks
        awning_interlocks = [
            "vehicle_not_moving",
            "parking_brake_engaged",
        ]

        self.add_interlock(
            SafetyInterlock(
                name="awning_safety",
                feature_name="firefly",  # Firefly controls awnings
                interlock_conditions=awning_interlocks,
                safe_state_action=SafeStateAction.MAINTAIN_POSITION,
            )
        )

        # Leveling jack safety interlocks
        leveling_interlocks = [
            "vehicle_not_moving",
            "parking_brake_engaged",
            "transmission_in_park",
            "engine_not_running",
        ]

        self.add_interlock(
            SafetyInterlock(
                name="leveling_jack_safety",
                feature_name="spartan_k2",  # Spartan K2 controls leveling
                interlock_conditions=leveling_interlocks,
                safe_state_action=SafeStateAction.MAINTAIN_POSITION,
            )
        )

    def add_interlock(self, interlock: SafetyInterlock) -> None:
        """
        Add a safety interlock to the system.

        Args:
            interlock: SafetyInterlock instance to add
        """
        self._interlocks[interlock.name] = interlock
        logger.info(
            "Added safety interlock: %s for feature %s", interlock.name, interlock.feature_name
        )

    def update_system_state(self, state_updates: dict[str, Any]) -> None:
        """
        Update system state information used by interlocks.

        Args:
            state_updates: Dictionary of state updates

        Note:
            The system initializes with safe defaults (parked RV with jacks down).
            Any updates should maintain consistency with the safety requirements.
            Key states include: parking_brake, leveling_jacks_down, vehicle_speed,
            transmission_gear, engine_running, and all_slides_retracted.
        """
        self._system_state.update(state_updates)
        logger.debug("Updated system state: %s", state_updates)

    async def check_safety_interlocks(self) -> dict[str, tuple[bool, str]]:
        """
        Check all safety interlocks and engage/disengage as needed.

        Returns:
            Dictionary mapping interlock names to (satisfied, reason) tuples
        """
        results = {}

        for interlock_name, interlock in self._interlocks.items():
            conditions_met, reason = await interlock.check_conditions(self._system_state)
            results[interlock_name] = (conditions_met, reason)

            if not conditions_met and not interlock.is_engaged:
                await interlock.engage(reason)
                await self._audit_log_event(
                    "interlock_engaged",
                    {
                        "interlock": interlock_name,
                        "feature": interlock.feature_name,
                        "reason": reason,
                    },
                )

                # Enhanced security audit logging for safety interlock violations
                if self.security_audit_service:
                    await self.security_audit_service.log_security_event(
                        event_type="safety_interlock_violated",
                        severity="high",
                        details={
                            "interlock_name": interlock_name,
                            "feature_name": interlock.feature_name,
                            "violation_reason": reason,
                            "safe_state_action": interlock.safe_state_action.value,
                        },
                        emergency_context=self._emergency_stop_active,
                    )
            elif conditions_met and interlock.is_engaged:
                await interlock.disengage("Conditions satisfied")
                await self._audit_log_event(
                    "interlock_disengaged",
                    {
                        "interlock": interlock_name,
                        "feature": interlock.feature_name,
                        "reason": "Conditions satisfied",
                    },
                )

        return results

    async def trigger_emergency_stop(
        self,
        reason: str,
        triggered_by: str,
    ) -> bool:
        """
        Trigger emergency stop with specific reason and source.

        Args:
            reason: Reason for triggering emergency stop
            triggered_by: Who/what triggered the stop

        Returns:
            True if emergency stop was activated
        """
        if self._emergency_stop_active:
            logger.warning("Emergency stop already active")
            return False

        self._emergency_stop_active = True
        self._emergency_stop_reason = reason
        self._emergency_stop_triggered_by = triggered_by
        self._emergency_stop_time = datetime.now(UTC)

        await self._audit_log_event(
            "emergency_stop_triggered",
            {
                "reason": reason,
                "triggered_by": triggered_by,
                "timestamp": self._emergency_stop_time.isoformat(),
            },
        )

        # Enhanced security audit logging
        if self.security_audit_service:
            await self.security_audit_service.log_security_event(
                event_type="emergency_stop_triggered",
                severity="critical",
                user_id=triggered_by,
                details={
                    "reason": reason,
                    "method": "trigger_emergency_stop",
                    "safety_actions_count": len(self._active_safety_actions),
                },
                emergency_context=True,
            )

        # Execute emergency stop actions
        await self._execute_emergency_stop_actions()

        logger.critical(
            "EMERGENCY STOP TRIGGERED - Reason: %s, By: %s",
            reason,
            triggered_by,
        )

        return True

    async def emergency_stop(self, reason: str = "Manual trigger") -> None:
        """
        Trigger emergency stop for all position-critical features.

        Args:
            reason: Reason for emergency stop
        """
        if self._emergency_stop_active:
            logger.warning("Emergency stop already active")
            return

        self._emergency_stop_active = True
        logger.critical("=== EMERGENCY STOP ACTIVATED ===")
        logger.critical("Reason: %s", reason)

        await self._audit_log_event(
            "emergency_stop_activated",
            {"reason": reason, "timestamp": datetime.now(UTC).isoformat()},
        )

        try:
            # Get all position-critical features
            position_critical_features = []
            for feature_name, feature in self.feature_manager.features.items():
                if (
                    hasattr(feature, "_safety_classification")
                    and feature._safety_classification == SafetyClassification.POSITION_CRITICAL
                ):
                    position_critical_features.append(feature_name)

            # Set all position-critical features to SAFE_SHUTDOWN
            for feature_name in position_critical_features:
                feature = self.feature_manager.get_feature(feature_name)
                if feature and feature.enabled:
                    logger.critical("Emergency stop: Setting %s to SAFE_SHUTDOWN", feature_name)
                    feature.state = FeatureState.SAFE_SHUTDOWN

            # Engage all safety interlocks
            for interlock in self._interlocks.values():
                if not interlock.is_engaged:
                    await interlock.engage(f"Emergency stop: {reason}")

            # Enter system-wide safe state
            await self._enter_safe_state(f"Emergency stop: {reason}")

            logger.critical("=== EMERGENCY STOP COMPLETED ===")

        except Exception as e:
            logger.critical("Error during emergency stop: %s", e)
            await self._audit_log_event("emergency_stop_error", {"error": str(e), "reason": reason})

    async def reset_emergency_stop(
        self,
        authorization_code: str,
        reset_by: str,
        pin_session_id: str | None = None,
    ) -> bool:
        """
        Reset emergency stop after manual authorization.

        Args:
            authorization_code: Authorization code for reset (legacy support)
            reset_by: Who is resetting the emergency stop
            pin_session_id: PIN session ID for enhanced authorization

        Returns:
            True if reset was successful
        """
        if not self._emergency_stop_active:
            logger.info("No emergency stop active to reset")
            return True

        # Enhanced authorization with PIN support
        authorized = False
        auth_method = "unknown"

        # Try PIN authorization first (preferred method)
        if pin_session_id and self.pin_manager:
            try:
                authorized = await self.pin_manager.authorize_operation(
                    session_id=pin_session_id, operation="emergency_reset", user_id=reset_by
                )
                auth_method = "pin_session"
                auth_status = "succeeded" if authorized else "failed"
                logger.info("PIN authorization %s for emergency reset", auth_status)
            except Exception as e:
                logger.error("PIN authorization error: %s", e)
                authorized = False

        # Fallback to legacy authorization code (for backward compatibility)
        if not authorized and authorization_code:
            if authorization_code == "SAFETY_OVERRIDE_ADMIN":
                authorized = True
                auth_method = "legacy_code"
                logger.warning("Emergency stop reset using legacy authorization code")
            else:
                logger.warning("Invalid legacy authorization code for emergency stop reset")

        if not authorized:
            await self._audit_log_event(
                "emergency_stop_reset_failed",
                {
                    "reset_by": reset_by,
                    "auth_method": auth_method,
                    "pin_session_id": pin_session_id,
                    "reason": "Authorization failed",
                },
            )
            return False

        logger.info("Resetting emergency stop with %s authorization", auth_method)

        self._emergency_stop_active = False
        self._emergency_stop_reason = None
        self._emergency_stop_triggered_by = None
        self._emergency_stop_time = None

        await self._audit_log_event(
            "emergency_stop_reset",
            {
                "reset_by": reset_by,
                "auth_method": auth_method,
                "pin_session_id": pin_session_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        # Enhanced security audit logging
        if self.security_audit_service:
            await self.security_audit_service.log_security_event(
                event_type="emergency_stop_reset",
                severity="high",
                user_id=reset_by,
                details={
                    "auth_method": auth_method,
                    "pin_session_used": pin_session_id is not None,
                    "reset_successful": True,
                },
                emergency_context=False,  # Emergency is being cleared
            )

        # Note: Individual features and interlocks must be manually re-enabled
        # This requires explicit operator action to ensure safety

        return True

    async def emergency_stop_with_pin(
        self,
        pin_session_id: str,
        reason: str,
        triggered_by: str,
    ) -> bool:
        """
        Trigger emergency stop using PIN authorization.

        Args:
            pin_session_id: PIN session ID for authorization
            reason: Reason for emergency stop
            triggered_by: User triggering the emergency stop

        Returns:
            True if emergency stop was successfully triggered
        """
        if not self.pin_manager:
            logger.error("PIN manager not available for emergency stop")
            return False

        # Authorize the emergency stop operation
        try:
            authorized = await self.pin_manager.authorize_operation(
                session_id=pin_session_id, operation="emergency_stop", user_id=triggered_by
            )

            if not authorized:
                logger.warning("Emergency stop authorization failed for user %s", triggered_by)
                await self._audit_log_event(
                    "emergency_stop_auth_failed",
                    {
                        "triggered_by": triggered_by,
                        "reason": reason,
                        "pin_session_id": pin_session_id,
                    },
                )

                # Enhanced security audit logging for failed authorization
                if self.security_audit_service:
                    await self.security_audit_service.log_security_event(
                        event_type="unauthorized_access",
                        severity="high",
                        user_id=triggered_by,
                        details={
                            "attempted_operation": "emergency_stop_with_pin",
                            "failure_reason": "pin_authorization_failed",
                            "pin_session_id": pin_session_id,
                        },
                        emergency_context=True,
                    )
                return False

            # Proceed with emergency stop
            await self.trigger_emergency_stop(reason, triggered_by)

            logger.warning(
                "PIN-authorized emergency stop triggered by %s: %s", triggered_by, reason
            )
            return True

        except Exception as e:
            logger.error("Error during PIN-authorized emergency stop: %s", e)
            await self._audit_log_event(
                "emergency_stop_pin_error",
                {
                    "triggered_by": triggered_by,
                    "reason": reason,
                    "error": str(e),
                },
            )
            return False

    async def validate_safety_operation(
        self,
        operation_type: str,
        user_id: str,
        source_ip: str | None = None,
        is_admin: bool = False,
        entity_id: str | None = None,
        details: dict | None = None,
    ) -> bool:
        """
        Validate a safety operation with rate limiting and audit logging.

        Args:
            operation_type: Type of operation (emergency, safety, control)
            user_id: User performing the operation
            source_ip: Source IP address for rate limiting
            is_admin: Whether user has admin privileges
            entity_id: Entity being operated on
            details: Additional operation details

        Returns:
            bool: True if operation is allowed
        """
        if not self.security_audit_service:
            # If no security audit service, allow operation (backward compatibility)
            return True

        # Determine endpoint category for rate limiting
        category_map = {
            "emergency": "emergency",
            "safety": "safety",
            "control": "safety",
            "pin_auth": "pin_auth",
        }
        category = category_map.get(operation_type, "safety")

        # Check rate limits
        identifier = source_ip or user_id
        rate_limit_ok = await self.security_audit_service.check_rate_limit(
            identifier=identifier,
            endpoint_category=category,
            is_admin=is_admin,
            source_ip=source_ip,
        )

        if not rate_limit_ok:
            # Log rate limit violation
            await self.security_audit_service.log_security_event(
                event_type="rate_limit_exceeded",
                severity="medium",
                user_id=user_id,
                source_ip=source_ip,
                details={
                    "operation_type": operation_type,
                    "category": category,
                    "entity_id": entity_id,
                    "blocked_reason": "rate_limit_exceeded",
                },
            )
            logger.warning("Rate limit exceeded for %s operation by %s", operation_type, user_id)
            return False

        # Log successful validation
        severity = "high" if operation_type == "emergency" else "medium"
        await self.security_audit_service.log_security_event(
            event_type="entity_control_success"
            if operation_type == "control"
            else "safety_operation_authorized",
            severity=severity,
            user_id=user_id,
            source_ip=source_ip,
            entity_id=entity_id,
            details={
                "operation_type": operation_type,
                "category": category,
                "validation_passed": True,
                **(details or {}),
            },
            emergency_context=self._emergency_stop_active,
        )

        return True

    async def reset_emergency_stop_with_pin(
        self,
        pin_session_id: str,
        reset_by: str,
    ) -> bool:
        """
        Reset emergency stop using PIN authorization only.

        Args:
            pin_session_id: PIN session ID for authorization
            reset_by: User resetting the emergency stop

        Returns:
            True if reset was successful
        """
        return await self.reset_emergency_stop(
            authorization_code="",  # No legacy code
            reset_by=reset_by,
            pin_session_id=pin_session_id,
        )

    async def override_interlock_with_pin(
        self,
        pin_session_id: str,
        interlock_name: str,
        reason: str,
        duration_minutes: int,
        overridden_by: str,
    ) -> bool:
        """
        Override a safety interlock using PIN authorization.

        Args:
            pin_session_id: PIN session ID for authorization
            interlock_name: Name of the interlock to override
            reason: Reason for overriding the interlock
            duration_minutes: How long the override should last
            overridden_by: User performing the override

        Returns:
            True if override was successful
        """
        if not self.pin_manager:
            logger.error("PIN manager not available for interlock override")
            return False

        # Check if interlock exists
        if interlock_name not in self._interlocks:
            logger.warning("Interlock '%s' not found", interlock_name)
            return False

        # Authorize the override operation
        try:
            authorized = await self.pin_manager.authorize_operation(
                session_id=pin_session_id, operation="interlock_override", user_id=overridden_by
            )

            if not authorized:
                logger.warning("Interlock override authorization failed for user %s", overridden_by)
                await self._audit_log_event(
                    "interlock_override_auth_failed",
                    {
                        "overridden_by": overridden_by,
                        "interlock_name": interlock_name,
                        "reason": reason,
                        "pin_session_id": pin_session_id,
                    },
                )

                # Enhanced security audit logging for failed authorization
                if self.security_audit_service:
                    await self.security_audit_service.log_security_event(
                        event_type="unauthorized_access",
                        severity="high",
                        user_id=overridden_by,
                        details={
                            "attempted_operation": "override_interlock_with_pin",
                            "failure_reason": "pin_authorization_failed",
                            "interlock_name": interlock_name,
                            "pin_session_id": pin_session_id,
                        },
                        emergency_context=self._emergency_stop_active,
                    )
                return False

            # Calculate expiration time
            expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)

            # Override the interlock
            interlock = self._interlocks[interlock_name]
            await interlock.override(
                session_id=pin_session_id,
                reason=reason,
                expires_at=expires_at,
                overridden_by=overridden_by,
            )

            # Track the override
            self._active_overrides[interlock_name] = expires_at

            # Audit log the override
            await self._audit_log_event(
                "interlock_override_activated",
                {
                    "interlock_name": interlock_name,
                    "overridden_by": overridden_by,
                    "reason": reason,
                    "duration_minutes": duration_minutes,
                    "expires_at": expires_at.isoformat(),
                    "pin_session_id": pin_session_id,
                },
            )

            # Enhanced security audit logging
            if self.security_audit_service:
                await self.security_audit_service.log_security_event(
                    event_type="safety_interlock_overridden",
                    severity="high",
                    user_id=overridden_by,
                    details={
                        "interlock_name": interlock_name,
                        "reason": reason,
                        "duration_minutes": duration_minutes,
                        "expires_at": expires_at.isoformat(),
                        "authorization_method": "pin_session",
                    },
                    emergency_context=self._emergency_stop_active,
                )

            logger.warning(
                "PIN-authorized interlock override: %s by %s for %d minutes",
                interlock_name,
                overridden_by,
                duration_minutes,
            )
            return True

        except Exception as e:
            logger.error("Error during PIN-authorized interlock override: %s", e)
            await self._audit_log_event(
                "interlock_override_error",
                {
                    "interlock_name": interlock_name,
                    "overridden_by": overridden_by,
                    "reason": reason,
                    "error": str(e),
                },
            )
            return False

    def clear_interlock_override(self, interlock_name: str) -> bool:
        """
        Clear an active interlock override.

        Args:
            interlock_name: Name of the interlock to clear

        Returns:
            True if override was cleared successfully
        """
        if interlock_name not in self._interlocks:
            logger.warning("Interlock '%s' not found", interlock_name)
            return False

        interlock = self._interlocks[interlock_name]
        override_info = interlock.get_override_info()
        if not override_info:
            logger.info("Interlock '%s' is not currently overridden", interlock_name)
            return False

        # Clear the override
        interlock.clear_override()

        # Remove from active overrides tracking
        self._active_overrides.pop(interlock_name, None)

        # Synchronous audit log for compatibility
        self._add_audit_log_entry(
            "interlock_override_cleared",
            {
                "interlock_name": interlock_name,
                "cleared_at": datetime.now(UTC).isoformat(),
            },
        )

        logger.info("Interlock override cleared for '%s'", interlock_name)
        return True

    async def enter_maintenance_mode_with_pin(
        self,
        pin_session_id: str,
        reason: str,
        duration_minutes: int,
        entered_by: str,
    ) -> bool:
        """
        Enter maintenance mode using PIN authorization.

        In maintenance mode, certain safety interlocks may be relaxed
        for service operations. Requires PIN authorization.

        Args:
            pin_session_id: PIN session ID for authorization
            reason: Reason for entering maintenance mode
            duration_minutes: How long maintenance mode should last
            entered_by: User entering maintenance mode

        Returns:
            True if maintenance mode was successfully entered
        """
        if not self.pin_manager:
            logger.error("PIN manager not available for maintenance mode")
            return False

        # Check if already in maintenance mode
        if self._operational_mode == SystemOperationalMode.MAINTENANCE:
            logger.warning("System already in maintenance mode")
            return False

        # Authorize the maintenance mode operation
        try:
            authorized = await self.pin_manager.authorize_operation(
                session_id=pin_session_id, operation="maintenance_mode", user_id=entered_by
            )

            if not authorized:
                logger.warning("Maintenance mode authorization failed for user %s", entered_by)
                await self._audit_log_event(
                    "maintenance_mode_auth_failed",
                    {
                        "entered_by": entered_by,
                        "reason": reason,
                        "pin_session_id": pin_session_id,
                    },
                )

                # Enhanced security audit logging for failed authorization
                if self.security_audit_service:
                    await self.security_audit_service.log_security_event(
                        event_type="unauthorized_access",
                        severity="high",
                        user_id=entered_by,
                        details={
                            "attempted_operation": "enter_maintenance_mode_with_pin",
                            "failure_reason": "pin_authorization_failed",
                            "pin_session_id": pin_session_id,
                        },
                        emergency_context=self._emergency_stop_active,
                    )
                return False

            # Calculate expiration time
            expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)

            # Enter maintenance mode
            previous_mode = self._operational_mode
            self._operational_mode = SystemOperationalMode.MAINTENANCE
            self._mode_session_id = pin_session_id
            self._mode_entered_by = entered_by
            self._mode_entered_at = datetime.now(UTC)
            self._mode_expires_at = expires_at

            # Audit log the mode change
            await self._audit_log_event(
                "maintenance_mode_entered",
                {
                    "previous_mode": previous_mode.value,
                    "entered_by": entered_by,
                    "reason": reason,
                    "duration_minutes": duration_minutes,
                    "expires_at": expires_at.isoformat(),
                    "pin_session_id": pin_session_id,
                },
            )

            # Enhanced security audit logging
            if self.security_audit_service:
                await self.security_audit_service.log_security_event(
                    event_type="maintenance_mode_activated",
                    severity="high",
                    user_id=entered_by,
                    details={
                        "reason": reason,
                        "duration_minutes": duration_minutes,
                        "expires_at": expires_at.isoformat(),
                        "authorization_method": "pin_session",
                        "previous_mode": previous_mode.value,
                    },
                    emergency_context=self._emergency_stop_active,
                )

            logger.warning(
                "MAINTENANCE MODE ACTIVATED by %s for %d minutes: %s",
                entered_by,
                duration_minutes,
                reason,
            )
            return True

        except Exception as e:
            logger.error("Error during PIN-authorized maintenance mode entry: %s", e)
            await self._audit_log_event(
                "maintenance_mode_error",
                {
                    "entered_by": entered_by,
                    "reason": reason,
                    "error": str(e),
                },
            )
            return False

    async def exit_maintenance_mode_with_pin(
        self,
        pin_session_id: str,
        exited_by: str,
    ) -> bool:
        """
        Exit maintenance mode using PIN authorization.

        Returns system to normal operational mode with all safety
        interlocks fully active.

        Args:
            pin_session_id: PIN session ID for authorization
            exited_by: User exiting maintenance mode

        Returns:
            True if maintenance mode was successfully exited
        """
        if not self.pin_manager:
            logger.error("PIN manager not available for maintenance mode exit")
            return False

        # Check if in maintenance mode
        if self._operational_mode != SystemOperationalMode.MAINTENANCE:
            logger.info("System not in maintenance mode")
            return True  # Already in normal mode

        # Verify the PIN session matches or is a new valid session
        try:
            # Allow exit with either the original session or a new authorized session
            authorized = await self.pin_manager.authorize_operation(
                session_id=pin_session_id, operation="maintenance_exit", user_id=exited_by
            )

            if not authorized:
                logger.warning("Maintenance mode exit authorization failed for user %s", exited_by)
                await self._audit_log_event(
                    "maintenance_mode_exit_auth_failed",
                    {
                        "exited_by": exited_by,
                        "pin_session_id": pin_session_id,
                        "original_session_id": self._mode_session_id,
                    },
                )
                return False

            # Calculate maintenance duration
            duration_minutes = 0
            if self._mode_entered_at:
                duration = datetime.now(UTC) - self._mode_entered_at
                duration_minutes = int(duration.total_seconds() / 60)

            # Exit maintenance mode
            self._operational_mode = SystemOperationalMode.NORMAL
            original_entered_by = self._mode_entered_by
            self._mode_session_id = None
            self._mode_entered_by = None
            self._mode_entered_at = None
            self._mode_expires_at = None

            # Clear any active overrides that were part of maintenance
            cleared_overrides = [
                interlock_name
                for interlock_name in list(self._active_overrides.keys())
                if self.clear_interlock_override(interlock_name)
            ]

            # Audit log the mode change
            await self._audit_log_event(
                "maintenance_mode_exited",
                {
                    "exited_by": exited_by,
                    "originally_entered_by": original_entered_by,
                    "duration_minutes": duration_minutes,
                    "cleared_overrides": cleared_overrides,
                    "pin_session_id": pin_session_id,
                },
            )

            # Enhanced security audit logging
            if self.security_audit_service:
                await self.security_audit_service.log_security_event(
                    event_type="maintenance_mode_deactivated",
                    severity="high",
                    user_id=exited_by,
                    details={
                        "duration_minutes": duration_minutes,
                        "cleared_overrides_count": len(cleared_overrides),
                        "authorization_method": "pin_session",
                    },
                    emergency_context=self._emergency_stop_active,
                )

            logger.warning(
                "MAINTENANCE MODE EXITED by %s after %d minutes",
                exited_by,
                duration_minutes,
            )
            return True

        except Exception as e:
            logger.error("Error during PIN-authorized maintenance mode exit: %s", e)
            await self._audit_log_event(
                "maintenance_mode_exit_error",
                {
                    "exited_by": exited_by,
                    "error": str(e),
                },
            )
            return False

    def check_mode_expiration(self) -> None:
        """
        Check if the current operational mode has expired and revert to normal if needed.
        This should be called periodically by the health monitoring loop.
        """
        if (
            self._operational_mode != SystemOperationalMode.NORMAL
            and self._mode_expires_at
            and datetime.now(UTC) > self._mode_expires_at
        ):
            logger.warning(
                "Operational mode %s has expired, reverting to NORMAL mode",
                self._operational_mode.value,
            )

            # Clear mode session data
            expired_mode = self._operational_mode
            self._operational_mode = SystemOperationalMode.NORMAL
            self._mode_session_id = None
            self._mode_entered_by = None
            self._mode_entered_at = None
            self._mode_expires_at = None

            # Clear any active overrides
            for interlock_name in list(self._active_overrides.keys()):
                self.clear_interlock_override(interlock_name)

            # Synchronous audit log for compatibility
            self._add_audit_log_entry(
                "operational_mode_expired",
                {
                    "expired_mode": expired_mode.value,
                    "expired_at": datetime.now(UTC).isoformat(),
                },
            )

    async def enter_diagnostic_mode_with_pin(
        self,
        pin_session_id: str,
        reason: str,
        duration_minutes: int,
        entered_by: str,
    ) -> bool:
        """
        Enter diagnostic mode using PIN authorization.

        In diagnostic mode, system diagnostics and testing can be performed
        with modified safety constraints. Requires PIN authorization.

        Args:
            pin_session_id: PIN session ID for authorization
            reason: Reason for entering diagnostic mode
            duration_minutes: How long diagnostic mode should last
            entered_by: User entering diagnostic mode

        Returns:
            True if diagnostic mode was successfully entered
        """
        if not self.pin_manager:
            logger.error("PIN manager not available for diagnostic mode")
            return False

        # Check if already in diagnostic mode
        if self._operational_mode == SystemOperationalMode.DIAGNOSTIC:
            logger.warning("System already in diagnostic mode")
            return False

        # Authorize the diagnostic mode operation
        try:
            authorized = await self.pin_manager.authorize_operation(
                session_id=pin_session_id, operation="diagnostic_mode", user_id=entered_by
            )

            if not authorized:
                logger.warning("Diagnostic mode authorization failed for user %s", entered_by)
                await self._audit_log_event(
                    "diagnostic_mode_auth_failed",
                    {
                        "entered_by": entered_by,
                        "reason": reason,
                        "pin_session_id": pin_session_id,
                    },
                )

                # Enhanced security audit logging for failed authorization
                if self.security_audit_service:
                    await self.security_audit_service.log_security_event(
                        event_type="unauthorized_access",
                        severity="high",
                        user_id=entered_by,
                        details={
                            "attempted_operation": "enter_diagnostic_mode_with_pin",
                            "failure_reason": "pin_authorization_failed",
                            "pin_session_id": pin_session_id,
                        },
                        emergency_context=self._emergency_stop_active,
                    )
                return False

            # Calculate expiration time
            expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)

            # Enter diagnostic mode
            previous_mode = self._operational_mode
            self._operational_mode = SystemOperationalMode.DIAGNOSTIC
            self._mode_session_id = pin_session_id
            self._mode_entered_by = entered_by
            self._mode_entered_at = datetime.now(UTC)
            self._mode_expires_at = expires_at

            # Audit log the mode change
            await self._audit_log_event(
                "diagnostic_mode_entered",
                {
                    "previous_mode": previous_mode.value,
                    "entered_by": entered_by,
                    "reason": reason,
                    "duration_minutes": duration_minutes,
                    "expires_at": expires_at.isoformat(),
                    "pin_session_id": pin_session_id,
                },
            )

            # Enhanced security audit logging
            if self.security_audit_service:
                await self.security_audit_service.log_security_event(
                    event_type="diagnostic_mode_activated",
                    severity="high",
                    user_id=entered_by,
                    details={
                        "reason": reason,
                        "duration_minutes": duration_minutes,
                        "expires_at": expires_at.isoformat(),
                        "authorization_method": "pin_session",
                        "previous_mode": previous_mode.value,
                    },
                    emergency_context=self._emergency_stop_active,
                )

            logger.warning(
                "DIAGNOSTIC MODE ACTIVATED by %s for %d minutes: %s",
                entered_by,
                duration_minutes,
                reason,
            )
            return True

        except Exception as e:
            logger.error("Error during PIN-authorized diagnostic mode entry: %s", e)
            await self._audit_log_event(
                "diagnostic_mode_error",
                {
                    "entered_by": entered_by,
                    "reason": reason,
                    "error": str(e),
                },
            )
            return False

    async def exit_diagnostic_mode_with_pin(
        self,
        pin_session_id: str,
        exited_by: str,
    ) -> bool:
        """
        Exit diagnostic mode using PIN authorization.

        Returns system to normal operational mode with all safety
        constraints fully active.

        Args:
            pin_session_id: PIN session ID for authorization
            exited_by: User exiting diagnostic mode

        Returns:
            True if diagnostic mode was successfully exited
        """
        if not self.pin_manager:
            logger.error("PIN manager not available for diagnostic mode exit")
            return False

        # Check if in diagnostic mode
        if self._operational_mode != SystemOperationalMode.DIAGNOSTIC:
            logger.info("System not in diagnostic mode")
            return True  # Already in normal mode

        # Verify the PIN session matches or is a new valid session
        try:
            # Allow exit with either the original session or a new authorized session
            authorized = await self.pin_manager.authorize_operation(
                session_id=pin_session_id, operation="diagnostic_exit", user_id=exited_by
            )

            if not authorized:
                logger.warning("Diagnostic mode exit authorization failed for user %s", exited_by)
                await self._audit_log_event(
                    "diagnostic_mode_exit_auth_failed",
                    {
                        "exited_by": exited_by,
                        "pin_session_id": pin_session_id,
                        "original_session_id": self._mode_session_id,
                    },
                )
                return False

            # Calculate diagnostic duration
            duration_minutes = 0
            if self._mode_entered_at:
                duration = datetime.now(UTC) - self._mode_entered_at
                duration_minutes = int(duration.total_seconds() / 60)

            # Exit diagnostic mode
            self._operational_mode = SystemOperationalMode.NORMAL
            original_entered_by = self._mode_entered_by
            self._mode_session_id = None
            self._mode_entered_by = None
            self._mode_entered_at = None
            self._mode_expires_at = None

            # Clear any active overrides that were part of diagnostics
            cleared_overrides = [
                interlock_name
                for interlock_name in list(self._active_overrides.keys())
                if self.clear_interlock_override(interlock_name)
            ]

            # Audit log the mode change
            await self._audit_log_event(
                "diagnostic_mode_exited",
                {
                    "exited_by": exited_by,
                    "originally_entered_by": original_entered_by,
                    "duration_minutes": duration_minutes,
                    "cleared_overrides": cleared_overrides,
                    "pin_session_id": pin_session_id,
                },
            )

            # Enhanced security audit logging
            if self.security_audit_service:
                await self.security_audit_service.log_security_event(
                    event_type="diagnostic_mode_deactivated",
                    severity="high",
                    user_id=exited_by,
                    details={
                        "duration_minutes": duration_minutes,
                        "cleared_overrides_count": len(cleared_overrides),
                        "authorization_method": "pin_session",
                    },
                    emergency_context=self._emergency_stop_active,
                )

            logger.warning(
                "DIAGNOSTIC MODE EXITED by %s after %d minutes",
                exited_by,
                duration_minutes,
            )
            return True

        except Exception as e:
            logger.error("Error during PIN-authorized diagnostic mode exit: %s", e)
            await self._audit_log_event(
                "diagnostic_mode_exit_error",
                {
                    "exited_by": exited_by,
                    "error": str(e),
                },
            )
            return False

    async def _execute_emergency_stop_actions(self) -> None:
        """Execute emergency stop safety actions."""
        self._active_safety_actions = []

        # 1. Position-critical features to safe shutdown
        position_critical_count = 0
        for feature_name, feature in self.feature_manager.features.items():
            if (
                hasattr(feature, "_safety_classification")
                and feature._safety_classification == SafetyClassification.POSITION_CRITICAL
            ):
                position_critical_count += 1
                if feature.enabled and feature.state != FeatureState.SAFE_SHUTDOWN:
                    logger.critical("Emergency stop: Setting %s to SAFE_SHUTDOWN", feature_name)
                    feature.state = FeatureState.SAFE_SHUTDOWN

        if position_critical_count > 0:
            self._active_safety_actions.append("position_critical_safe_shutdown")
            self._active_safety_actions.append("maintain_position")

        # 2. Engage all safety interlocks
        for interlock in self._interlocks.values():
            if not interlock.is_engaged:
                await interlock.engage(f"Emergency stop: {self._emergency_stop_reason}")
                self._active_safety_actions.append(f"interlock_engaged_{interlock.name}")

        # 3. Enter system-wide safe state
        await self._enter_safe_state(f"Emergency stop: {self._emergency_stop_reason}")

    async def check_all_interlocks(self) -> None:
        """Check all safety interlocks and engage if needed."""
        results = await self.check_safety_interlocks()

        # Count violations
        violations = 0
        for name, (satisfied, _reason) in results.items():
            if not satisfied:
                violations += 1
                if name not in self._active_safety_actions:
                    self._active_safety_actions.append(f"interlock_violated_{name}")

        # Multiple violations trigger emergency stop
        if violations >= self.MULTIPLE_VIOLATION_THRESHOLD:
            await self.trigger_emergency_stop(
                f"Multiple interlock violations: {violations}", "safety_monitoring"
            )

    async def _check_interlock_conditions(self, interlock: SafetyInterlock) -> bool:
        """Check if interlock conditions are violated."""
        conditions_met, reason = await interlock.check_conditions(self._system_state)
        return not conditions_met  # Return True if violated

    async def _perform_health_check(self) -> None:
        """Perform comprehensive health check."""
        self._last_health_check = datetime.now(UTC)

        # Check feature health
        health_report = await self.feature_manager.check_system_health()

        # Check for critical failures
        failed_critical = health_report.get("failed_critical", [])
        if failed_critical:
            await self.trigger_emergency_stop(
                f"Critical feature failed: {', '.join(failed_critical)}", "health_monitoring"
            )
            return

        # Check watchdog timeout
        if self._check_watchdog_timeout():
            await self.trigger_emergency_stop("Watchdog timeout", "watchdog_monitor")
            return

        # Update watchdog
        self._last_watchdog_kick = time.time()

        # Check all interlocks
        await self.check_all_interlocks()

        # Check operational mode expiration
        self.check_mode_expiration()

    def _check_watchdog_timeout(self) -> bool:
        """Check if watchdog has timed out."""
        if self._last_watchdog_kick == 0:
            return False
        return (time.time() - self._last_watchdog_kick) > self.watchdog_timeout

    def _add_audit_log_entry(self, event_type: str, details: dict[str, Any]) -> None:
        """Add entry to audit log (sync version for compatibility)."""
        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "details": details,
        }
        self._audit_log.append(audit_entry)

        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries :]

    async def get_safety_status_async(self) -> dict[str, Any]:
        """Get comprehensive safety status (async version)."""
        return self.get_safety_status()

    async def start_monitoring(self) -> None:
        """Start safety monitoring tasks (watchdog and health checks)."""
        logger.info("Starting safety monitoring with system state: %s", self._system_state)

        if self._health_monitor_task is None:
            self._health_monitor_task = asyncio.create_task(self._health_monitoring_loop())
            logger.info("Started safety health monitoring")

        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            logger.info("Started safety watchdog monitoring")

        # Initialize watchdog
        self._last_watchdog_kick = time.time()

    async def stop_monitoring(self) -> None:
        """Stop safety monitoring tasks."""
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._health_monitor_task
            self._health_monitor_task = None
            logger.info("Stopped safety health monitoring")

        if self._watchdog_task:
            self._watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watchdog_task
            self._watchdog_task = None
            logger.info("Stopped safety watchdog monitoring")

    async def _health_monitoring_loop(self) -> None:
        """ISO 26262-compliant health monitoring loop with watchdog pattern."""
        logger.info("Starting safety health monitoring loop")

        while not self._in_safe_state:
            try:
                start_time = time.time()

                # Check feature health via feature manager
                health_report = await self.feature_manager.check_system_health()

                # Check safety interlocks
                interlock_results = await self.check_safety_interlocks()

                # Update watchdog timer
                self._last_watchdog_kick = time.time()

                # Check for emergency conditions
                await self._check_emergency_conditions(health_report, interlock_results)

                # Check monitoring loop performance
                loop_duration = time.time() - start_time
                if loop_duration > self.health_check_interval:
                    logger.warning(
                        "Safety monitoring loop took %.2fs (threshold: %.2fs)",
                        loop_duration,
                        self.health_check_interval,
                    )

                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.critical("Safety monitoring loop failed: %s", e)
                await self._enter_safe_state(f"Monitoring loop failure: {e}")
                break

    async def _watchdog_loop(self) -> None:
        """Separate watchdog task to monitor health check kicks."""
        logger.info("Starting safety watchdog loop")

        while not self._in_safe_state:
            current_time = time.time()
            time_since_kick = current_time - self._last_watchdog_kick

            if time_since_kick > self.watchdog_timeout:
                logger.critical(
                    "Safety watchdog timeout detected (%.1fs > %.1fs)",
                    time_since_kick,
                    self.watchdog_timeout,
                )
                await self._enter_safe_state("Watchdog timeout")
                break

            await asyncio.sleep(1.0)

    async def _check_emergency_conditions(
        self, health_report: dict[str, Any], interlock_results: dict[str, tuple[bool, str]]
    ) -> None:
        """
        Check for conditions that require emergency stop.

        Args:
            health_report: System health report from feature manager
            interlock_results: Results from safety interlock checks
        """
        # Check for critical feature failures
        failed_critical = health_report.get("failed_critical", [])
        if failed_critical:
            logger.critical("Critical features failed: %s", failed_critical)
            await self.emergency_stop(f"Critical feature failure: {', '.join(failed_critical)}")

        # Check for multiple interlock violations
        violated_interlocks = [
            name for name, (satisfied, _) in interlock_results.items() if not satisfied
        ]

        multiple_violation_threshold = 3
        if len(violated_interlocks) >= multiple_violation_threshold:  # Multiple safety violations
            logger.critical("Multiple safety interlocks violated: %s", violated_interlocks)
            await self.emergency_stop(
                f"Multiple interlock violations: {', '.join(violated_interlocks)}"
            )

    async def _enter_safe_state(self, reason: str) -> None:
        """
        Enter system-wide safe state.

        Args:
            reason: Reason for entering safe state
        """
        if self._in_safe_state:
            return  # Already in safe state

        self._in_safe_state = True
        logger.critical("=== ENTERING SAFE STATE ===")
        logger.critical("Reason: %s", reason)

        await self._audit_log_event(
            "safe_state_entered", {"reason": reason, "timestamp": datetime.now(UTC).isoformat()}
        )

        try:
            # Capture current device states for forensics
            system_snapshot = dict(self._system_state)
            logger.info("System state snapshot: %s", system_snapshot)

            # Set all safety-critical features to safe shutdown
            await self._shutdown_safety_critical_features()

            # Engage all safety interlocks
            for interlock in self._interlocks.values():
                if not interlock.is_engaged:
                    await interlock.engage(f"Safe state: {reason}")

            logger.critical("=== SAFE STATE ESTABLISHED ===")

        except Exception as e:
            logger.critical("Failed to enter safe state: %s", e)
            await self._audit_log_event("safe_state_error", {"error": str(e), "reason": reason})

    async def _shutdown_safety_critical_features(self) -> None:
        """Shut down safety-critical features in controlled manner."""
        for feature_name, feature in self.feature_manager.features.items():
            if hasattr(feature, "_safety_classification"):
                classification = feature._safety_classification  # noqa: SLF001

                if (
                    classification
                    in [
                        SafetyClassification.CRITICAL,
                        SafetyClassification.POSITION_CRITICAL,
                    ]
                    and feature.enabled
                    and feature.state != FeatureState.SAFE_SHUTDOWN
                ):
                    logger.warning("Safe state: Setting %s to SAFE_SHUTDOWN", feature_name)
                    feature.state = FeatureState.SAFE_SHUTDOWN

    async def _audit_log_event(self, event_type: str, details: dict[str, Any]) -> None:
        """
        Log safety-critical event to audit trail.

        Args:
            event_type: Type of event
            details: Event details
        """
        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "details": details,
        }

        self._audit_log.append(audit_entry)

        # Trim audit log if it gets too large
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries :]

        # Log to standard logger as well
        logger.info("AUDIT: %s - %s", event_type, details)

    def get_audit_log(self, max_entries: int = 100) -> list[dict[str, Any]]:
        """
        Get recent audit log entries.

        Args:
            max_entries: Maximum number of entries to return

        Returns:
            List of audit log entries
        """
        return self._audit_log[-max_entries:] if self._audit_log else []

    def get_safety_status(self) -> dict[str, Any]:
        """
        Get comprehensive safety system status.

        Returns:
            Dictionary containing safety system status
        """
        return {
            "in_safe_state": self._in_safe_state,
            "emergency_stop_active": self._emergency_stop_active,
            "operational_mode": self._operational_mode.value,
            "mode_session": {
                "session_id": self._mode_session_id,
                "entered_by": self._mode_entered_by,
                "entered_at": self._mode_entered_at.isoformat() if self._mode_entered_at else None,
                "expires_at": self._mode_expires_at.isoformat() if self._mode_expires_at else None,
            }
            if self._operational_mode != SystemOperationalMode.NORMAL
            else None,
            "active_overrides": {
                name: expiry.isoformat() for name, expiry in self._active_overrides.items()
            },
            "watchdog_timeout": self.watchdog_timeout,
            "time_since_last_kick": time.time() - self._last_watchdog_kick,
            "interlocks": {
                name: {
                    "engaged": interlock.is_engaged,
                    "feature": interlock.feature_name,
                    "conditions": interlock.interlock_conditions,
                    "engagement_time": interlock.engagement_time.isoformat()
                    if interlock.engagement_time
                    else None,
                    "engagement_reason": interlock.engagement_reason,
                }
                for name, interlock in self._interlocks.items()
            },
            "system_state": dict(self._system_state),
            "audit_log_entries": len(self._audit_log),
            "emergency_stop_reason": self._emergency_stop_reason,
            "active_safety_actions": list(self._active_safety_actions),
        }
