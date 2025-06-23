"""
Protocol Router for unified CAN message routing and processing.

This module provides a centralized routing system that coordinates between
BAM handler, RV-C decoder, J1939 decoder, security manager, and safety engine.
Ensures proper message flow and enforces safety and security policies.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, ClassVar

from backend.core.safety_state_engine import SafetyEvent, SafetyStateEngine
from backend.integrations.rvc.bam_handler import BAMHandler
from backend.integrations.rvc.decoder_core import DecodedValue, DecodeError

logger = logging.getLogger(__name__)


@dataclass
class CANFrame:
    """Represents a CAN frame for processing."""

    arbitration_id: int
    pgn: int
    source_address: int
    destination_address: int
    data: bytes
    timestamp: float
    is_extended: bool = True


@dataclass
class ProcessedMessage:
    """Result of message processing through the router."""

    pgn: int
    source_address: int
    decoded_data: dict[str, DecodedValue | DecodeError]
    errors: list[DecodeError]
    processing_time_ms: float
    protocol: str  # "RVC", "J1939", "BAM"
    safety_events: list[SafetyEvent]


class SecurityManager:
    """Basic security manager interface for validation."""

    def validate_frame(self, frame: CANFrame) -> bool:
        """Validate frame against security policies."""
        # Basic validation - can be replaced with more sophisticated logic
        return True


class ProtocolRouter:
    """
    Unified protocol router for CAN message processing.

    This router coordinates between different protocol handlers and ensures
    proper message flow with security validation and safety event processing.
    """

    # Transport Protocol PGNs
    TRANSPORT_PGNS: ClassVar[set[int]] = {0xEC00, 0xEB00}  # TP.CM, TP.DT

    # RV-C specific PGN ranges
    RVC_PGN_MIN: ClassVar[int] = 0x1F000
    RVC_PGN_MAX: ClassVar[int] = 0x1FFFF

    # Speed threshold for vehicle movement detection
    MOVING_SPEED_THRESHOLD: ClassVar[float] = 0.5  # mph

    def __init__(
        self,
        bam_handler: BAMHandler,
        safety_engine: SafetyStateEngine,
        security_manager: SecurityManager | None = None,
    ):
        """
        Initialize the protocol router.

        Args:
            bam_handler: Handler for multi-packet BAM messages
            safety_engine: Safety state management engine
            security_manager: Optional security validation manager
        """
        self.bam_handler = bam_handler
        self.safety_engine = safety_engine
        self.security_manager = security_manager or SecurityManager()

        # Performance tracking
        self.processed_count = 0
        self.error_count = 0
        self.last_reset = time.time()

        # Mock decoders - these would be replaced with actual implementations
        self._rvc_decoder = None
        self._j1939_decoder = None

    async def route_frame(self, frame: CANFrame) -> ProcessedMessage | None:
        """
        Route a CAN frame through the appropriate processing pipeline.

        Args:
            frame: The CAN frame to process

        Returns:
            ProcessedMessage if processing succeeded, None if filtered/failed
        """
        start_time = time.time()
        self.processed_count += 1

        try:
            # 1. Security validation first
            if not self.security_manager.validate_frame(frame):
                logger.warning(f"Security validation failed for frame PGN {frame.pgn:04X}")
                return None

            # 2. Route to appropriate handler
            if frame.pgn in self.TRANSPORT_PGNS:
                # Multi-packet transport protocol
                completed_message = self.bam_handler.process_frame(
                    frame.pgn, frame.data, frame.source_address
                )
                if completed_message:
                    target_pgn, reassembled_data = completed_message
                    return await self._decode_completed_message(
                        target_pgn, reassembled_data, frame.source_address, start_time
                    )
            else:
                # Single-frame message
                return await self._decode_single_frame(frame, start_time)

        except Exception as e:
            self.error_count += 1
            logger.error(f"Error routing frame PGN {frame.pgn:04X}: {e}")
            return None

        return None

    async def _decode_single_frame(
        self, frame: CANFrame, start_time: float
    ) -> ProcessedMessage | None:
        """Decode a single-frame CAN message."""
        # Mock implementation - would use actual decoders
        protocol = "RVC" if self._is_rvc_pgn(frame.pgn) else "J1939"

        # Simulate decoding result
        decoded_data = {
            "signal_1": DecodedValue(value=42, unit="units", raw_value=42),
            "signal_2": DecodedValue(value="test", unit=None, raw_value=1),
        }
        errors = []

        # Extract safety events from decoded data
        safety_events = self._extract_safety_events(decoded_data, frame.pgn)

        # Process safety events
        for event in safety_events:
            await self._process_safety_event(event, decoded_data)

        processing_time = (time.time() - start_time) * 1000  # Convert to ms

        return ProcessedMessage(
            pgn=frame.pgn,
            source_address=frame.source_address,
            decoded_data=decoded_data,
            errors=errors,
            processing_time_ms=processing_time,
            protocol=protocol,
            safety_events=safety_events,
        )

    async def _decode_completed_message(
        self, pgn: int, data: bytes, source_address: int, start_time: float
    ) -> ProcessedMessage | None:
        """Decode a completed multi-packet message."""
        protocol = "BAM"

        # Mock implementation - would use actual decoders
        decoded_data = {
            "multi_packet_data": DecodedValue(value=len(data), unit="bytes", raw_value=len(data)),
        }
        errors = []

        # Extract safety events
        safety_events = self._extract_safety_events(decoded_data, pgn)

        # Process safety events
        for event in safety_events:
            await self._process_safety_event(event, decoded_data)

        processing_time = (time.time() - start_time) * 1000

        return ProcessedMessage(
            pgn=pgn,
            source_address=source_address,
            decoded_data=decoded_data,
            errors=errors,
            processing_time_ms=processing_time,
            protocol=protocol,
            safety_events=safety_events,
        )

    def _extract_safety_events(
        self, decoded_data: dict[str, DecodedValue | DecodeError], pgn: int
    ) -> list[SafetyEvent]:
        """Extract safety-relevant events from decoded message data."""
        events = []

        # Example safety event extraction based on PGN and signal values
        for signal_name, result in decoded_data.items():
            if isinstance(result, DecodedValue):
                # Parking brake status
                if "park_brake" in signal_name.lower():
                    if result.value is True:
                        events.append(SafetyEvent.PARKING_BRAKE_SET)
                    elif result.value is False:
                        events.append(SafetyEvent.PARKING_BRAKE_RELEASED)

                # Engine status
                elif "engine" in signal_name.lower() and "running" in signal_name.lower():
                    if result.value is True:
                        events.append(SafetyEvent.ENGINE_STARTED)
                    elif result.value is False:
                        events.append(SafetyEvent.ENGINE_STOPPED)

                # Vehicle speed
                elif "speed" in signal_name.lower() and isinstance(result.value, int | float):
                    if result.value > self.MOVING_SPEED_THRESHOLD:
                        events.append(SafetyEvent.VEHICLE_MOVING)
                    else:
                        events.append(SafetyEvent.VEHICLE_STOPPED)

                # Transmission gear
                elif (
                    "transmission" in signal_name.lower() or "gear" in signal_name.lower()
                ) and isinstance(result.value, str):
                    if result.value.lower() in ["park", "p"]:
                        events.append(SafetyEvent.TRANSMISSION_PARK)
                    elif result.value.lower() in ["drive", "d", "reverse", "r"]:
                        events.append(SafetyEvent.TRANSMISSION_DRIVE)

        return events

    async def _process_safety_event(
        self, event: SafetyEvent, decoded_data: dict[str, DecodedValue | DecodeError]
    ) -> None:
        """Process a safety event through the safety engine."""
        # Prepare event data for safety engine
        event_data = {}

        for signal_name, result in decoded_data.items():
            if isinstance(result, DecodedValue):
                # Add relevant data to event context
                if "speed" in signal_name.lower():
                    event_data["speed"] = result.value
                elif "gear" in signal_name.lower() or "transmission" in signal_name.lower():
                    event_data["gear"] = result.value

        # Process through safety engine
        safety_command = self.safety_engine.process_event(event, event_data)

        if safety_command:
            await self._execute_safety_command(safety_command)

    async def _execute_safety_command(self, command) -> None:
        """Execute a safety command generated by the safety engine."""
        logger.info(
            "Executing safety command: %s for %s - %s",
            command.command_type,
            command.target_entity,
            command.reason,
        )

        # This would integrate with the entity control system
        # For now, just log the command
        if not command.allowed:
            logger.warning(f"Safety system blocked operation: {command.reason}")

    def _is_rvc_pgn(self, pgn: int) -> bool:
        """Check if a PGN is in the RV-C range."""
        return self.RVC_PGN_MIN <= pgn <= self.RVC_PGN_MAX

    def get_performance_stats(self) -> dict[str, Any]:
        """Get performance statistics for monitoring."""
        current_time = time.time()
        uptime = current_time - self.last_reset

        return {
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(self.processed_count, 1),
            "processing_rate": self.processed_count / max(uptime, 1),
            "uptime_seconds": uptime,
        }

    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self.processed_count = 0
        self.error_count = 0
        self.last_reset = time.time()
