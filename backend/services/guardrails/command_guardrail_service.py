"""
Guardrail service for the API command-validation tier.

Implements defense-in-depth API guardrail patterns including:
- Interlocks for position-critical commands (refuse to forward unsafe frames)
- Command halt on the orchestration loop
- Watchdog monitoring of dependent services
- Audit logging for command-validation operations
- Enhanced security audit logging and rate limiting

"Safety" naming is historical; the OEM Firefly MIRA panel owns the actual
vehicle safety case. CoachIQ refuses to forward bad commands; it does not
enforce physical-command preconditions. See
`docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`.
"""

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from backend.core.guardrail_interfaces import CommandHaltAction

logger = logging.getLogger(__name__)


class SystemOperationalMode(str, Enum):
    """
    Operational modes for the guardrail tier.

    Inspired by classic operational-mode patterns from safety-of-the-intended-
    function literature, but applied here to API guardrails (see ADR-0004):
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


class CommandPrecondition:
    """
    Command precondition for position-critical features.

    Prevents unsafe operations and enforces guardrail constraints
    for physical positioning systems like slides, awnings, leveling jacks.
    """

    def __init__(
        self,
        name: str,
        feature_name: str,
        interlock_conditions: list[str],
        command_halt_action: CommandHaltAction = CommandHaltAction.BLOCK_COMMANDS,
    ):
        """
        Initialize command precondition.

        Args:
            name: Unique identifier for this interlock
            feature_name: Name of the feature this interlock protects
            interlock_conditions: List of conditions that must be met
            command_halt_action: Action to take when interlock is triggered
        """
        self.name = name
        self.feature_name = feature_name
        self.interlock_conditions = interlock_conditions
        self.command_halt_action = command_halt_action
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

    async def _evaluate_condition(  # noqa: PLR0911 - condition table is intentionally explicit
        self, condition: str, system_state: dict[str, Any]
    ) -> bool:
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
        Engage the command precondition.

        Args:
            reason: Reason for engaging the interlock
        """
        if not self.is_engaged:
            self.is_engaged = True
            self.engagement_time = datetime.now(UTC)
            self.engagement_reason = reason

            logger.warning(
                "Command precondition '%s' ENGAGED for feature '%s': %s",
                self.name,
                self.feature_name,
                reason,
            )

    async def disengage(self, reason: str = "Manual override") -> None:
        """
        Disengage the command precondition.

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
                "Command precondition '%s' DISENGAGED for feature '%s' after %.1fs: %s",
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
        Override the command precondition temporarily.

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
            "Command precondition '%s' OVERRIDDEN for feature '%s' by %s: %s (expires: %s)",
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
                "Command precondition '%s' override CLEARED for feature '%s'",
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


class CommandGuardrailService:
    """
    API command-validation guardrail service.

    Implements defense-in-depth API guardrail patterns including interlocks,
    command halt on the orchestration loop, watchdog monitoring, and audit
    logging. "Safety" naming is historical; the OEM Firefly MIRA panel owns
    the vehicle safety case (see ADR-0004).

    The service initializes with a safe default system state representing
    a parked and stabilized RV with parking brake engaged, leveling jacks
    deployed, and transmission in park to prevent false guardrail violations
    at startup.
    """

    # Constants
    MULTIPLE_VIOLATION_THRESHOLD = 3  # Number of violations to trigger command halt

    def __init__(
        self,
        guardrail_coordinator=None,
        health_check_interval: float = 5.0,
        watchdog_timeout: float = 15.0,
        pin_manager=None,
        security_audit_service=None,
    ):
        """
        Initialize command guardrail service with a guardrail coordinator.

        Args:
            guardrail_coordinator: Coordinator/health adapter for guardrail-aware services
            health_check_interval: Interval between health checks (seconds)
            watchdog_timeout: Watchdog timeout threshold (seconds)
            pin_manager: Optional PIN manager for enhanced authorization
            security_audit_service: Optional security audit service for enhanced logging
        """
        self.guardrail_coordinator = guardrail_coordinator
        self.health_check_interval = health_check_interval
        self.watchdog_timeout = watchdog_timeout
        self.pin_manager = pin_manager
        self.security_audit_service = security_audit_service

        # Safety state tracking
        self._in_command_halt_state = False
        self._command_halt_active = False
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
        self._interlocks: dict[str, CommandPrecondition] = {}
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

        # Command halt tracking
        self._halt_command_emission_reason: str | None = None
        self._halt_command_emission_triggered_by: str | None = None
        self._halt_command_emission_time: datetime | None = None
        self._active_guardrail_actions: list[str] = []
        self._last_health_check: datetime | None = None

        # Initialize default interlocks
        self._setup_default_interlocks()

        logger.info(
            "CommandGuardrailService initialized with default system state: %s",
            self._system_state,
        )

    def _setup_default_interlocks(self) -> None:
        """Set up default command preconditions for common RV systems."""

        # Slide room command preconditions
        slide_interlocks = [
            "vehicle_not_moving",
            "parking_brake_engaged",
            "leveling_jacks_deployed",
            "transmission_in_park",
        ]

        self.add_interlock(
            CommandPrecondition(
                name="slide_room_precondition",
                feature_name="firefly",  # Firefly controls slide rooms
                interlock_conditions=slide_interlocks,
                command_halt_action=CommandHaltAction.BLOCK_COMMANDS,
            )
        )

        # Awning command preconditions
        awning_interlocks = [
            "vehicle_not_moving",
            "parking_brake_engaged",
        ]

        self.add_interlock(
            CommandPrecondition(
                name="awning_precondition",
                feature_name="firefly",  # Firefly controls awnings
                interlock_conditions=awning_interlocks,
                command_halt_action=CommandHaltAction.BLOCK_COMMANDS,
            )
        )

        # Leveling jack command preconditions
        leveling_interlocks = [
            "vehicle_not_moving",
            "parking_brake_engaged",
            "transmission_in_park",
            "engine_not_running",
        ]

        self.add_interlock(
            CommandPrecondition(
                name="leveling_jack_precondition",
                feature_name="spartan_k2",  # Spartan K2 controls leveling
                interlock_conditions=leveling_interlocks,
                command_halt_action=CommandHaltAction.BLOCK_COMMANDS,
            )
        )

    def add_interlock(self, interlock: CommandPrecondition) -> None:
        """
        Add a command precondition to the system.

        Args:
            interlock: CommandPrecondition instance to add
        """
        self._interlocks[interlock.name] = interlock
        logger.info(
            "Added command precondition: %s for feature %s", interlock.name, interlock.feature_name
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

    async def check_command_preconditions(self) -> dict[str, tuple[bool, str]]:
        """
        Check all command preconditions and engage/disengage as needed.

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

                # Enhanced security audit logging for command precondition violations
                if self.security_audit_service:
                    await self.security_audit_service.log_security_event(
                        event_type="safety_interlock_violated",
                        severity="high",
                        details={
                            "interlock_name": interlock_name,
                            "feature_name": interlock.feature_name,
                            "violation_reason": reason,
                            "command_halt_action": interlock.command_halt_action.value,
                        },
                        emergency_context=self._command_halt_active,
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

    async def halt_command_emission(  # noqa: C901 - command-halt flow is kept explicit
        self, reason: str = "Manual trigger", triggered_by: str = "system"
    ) -> bool:
        """Halt CoachIQ command emission and record the cause."""
        if self._command_halt_active:
            logger.warning("Command halt already active")
            return False

        self._command_halt_active = True
        self._halt_command_emission_reason = reason
        self._halt_command_emission_triggered_by = triggered_by
        self._halt_command_emission_time = datetime.now(UTC)

        await self._audit_log_event(
            "command_halt_activated",
            {
                "reason": reason,
                "triggered_by": triggered_by,
                "timestamp": self._halt_command_emission_time.isoformat(),
            },
        )

        if self.security_audit_service:
            await self.security_audit_service.log_security_event(
                event_type="command_halt_activated",
                severity="critical",
                user_id=triggered_by,
                details={"reason": reason, "method": "halt_command_emission"},
                emergency_context=True,
            )

        try:
            if self.guardrail_coordinator and hasattr(
                self.guardrail_coordinator, "halt_command_emission"
            ):
                logger.critical(
                    "Initiating coordinated command halt via GuardrailRuntimeCoordinator"
                )
                command_halt_results = await self.guardrail_coordinator.halt_command_emission(
                    reason=reason, triggered_by="command_guardrail_service"
                )
                successful_stops = sum(1 for success in command_halt_results.values() if success)
                failed_stops = sum(1 for success in command_halt_results.values() if not success)

                logger.critical(
                    "Command halt coordination complete: %d successful, %d failed",
                    successful_stops,
                    failed_stops,
                )

                if failed_stops > 0:
                    failed_services = [
                        name for name, success in command_halt_results.items() if not success
                    ]
                    logger.error("Command halt failed for services: %s", failed_services)

            else:
                logger.warning(
                    "GuardrailRuntimeCoordinator not available, using fallback command halt"
                )
                for service_name in self._get_command_halt_targets():
                    try:
                        service = (
                            self.guardrail_coordinator.get_service(service_name)
                            if self.guardrail_coordinator
                            else None
                        )
                        if service and hasattr(service, "halt_command_emission"):
                            logger.critical("Command halt target: %s", service_name)
                            await service.halt_command_emission(reason)
                    except Exception as e:
                        logger.error("Error halting service %s: %s", service_name, e)

            self._active_guardrail_actions = ["halt_command_emission"]
            for interlock in self._interlocks.values():
                if not interlock.is_engaged:
                    await interlock.engage(f"Command halt: {reason}")
                    self._active_guardrail_actions.append(f"precondition_engaged_{interlock.name}")

            self._in_command_halt_state = True
            logger.critical("Command emission halted: %s", reason)
            return True

        except Exception as e:
            logger.critical("Error during command halt: %s", e)
            await self._audit_log_event("command_halt_error", {"error": str(e), "reason": reason})
            return False

    def _get_command_halt_targets(self) -> list[str]:
        """
        Get list of CRITICAL-classified service names from GuardrailRuntimeCoordinator.

        Returns:
            List of service names classified CRITICAL that need command halt.
        """
        # Use GuardrailRuntimeCoordinator if available for accurate classification
        if self.guardrail_coordinator and hasattr(
            self.guardrail_coordinator, "get_command_halt_targets"
        ):
            return self.guardrail_coordinator.get_command_halt_targets()

        # Fallback: use the CAN facade as the single command-halt coordinator.
        fallback_critical_services = ["can_facade"]

        # Filter to only services that are actually registered and running
        if self.guardrail_coordinator:
            return [
                service_name
                for service_name in fallback_critical_services
                if self.guardrail_coordinator.has_service(service_name)
            ]

        return []

    async def clear_command_halt(
        self,
        authorization_code: str,
        reset_by: str,
        pin_session_id: str | None = None,
    ) -> bool:
        """
        Reset command halt after manual authorization.

        Args:
            authorization_code: Authorization code for reset (legacy support)
            reset_by: Who is resetting the command halt
            pin_session_id: PIN session ID for enhanced authorization

        Returns:
            True if reset was successful
        """
        if not self._command_halt_active:
            logger.info("No command halt active to reset")
            return True

        # Enhanced authorization with PIN support
        authorized = False
        auth_method = "unknown"

        # Try PIN authorization first (preferred method)
        if pin_session_id and self.pin_manager:
            try:
                authorized = await self.pin_manager.authorize_operation(
                    session_id=pin_session_id, operation="clear_command_halt", user_id=reset_by
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
                logger.warning("Command halt reset using legacy authorization code")
            else:
                logger.warning("Invalid legacy authorization code for command halt reset")

        if not authorized:
            await self._audit_log_event(
                "halt_command_emission_reset_failed",
                {
                    "reset_by": reset_by,
                    "auth_method": auth_method,
                    "pin_session_id": pin_session_id,
                    "reason": "Authorization failed",
                },
            )
            return False

        logger.info("Resetting command halt with %s authorization", auth_method)

        self._command_halt_active = False
        self._halt_command_emission_reason = None
        self._halt_command_emission_triggered_by = None
        self._halt_command_emission_time = None
        self._in_command_halt_state = False
        self._active_guardrail_actions.clear()

        for interlock in self._interlocks.values():
            await interlock.disengage("Command halt cleared")

        await self._audit_log_event(
            "halt_command_emission_reset",
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
                event_type="halt_command_emission_reset",
                severity="high",
                user_id=reset_by,
                details={
                    "auth_method": auth_method,
                    "pin_session_used": pin_session_id is not None,
                    "reset_successful": True,
                },
                emergency_context=False,  # Emergency is being cleared
            )

        return True

    async def halt_command_emission_with_pin(
        self,
        pin_session_id: str,
        reason: str,
        triggered_by: str,
    ) -> bool:
        """
        Trigger command halt using PIN authorization.

        Args:
            pin_session_id: PIN session ID for authorization
            reason: Reason for command halt
            triggered_by: User triggering the command halt

        Returns:
            True if command halt was successfully triggered
        """
        if not self.pin_manager:
            logger.error("PIN manager not available for command halt")
            return False

        # Authorize the command halt operation
        try:
            authorized = await self.pin_manager.authorize_operation(
                session_id=pin_session_id, operation="halt_command_emission", user_id=triggered_by
            )

            if not authorized:
                logger.warning("Command halt authorization failed for user %s", triggered_by)
                await self._audit_log_event(
                    "halt_command_emission_auth_failed",
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
                            "attempted_operation": "halt_command_emission_with_pin",
                            "failure_reason": "pin_authorization_failed",
                            "pin_session_id": pin_session_id,
                        },
                        emergency_context=True,
                    )
                return False

            # Proceed with command halt
            await self.halt_command_emission(reason, triggered_by)

            logger.warning("PIN-authorized command halt triggered by %s: %s", triggered_by, reason)
            return True

        except Exception as e:
            logger.error("Error during PIN-authorized command halt: %s", e)
            await self._audit_log_event(
                "halt_command_emission_pin_error",
                {
                    "triggered_by": triggered_by,
                    "reason": reason,
                    "error": str(e),
                },
            )
            return False

    async def validate_guardrail_operation(  # noqa: PLR0913 - API audit context is intentionally explicit
        self,
        operation_type: str,
        user_id: str,
        source_ip: str | None = None,
        is_admin: bool = False,
        entity_id: str | None = None,
        details: dict | None = None,
    ) -> bool:
        """
        Validate a guardrail operation with rate limiting and audit logging.

        Args:
            operation_type: Type of operation (command_halt, guardrail, control)
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
            "command_halt": "guardrail",
            "guardrail": "guardrail",
            "control": "guardrail",
            "pin_auth": "pin_auth",
        }
        category = category_map.get(operation_type, "guardrail")

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
        severity = "high" if operation_type == "command_halt" else "medium"
        await self.security_audit_service.log_security_event(
            event_type="entity_control_success"
            if operation_type == "control"
            else "guardrail_operation_authorized",
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
            emergency_context=self._command_halt_active,
        )

        return True

    async def clear_command_halt_with_pin(
        self,
        pin_session_id: str,
        reset_by: str,
    ) -> bool:
        """
        Reset command halt using PIN authorization only.

        Args:
            pin_session_id: PIN session ID for authorization
            reset_by: User resetting the command halt

        Returns:
            True if reset was successful
        """
        return await self.clear_command_halt(
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
        Override a command precondition using PIN authorization.

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
                        emergency_context=self._command_halt_active,
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
                    emergency_context=self._command_halt_active,
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

        In maintenance mode, certain command preconditions may be relaxed
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
                        emergency_context=self._command_halt_active,
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
                    emergency_context=self._command_halt_active,
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
                    emergency_context=self._command_halt_active,
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

            # Clear any active overrides. Pop directly first so orphaned
            # override entries (whose underlying interlock has been
            # unregistered) are still removed; then call the canonical
            # clear method to fire audit events for any that ARE registered.
            for interlock_name in list(self._active_overrides.keys()):
                self._active_overrides.pop(interlock_name, None)
                if interlock_name in self._interlocks:
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
        with modified guardrail constraints. Requires PIN authorization.

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
                        emergency_context=self._command_halt_active,
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
                    emergency_context=self._command_halt_active,
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
                    emergency_context=self._command_halt_active,
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

    async def _halt_command_emission_actions(self) -> None:
        """Execute command halt guardrail actions."""
        self._active_guardrail_actions = []

        # 1. Safety-critical services to safe shutdown
        guardrail_critical_services = self._get_command_halt_targets()
        safety_shutdown_count = 0

        for service_name in guardrail_critical_services:
            try:
                service = (
                    self.guardrail_coordinator.get_service(service_name)
                    if self.guardrail_coordinator
                    else None
                )
                if service:
                    safety_shutdown_count += 1
                    if hasattr(service, "halt_command_emission"):
                        logger.critical(
                            "Command halt action: Triggering safe shutdown for %s", service_name
                        )
                        await service.halt_command_emission("Safety system command halt")
                    else:
                        logger.warning(
                            "Service %s does not support halt_command_emission method", service_name
                        )
            except Exception as e:
                logger.error("Error executing command halt for service %s: %s", service_name, e)

        if safety_shutdown_count > 0:
            self._active_guardrail_actions.append("guardrail_critical_safe_shutdown")
            self._active_guardrail_actions.append("maintain_command_halt_state")

        # 2. Engage all command preconditions
        for interlock in self._interlocks.values():
            if not interlock.is_engaged:
                await interlock.engage(f"Command halt: {self._halt_command_emission_reason}")
                self._active_guardrail_actions.append(f"interlock_engaged_{interlock.name}")

        # 3. Enter system-wide command halt state
        await self._enter_command_halt_state(f"Command halt: {self._halt_command_emission_reason}")

    async def check_all_interlocks(self) -> None:
        """Check all command preconditions and engage if needed."""
        results = await self.check_command_preconditions()

        # Count violations
        violations = 0
        for name, (satisfied, _reason) in results.items():
            if not satisfied:
                violations += 1
                if name not in self._active_guardrail_actions:
                    self._active_guardrail_actions.append(f"interlock_violated_{name}")

        # Multiple violations trigger command halt
        if violations >= self.MULTIPLE_VIOLATION_THRESHOLD:
            await self.halt_command_emission(
                f"Multiple interlock violations: {violations}", "guardrail_monitoring"
            )

    async def _check_interlock_conditions(self, interlock: CommandPrecondition) -> bool:
        """Check if interlock conditions are violated."""
        conditions_met, _reason = await interlock.check_conditions(self._system_state)
        return not conditions_met  # Return True if violated

    async def _perform_health_check(self) -> None:  # noqa: C901, PLR0912
        """Perform comprehensive health check."""
        self._last_health_check = datetime.now(UTC)

        # Check service health via GuardrailRuntimeCoordinator
        if self.guardrail_coordinator and hasattr(
            self.guardrail_coordinator, "get_guardrail_status_summary"
        ):
            try:
                # Use comprehensive guardrail status from GuardrailRuntimeCoordinator
                guardrail_summary = await self.guardrail_coordinator.get_guardrail_status_summary()

                # Check for critical guardrail issues
                overall_status = guardrail_summary.get("overall_guardrail_status", "safe")
                unsafe_count = guardrail_summary.get("summary", {}).get("unsafe_count", 0)

                if overall_status == "unsafe" or unsafe_count > 0:
                    # Find which services are unsafe
                    failed_critical = []
                    for category in [
                        "critical_services",
                        "operational_services",
                        "maintenance_services",
                    ]:
                        services = guardrail_summary.get(category, {})
                        for service_name, status in services.items():
                            if status in ["unsafe", "halt_command_emission"]:
                                failed_critical.append(service_name)

                    if failed_critical:
                        await self.halt_command_emission(
                            f"Critical guardrail failure detected: {', '.join(failed_critical)}",
                            "health_monitoring",
                        )
                        return

                elif overall_status == "degraded":
                    logger.warning("System operating in degraded guardrail mode")

            except Exception as e:
                logger.error("Error checking guardrail status summary: %s", e)
                # Fallback to individual service checks
                failed_critical = []
                guardrail_critical_services = self._get_command_halt_targets()

                for service_name in guardrail_critical_services:
                    try:
                        status = self.guardrail_coordinator.get_service_status(service_name)
                        if status in ["FAILED", "DEGRADED"]:
                            failed_critical.append(service_name)
                    except Exception as e:
                        logger.error("Error checking health of service %s: %s", service_name, e)
                        failed_critical.append(service_name)

                # Check for critical failures
                if failed_critical:
                    await self.halt_command_emission(
                        f"Critical service failed: {', '.join(failed_critical)}",
                        "health_monitoring",
                    )
            return

        # Check watchdog timeout
        if self._check_watchdog_timeout():
            await self.halt_command_emission("Watchdog timeout", "watchdog_monitor")
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

    async def get_guardrail_status_async(self) -> dict[str, Any]:
        """Get comprehensive guardrail status (async version)."""
        return self.get_guardrail_status()

    async def start_monitoring(self) -> None:
        """Start guardrail monitoring tasks (watchdog and health checks)."""
        logger.info("Starting guardrail monitoring with system state: %s", self._system_state)

        if self._health_monitor_task is None:
            self._health_monitor_task = asyncio.create_task(self._health_monitoring_loop())
            logger.info("Started safety health monitoring")

        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            logger.info("Started guardrail watchdog monitoring")

        # Initialize watchdog
        self._last_watchdog_kick = time.time()

    async def stop_monitoring(self) -> None:
        """Stop guardrail monitoring tasks."""
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
            logger.info("Stopped guardrail watchdog monitoring")

    async def _health_monitoring_loop(self) -> None:
        """Health monitoring loop with watchdog pattern (see ADR-0004 for framing)."""
        logger.info("Starting safety health monitoring loop")

        while not self._in_command_halt_state:
            try:
                start_time = time.time()

                # Check service health via guardrail coordinator
                if self.guardrail_coordinator:
                    # Use guardrail coordinator to check service health
                    health_summary = self.guardrail_coordinator.get_health_summary()
                    failed_services = [
                        name
                        for name, status in health_summary.items()
                        if status.get("status") in ["FAILED", "DEGRADED"]
                    ]

                    # Create health report compatible with existing logic
                    health_report = {
                        "failed_critical": [
                            s for s in failed_services if s in self._get_command_halt_targets()
                        ],
                        "healthy": len(failed_services) == 0,
                    }
                else:
                    # Fallback when guardrail coordinator not available
                    health_report = {"failed_critical": [], "healthy": True}

                # Check command preconditions
                interlock_results = await self.check_command_preconditions()

                # Update watchdog timer
                self._last_watchdog_kick = time.time()

                # Check for emergency conditions
                await self._check_emergency_conditions(health_report, interlock_results)

                # Check monitoring loop performance
                loop_duration = time.time() - start_time
                if loop_duration > self.health_check_interval:
                    logger.warning(
                        "Guardrail monitoring loop took %.2fs (threshold: %.2fs)",
                        loop_duration,
                        self.health_check_interval,
                    )

                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.critical("Guardrail monitoring loop failed: %s", e)
                await self._enter_command_halt_state(f"Monitoring loop failure: {e}")
                break

    async def _watchdog_loop(self) -> None:
        """Separate watchdog task to monitor health check kicks."""
        logger.info("Starting guardrail watchdog loop")

        while not self._in_command_halt_state:
            current_time = time.time()
            time_since_kick = current_time - self._last_watchdog_kick

            if time_since_kick > self.watchdog_timeout:
                logger.critical(
                    "Guardrail watchdog timeout detected (%.1fs > %.1fs)",
                    time_since_kick,
                    self.watchdog_timeout,
                )
                await self._enter_command_halt_state("Watchdog timeout")
                break

            await asyncio.sleep(1.0)

    async def _check_emergency_conditions(
        self, health_report: dict[str, Any], interlock_results: dict[str, tuple[bool, str]]
    ) -> None:
        """
        Check for conditions that require command halt.

        Args:
            health_report: System health report from service registry
            interlock_results: Results from command precondition checks
        """
        # Check for critical feature failures
        failed_critical = health_report.get("failed_critical", [])
        if failed_critical:
            logger.critical("Critical features failed: %s", failed_critical)
            await self.halt_command_emission(
                f"Critical feature failure: {', '.join(failed_critical)}"
            )

        # Check for multiple interlock violations
        violated_interlocks = [
            name for name, (satisfied, _) in interlock_results.items() if not satisfied
        ]

        multiple_violation_threshold = 3
        if len(violated_interlocks) >= multiple_violation_threshold:
            logger.critical("Multiple command preconditions violated: %s", violated_interlocks)
            await self.halt_command_emission(
                f"Multiple interlock violations: {', '.join(violated_interlocks)}"
            )

    async def _enter_command_halt_state(self, reason: str) -> None:
        """
        Enter system-wide command halt state.

        Args:
            reason: Reason for entering command halt state
        """
        if self._in_command_halt_state:
            return  # Already in command halt state

        self._in_command_halt_state = True
        logger.critical("=== ENTERING COMMAND HALT STATE ===")
        logger.critical("Reason: %s", reason)

        await self._audit_log_event(
            "command_halt_state_entered",
            {"reason": reason, "timestamp": datetime.now(UTC).isoformat()},
        )

        try:
            # Capture current device states for forensics
            system_snapshot = dict(self._system_state)
            logger.info("System state snapshot: %s", system_snapshot)

            # Set all CRITICAL-classified features to command halt.
            await self._shutdown_guardrail_critical_features()

            # Engage all command preconditions
            for interlock in self._interlocks.values():
                if not interlock.is_engaged:
                    await interlock.engage(f"Command halt state: {reason}")

            logger.critical("=== COMMAND HALT STATE ESTABLISHED ===")

        except Exception as e:
            logger.critical("Failed to enter command halt state: %s", e)
            await self._audit_log_event(
                "command_halt_state_error", {"error": str(e), "reason": reason}
            )

    async def _shutdown_guardrail_critical_features(self) -> None:
        """Shut down CRITICAL-classified services in controlled manner."""
        guardrail_critical_services = self._get_command_halt_targets()

        for service_name in guardrail_critical_services:
            try:
                service = (
                    self.guardrail_coordinator.get_service(service_name)
                    if self.guardrail_coordinator
                    else None
                )
                if service:
                    if hasattr(service, "halt_command_emission"):
                        logger.info("Command halt state shutdown: %s", service_name)
                        await service.halt_command_emission("Entering command halt state")
                    elif hasattr(service, "stop"):
                        logger.info("Command halt state shutdown: %s", service_name)
                        await service.stop()
            except Exception as e:
                logger.error("Error shutting down service %s: %s", service_name, e)

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for guardrail coordinator monitoring."""
        return {
            "healthy": not self._command_halt_active and not self._in_command_halt_state,
            "command_halt_active": self._command_halt_active,
            "in_command_halt_state": self._in_command_halt_state,
            "operational_mode": self._operational_mode.value,
            "active_interlocks": len([i for i in self._interlocks.values() if i.is_engaged]),
            "last_health_check": self._last_health_check.isoformat()
            if self._last_health_check
            else None,
        }

    async def stop(self) -> None:
        """Stop the safety service gracefully."""
        await self.stop_monitoring()

    async def _audit_log_event(self, event_type: str, details: dict[str, Any]) -> None:
        """
        Log a guardrail-tier event to the audit trail.

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

    def get_guardrail_status(self) -> dict[str, Any]:
        """
        Get comprehensive guardrail subsystem status.

        Returns:
            Dictionary containing guardrail subsystem status
        """
        return {
            "in_command_halt_state": self._in_command_halt_state,
            "command_halt_active": self._command_halt_active,
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
            "halt_command_emission_reason": self._halt_command_emission_reason,
            "active_guardrail_actions": list(self._active_guardrail_actions),
        }
