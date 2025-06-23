"""
Safety interfaces and protocols for ISO 26262-compliant RV-C vehicle control.

This module provides the foundation for safety-aware services in the
ServiceRegistry architecture, ensuring all safety capabilities are preserved
for ISO 26262-compliant vehicle control systems.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Protocol


class SafetyClassification(str, Enum):
    """Safety classification levels for features and services."""

    CRITICAL = "critical"
    """Safety-critical: failure could result in injury or damage."""

    OPERATIONAL = "operational"
    """Important for operation but not safety-critical."""

    MAINTENANCE = "maintenance"
    """Diagnostic and utility features."""


class SafeStateAction(str, Enum):
    """Actions to take when entering safe state for different feature types."""

    MAINTAIN_POSITION = "maintain_position"
    """Maintain current physical position, disable movement commands."""

    CONTINUE_OPERATION = "continue_operation"
    """Continue normal operation (e.g., lighting, climate)."""

    DISABLE = "disable"
    """Disable the feature completely."""

    SAFE_DEFAULT = "safe_default"
    """Revert to safe default values (e.g., moderate temp)."""


class SafetyStatus(Enum):
    """Service safety status enumeration for ISO 26262 compliance."""

    SAFE = "safe"
    DEGRADED = "degraded"
    UNSAFE = "unsafe"
    EMERGENCY_STOP = "emergency_stop"


class SafetyCapable(Protocol):
    """
    Protocol for services that participate in the safety system.

    Services implementing this protocol can be monitored by SafetyService
    and participate in emergency stop procedures.
    """

    @property
    def safety_classification(self) -> SafetyClassification:
        """Return the safety classification for this service."""
        ...

    async def emergency_stop(self, reason: str) -> None:
        """Perform emergency stop procedure for this service."""
        ...

    async def get_safety_status(self) -> SafetyStatus:
        """Get current safety status of the service."""
        ...

    async def validate_safety_interlock(self, operation: str) -> bool:
        """Validate if operation is safe to perform given current interlocks."""
        ...


class SafetyAware(ABC):
    """
    Base class for safety-aware services.

    Provides default implementations of safety interfaces and ensures
    consistent safety behavior across all safety-critical services.
    """

    def __init__(
        self,
        safety_classification: SafetyClassification,
        safe_state_action: SafeStateAction = SafeStateAction.MAINTAIN_POSITION,
    ):
        """
        Initialize safety-aware service.

        Args:
            safety_classification: ISO 26262 safety classification
            safe_state_action: Action to take when entering safe state
        """
        self._safety_classification = safety_classification
        self._safe_state_action = safe_state_action
        self._safety_status = SafetyStatus.SAFE
        self._emergency_stop_active = False

    @property
    def safety_classification(self) -> SafetyClassification:
        """Return the safety classification for this service."""
        return self._safety_classification

    @property
    def safe_state_action(self) -> SafeStateAction:
        """Return the safe state action for this service."""
        return self._safe_state_action

    @abstractmethod
    async def emergency_stop(self, reason: str) -> None:
        """
        Implement service-specific emergency stop logic.

        This method MUST be implemented by all safety-aware services
        to define how they respond to emergency stop conditions.

        Args:
            reason: Reason for emergency stop (for audit logging)
        """

    async def get_safety_status(self) -> SafetyStatus:
        """Get current safety status of the service."""
        return self._safety_status

    async def validate_safety_interlock(self, operation: str) -> bool:
        """
        Default safety interlock validation.

        Override this method for service-specific safety validations.

        Args:
            operation: Operation being validated

        Returns:
            True if operation is safe to perform
        """
        return self._safety_status in [SafetyStatus.SAFE, SafetyStatus.DEGRADED]

    def _set_safety_status(self, status: SafetyStatus) -> None:
        """Internal method to update safety status."""
        self._safety_status = status

    def _set_emergency_stop_active(self, active: bool) -> None:
        """Internal method to update emergency stop state."""
        self._emergency_stop_active = active
        if active:
            self._safety_status = SafetyStatus.EMERGENCY_STOP


class SafetyValidationError(Exception):
    """Exception raised when safety validation fails."""

    def __init__(self, operation: str, reason: str, safety_status: SafetyStatus):
        """
        Initialize safety validation error.

        Args:
            operation: Operation that failed validation
            reason: Reason for validation failure
            safety_status: Current safety status
        """
        self.operation = operation
        self.reason = reason
        self.safety_status = safety_status
        super().__init__(f"Safety validation failed for '{operation}': {reason}")
