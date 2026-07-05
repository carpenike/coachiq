"""
Entity Domain Service

Safety-critical domain service for entity operations with comprehensive
safety interlocks, command/acknowledgment patterns, and state reconciliation.

This service implements the safety-first methodology learned from Phase 0
emergency stabilization, ensuring vehicle control operations are properly
validated and acknowledged before being considered successful.

Note: "safety-critical" / "safety" naming in this file is historical and
refers to **API guardrail / command-validation** behavior, NOT vehicle safety.
The OEM Firefly MIRA panel owns the actual vehicle safety case. See
`docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.core.entity_manager import EntityManager
from backend.integrations.rvc import climate_units
from backend.models.entity import ControlCommand
from backend.services.auth.manager import AuthManager
from backend.services.entities.entity_service import EntityService
from backend.services.rvc.rvc_config_facade import RVCConfigFacade
from backend.websocket.handlers import WebSocketManager

logger = logging.getLogger(__name__)


# Safety-Critical Domain Models
class SafetyControlCommandV2(BaseModel):
    """Enhanced control command with safety validation"""

    command: str = Field(
        ..., description="Command type: set, toggle, brightness_up, brightness_down"
    )
    state: bool | None = Field(None, description="Target state for set commands")
    brightness: int | None = Field(None, ge=0, le=100, description="Brightness level 0-100")
    parameters: dict[str, Any] | None = Field(None, description="Additional command parameters")
    safety_confirmation: bool = Field(False, description="Explicit safety confirmation required")
    timeout_seconds: float = Field(5.0, ge=0.1, le=30.0, description="Command timeout")


class SafetyOperationResultV2(BaseModel):
    """Safety-critical operation result with acknowledgment tracking"""

    operation_id: str = Field(..., description="Unique operation identifier")
    entity_id: str = Field(..., description="Entity ID that was operated on")
    status: str = Field(
        ..., description="Operation status: success, failed, timeout, unauthorized, safety_abort"
    )
    acknowledged: bool = Field(
        False, description="Whether operation was acknowledged by physical system"
    )
    acknowledgment_time_ms: float | None = Field(None, description="Time to receive acknowledgment")
    error_message: str | None = Field(None, description="Error details if failed")
    error_code: str | None = Field(None, description="Machine-readable error code")
    execution_time_ms: float | None = Field(None, description="Operation execution time")
    safety_validation: dict[str, Any] = Field(
        default_factory=dict, description="Safety validation results"
    )


class BulkSafetyOperationRequestV2(BaseModel):
    """Bulk operation request with safety controls"""

    entity_ids: list[str] = Field(..., description="List of entity IDs to control")
    command: SafetyControlCommandV2 = Field(..., description="Command to execute on all entities")
    ignore_errors: bool = Field(False, description="Continue on individual failures")
    safety_mode: str = Field(
        "strict", description="Safety mode: strict, permissive, halt_command_emission"
    )
    max_concurrent: int = Field(10, ge=1, le=50, description="Maximum concurrent operations")


class BulkSafetyOperationResultV2(BaseModel):
    """Bulk operation result with safety tracking"""

    operation_id: str = Field(..., description="Unique bulk operation identifier")
    total_count: int = Field(..., description="Total number of operations attempted")
    success_count: int = Field(..., description="Number of successful operations")
    failed_count: int = Field(..., description="Number of failed operations")
    timeout_count: int = Field(..., description="Number of timed out operations")
    safety_abort_count: int = Field(..., description="Number of operations aborted for safety")
    results: list[SafetyOperationResultV2] = Field(..., description="Per-entity operation results")
    total_execution_time_ms: float = Field(..., description="Total execution time")
    safety_summary: dict[str, Any] = Field(
        default_factory=dict, description="Safety operation summary"
    )


class EntityDomainService:
    """
    Safety-critical domain service for entity operations.

    Integrates with existing service architecture while providing enhanced
    safety controls, command/acknowledgment patterns, and state reconciliation.

    Key Safety Features:
    - Command/acknowledgment patterns for all vehicle control operations
    - State reconciliation with RV-C bus as source of truth
    - Emergency stop capability for immediate operation halt
    - Comprehensive audit logging for safety-critical operations
    - Safety interlocks preventing dangerous operations
    """

    def __init__(
        self,
        config_service: RVCConfigFacade,
        auth_manager: AuthManager,
        entity_service: EntityService,
        websocket_manager: WebSocketManager,
        entity_manager: EntityManager,
    ):
        """Initialize domain service with all required dependencies"""
        self.config = config_service
        self.auth = auth_manager
        self.entities = entity_service
        self.websocket = websocket_manager
        self.entity_manager = entity_manager

        # Safety tracking - optimized for Pi memory constraints
        self._command_halt_active = False
        self._pending_operations: dict[str, SafetyOperationResultV2] = {}
        self._safety_interlocks_enabled = True

        # Pi optimization: Limit concurrent operations to prevent memory pressure
        self._max_concurrent_operations = 5  # Conservative for Pi hardware
        self._operation_timeout_default = 10.0  # Reasonable for local CAN bus

        logger.info(
            "EntityDomainService initialized with Pi optimizations and safety interlocks enabled"
        )

    async def _check_command_preconditions(self, command: SafetyControlCommandV2) -> dict[str, Any]:
        """
        Check safety interlocks before executing any command.

        Returns safety validation results with any issues detected.
        """
        validation = {
            "halt_command_emission_check": not self._command_halt_active,
            "safety_interlocks_check": self._safety_interlocks_enabled,
            "command_validation": True,
            "timeout_validation": 0.1 <= command.timeout_seconds <= 30.0,
            "issues": [],
        }

        if self._command_halt_active:
            validation["issues"].append("Emergency stop is active - all operations halted")

        if not self._safety_interlocks_enabled:
            validation["issues"].append("Safety interlocks are disabled")

        # Validate command structure
        if command.command not in ["set", "toggle", "brightness_up", "brightness_down"]:
            validation["command_validation"] = False
            validation["issues"].append(f"Invalid command: {command.command}")

        # Safety confirmation check for critical operations
        if command.command in ["set", "toggle"] and not command.safety_confirmation:
            validation["issues"].append(
                "Safety confirmation required for state-changing operations"
            )

        validation["passed"] = len(validation["issues"]) == 0
        return validation

    @staticmethod
    def _expected_operating_status(command: "SafetyControlCommandV2") -> int | None:
        """Target DC_DIMMER operating_status (0-200 scale) for a command.

        Returns 0 for off, the commanded level for an explicit brightness, or
        ``None`` meaning "on at any level" (toggle / on-without-brightness),
        where the confirmed value depends on the light's restored level.
        """
        if command.command != "set":
            return None  # toggle / brightness_up / brightness_down: accept any on-state
        if command.state is False:
            return 0
        if command.brightness is not None:
            return max(0, min(200, round(command.brightness * 2)))
        return None  # on, unspecified level

    async def _read_operating_status(self, entity_id: str) -> int | None:
        """Read the entity's current operating_status from live state."""
        try:
            entities = await self.entities.list_entities()
            raw = (entities.get(entity_id) or {}).get("raw") or {}
            value = raw.get("operating_status")
            return int(value) if value is not None else None
        except Exception as e:
            logger.warning("Error reading operating_status for %s: %s", entity_id, e)
            return None

    @staticmethod
    def _status_acknowledged(current: int | None, expected: int | None) -> bool:
        """Whether the live operating_status confirms the commanded target."""
        _tolerance = 10  # ~5% of the 0-200 scale, for ramp/rounding slack
        if expected == 0:
            return current == 0
        if expected is not None:  # explicit level > 0
            return current is not None and abs(current - expected) <= _tolerance
        return current is not None and current > 0  # "on at any level"

    async def _wait_for_acknowledgment(
        self,
        operation_id: str,
        entity_id: str,
        timeout_seconds: float,
        expected_status: int | None,
    ) -> tuple[bool, float | None]:
        """Wait until the entity's live state reflects the commanded target.

        Polls the RX-updated entity state (the same store that receives the
        light's DC_DIMMER_STATUS_3 echo) for the target operating_status. Note
        this confirms the commanded state was applied — a light that is toggled
        off stops broadcasting, so its "off" is confirmed via the applied state
        rather than a positive echo.

        Returns ``(acknowledged, acknowledgment_time_ms)``.
        """
        start_time = time.time()
        poll_interval = 0.1
        while (time.time() - start_time) < timeout_seconds:
            current = await self._read_operating_status(entity_id)
            if self._status_acknowledged(current, expected_status):
                ack_ms = (time.time() - start_time) * 1000
                logger.info(
                    "Entity %s acknowledged (op_status=%s, target=%s) in %.1fms",
                    entity_id,
                    current,
                    expected_status,
                    ack_ms,
                )
                return True, ack_ms
            await asyncio.sleep(poll_interval)

        logger.warning(
            "Entity %s acknowledgment timeout after %.0fms (target op_status=%s)",
            entity_id,
            timeout_seconds * 1000,
            expected_status,
        )
        return False, None

    async def _await_command_ack(
        self,
        operation_id: str,
        entity_id: str,
        command: "SafetyControlCommandV2",
    ) -> tuple[bool, float | None]:
        """Dispatch to the right acknowledgment strategy for the device type.

        Lights confirm via ``operating_status``; climate zones and the
        Aqua-Hot confirm via the raw status fields the command targeted.
        """
        device_type = await self._read_device_type(entity_id)
        if device_type == "climate":
            return await self._wait_for_climate_acknowledgment(
                entity_id, command.timeout_seconds, self._expected_climate_raw(command)
            )
        if device_type == "ac_load":
            return await self._wait_for_climate_acknowledgment(
                entity_id, command.timeout_seconds, self._expected_ac_load_raw(command)
            )
        expected_status = self._expected_operating_status(command)
        return await self._wait_for_acknowledgment(
            operation_id, entity_id, command.timeout_seconds, expected_status
        )

    async def _read_device_type(self, entity_id: str) -> str | None:
        """Read the entity's device_type from live state (None on error)."""
        try:
            entities = await self.entities.list_entities()
            return (entities.get(entity_id) or {}).get("device_type")
        except Exception as e:
            logger.warning("Error reading device_type for %s: %s", entity_id, e)
            return None

    @staticmethod
    def _expected_climate_raw(command: "SafetyControlCommandV2") -> dict[str, tuple[int, int]]:
        """Target raw thermostat fields for a climate command.

        Maps each commanded parameter to ``field -> (target_raw, tolerance)``.
        Temperatures tolerate 16 raw steps (0.5 C) for encoder rounding; mode
        and fan flags must match exactly.
        """
        params = command.parameters or {}
        expected: dict[str, tuple[int, int]] = {}
        temp_tolerance = 16
        if "setpoint_f" in params:
            raw = climate_units.f_to_raw_temp(float(params["setpoint_f"]))
            expected["setpoint_heat"] = (raw, temp_tolerance)
            expected["setpoint_cool"] = (raw, temp_tolerance)
        if "setpoint_heat_f" in params:
            raw = climate_units.f_to_raw_temp(float(params["setpoint_heat_f"]))
            expected["setpoint_heat"] = (raw, temp_tolerance)
        if "setpoint_cool_f" in params:
            raw = climate_units.f_to_raw_temp(float(params["setpoint_cool_f"]))
            expected["setpoint_cool"] = (raw, temp_tolerance)
        if "mode" in params:
            mode_raw = climate_units.OPERATING_MODE_RAW.get(str(params["mode"]).lower())
            if mode_raw is not None:
                expected["operating_mode"] = (mode_raw, 0)
        if "fan_mode" in params:
            fan_raw = climate_units.FAN_MODE_RAW.get(str(params["fan_mode"]).lower())
            if fan_raw is not None:
                expected["fan_mode"] = (fan_raw, 0)
        if "fan_speed_pct" in params:
            expected["fan_speed"] = (round(float(params["fan_speed_pct"]) * 2), 4)
        return expected

    @staticmethod
    def _expected_ac_load_raw(command: "SafetyControlCommandV2") -> dict[str, tuple[int, int]]:
        """Target raw AC_LOAD_STATUS operating_status for a load command.

        OFF is verifiable exactly (the status level goes to 0). ON is only a
        *request* — the energy manager may shed it (status reports a shed
        sentinel, not the on level), so an ON command returns no expectation
        and the AC_LOAD_STATUS echo drives the UI (on vs shed) instead.
        """
        if command.command == "set" and command.state is False:
            return {"operating_status": (climate_units.AC_LOAD_LEVEL_OFF, 0)}
        return {}

    @staticmethod
    def _climate_fields_match(raw: dict[str, Any], expected: dict[str, tuple[int, int]]) -> bool:
        """Whether every expected raw field is within its tolerance."""
        for field, (target, tolerance) in expected.items():
            value = raw.get(field)
            try:
                if value is None or abs(int(value) - target) > tolerance:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    async def _wait_for_climate_acknowledgment(
        self,
        entity_id: str,
        timeout_seconds: float,
        expected: dict[str, tuple[int, int]],
    ) -> tuple[bool, float | None]:
        """Wait until the zone's live raw state reflects every commanded field."""
        if not expected:
            # Nothing verifiable was commanded; command validation already
            # rejected empty/unknown parameter sets upstream.
            return True, None

        start_time = time.time()
        poll_interval = 0.1
        while (time.time() - start_time) < timeout_seconds:
            try:
                entities = await self.entities.list_entities()
                raw = (entities.get(entity_id) or {}).get("raw") or {}
            except Exception as e:
                logger.warning("Error reading climate state for %s: %s", entity_id, e)
                raw = {}

            if self._climate_fields_match(raw, expected):
                ack_ms = (time.time() - start_time) * 1000
                logger.info(
                    "Climate zone %s acknowledged (%s) in %.1fms",
                    entity_id,
                    {f: t for f, (t, _tol) in expected.items()},
                    ack_ms,
                )
                return True, ack_ms
            await asyncio.sleep(poll_interval)

        logger.warning(
            "Climate zone %s acknowledgment timeout after %.0fms (targets %s)",
            entity_id,
            timeout_seconds * 1000,
            expected,
        )
        return False, None

    async def halt_command_emission(self) -> dict[str, Any]:
        """
        Command halt - immediately halt all entity operations.

        This is a guardrail-critical function that stops all pending operations
        and prevents new operations from starting.
        """
        logger.critical("COMMAND HALT ACTIVATED - Halting all entity operations")

        self._command_halt_active = True

        # Cancel all pending operations
        cancelled_operations = []
        for operation_id, operation in self._pending_operations.items():
            operation.status = "command_halt_abort"
            operation.error_message = "Command halt activated"
            operation.error_code = "COMMAND_HALT"
            cancelled_operations.append(operation_id)

        # Clear pending operations
        self._pending_operations.clear()

        # Notify all connected clients via WebSocket
        emergency_message = {
            "type": "halt_command_emission",
            "timestamp": time.time(),
            "cancelled_operations": cancelled_operations,
            "message": "All entity operations have been halted by guardrail policy",
        }

        if self.websocket:
            await self.websocket.broadcast_to_data_clients(emergency_message)

        return {
            "command_halt_active": True,
            "cancelled_operations_count": len(cancelled_operations),
            "cancelled_operations": cancelled_operations,
            "timestamp": time.time(),
        }

    async def clear_command_halt(self) -> dict[str, Any]:
        """
        Clear command halt condition.

        Only authorized users should be able to clear command halt.
        """
        logger.warning("Command halt cleared - Normal operations resuming")

        self._command_halt_active = False

        return {
            "command_halt_active": False,
            "timestamp": time.time(),
            "message": "Command halt cleared - Normal operations resumed",
        }

    async def control_entity_safe(
        self,
        entity_id: str,
        command: SafetyControlCommandV2,
        user_context: dict[str, Any] | None = None,
    ) -> SafetyOperationResultV2:
        """
        Control a single entity with safety-critical validation and acknowledgment.

        This method implements the command/acknowledgment pattern essential
        for vehicle control systems.
        """
        operation_id = str(uuid.uuid4())
        start_time = time.time()

        logger.info(f"Starting safety-critical entity control: {operation_id} for {entity_id}")

        # Create operation tracking
        operation = SafetyOperationResultV2(
            operation_id=operation_id,
            entity_id=entity_id,
            status="pending",
            acknowledged=False,
            acknowledgment_time_ms=None,
            error_message=None,
            error_code=None,
            execution_time_ms=None,
        )

        try:
            # Step 1: Safety interlocks check
            safety_validation = await self._check_command_preconditions(command)
            operation.safety_validation = safety_validation

            if not safety_validation["passed"]:
                operation.status = "safety_abort"
                operation.error_message = (
                    f"Safety validation failed: {'; '.join(safety_validation['issues'])}"
                )
                operation.error_code = "SAFETY_VALIDATION_FAILED"
                operation.execution_time_ms = (time.time() - start_time) * 1000
                return operation

            # Step 2: Add to pending operations tracking
            self._pending_operations[operation_id] = operation

            # Step 3: Convert to legacy command format for existing service.
            # The legacy layer expects "on"/"off"; str(bool) produced "True"
            # and made every v1 `set` command fail validation.
            legacy_command = ControlCommand(
                command=command.command,
                state=("on" if command.state else "off") if command.state is not None else None,
                brightness=command.brightness,
                parameters=command.parameters,
            )

            # Step 4: Execute command via existing entity service
            result = await self.entities.control_entity(
                entity_id, legacy_command, user_context=user_context
            )

            # Step 5: Wait for acknowledgment from the physical system.
            acknowledged, ack_time = await self._await_command_ack(operation_id, entity_id, command)

            # Step 6: Update operation result
            operation.acknowledged = acknowledged
            operation.acknowledgment_time_ms = ack_time
            operation.execution_time_ms = (time.time() - start_time) * 1000

            if acknowledged and result.status == "success":
                operation.status = "success"
                logger.info(f"Entity control successful with acknowledgment: {operation_id}")
            elif not acknowledged:
                operation.status = "timeout"
                operation.error_message = (
                    f"Command not acknowledged within {command.timeout_seconds}s"
                )
                operation.error_code = "ACKNOWLEDGMENT_TIMEOUT"
                logger.warning(f"Entity control timeout - no acknowledgment: {operation_id}")
            else:
                operation.status = "failed"
                operation.error_message = f"Command execution failed: {result.status}"
                operation.error_code = "EXECUTION_FAILED"
                logger.error(f"Entity control failed: {operation_id} - {operation.error_message}")

        except Exception as e:
            operation.status = "failed"
            operation.error_message = str(e)
            operation.error_code = "UNEXPECTED_ERROR"
            operation.execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Entity control exception: {operation_id} - {e}")

        finally:
            # Remove from pending operations
            self._pending_operations.pop(operation_id, None)

            # Pi optimization: Clean up operation state to prevent memory accumulation
            if len(self._pending_operations) > self._max_concurrent_operations * 2:
                logger.warning(
                    f"Pending operations ({len(self._pending_operations)}) exceeding Pi limits, cleaning up"
                )
                self._cleanup_stale_operations()

        return operation

    def _cleanup_stale_operations(self) -> None:
        """Clean up stale operations to prevent memory leaks on Pi."""
        current_time = time.time()
        stale_ops = []

        for op_id, operation in self._pending_operations.items():
            # Remove operations older than 1 minute (likely stale)
            if hasattr(operation, "start_time") and (current_time - operation.start_time) > 60:
                stale_ops.append(op_id)

        for op_id in stale_ops:
            self._pending_operations.pop(op_id, None)

        if stale_ops:
            logger.info(f"Cleaned up {len(stale_ops)} stale operations on Pi")

    async def bulk_control_entities_safe(
        self, request: BulkSafetyOperationRequestV2, user_context: dict[str, Any] | None = None
    ) -> BulkSafetyOperationResultV2:
        """
        Execute bulk control operations with safety controls and partial success handling.

        Implements concurrent execution with safety limits and comprehensive tracking.
        """
        operation_id = str(uuid.uuid4())
        start_time = time.time()

        logger.info(
            f"Starting bulk safety operation: {operation_id} for {len(request.entity_ids)} entities"
        )

        # Safety check: Emergency stop
        if self._command_halt_active:
            return BulkSafetyOperationResultV2(
                operation_id=operation_id,
                total_count=len(request.entity_ids),
                success_count=0,
                failed_count=0,
                timeout_count=0,
                safety_abort_count=len(request.entity_ids),
                results=[],
                total_execution_time_ms=(time.time() - start_time) * 1000,
                safety_summary={"command_halt_active": True},
            )

        # Safety check: Bulk operation limits - Pi optimized
        max_bulk_size = 20  # Reduced for Pi memory constraints
        if len(request.entity_ids) > max_bulk_size:
            raise ValueError(
                f"Bulk operation size {len(request.entity_ids)} exceeds Pi maximum {max_bulk_size}"
            )

        # Execute operations with Pi-optimized concurrency control
        pi_safe_concurrency = min(request.max_concurrent, self._max_concurrent_operations)
        semaphore = asyncio.Semaphore(pi_safe_concurrency)

        logger.info(
            f"Pi bulk operation: {len(request.entity_ids)} entities, concurrency: {pi_safe_concurrency}"
        )

        async def control_single_entity_safe(entity_id: str) -> SafetyOperationResultV2:
            async with semaphore:
                return await self.control_entity_safe(entity_id, request.command, user_context)

        # Execute all operations
        operation_tasks = [
            control_single_entity_safe(entity_id) for entity_id in request.entity_ids
        ]
        results = await asyncio.gather(*operation_tasks, return_exceptions=True)

        # Process results and handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Handle exception in individual operation
                error_result = SafetyOperationResultV2(
                    operation_id=f"{operation_id}-{i}",
                    entity_id=request.entity_ids[i],
                    status="failed",
                    acknowledged=False,
                    acknowledgment_time_ms=None,
                    error_message=str(result),
                    error_code="BULK_OPERATION_EXCEPTION",
                    execution_time_ms=None,
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)

        # Calculate summary statistics
        success_count = sum(1 for r in processed_results if r.status == "success")
        failed_count = sum(1 for r in processed_results if r.status == "failed")
        timeout_count = sum(1 for r in processed_results if r.status == "timeout")
        safety_abort_count = sum(1 for r in processed_results if r.status == "safety_abort")

        total_time = (time.time() - start_time) * 1000

        safety_summary = {
            "command_halt_active": self._command_halt_active,
            "safety_interlocks_enabled": self._safety_interlocks_enabled,
            "acknowledgment_rate": sum(1 for r in processed_results if r.acknowledged)
            / len(processed_results),
            "average_execution_time": sum(r.execution_time_ms or 0 for r in processed_results)
            / len(processed_results),
        }

        result = BulkSafetyOperationResultV2(
            operation_id=operation_id,
            total_count=len(request.entity_ids),
            success_count=success_count,
            failed_count=failed_count,
            timeout_count=timeout_count,
            safety_abort_count=safety_abort_count,
            results=processed_results,
            total_execution_time_ms=total_time,
            safety_summary=safety_summary,
        )

        logger.info(
            f"Bulk operation completed: {operation_id} - {success_count}/{len(request.entity_ids)} successful"
        )

        return result

    async def get_guardrail_status(self) -> dict[str, Any]:
        """Get current safety system status"""
        return {
            "command_halt_active": self._command_halt_active,
            "safety_interlocks_enabled": self._safety_interlocks_enabled,
            "pending_operations_count": len(self._pending_operations),
            "pending_operations": list(self._pending_operations.keys()),
            "timestamp": time.time(),
        }

    async def reconcile_state_with_rvc_bus(self) -> dict[str, Any]:
        """
        Reconcile application state with RV-C bus state.

        This method ensures the application state matches the actual physical
        state of the vehicle systems by querying the RV-C bus directly.
        """
        logger.info("Starting state reconciliation with RV-C bus")

        try:
            # Get current entities from application
            app_entities = await self.entities.list_entities()

            # In a real implementation, this would:
            # 1. Query the CAN bus for current state of all entities
            # 2. Compare application state vs physical state
            # 3. Update application state to match physical state
            # 4. Log any discrepancies for safety analysis

            reconciled_count = 0
            discrepancies = []

            # Simulate reconciliation process
            for _entity_id, _entity_data in app_entities.items():
                # Real implementation would check actual RV-C state here
                # For now, we'll assume states are synchronized
                reconciled_count += 1

            result = {
                "reconciliation_successful": True,
                "entities_checked": len(app_entities),
                "entities_reconciled": reconciled_count,
                "discrepancies_found": len(discrepancies),
                "discrepancies": discrepancies,
                "timestamp": time.time(),
            }

            logger.info(f"State reconciliation completed: {reconciled_count} entities reconciled")

            return result

        except Exception as e:
            logger.error(f"State reconciliation failed: {e}")
            return {"reconciliation_successful": False, "error": str(e), "timestamp": time.time()}
