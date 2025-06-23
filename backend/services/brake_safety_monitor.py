"""
Brake Safety Performance Monitor

Implements 50ms deadline monitoring for safety-critical brake operations
following IETF health check standards and RV-C safety requirements.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CriticalOperation(Enum):
    """Safety-critical operations requiring deadline monitoring"""

    BRAKE_COMMAND = "brake_command"
    BRAKE_ACKNOWLEDGMENT = "brake_acknowledgment"
    EMERGENCY_STOP = "emergency_stop"
    SAFETY_INTERLOCK = "safety_interlock"


@dataclass
class DeadlineViolation:
    """Records a safety deadline violation"""

    operation: CriticalOperation
    entity_id: str
    command_timestamp: float
    response_timestamp: float
    deadline_ms: float
    actual_response_time_ms: float
    severity: str  # "WARNING", "CRITICAL"
    pgn: int | None = None
    data: str | None = None


@dataclass
class SafetyMetrics:
    """Safety performance metrics for health monitoring"""

    total_operations: int = 0
    deadline_violations: int = 0
    critical_violations: int = 0
    average_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    last_violation_time: float | None = None


class BrakeSafetyMonitor:
    """
    50ms deadline monitoring for safety-critical brake operations.

    Implements IETF health check patterns for safety-critical monitoring.
    Integrates with existing RV-C performance monitoring infrastructure.
    """

    # Safety-critical response deadlines per RV-C safety requirements
    CRITICAL_DEADLINES = {
        CriticalOperation.BRAKE_COMMAND: 50.0,
        CriticalOperation.BRAKE_ACKNOWLEDGMENT: 50.0,
        CriticalOperation.EMERGENCY_STOP: 25.0,  # Even stricter for emergency
        CriticalOperation.SAFETY_INTERLOCK: 100.0,  # Slightly more lenient
    }

    # PGN mappings for brake-related messages (from RV-C spec)
    BRAKE_COMMAND_PGNS = {
        0x1FEF7: "brake_command",  # Example - replace with actual RV-C PGNs
        0x1FEF8: "emergency_brake",
    }

    BRAKE_RESPONSE_PGNS = {
        0x1FEF9: "brake_status_response",  # Example - replace with actual RV-C PGNs
        0x1FEFA: "brake_acknowledgment",
    }

    def __init__(self):
        self.pending_operations: dict[str, dict[str, Any]] = {}
        self.deadline_violations: deque = deque(maxlen=1000)  # Keep last 1000 violations
        self.metrics = SafetyMetrics()
        self.violation_callbacks: list[Callable] = []
        self._enabled = True

        logger.info("Brake safety monitor initialized with 50ms deadline monitoring")

    def is_healthy(self) -> bool:
        """Health check for IETF compliance - critical if recent violations"""
        if not self._enabled:
            return True

        # Consider unhealthy if critical violations in last 5 minutes
        cutoff_time = time.time() - 300  # 5 minutes ago
        recent_critical = sum(
            1
            for v in self.deadline_violations
            if v.response_timestamp > cutoff_time and v.severity == "CRITICAL"
        )

        return recent_critical == 0

    def get_health_status(self) -> str:
        """Get IETF-compliant health status"""
        if not self._enabled:
            return "disabled"
        if not self.is_healthy():
            return "failed"
        if self.deadline_violations and self.deadline_violations[-1].response_timestamp > (
            time.time() - 60
        ):
            return "degraded"  # Warning violations in last minute
        return "healthy"

    async def track_critical_operation(
        self,
        operation: CriticalOperation,
        entity_id: str,
        pgn: int | None = None,
        command_data: dict | None = None,
    ) -> str:
        """
        Start tracking a critical operation with deadline monitoring.

        Returns operation_id for later completion tracking.
        """
        if not self._enabled:
            return ""

        operation_id = f"{operation.value}_{entity_id}_{int(time.time() * 1000)}"
        deadline_ms = self.CRITICAL_DEADLINES[operation]
        start_time = time.time()

        self.pending_operations[operation_id] = {
            "operation": operation,
            "entity_id": entity_id,
            "start_time": start_time,
            "deadline_ms": deadline_ms,
            "pgn": pgn,
            "command_data": command_data or {},
        }

        # Schedule deadline violation check
        asyncio.create_task(self._check_deadline(operation_id))

        logger.debug(
            f"Started tracking {operation.value} for {entity_id} "
            f"with {deadline_ms}ms deadline (ID: {operation_id})"
        )

        return operation_id

    async def complete_critical_operation(
        self, operation_id: str, response_data: dict | None = None
    ) -> DeadlineViolation | None:
        """
        Mark operation as complete and check for deadline violations.

        Returns DeadlineViolation if deadline was exceeded, None otherwise.
        """
        if not self._enabled or operation_id not in self.pending_operations:
            return None

        op_data = self.pending_operations.pop(operation_id)
        response_time = time.time()
        response_time_ms = (response_time - op_data["start_time"]) * 1000

        # Update metrics
        self.metrics.total_operations += 1
        self.metrics.average_response_time_ms = (
            self.metrics.average_response_time_ms * (self.metrics.total_operations - 1)
            + response_time_ms
        ) / self.metrics.total_operations
        self.metrics.max_response_time_ms = max(self.metrics.max_response_time_ms, response_time_ms)

        # Check for deadline violation
        if response_time_ms > op_data["deadline_ms"]:
            violation = DeadlineViolation(
                operation=op_data["operation"],
                entity_id=op_data["entity_id"],
                command_timestamp=op_data["start_time"],
                response_timestamp=response_time,
                deadline_ms=op_data["deadline_ms"],
                actual_response_time_ms=response_time_ms,
                severity="CRITICAL"
                if response_time_ms > (op_data["deadline_ms"] * 2)
                else "WARNING",
                pgn=op_data.get("pgn"),
                data=str(response_data) if response_data else None,
            )

            self.deadline_violations.append(violation)
            self.metrics.deadline_violations += 1
            self.metrics.last_violation_time = response_time

            if violation.severity == "CRITICAL":
                self.metrics.critical_violations += 1

            await self._handle_deadline_violation(violation)

            logger.warning(
                f"Deadline violation: {violation.operation.value} for {violation.entity_id} "
                f"took {violation.actual_response_time_ms:.2f}ms "
                f"(deadline: {violation.deadline_ms}ms, severity: {violation.severity})"
            )

            return violation

        logger.debug(
            f"Completed {op_data['operation'].value} for {op_data['entity_id']} "
            f"in {response_time_ms:.2f}ms (within {op_data['deadline_ms']}ms deadline)"
        )

        return None

    async def _check_deadline(self, operation_id: str):
        """Check if operation has exceeded its deadline"""
        if operation_id not in self.pending_operations:
            return

        op_data = self.pending_operations[operation_id]
        deadline_seconds = op_data["deadline_ms"] / 1000.0

        # Wait for deadline
        await asyncio.sleep(deadline_seconds)

        # Check if operation is still pending (not completed)
        if operation_id in self.pending_operations:
            # Force completion with timeout violation
            await self.complete_critical_operation(operation_id, {"timeout": True})

    async def _handle_deadline_violation(self, violation: DeadlineViolation):
        """Handle a deadline violation with appropriate safety actions"""

        # Log violation for audit trail
        logger.error(
            f"SAFETY DEADLINE VIOLATION: {violation.operation.value} "
            f"exceeded {violation.deadline_ms}ms deadline "
            f"(actual: {violation.actual_response_time_ms:.2f}ms, "
            f"severity: {violation.severity})"
        )

        # Call registered violation callbacks
        for callback in self.violation_callbacks:
            try:
                await callback(violation)
            except Exception as e:
                logger.error(f"Error in violation callback: {e}")

        # For critical brake violations, trigger additional safety measures
        if (
            violation.operation
            in [CriticalOperation.BRAKE_COMMAND, CriticalOperation.EMERGENCY_STOP]
            and violation.severity == "CRITICAL"
        ):
            logger.critical(
                f"CRITICAL BRAKE SAFETY VIOLATION - "
                f"brake response exceeded {violation.deadline_ms}ms deadline"
            )

            # In a real implementation, this would trigger:
            # - Emergency notifications
            # - Redundant brake system activation
            # - Safety system state changes

    def register_violation_callback(self, callback: Callable[[DeadlineViolation], None]):
        """Register callback for deadline violations"""
        self.violation_callbacks.append(callback)

    def get_metrics(self) -> SafetyMetrics:
        """Get current safety performance metrics"""
        return self.metrics

    def get_recent_violations(self, limit: int = 10) -> list[DeadlineViolation]:
        """Get recent deadline violations"""
        violations = list(self.deadline_violations)
        return violations[-limit:] if violations else []

    def get_active_operations(self) -> dict[str, dict]:
        """Get currently active operations"""
        return dict(self.pending_operations)

    def reset_metrics(self):
        """Reset safety metrics (for testing/maintenance)"""
        self.metrics = SafetyMetrics()
        logger.info("Brake safety metrics reset")

    def enable(self):
        """Enable brake safety monitoring"""
        self._enabled = True
        logger.info("Brake safety monitoring enabled")

    def disable(self):
        """Disable brake safety monitoring"""
        self._enabled = False
        # Clear pending operations
        self.pending_operations.clear()
        logger.warning("Brake safety monitoring disabled")

    @property
    def enabled(self) -> bool:
        """Check if monitoring is enabled"""
        return self._enabled


# Global instance for integration with feature system
brake_safety_monitor = BrakeSafetyMonitor()
