"""Guardrail coordinator for command-emission control.

This transitional class still extends ServiceRegistry until ADR-0014 Phase A
replaces the generic DI container. Its guardrail behavior is separate: it tracks
health/startup criticality and explicitly registered command-halt participants.
"""

import logging
from typing import Any

from backend.core.guardrail_interfaces import GuardrailStatus, GuardrailTier
from backend.core.service_dependency_resolver import ServiceDependency
from backend.core.service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


class GuardrailCoordinator(ServiceRegistry):
    """ServiceRegistry with guardrail metadata and command-halt coordination."""

    def __init__(self):
        """Initialize guardrail-aware service metadata."""
        super().__init__()
        self._guardrail_tiers: dict[str, GuardrailTier] = {}
        self._guardrail_metadata: dict[str, dict[str, Any]] = {}
        self._command_halt_targets: set[str] = set()

    def register_guardrail_service(  # noqa: PLR0913 - mirrors ServiceRegistry registration API
        self,
        name: str,
        init_func,
        guardrail_tier: GuardrailTier,
        command_halt_participant: bool = False,
        dependencies: list[ServiceDependency] | None = None,
        description: str = "",
        tags: set[str] | None = None,
        health_check=None,
        **kwargs,
    ) -> None:
        """Register a service with guardrail metadata."""
        if tags is None:
            tags = set()
        tags.add("guardrail-aware")
        tags.add(f"guardrail-{guardrail_tier.value}")
        if command_halt_participant:
            tags.add("command-halt-target")

        self._guardrail_tiers[name] = guardrail_tier
        if command_halt_participant:
            self._command_halt_targets.add(name)

        self._guardrail_metadata[name] = {
            "tier": guardrail_tier,
            "command_halt_participant": command_halt_participant,
            "description": description,
            "registered_at": self._get_current_timestamp(),
        }

        self.register_service(
            name=name,
            init_func=init_func,
            dependencies=dependencies or [],
            description=f"[{guardrail_tier.value.upper()}] {description}",
            tags=tags,
            health_check=health_check,
            **kwargs,
        )

        logger.info(
            "Registered guardrail service '%s' tier=%s halt_target=%s",
            name,
            guardrail_tier.value,
            command_halt_participant,
        )

    def get_command_halt_targets(self) -> list[str]:
        """Return services that participate in command-emission halt fan-out."""
        return sorted(self._command_halt_targets)

    def get_services_by_guardrail_tier(self, tier: GuardrailTier) -> list[str]:
        """Return services by health/startup guardrail tier."""
        return [
            name for name, service_tier in self._guardrail_tiers.items() if service_tier == tier
        ]

    def get_guardrail_tier(self, service_name: str) -> GuardrailTier | None:
        """Return a service's guardrail tier, if any."""
        return self._guardrail_tiers.get(service_name)

    async def halt_command_emission(self, reason: str, triggered_by: str) -> dict[str, bool]:
        """Halt command emission on explicit command-halt participants."""
        logger.critical("Halting command emission: %s (triggered by: %s)", reason, triggered_by)

        results: dict[str, bool] = {}
        for service_name in self.get_command_halt_targets():
            try:
                service = self.get_service(service_name)
                if not hasattr(service, "halt_command_emission"):
                    logger.warning("Service %s cannot halt command emission", service_name)
                    results[service_name] = False
                    continue

                logger.critical("Command halt target: %s", service_name)
                await service.halt_command_emission(reason)
                results[service_name] = True
            except Exception as exc:
                logger.error("Command halt failed for %s: %s", service_name, exc)
                results[service_name] = False

        logger.critical("Command halt completed. Results: %s", results)
        return results

    async def get_guardrail_status_summary(self) -> dict[str, Any]:  # noqa: C901, PLR0912
        """Return guardrail status across registered services."""
        status: dict[str, Any] = {
            "critical_services": {},
            "operational_services": {},
            "maintenance_services": {},
            "overall_guardrail_status": GuardrailStatus.SAFE.value,
            "summary": {
                "total_guardrail_services": len(self._guardrail_tiers),
                "critical_count": 0,
                "degraded_count": 0,
                "unsafe_count": 0,
                "command_halt_count": 0,
            },
        }

        worst_status = GuardrailStatus.SAFE
        for service_name, tier in self._guardrail_tiers.items():
            try:
                service = self.get_service(service_name)
                if hasattr(service, "get_guardrail_status"):
                    service_status = await service.get_guardrail_status()
                else:
                    registry_status = self.get_service_status(service_name)
                    if registry_status == "HEALTHY":
                        service_status = GuardrailStatus.SAFE
                    elif registry_status == "DEGRADED":
                        service_status = GuardrailStatus.DEGRADED
                    else:
                        service_status = GuardrailStatus.UNSAFE

                category = f"{tier.value}_services"
                if category in status:
                    status[category][service_name] = service_status.value

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
            except Exception as exc:
                logger.error("Guardrail status check failed for %s: %s", service_name, exc)
                status["critical_services"][service_name] = "unknown"
                status["summary"]["unsafe_count"] += 1
                worst_status = GuardrailStatus.UNSAFE

        status["overall_guardrail_status"] = worst_status.value
        return status

    def get_guardrail_metadata(self, service_name: str) -> dict[str, Any] | None:
        """Return guardrail metadata for a service."""
        return self._guardrail_metadata.get(service_name)

    def list_guardrail_services(self) -> dict[str, dict[str, Any]]:
        """List guardrail-aware services with metadata."""
        return {
            service_name: {
                "tier": tier.value,
                "metadata": self._guardrail_metadata.get(service_name, {}),
                "command_halt_participant": service_name in self._command_halt_targets,
                "status": self.get_service_status(service_name),
                "registered": self.has_service(service_name),
            }
            for service_name, tier in self._guardrail_tiers.items()
        }

    def _get_current_timestamp(self) -> str:
        """Return an ISO timestamp for metadata."""
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()
