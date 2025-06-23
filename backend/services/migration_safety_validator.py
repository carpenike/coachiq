"""Migration safety validation service."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MigrationSafetyValidator:
    """
    Validates system state before allowing migrations.

    Target architecture: Repository injection only, no app_state.
    """

    def __init__(
        self,
        safety_repository,
        connection_repository,
        performance_monitor=None,
    ):
        """
        Initialize with repositories only.

        NO app_state parameter!
        NO backward compatibility!
        """
        self._safety_repo = safety_repository
        self._connection_repo = connection_repository
        self._performance_monitor = performance_monitor

    async def initialize(self) -> None:
        """Initialize the validator."""
        logger.info("MigrationSafetyValidator initialized")

    async def validate_safe_for_migration(self) -> tuple[bool, list[str]]:
        """
        Check if system is in safe state for migration.

        Returns:
            Tuple of (is_safe, reasons_if_not)
        """
        reasons = []

        try:
            # Get system state from repository
            safety_state = await self._safety_repo.get_current_state()

            # Vehicle must be stopped
            if safety_state.get("vehicle_speed", 0) > 0:
                reasons.append("Vehicle is in motion")

            # Parking brake must be engaged
            if not safety_state.get("parking_brake", False):
                reasons.append("Parking brake not engaged")

            # Engine should be off
            if safety_state.get("engine_running", True):
                reasons.append("Engine is running - shutdown recommended")

            # No active entity controls
            active_controls = await self._safety_repo.get_active_control_count()
            if active_controls > 0:
                reasons.append(f"Active entity control operations: {active_controls}")

            # Check safety interlocks
            interlocks = await self._safety_repo.get_interlock_status()
            if not interlocks.get("all_satisfied", False):
                violations = interlocks.get("violations", [])
                reasons.append(f"Safety interlocks not satisfied: {', '.join(violations)}")

            # Check transmission state
            if safety_state.get("transmission_gear", "PARK") != "PARK":
                reasons.append("Transmission not in PARK")

            # Check database health
            db_health = await self._connection_repo.check_health()
            if not db_health.get("healthy", False):
                reasons.append("Database connection unhealthy")

        except Exception as e:
            logger.error("Error during safety validation: %s", e)
            reasons.append(f"Safety validation error: {e!s}")

        is_safe = len(reasons) == 0

        if is_safe:
            logger.info("System validated as safe for migration")
        else:
            logger.warning("System not safe for migration: %s", "; ".join(reasons))

        return is_safe, reasons

    async def get_safety_report(self) -> dict[str, Any]:
        """Get detailed safety report for UI display."""
        is_safe, reasons = await self.validate_safe_for_migration()
        safety_state = await self._safety_repo.get_current_state()
        interlocks = await self._safety_repo.get_interlock_status()

        return {
            "is_safe": is_safe,
            "blocking_reasons": reasons,
            "system_state": safety_state,
            "interlocks": interlocks,
            "recommendations": self._get_safety_recommendations(reasons),
        }

    def _get_safety_recommendations(self, reasons: list[str]) -> list[str]:
        """Generate recommendations based on blocking reasons."""
        recommendations = []

        if any("motion" in r for r in reasons):
            recommendations.append("Stop the vehicle completely")

        if any("parking brake" in r for r in reasons):
            recommendations.append("Engage the parking brake")

        if any("engine" in r for r in reasons):
            recommendations.append("Turn off the engine for safety")

        if any("control operations" in r for r in reasons):
            recommendations.append("Wait for all control operations to complete")

        if any("transmission" in r for r in reasons):
            recommendations.append("Shift transmission to PARK")

        if any("database" in r for r in reasons):
            recommendations.append("Check database connection and retry")

        return recommendations
