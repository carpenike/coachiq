"""
Centralized Safety State Engine for RV-C vehicle control system.

This module provides a centralized safety state management system that tracks
vehicle state transitions and enforces safety rules for all control operations.
Critical for preventing dangerous operations like slideout extension while moving.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class VehicleState(Enum):
    """Represents the current safety state of the vehicle."""

    UNKNOWN = "unknown"
    PARKED_SAFE = "parked_safe"  # Brake set, engine off
    PARKED_RUNNING = "parked_running"  # Brake set, engine on
    DRIVING = "driving"  # Moving
    UNSAFE = "unsafe"  # Invalid state combination


class SafetyEvent(Enum):
    """Safety-relevant events that can trigger state transitions."""

    PARKING_BRAKE_SET = "parking_brake_set"
    PARKING_BRAKE_RELEASED = "parking_brake_released"
    ENGINE_STARTED = "engine_started"
    ENGINE_STOPPED = "engine_stopped"
    VEHICLE_MOVING = "vehicle_moving"
    VEHICLE_STOPPED = "vehicle_stopped"
    TRANSMISSION_PARK = "transmission_park"
    TRANSMISSION_DRIVE = "transmission_drive"


@dataclass
class SafetyCommand:
    """Represents a safety command that needs to be executed."""

    command_type: str
    target_entity: str
    allowed: bool
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class StateData:
    """Internal vehicle state data."""

    parking_brake_set: bool | None = None
    engine_running: bool | None = None
    vehicle_speed: float | None = None  # mph or km/h
    transmission_gear: str | None = None
    last_updated: float = field(default_factory=time.time)


class SafetyStateEngine:
    """
    Centralized safety state management and operation validation.

    This engine tracks vehicle state based on incoming CAN messages and
    provides safety validation for all control operations. It maintains
    a state machine that prevents dangerous operations.
    """

    # Speed threshold for considering vehicle "moving" (mph)
    MOVING_SPEED_THRESHOLD = 0.5

    # Maximum time to consider state data valid (seconds)
    STATE_DATA_TIMEOUT = 30.0

    def __init__(self):
        """Initialize the safety state engine."""
        self.current_state = VehicleState.UNKNOWN
        self.state_data = StateData()
        self.transition_table = self._build_transition_table()
        self.observers: list[Callable[[SafetyCommand], None]] = []
        self._last_state_change = time.time()

    def process_event(self, event: SafetyEvent, data: dict[str, Any]) -> SafetyCommand | None:
        """
        Process a safety event and update vehicle state.

        Args:
            event: The safety event that occurred
            data: Additional data from the event

        Returns:
            SafetyCommand if action is required, None otherwise
        """
        logger.debug(f"Processing safety event: {event.value} with data: {data}")

        # Update internal state data
        self._update_state_data(event, data)

        # Check for state transition
        new_state = self._evaluate_current_state()
        if new_state != self.current_state:
            self._transition_to(new_state)

        # Evaluate safety rules and generate commands if needed
        return self._evaluate_safety_rules(event, data)

    def is_operation_safe(self, operation: str, entity: str) -> tuple[bool, str]:
        """
        Check if an operation is safe in the current vehicle state.

        Args:
            operation: The operation to validate (e.g., "slideout_extend")
            entity: The target entity for the operation

        Returns:
            Tuple of (is_safe, reason)
        """
        current_time = time.time()

        # Check if state data is too old
        if current_time - self.state_data.last_updated > self.STATE_DATA_TIMEOUT:
            return False, "State data too old - cannot ensure safety"

        # Vehicle-wide safety rules
        if self.current_state == VehicleState.DRIVING and operation in [
            "slideout_extend",
            "slideout_retract",
            "leveling_extend",
            "leveling_retract",
        ]:
            return False, f"Operation '{operation}' not allowed while vehicle is moving"

        if self.current_state == VehicleState.UNSAFE:
            return False, "Vehicle in unsafe state - no operations allowed"

        # Operation-specific safety rules
        if operation == "slideout_extend":
            if self.current_state not in [VehicleState.PARKED_SAFE, VehicleState.PARKED_RUNNING]:
                return False, f"Slideout extension not allowed in state {self.current_state.value}"

            if self.state_data.parking_brake_set is False:
                return False, "Slideout extension requires parking brake to be set"

        elif operation == "engine_start":
            if self.state_data.transmission_gear not in [None, "park", "P"]:
                return False, "Engine start not allowed when transmission not in park"

        elif operation in ["leveling_extend", "leveling_retract"]:
            if self.state_data.parking_brake_set is False:
                return False, "Leveling operations require parking brake to be set"

        return True, "Operation allowed"

    def add_observer(self, observer: Callable[[SafetyCommand], None]) -> None:
        """Add an observer to receive safety commands."""
        self.observers.append(observer)

    def remove_observer(self, observer: Callable[[SafetyCommand], None]) -> None:
        """Remove an observer."""
        if observer in self.observers:
            self.observers.remove(observer)

    def get_current_state(self) -> VehicleState:
        """Get the current vehicle safety state."""
        return self.current_state

    def get_state_data(self) -> StateData:
        """Get the current state data for debugging."""
        return self.state_data

    def _update_state_data(self, event: SafetyEvent, data: dict[str, Any]) -> None:
        """Update internal state data based on an event."""
        current_time = time.time()

        if event == SafetyEvent.PARKING_BRAKE_SET:
            self.state_data.parking_brake_set = True
        elif event == SafetyEvent.PARKING_BRAKE_RELEASED:
            self.state_data.parking_brake_set = False
        elif event == SafetyEvent.ENGINE_STARTED:
            self.state_data.engine_running = True
        elif event == SafetyEvent.ENGINE_STOPPED:
            self.state_data.engine_running = False
        elif event in [SafetyEvent.VEHICLE_MOVING, SafetyEvent.VEHICLE_STOPPED]:
            # Extract speed from data
            speed = data.get("speed", 0.0)
            self.state_data.vehicle_speed = speed
        elif event in [SafetyEvent.TRANSMISSION_PARK, SafetyEvent.TRANSMISSION_DRIVE]:
            self.state_data.transmission_gear = data.get("gear", "unknown")

        self.state_data.last_updated = current_time

    def _evaluate_current_state(self) -> VehicleState:
        """Evaluate what the current vehicle state should be based on state data."""
        # If we don't have recent data, we can't determine state safely
        current_time = time.time()
        if current_time - self.state_data.last_updated > self.STATE_DATA_TIMEOUT:
            return VehicleState.UNKNOWN

        # Check for unsafe combinations first
        if (
            self.state_data.engine_running is True
            and self.state_data.parking_brake_set is False
            and self.state_data.vehicle_speed is not None
            and self.state_data.vehicle_speed > self.MOVING_SPEED_THRESHOLD
        ):
            # This is normal driving
            return VehicleState.DRIVING

        # Check if vehicle is moving
        if (
            self.state_data.vehicle_speed is not None
            and self.state_data.vehicle_speed > self.MOVING_SPEED_THRESHOLD
        ):
            return VehicleState.DRIVING

        # Vehicle is stopped, check parking brake and engine
        if self.state_data.parking_brake_set is True:
            if self.state_data.engine_running is True:
                return VehicleState.PARKED_RUNNING
            return VehicleState.PARKED_SAFE

        # If we have some data but can't determine a clear state
        if (
            self.state_data.parking_brake_set is not None
            or self.state_data.engine_running is not None
            or self.state_data.vehicle_speed is not None
        ):
            return VehicleState.UNKNOWN

        # No data at all
        return VehicleState.UNKNOWN

    def _transition_to(self, new_state: VehicleState) -> None:
        """Transition to a new vehicle state."""
        old_state = self.current_state
        self.current_state = new_state
        self._last_state_change = time.time()

        logger.info(f"Vehicle state transition: {old_state.value} -> {new_state.value}")

        # Notify observers if transitioning to unsafe state
        if new_state == VehicleState.UNSAFE:
            command = SafetyCommand(
                command_type="emergency_stop",
                target_entity="all",
                allowed=False,
                reason=f"Vehicle transitioned to unsafe state from {old_state.value}",
            )
            self._notify_observers(command)

    def _evaluate_safety_rules(
        self, event: SafetyEvent, data: dict[str, Any]
    ) -> SafetyCommand | None:
        """Evaluate safety rules and generate commands if needed."""
        # Example: If parking brake is released while slideouts are extended
        if event == SafetyEvent.PARKING_BRAKE_RELEASED:
            # This would require checking if slideouts are extended
            # For now, just log the event
            logger.warning("Parking brake released - ensure all slideouts are retracted")

        # Add more safety rule evaluations here
        return None

    def _build_transition_table(self) -> dict[tuple[VehicleState, SafetyEvent], VehicleState]:
        """Build the state transition table."""
        # This is a simplified transition table
        # In a real implementation, this would be more comprehensive
        return {
            (VehicleState.UNKNOWN, SafetyEvent.PARKING_BRAKE_SET): VehicleState.PARKED_SAFE,
            (VehicleState.PARKED_SAFE, SafetyEvent.ENGINE_STARTED): VehicleState.PARKED_RUNNING,
            (VehicleState.PARKED_RUNNING, SafetyEvent.ENGINE_STOPPED): VehicleState.PARKED_SAFE,
            (VehicleState.PARKED_RUNNING, SafetyEvent.PARKING_BRAKE_RELEASED): VehicleState.DRIVING,
            (VehicleState.DRIVING, SafetyEvent.PARKING_BRAKE_SET): VehicleState.PARKED_RUNNING,
            (VehicleState.DRIVING, SafetyEvent.VEHICLE_STOPPED): VehicleState.PARKED_RUNNING,
        }

    def _notify_observers(self, command: SafetyCommand) -> None:
        """Notify all observers of a safety command."""
        for observer in self.observers:
            try:
                observer(command)
            except Exception as e:
                logger.error(f"Error notifying safety observer: {e}")
