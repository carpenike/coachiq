"""
Service-classification interfaces and protocols for the ServiceRegistry.

This module provides the foundation for "safety-aware" services in the
ServiceRegistry architecture. The "safety" naming here is historical and
refers to **API guardrail behavior** (refuse to forward bad commands,
emergency-stop the orchestration loop, validate interlocks before sending
CAN frames) -- NOT vehicle safety. The OEM Firefly MIRA panel owns the
actual vehicle safety case.

See `docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md` for the full
framing.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Protocol


class SafetyClassification(str, Enum):
    """Service-criticality classification for ServiceRegistry startup, restart,
    and emergency-stop policy.

    Despite the historical name, this is **operational criticality**, not
    a vehicle-safety classification. See ADR-0004.
    """

    CRITICAL = "critical"
    """Operationally critical: API guardrail or auth path; failure should
    block startup and trigger emergency-stop on other CRITICAL services."""

    OPERATIONAL = "operational"
    """Important for normal operation but not in the API-guardrail path."""

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
    """Service guardrail status. "Safety" here is historical -- see ADR-0004."""

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
    Base class for guardrail-aware services.

    Provides default implementations of the guardrail interfaces and ensures
    consistent behavior across all CRITICAL-classified services. "Safety"
    naming is historical -- this is API command-validation, not vehicle
    safety. See ADR-0004.
    """

    def __init__(
        self,
        safety_classification: SafetyClassification,
        safe_state_action: SafeStateAction = SafeStateAction.MAINTAIN_POSITION,
    ):
        """
        Initialize guardrail-aware service.

        Args:
            safety_classification: Service-criticality classification (see
                ``SafetyClassification``); historical name, not ISO 26262.
            safe_state_action: Action to take when entering safe state.
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
