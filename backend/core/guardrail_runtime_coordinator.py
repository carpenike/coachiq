"""Guardrail-only runtime coordinator.

This coordinator is constructed by the composition root and owns guardrail
metadata/command-halt reads. It intentionally does not inherit composition root.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.core.guardrail_interfaces import GuardrailStatus, GuardrailTier

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GuardrailRuntimeEntry:
    """Guardrail metadata for a root-constructed service."""

    service: Any
    tier: GuardrailTier
    command_halt_participant: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class GuardrailRuntimeCoordinator:
    """Coordinate command-halt and guardrail status for root-owned services."""

    def __init__(self) -> None:
        self._entries: dict[str, GuardrailRuntimeEntry] = {}

    def add_guardrail_service(
        self,
        service_name: str,
        service: Any,
        tier: GuardrailTier,
        command_halt_participant: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a root-owned service with guardrail metadata."""
        self._entries[service_name] = GuardrailRuntimeEntry(
            service=service,
            tier=tier,
            command_halt_participant=command_halt_participant,
            metadata=metadata or {},
        )

    def has_service(self, service_name: str) -> bool:
        """Return whether a guardrail-aware service is registered."""
        return service_name in self._entries

    def get_service(self, service_name: str) -> Any:
        """Return a guardrail-aware service by name."""
        entry = self._entries.get(service_name)
        if entry is None:
            msg = f"Service '{service_name}' not available"
            raise RuntimeError(msg)
        return entry.service

    def get_service_status(self, service_name: str) -> str:
        """Return a synchronous guardrail service status snapshot."""
        if service_name not in self._entries:
            return "PENDING"
        return "HEALTHY"

    def get_health_summary(self) -> dict[str, dict[str, str]]:
        """Return a synchronous health summary for guardrail monitoring."""
        return {
            service_name: {"status": self.get_service_status(service_name)}
            for service_name in self._entries
        }

    def get_command_halt_targets(self) -> list[str]:
        """Return explicit command-halt participants."""
        return sorted(
            name for name, entry in self._entries.items() if entry.command_halt_participant
        )

    async def halt_command_emission(self, reason: str, triggered_by: str) -> dict[str, bool]:
        """Halt command emission on explicit participants."""
        results: dict[str, bool] = {}
        for service_name in self.get_command_halt_targets():
            entry = self._entries[service_name]
            try:
                if not hasattr(entry.service, "halt_command_emission"):
                    results[service_name] = False
                    continue
                logger.critical(
                    "Command halt target: %s (triggered by %s)", service_name, triggered_by
                )
                await entry.service.halt_command_emission(reason)
                results[service_name] = True
            except Exception as exc:
                logger.error("Command halt failed for %s: %s", service_name, exc)
                results[service_name] = False
        return results

    async def get_guardrail_status_summary(self) -> dict[str, Any]:
        """Return guardrail status across root-owned services."""
        status: dict[str, Any] = {
            "critical_services": {},
            "operational_services": {},
            "maintenance_services": {},
            "overall_guardrail_status": GuardrailStatus.SAFE.value,
            "summary": {
                "total_guardrail_services": len(self._entries),
                "critical_count": 0,
                "degraded_count": 0,
                "unsafe_count": 0,
                "command_halt_count": 0,
            },
        }

        worst_status = GuardrailStatus.SAFE
        for service_name, entry in self._entries.items():
            service_status = await self._get_service_guardrail_status(entry.service)
            category = f"{entry.tier.value}_services"
            if category in status:
                status[category][service_name] = service_status.value

            if entry.tier == GuardrailTier.CRITICAL:
                status["summary"]["critical_count"] += 1
            if service_status == GuardrailStatus.COMMAND_HALTED:
                status["summary"]["command_halt_count"] += 1
                worst_status = GuardrailStatus.COMMAND_HALTED
            elif service_status == GuardrailStatus.UNSAFE:
                status["summary"]["unsafe_count"] += 1
                if worst_status != GuardrailStatus.COMMAND_HALTED:
                    worst_status = GuardrailStatus.UNSAFE
            elif service_status == GuardrailStatus.DEGRADED:
                status["summary"]["degraded_count"] += 1
                if worst_status == GuardrailStatus.SAFE:
                    worst_status = GuardrailStatus.DEGRADED

        status["overall_guardrail_status"] = worst_status.value
        return status

    def get_guardrail_metadata(self, service_name: str) -> dict[str, Any] | None:
        """Return metadata for one guardrail-aware service."""
        entry = self._entries.get(service_name)
        return entry.metadata if entry else None

    def list_guardrail_services(self) -> dict[str, dict[str, Any]]:
        """List root-owned guardrail-aware services."""
        return {
            service_name: {
                "tier": entry.tier.value,
                "metadata": entry.metadata,
                "command_halt_participant": entry.command_halt_participant,
                "registered": True,
            }
            for service_name, entry in self._entries.items()
        }

    async def _get_service_guardrail_status(self, service: Any) -> GuardrailStatus:
        """Read guardrail status from a service when available."""
        if hasattr(service, "get_guardrail_status"):
            service_status = service.get_guardrail_status()
            if hasattr(service_status, "__await__"):
                service_status = await service_status
            if isinstance(service_status, GuardrailStatus):
                return service_status
        return GuardrailStatus.SAFE
