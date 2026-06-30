"""Guardrail interfaces for command-emission control.

These types model CoachIQ's API guardrails: refusing bad commands, halting
command emission, and reporting guardrail state. They are not vehicle-safety
types; the OEM Firefly MIRA panel owns physical interlocks.
"""

from abc import ABC, abstractmethod
from enum import Enum


class GuardrailTier(str, Enum):
    """Health/startup criticality for guardrail-aware services."""

    CRITICAL = "critical"
    """Operationally critical: failure should make health/startup fail."""

    OPERATIONAL = "operational"
    """Important for normal operation but not in the API-guardrail path."""

    MAINTENANCE = "maintenance"
    """Diagnostic and utility features."""


class CommandHaltAction(str, Enum):
    """Local action to take when command emission is halted."""

    BLOCK_COMMANDS = "block_commands"
    """Refuse new commands while leaving physical state to OEM controllers."""

    CONTINUE_OPERATION = "continue_operation"
    """Continue normal operation (e.g., lighting, climate)."""

    DISABLE_COMMANDS = "disable_commands"
    """Disable this component's command-emission path."""

    FALLBACK_DEFAULT = "fallback_default"
    """Use a conservative software default for API responses or state."""


class GuardrailStatus(Enum):
    """Guardrail status for command-emission components."""

    SAFE = "safe"
    DEGRADED = "degraded"
    UNSAFE = "unsafe"
    COMMAND_HALTED = "command_halted"


class GuardrailParticipant(ABC):
    """Base class for services that can halt command emission."""

    def __init__(
        self,
        guardrail_tier: GuardrailTier,
        command_halt_action: CommandHaltAction = CommandHaltAction.BLOCK_COMMANDS,
    ):
        """
        Initialize guardrail-aware service.

        Args:
            guardrail_tier: Health/startup criticality tier.
            command_halt_action: Local software action when command emission halts.
        """
        self._guardrail_tier = guardrail_tier
        self._command_halt_action = command_halt_action
        self._guardrail_status = GuardrailStatus.SAFE
        self._command_halt_active = False

    @property
    def guardrail_tier(self) -> GuardrailTier:
        """Return the guardrail tier for this service."""
        return self._guardrail_tier

    @property
    def command_halt_action(self) -> CommandHaltAction:
        """Return the command-halt action for this service."""
        return self._command_halt_action

    @abstractmethod
    async def halt_command_emission(self, reason: str) -> None:
        """Implement service-specific command-halt logic.

        Args:
            reason: Reason for halting command emission.
        """

    async def get_guardrail_status(self) -> GuardrailStatus:
        """Get current safety status of the service."""
        return self._guardrail_status

    async def validate_command_precondition(self, _operation: str) -> bool:
        """
        Default command-precondition validation.

        Override this method for service-specific guardrail validations.

        Args:
            operation: Operation being validated

        Returns:
            True if operation may proceed
        """
        return self._guardrail_status in [GuardrailStatus.SAFE, GuardrailStatus.DEGRADED]

    def _set_guardrail_status(self, status: GuardrailStatus) -> None:
        """Internal method to update guardrail status."""
        self._guardrail_status = status

    def _set_command_halt_active(self, active: bool) -> None:
        """Internal method to update command-halt state."""
        self._command_halt_active = active
        if active:
            self._guardrail_status = GuardrailStatus.COMMAND_HALTED
