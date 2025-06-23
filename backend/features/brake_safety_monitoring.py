"""
Brake Safety Monitoring Feature

Implements 50ms deadline monitoring for safety-critical brake operations.
Integrates with the feature management system and provides health monitoring.
"""

import logging
import time
from typing import Any, Dict, Optional

from backend.services.brake_safety_monitor import CriticalOperation, brake_safety_monitor
from backend.services.feature_base import FeatureBase

logger = logging.getLogger(__name__)


class BrakeSafetyMonitoringFeature(FeatureBase):
    """
    Feature implementation for brake safety monitoring with 50ms deadline enforcement.

    Provides IETF health check compliance and integrates with the feature management system.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.brake_monitor = brake_safety_monitor
        self._last_health_check = 0
        self._health_check_interval = config.get("safety_monitoring_interval_seconds", 1.0)

        # Configure deadlines from feature config
        if hasattr(self.brake_monitor, "CRITICAL_DEADLINES"):
            brake_deadline = config.get("brake_response_deadline_ms", 50.0)
            emergency_deadline = config.get("emergency_brake_deadline_ms", 25.0)
            interlock_deadline = config.get("safety_interlock_deadline_ms", 100.0)

            self.brake_monitor.CRITICAL_DEADLINES.update(
                {
                    CriticalOperation.BRAKE_COMMAND: brake_deadline,
                    CriticalOperation.BRAKE_ACKNOWLEDGMENT: brake_deadline,
                    CriticalOperation.EMERGENCY_STOP: emergency_deadline,
                    CriticalOperation.SAFETY_INTERLOCK: interlock_deadline,
                }
            )

        logger.info(f"Brake safety monitoring feature initialized with {brake_deadline}ms deadline")

    def initialize(self) -> bool:
        """Initialize the brake safety monitoring feature"""
        try:
            # Enable the brake safety monitor
            self.brake_monitor.enable()

            # Register violation callback for emergency notifications
            if self.config.get("enable_emergency_notifications", True):
                self.brake_monitor.register_violation_callback(self._handle_emergency_violation)

            self._enabled = True
            logger.info("Brake safety monitoring feature initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize brake safety monitoring: {e}")
            self._enabled = False
            return False

    def cleanup(self) -> bool:
        """Cleanup the brake safety monitoring feature"""
        try:
            # Disable the brake safety monitor
            self.brake_monitor.disable()

            self._enabled = False
            logger.info("Brake safety monitoring feature cleaned up successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to cleanup brake safety monitoring: {e}")
            return False

    def is_healthy(self) -> bool:
        """
        Check if brake safety monitoring is healthy.

        Returns False if there are recent critical deadline violations.
        """
        if not self._enabled:
            return False

        # Rate limit health checks to avoid performance impact
        current_time = time.time()
        if current_time - self._last_health_check < self._health_check_interval:
            return getattr(self, "_last_health_status", True)

        self._last_health_check = current_time

        # Check brake monitor health
        health_status = self.brake_monitor.is_healthy()
        self._last_health_status = health_status

        return health_status

    @property
    def health(self) -> str:
        """Get IETF-compliant health status"""
        if not self._enabled:
            return "disabled"

        return self.brake_monitor.get_health_status()

    def get_status(self) -> dict[str, Any]:
        """Get detailed brake safety monitoring status"""
        if not self._enabled:
            return {
                "status": "disabled",
                "enabled": False,
                "message": "Brake safety monitoring is disabled",
            }

        metrics = self.brake_monitor.get_metrics()
        recent_violations = self.brake_monitor.get_recent_violations(limit=5)
        active_operations = self.brake_monitor.get_active_operations()

        return {
            "status": "operational",
            "enabled": True,
            "health": self.health,
            "metrics": {
                "total_operations": metrics.total_operations,
                "deadline_violations": metrics.deadline_violations,
                "critical_violations": metrics.critical_violations,
                "average_response_time_ms": round(metrics.average_response_time_ms, 2),
                "max_response_time_ms": round(metrics.max_response_time_ms, 2),
                "last_violation_time": metrics.last_violation_time,
            },
            "recent_violations": [
                {
                    "operation": v.operation.value,
                    "entity_id": v.entity_id,
                    "deadline_ms": v.deadline_ms,
                    "actual_response_time_ms": round(v.actual_response_time_ms, 2),
                    "severity": v.severity,
                    "timestamp": v.response_timestamp,
                }
                for v in recent_violations
            ],
            "active_operations": len(active_operations),
            "configuration": {
                "brake_deadline_ms": self.brake_monitor.CRITICAL_DEADLINES.get(
                    CriticalOperation.BRAKE_COMMAND, 50.0
                ),
                "emergency_deadline_ms": self.brake_monitor.CRITICAL_DEADLINES.get(
                    CriticalOperation.EMERGENCY_STOP, 25.0
                ),
                "monitoring_enabled": self.brake_monitor.enabled,
            },
        }

    async def _handle_emergency_violation(self, violation):
        """Handle emergency deadline violations"""
        logger.critical(
            f"EMERGENCY BRAKE DEADLINE VIOLATION: {violation.operation.value} "
            f"for {violation.entity_id} exceeded {violation.deadline_ms}ms deadline "
            f"(actual: {violation.actual_response_time_ms:.2f}ms)"
        )

        # In a real implementation, this would:
        # 1. Send emergency notifications
        # 2. Trigger emergency brake systems
        # 3. Log to safety audit trail
        # 4. Potentially initiate emergency stop sequence

        # For now, just ensure it's logged as a critical safety event
        if hasattr(self, "safety_logger"):
            self.safety_logger.critical(
                "SAFETY_VIOLATION",
                extra={
                    "violation_type": "brake_deadline_exceeded",
                    "operation": violation.operation.value,
                    "entity_id": violation.entity_id,
                    "deadline_ms": violation.deadline_ms,
                    "actual_ms": violation.actual_response_time_ms,
                    "severity": violation.severity,
                },
            )

    async def track_brake_command(
        self, entity_id: str, pgn: int | None = None, command_data: dict | None = None
    ) -> str:
        """
        Track a brake command with deadline monitoring.

        Returns operation_id for later completion tracking.
        """
        if not self._enabled:
            return ""

        return await self.brake_monitor.track_critical_operation(
            CriticalOperation.BRAKE_COMMAND, entity_id, pgn=pgn, command_data=command_data
        )

    async def track_brake_acknowledgment(
        self, entity_id: str, pgn: int | None = None, response_data: dict | None = None
    ) -> str:
        """
        Track a brake acknowledgment with deadline monitoring.

        Returns operation_id for later completion tracking.
        """
        if not self._enabled:
            return ""

        return await self.brake_monitor.track_critical_operation(
            CriticalOperation.BRAKE_ACKNOWLEDGMENT, entity_id, pgn=pgn, command_data=response_data
        )

    async def complete_brake_operation(self, operation_id: str, response_data: dict | None = None):
        """Complete a brake operation and check for deadline violations"""
        if not self._enabled or not operation_id:
            return

        violation = await self.brake_monitor.complete_critical_operation(
            operation_id, response_data
        )

        if violation and violation.severity == "CRITICAL":
            # Additional safety measures for critical violations
            logger.error(
                f"Critical brake safety violation detected - "
                f"operation {violation.operation.value} exceeded safety deadline"
            )

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get performance metrics for monitoring dashboard"""
        if not self._enabled:
            return {}

        metrics = self.brake_monitor.get_metrics()

        return {
            "brake_safety_monitoring": {
                "total_operations": metrics.total_operations,
                "violation_rate": (
                    metrics.deadline_violations / max(metrics.total_operations, 1) * 100
                    if metrics.total_operations > 0
                    else 0
                ),
                "critical_violation_rate": (
                    metrics.critical_violations / max(metrics.total_operations, 1) * 100
                    if metrics.total_operations > 0
                    else 0
                ),
                "average_response_time_ms": metrics.average_response_time_ms,
                "max_response_time_ms": metrics.max_response_time_ms,
                "active_operations": len(self.brake_monitor.get_active_operations()),
                "health_status": self.health,
            }
        }


# Feature factory function
def create_feature(config: dict[str, Any]) -> BrakeSafetyMonitoringFeature:
    """Create and return a brake safety monitoring feature instance"""
    return BrakeSafetyMonitoringFeature(config)
