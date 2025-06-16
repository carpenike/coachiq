"""
CAN Message Injection Tool

Safe and controlled CAN message injection for testing and diagnostics.
Includes safety checks, validation, and audit logging.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import can

from backend.models.can_message import CANMessage
from backend.services.feature_base import Feature

logger = logging.getLogger(__name__)

# Safety constants
MAX_INJECTION_RATE = 100  # Max messages per second
MIN_MESSAGE_INTERVAL = 0.01  # 10ms minimum between messages
DANGEROUS_PGNS = {
    0xFEF1,  # Cruise Control/Vehicle Speed
    0xFEF2,  # Electronic Brake Controller
    0xFEF3,  # Electronic Transmission Controller
    0xFEF4,  # Electronic Engine Controller
    0xFEF5,  # Electronic Retarder Controller
    0xFEFC,  # Dash Display
    0xFEEC,  # Vehicle Electrical Power
    0xFEEF,  # Engine Fluid Level/Pressure
}


class InjectionMode(str, Enum):
    """Message injection modes."""

    SINGLE = "single"  # Send one message
    BURST = "burst"  # Send burst of messages
    PERIODIC = "periodic"  # Send messages at regular intervals
    SEQUENCE = "sequence"  # Send a sequence of different messages


class SafetyLevel(str, Enum):
    """Safety validation levels."""

    STRICT = "strict"  # Block all potentially dangerous messages
    MODERATE = "moderate"  # Warn on dangerous messages
    PERMISSIVE = "permissive"  # Allow all messages (testing only)


@dataclass
class InjectionRequest:
    """Request to inject CAN messages."""

    can_id: int
    data: bytes
    interface: str = "can0"
    mode: InjectionMode = InjectionMode.SINGLE
    count: int = 1  # For burst mode
    interval: float = 1.0  # For periodic mode (seconds)
    duration: float = 0.0  # For periodic mode (0 = infinite)
    priority: int = 6  # J1939 priority (0-7)
    source_address: int = 0xFE  # Use test source address
    destination_address: int = 0xFF  # Global destination

    # Metadata
    description: str = ""
    reason: str = ""
    user: str = "system"

    def __post_init__(self):
        """Validate injection request."""
        if self.can_id < 0 or self.can_id > 0x1FFFFFFF:
            raise ValueError(f"Invalid CAN ID: {self.can_id}")

        if len(self.data) > 8:
            raise ValueError(f"Data too long: {len(self.data)} bytes (max 8)")

        if self.mode == InjectionMode.BURST and self.count > 1000:
            raise ValueError(f"Burst count too high: {self.count} (max 1000)")

        if self.mode == InjectionMode.PERIODIC and self.interval < MIN_MESSAGE_INTERVAL:
            raise ValueError(
                f"Interval too short: {self.interval}s (min {MIN_MESSAGE_INTERVAL}s)"
            )


@dataclass
class InjectionResult:
    """Result of message injection."""

    success: bool
    messages_sent: int = 0
    messages_failed: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: float = field(default_factory=time.time)
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        """Get injection duration in seconds."""
        return self.end_time - self.start_time

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        total = self.messages_sent + self.messages_failed
        return (self.messages_sent / total * 100) if total > 0 else 0.0


class CANMessageInjector(Feature):
    """
    Safe CAN message injection tool.

    Features:
    - Multiple injection modes (single, burst, periodic, sequence)
    - Safety validation with configurable levels
    - Rate limiting and timing controls
    - Audit logging of all injections
    - J1939 protocol support
    - Dangerous message detection
    """

    def __init__(
        self,
        name: str = "can_message_injector",
        enabled: bool = True,
        core: bool = False,
        safety_level: SafetyLevel = SafetyLevel.MODERATE,
        audit_callback: Optional[Callable[[InjectionRequest, InjectionResult], None]] = None,
        **kwargs,
    ):
        """
        Initialize CAN message injector.

        Args:
            name: Feature name
            enabled: Whether feature is enabled
            core: Whether this is a core feature
            safety_level: Safety validation level
            audit_callback: Optional callback for audit logging
            **kwargs: Additional feature configuration
        """
        super().__init__(name=name, enabled=enabled, core=core, **kwargs)

        self.safety_level = safety_level
        self.audit_callback = audit_callback

        # CAN interfaces
        self._buses: dict[str, can.BusABC] = {}
        self._active_injections: dict[str, asyncio.Task] = {}

        # Statistics
        self._stats = {
            "total_injected": 0,
            "total_failed": 0,
            "dangerous_blocked": 0,
            "rate_limited": 0,
        }

        logger.info(
            "CANMessageInjector initialized: safety_level=%s",
            safety_level.value
        )

    async def startup(self) -> None:
        """Start the message injector."""
        logger.info("Starting CAN message injector")

    async def shutdown(self) -> None:
        """Shutdown the message injector."""
        logger.info("Shutting down CAN message injector")

        # Cancel all active injections
        for task_id, task in self._active_injections.items():
            logger.debug("Cancelling injection task: %s", task_id)
            task.cancel()

        # Wait for tasks to complete
        if self._active_injections:
            await asyncio.gather(
                *self._active_injections.values(),
                return_exceptions=True
            )

        # Close CAN buses
        for interface, bus in self._buses.items():
            logger.debug("Closing CAN bus: %s", interface)
            bus.shutdown()

        self._buses.clear()
        self._active_injections.clear()

    def _get_or_create_bus(self, interface: str) -> can.BusABC:
        """Get or create CAN bus for interface."""
        if interface not in self._buses:
            try:
                self._buses[interface] = can.interface.Bus(
                    interface, bustype="socketcan"
                )
                logger.info("Created CAN bus for interface: %s", interface)
            except Exception as e:
                logger.error("Failed to create CAN bus %s: %s", interface, e)
                raise

        return self._buses[interface]

    def _extract_pgn(self, can_id: int) -> int:
        """Extract PGN from J1939 CAN ID."""
        # J1939 29-bit identifier structure
        if can_id > 0x7FF:  # Extended CAN ID
            pgn = (can_id >> 8) & 0x3FFFF
            # Handle PDU1 vs PDU2 format
            if (pgn >> 8) < 240:
                pgn &= 0x3FF00  # PDU1: zero out destination address
            return pgn
        return 0

    def _validate_safety(self, request: InjectionRequest) -> list[str]:
        """
        Validate injection request for safety.

        Returns:
            List of warnings (empty if safe)

        Raises:
            ValueError: If request violates safety rules
        """
        warnings = []

        # Extract PGN for J1939 messages
        pgn = self._extract_pgn(request.can_id)

        # Check dangerous PGNs
        if pgn in DANGEROUS_PGNS:
            msg = f"Dangerous PGN detected: 0x{pgn:04X} - {self._get_pgn_name(pgn)}"

            if self.safety_level == SafetyLevel.STRICT:
                self._stats["dangerous_blocked"] += 1
                raise ValueError(f"Safety violation: {msg}")
            elif self.safety_level == SafetyLevel.MODERATE:
                warnings.append(f"Warning: {msg}")

        # Check for broadcast storms
        if request.mode == InjectionMode.PERIODIC and request.interval < 0.1:
            msg = "High frequency injection may cause broadcast storm"
            if self.safety_level != SafetyLevel.PERMISSIVE:
                warnings.append(f"Warning: {msg}")

        # Check data patterns that might indicate control messages
        if len(request.data) >= 2:
            # Check for specific control patterns
            if request.data[0] in [0x00, 0x01] and request.data[1] in range(0x10):
                warnings.append("Data pattern suggests control message")

        return warnings

    def _get_pgn_name(self, pgn: int) -> str:
        """Get human-readable name for PGN."""
        pgn_names = {
            0xFEF1: "Cruise Control/Vehicle Speed",
            0xFEF2: "Electronic Brake Controller",
            0xFEF3: "Electronic Transmission Controller",
            0xFEF4: "Electronic Engine Controller",
            0xFEF5: "Electronic Retarder Controller",
            0xFEFC: "Dash Display",
            0xFEEC: "Vehicle Electrical Power",
            0xFEEF: "Engine Fluid Level/Pressure",
        }
        return pgn_names.get(pgn, f"Unknown PGN 0x{pgn:04X}")

    async def inject(self, request: InjectionRequest) -> InjectionResult:
        """
        Inject CAN message(s) based on request.

        Args:
            request: Injection request

        Returns:
            Injection result
        """
        result = InjectionResult(success=False)

        try:
            # Validate safety
            warnings = self._validate_safety(request)
            result.warnings.extend(warnings)

            # Log injection attempt
            logger.info(
                "Injection request: interface=%s, can_id=0x%X, mode=%s, user=%s, reason=%s",
                request.interface, request.can_id, request.mode.value,
                request.user, request.reason
            )

            # Get CAN bus
            bus = self._get_or_create_bus(request.interface)

            # Perform injection based on mode
            if request.mode == InjectionMode.SINGLE:
                await self._inject_single(bus, request, result)
            elif request.mode == InjectionMode.BURST:
                await self._inject_burst(bus, request, result)
            elif request.mode == InjectionMode.PERIODIC:
                await self._inject_periodic(bus, request, result)
            elif request.mode == InjectionMode.SEQUENCE:
                # TODO: Implement sequence mode
                raise NotImplementedError("Sequence mode not yet implemented")

            result.success = result.messages_sent > 0
            result.end_time = time.time()

        except Exception as e:
            logger.error("Injection failed: %s", e)
            result.error = str(e)
            result.end_time = time.time()

        # Update statistics
        self._stats["total_injected"] += result.messages_sent
        self._stats["total_failed"] += result.messages_failed

        # Audit logging
        if self.audit_callback:
            try:
                self.audit_callback(request, result)
            except Exception as e:
                logger.error("Audit callback failed: %s", e)

        return result

    async def _inject_single(
        self,
        bus: can.BusABC,
        request: InjectionRequest,
        result: InjectionResult,
    ) -> None:
        """Inject a single message."""
        msg = can.Message(
            arbitration_id=request.can_id,
            data=request.data,
            is_extended_id=(request.can_id > 0x7FF),
        )

        try:
            bus.send(msg)
            result.messages_sent = 1
            logger.debug("Injected single message: %s", msg)
        except Exception as e:
            logger.error("Failed to send message: %s", e)
            result.messages_failed = 1
            raise

    async def _inject_burst(
        self,
        bus: can.BusABC,
        request: InjectionRequest,
        result: InjectionResult,
    ) -> None:
        """Inject a burst of messages."""
        msg = can.Message(
            arbitration_id=request.can_id,
            data=request.data,
            is_extended_id=(request.can_id > 0x7FF),
        )

        # Calculate timing
        interval = max(MIN_MESSAGE_INTERVAL, 1.0 / MAX_INJECTION_RATE)

        for i in range(request.count):
            try:
                bus.send(msg)
                result.messages_sent += 1

                # Rate limiting
                if i < request.count - 1:
                    await asyncio.sleep(interval)

            except Exception as e:
                logger.error("Failed to send message %d: %s", i, e)
                result.messages_failed += 1
                if result.messages_failed > 10:  # Stop after 10 failures
                    raise

        logger.debug(
            "Injected burst: sent=%d, failed=%d",
            result.messages_sent, result.messages_failed
        )

    async def _inject_periodic(
        self,
        bus: can.BusABC,
        request: InjectionRequest,
        result: InjectionResult,
    ) -> None:
        """Inject messages periodically."""
        msg = can.Message(
            arbitration_id=request.can_id,
            data=request.data,
            is_extended_id=(request.can_id > 0x7FF),
        )

        # Create unique task ID
        task_id = f"{request.interface}_{request.can_id}_{time.time()}"

        async def periodic_sender():
            """Periodic message sender task."""
            start_time = time.time()

            try:
                while True:
                    # Check duration limit
                    if request.duration > 0:
                        if time.time() - start_time > request.duration:
                            break

                    try:
                        bus.send(msg)
                        result.messages_sent += 1
                    except Exception as e:
                        logger.error("Failed to send periodic message: %s", e)
                        result.messages_failed += 1

                    await asyncio.sleep(request.interval)

            except asyncio.CancelledError:
                logger.debug("Periodic injection cancelled: %s", task_id)
                raise
            finally:
                # Remove from active injections
                self._active_injections.pop(task_id, None)

        # Start periodic task
        task = asyncio.create_task(periodic_sender())
        self._active_injections[task_id] = task

        # If duration specified, wait for completion
        if request.duration > 0:
            await asyncio.sleep(request.duration)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def stop_injection(self, pattern: Optional[str] = None) -> int:
        """
        Stop active periodic injections.

        Args:
            pattern: Optional pattern to match task IDs

        Returns:
            Number of injections stopped
        """
        stopped = 0

        for task_id, task in list(self._active_injections.items()):
            if pattern is None or pattern in task_id:
                logger.info("Stopping injection: %s", task_id)
                task.cancel()
                stopped += 1

        return stopped

    def get_statistics(self) -> dict[str, Any]:
        """Get injection statistics."""
        return {
            **self._stats,
            "active_injections": len(self._active_injections),
            "active_interfaces": list(self._buses.keys()),
            "safety_level": self.safety_level.value,
        }

    def create_j1939_message(
        self,
        pgn: int,
        data: bytes,
        priority: int = 6,
        source_address: int = 0xFE,
        destination_address: int = 0xFF,
    ) -> int:
        """
        Create J1939 CAN ID from components.

        Args:
            pgn: Parameter Group Number
            data: Message data
            priority: Message priority (0-7)
            source_address: Source address
            destination_address: Destination address (for PDU1)

        Returns:
            29-bit CAN identifier
        """
        # Determine PDU format
        pdu_format = (pgn >> 8) & 0xFF

        if pdu_format < 240:  # PDU1 - destination specific
            can_id = (
                (priority & 0x7) << 26 |
                (pgn & 0x3FF00) << 8 |
                (destination_address & 0xFF) << 8 |
                (source_address & 0xFF)
            )
        else:  # PDU2 - broadcast
            can_id = (
                (priority & 0x7) << 26 |
                (pgn & 0x3FFFF) << 8 |
                (source_address & 0xFF)
            )

        return can_id | 0x80000000  # Set extended ID bit
