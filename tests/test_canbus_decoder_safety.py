"""
CAN Bus Decoder Safety Validation Tests

This module contains comprehensive safety validation tests for the CAN decoder
architecture improvements. Tests critical safety scenarios that could result
in dangerous vehicle operations if not properly handled.

CRITICAL: These tests validate safety-critical behavior that prevents:
- Slideout operation while vehicle is moving
- Engine start when transmission not in park
- Emergency stop functionality
- Load testing under realistic CAN traffic
"""

import asyncio
import logging
import time
from unittest.mock import MagicMock

import pytest

from backend.core.safety_state_engine import (
    SafetyCommand,
    SafetyEvent,
    SafetyStateEngine,
    VehicleState,
)
from backend.integrations.can.protocol_router import CANFrame, ProtocolRouter
from backend.integrations.rvc.bam_handler import BAMHandler

# Disable debug logging for cleaner test output
logging.getLogger("backend").setLevel(logging.WARNING)


class TestSafetyValidation:
    """
    Critical safety validation tests for RV-C vehicle control system.

    These tests ensure that the safety state engine properly prevents
    dangerous operations and maintains vehicle safety under all conditions.
    """

    @pytest.fixture
    def safety_engine(self):
        """Create a fresh safety state engine for each test."""
        return SafetyStateEngine()

    @pytest.fixture
    def mock_bam_handler(self):
        """Create a mock BAM handler for testing."""
        return MagicMock(spec=BAMHandler)

    @pytest.fixture
    def protocol_router(self, mock_bam_handler, safety_engine):
        """Create a protocol router with real safety engine."""
        return ProtocolRouter(
            bam_handler=mock_bam_handler,
            safety_engine=safety_engine,
        )

    def test_slideout_blocked_when_vehicle_moving(self, safety_engine):
        """
        CRITICAL: Test that slideout extension is blocked when vehicle is moving.

        This is a critical safety test - slideouts must NEVER extend while
        the vehicle is in motion as this could cause loss of control.
        """
        # Start with vehicle parked safely
        safety_engine.process_event(SafetyEvent.PARKING_BRAKE_SET, {})
        safety_engine.process_event(SafetyEvent.ENGINE_STARTED, {})

        # Verify slideout is allowed when parked
        is_safe, reason = safety_engine.is_operation_safe("slideout_extend", "main_slideout")
        assert is_safe, f"Slideout should be allowed when parked: {reason}"

        # Vehicle starts moving
        safety_engine.process_event(SafetyEvent.VEHICLE_MOVING, {"speed": 5.0})

        # CRITICAL: Slideout must be blocked
        is_safe, reason = safety_engine.is_operation_safe("slideout_extend", "main_slideout")
        assert not is_safe, "SAFETY FAILURE: Slideout extension allowed while moving!"
        assert "moving" in reason.lower(), f"Reason should mention movement: {reason}"

        # Verify current state
        assert safety_engine.get_current_state() == VehicleState.DRIVING

    def test_slideout_blocked_without_parking_brake(self, safety_engine):
        """
        CRITICAL: Test that slideout extension requires parking brake to be set.

        Slideouts should only extend when the parking brake is engaged.
        """
        # Vehicle is stopped but parking brake not set
        safety_engine.process_event(SafetyEvent.VEHICLE_STOPPED, {"speed": 0.0})
        safety_engine.process_event(SafetyEvent.ENGINE_STARTED, {})

        # CRITICAL: Slideout must be blocked without parking brake
        is_safe, reason = safety_engine.is_operation_safe("slideout_extend", "main_slideout")
        assert not is_safe, "SAFETY FAILURE: Slideout allowed without parking brake!"
        assert "parking brake" in reason.lower(), f"Reason should mention parking brake: {reason}"

    def test_engine_start_blocked_when_not_in_park(self, safety_engine):
        """
        CRITICAL: Test that engine start is blocked when transmission is not in park.

        Engine should only start when transmission is in park position.
        """
        # Set transmission to drive
        safety_engine.process_event(SafetyEvent.TRANSMISSION_DRIVE, {"gear": "drive"})

        # CRITICAL: Engine start must be blocked
        is_safe, reason = safety_engine.is_operation_safe("engine_start", "main_engine")
        assert not is_safe, "SAFETY FAILURE: Engine start allowed when not in park!"
        assert "park" in reason.lower(), f"Reason should mention park requirement: {reason}"

        # Set to park - should now allow engine start
        safety_engine.process_event(SafetyEvent.TRANSMISSION_PARK, {"gear": "park"})
        is_safe, reason = safety_engine.is_operation_safe("engine_start", "main_engine")
        assert is_safe, f"Engine start should be allowed in park: {reason}"

    def test_leveling_operations_require_parking_brake(self, safety_engine):
        """
        CRITICAL: Test that leveling operations require parking brake.

        Leveling jacks should only operate when parking brake is set.
        """
        # Vehicle stopped but no parking brake
        safety_engine.process_event(SafetyEvent.VEHICLE_STOPPED, {"speed": 0.0})

        # CRITICAL: Leveling must be blocked without parking brake
        is_safe, reason = safety_engine.is_operation_safe("leveling_extend", "front_jack")
        assert not is_safe, "SAFETY FAILURE: Leveling allowed without parking brake!"

        is_safe, reason = safety_engine.is_operation_safe("leveling_retract", "front_jack")
        assert not is_safe, "SAFETY FAILURE: Leveling retract allowed without parking brake!"

        # Set parking brake - should now allow leveling
        safety_engine.process_event(SafetyEvent.PARKING_BRAKE_SET, {})

        is_safe, reason = safety_engine.is_operation_safe("leveling_extend", "front_jack")
        assert is_safe, f"Leveling should be allowed with parking brake: {reason}"

    def test_state_data_timeout_prevents_operations(self, safety_engine):
        """
        CRITICAL: Test that stale state data prevents safety-critical operations.

        If state data is too old, we cannot guarantee safety and must block operations.
        """
        # Set up initial safe state
        safety_engine.process_event(SafetyEvent.PARKING_BRAKE_SET, {})
        safety_engine.process_event(SafetyEvent.VEHICLE_STOPPED, {"speed": 0.0})

        # Verify operation is initially allowed
        is_safe, reason = safety_engine.is_operation_safe("slideout_extend", "main_slideout")
        assert is_safe, f"Operation should be allowed with fresh data: {reason}"

        # Simulate state data timeout by manipulating last_updated time
        old_time = time.time() - (SafetyStateEngine.STATE_DATA_TIMEOUT + 10)
        safety_engine.state_data.last_updated = old_time

        # CRITICAL: Operation must be blocked with stale data
        is_safe, reason = safety_engine.is_operation_safe("slideout_extend", "main_slideout")
        assert not is_safe, "SAFETY FAILURE: Operation allowed with stale state data!"
        assert "too old" in reason.lower(), f"Reason should mention stale data: {reason}"

    def test_unsafe_state_blocks_all_operations(self, safety_engine):
        """
        CRITICAL: Test that UNSAFE state blocks all operations.

        When the vehicle is in an unsafe state, no operations should be allowed.
        """
        # Force transition to unsafe state (this would normally happen automatically)
        safety_engine.current_state = VehicleState.UNSAFE

        # Test various operations - all should be blocked
        operations = [
            "slideout_extend",
            "slideout_retract",
            "leveling_extend",
            "leveling_retract",
            "engine_start",
        ]

        for operation in operations:
            is_safe, reason = safety_engine.is_operation_safe(operation, "test_entity")
            assert not is_safe, f"SAFETY FAILURE: {operation} allowed in UNSAFE state!"
            assert "unsafe state" in reason.lower(), f"Reason should mention unsafe state: {reason}"

    def test_emergency_stop_on_unsafe_transition(self, safety_engine):
        """
        CRITICAL: Test that emergency stop is triggered on unsafe state transition.

        When vehicle transitions to unsafe state, emergency stop should be commanded.
        """
        # Set up observer to capture safety commands
        commands_received = []

        def safety_observer(command: SafetyCommand):
            commands_received.append(command)

        safety_engine.add_observer(safety_observer)

        # Force transition to unsafe state
        safety_engine._transition_to(VehicleState.UNSAFE)

        # Verify emergency stop command was issued
        assert len(commands_received) == 1, "Emergency stop command should be issued"

        command = commands_received[0]
        assert command.command_type == "emergency_stop"
        assert command.target_entity == "all"
        assert not command.allowed
        assert "unsafe state" in command.reason.lower()

    @pytest.mark.asyncio
    async def test_safety_event_processing_in_protocol_router(self, protocol_router):
        """
        Test that protocol router properly processes safety events.

        This ensures safety events are extracted from CAN messages and
        processed through the safety engine.
        """
        # Create a CAN frame that would trigger safety events
        frame = CANFrame(
            arbitration_id=0x18FED100,  # Example RV-C PGN
            pgn=0x1FED1,
            source_address=0x00,
            destination_address=0xFF,
            data=b"\x01\x00\x00\x00\x00\x00\x00\x00",  # Mock data
            timestamp=time.time(),
        )

        # Process the frame
        result = await protocol_router.route_frame(frame)

        # Verify frame was processed
        assert result is not None, "Frame should be processed successfully"
        assert result.safety_events is not None, "Safety events should be extracted"

    @pytest.mark.asyncio
    async def test_performance_under_load(self, protocol_router):
        """
        PERFORMANCE: Test safety system performance under realistic CAN load.

        Verifies that safety processing maintains acceptable latency
        under high message rates typical of RV CAN networks.
        """
        target_msg_rate = 1000  # 1000 messages per second
        test_duration = 2.0  # 2 seconds
        max_latency_ms = 10.0  # 10ms maximum processing time

        frames_processed = 0
        max_processing_time = 0.0

        # Generate test frames
        test_frames = []
        for i in range(int(target_msg_rate * test_duration)):
            frame = CANFrame(
                arbitration_id=0x18FED100 + (i % 10),
                pgn=0x1FED1 + (i % 10),
                source_address=0x00 + (i % 8),
                destination_address=0xFF,
                data=bytes([i % 256] + [0] * 7),
                timestamp=time.time(),
            )
            test_frames.append(frame)

        # Process frames and measure performance
        start_time = time.time()

        for frame in test_frames:
            frame_start = time.time()

            result = await protocol_router.route_frame(frame)

            processing_time = (time.time() - frame_start) * 1000  # Convert to ms
            max_processing_time = max(max_processing_time, processing_time)

            if result:
                frames_processed += 1

        total_time = time.time() - start_time
        actual_rate = frames_processed / total_time

        # Verify performance requirements
        assert max_processing_time < max_latency_ms, (
            f"Processing latency too high: {max_processing_time:.2f}ms > {max_latency_ms}ms"
        )

        assert actual_rate > (target_msg_rate * 0.8), (
            f"Processing rate too low: {actual_rate:.1f} < {target_msg_rate * 0.8}"
        )

        print("Performance test results:")
        print(f"  Processed: {frames_processed} frames")
        print(f"  Rate: {actual_rate:.1f} frames/sec")
        print(f"  Max latency: {max_processing_time:.2f}ms")

    def test_state_transition_logging(self, safety_engine, caplog):
        """
        Test that state transitions are properly logged for audit trail.

        Safety-critical systems require comprehensive logging for compliance.
        """
        with caplog.at_level(logging.INFO, logger="backend.core.safety_state_engine"):
            # Trigger state transitions
            safety_engine.process_event(SafetyEvent.PARKING_BRAKE_SET, {})
            safety_engine.process_event(SafetyEvent.ENGINE_STARTED, {})
            safety_engine.process_event(SafetyEvent.PARKING_BRAKE_RELEASED, {})

        # Verify state transitions were logged
        log_messages = [record.message for record in caplog.records]
        transition_logs = [msg for msg in log_messages if "state transition" in msg.lower()]

        assert len(transition_logs) >= 2, "State transitions should be logged"

        # Verify log format includes old and new states
        for log_msg in transition_logs:
            assert "->" in log_msg, "Log should show state transition with arrow"

    def test_speed_threshold_accuracy(self, safety_engine):
        """
        Test that speed threshold for movement detection is accurate.

        Verifies that the MOVING_SPEED_THRESHOLD prevents false triggers
        from sensor noise while detecting actual movement.
        """
        # Test values around the threshold
        threshold = SafetyStateEngine.MOVING_SPEED_THRESHOLD

        # Below threshold - should not trigger movement
        safety_engine.process_event(SafetyEvent.VEHICLE_STOPPED, {"speed": threshold - 0.1})
        state = safety_engine.get_current_state()
        assert state != VehicleState.DRIVING, "Below threshold should not trigger driving state"

        # Above threshold - should trigger movement
        safety_engine.process_event(SafetyEvent.VEHICLE_MOVING, {"speed": threshold + 0.1})
        state = safety_engine.get_current_state()
        assert state == VehicleState.DRIVING, "Above threshold should trigger driving state"

    @pytest.mark.asyncio
    async def test_concurrent_safety_processing(self, safety_engine):
        """
        Test safety engine behavior under concurrent access.

        Ensures thread safety when multiple CAN messages trigger
        safety events simultaneously.
        """
        # Create multiple concurrent safety events
        events = [
            (SafetyEvent.PARKING_BRAKE_SET, {}),
            (SafetyEvent.ENGINE_STARTED, {}),
            (SafetyEvent.VEHICLE_STOPPED, {"speed": 0.0}),
            (SafetyEvent.TRANSMISSION_PARK, {"gear": "park"}),
        ]

        # Process events concurrently
        tasks = []
        for event, data in events:
            task = asyncio.create_task(self._process_safety_event(safety_engine, event, data))
            tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # Verify all events were processed successfully
        assert all(result is not None for result in results), (
            "All events should process successfully"
        )

        # Verify final state is consistent
        final_state = safety_engine.get_current_state()
        assert final_state in [VehicleState.PARKED_RUNNING, VehicleState.PARKED_SAFE], (
            f"Final state should be parked, got: {final_state}"
        )

    async def _process_safety_event(self, safety_engine, event, data):
        """Helper method for concurrent testing."""
        # Add small random delay to increase chance of race conditions
        await asyncio.sleep(0.001)
        return safety_engine.process_event(event, data)


class TestBAMHandlerSafety:
    """
    Safety tests specific to BAM handler performance optimization.

    Ensures that the O(1) optimization doesn't introduce safety issues
    or affect message reliability under load.
    """

    @pytest.fixture
    def bam_handler(self):
        """Create a BAM handler for testing."""
        return BAMHandler(session_timeout=30.0, max_concurrent_sessions=50)

    def test_bam_session_cleanup_under_load(self, bam_handler):
        """
        Test that BAM session cleanup works correctly under high load.

        Verifies that the session mapping consistency is maintained
        during cleanup operations.
        """
        # Create many sessions to trigger cleanup
        for source in range(60):  # Exceed max_concurrent_sessions
            for target_pgn in [0x1FEF2, 0x1FEF3]:
                # Simulate BAM start message
                control_data = bytes(
                    [
                        0x20,  # BAM control byte
                        0x20,
                        0x00,  # 32 bytes total
                        0x05,  # 5 packets
                        0xFF,  # Reserved
                        target_pgn & 0xFF,
                        (target_pgn >> 8) & 0xFF,
                        (target_pgn >> 16) & 0xFF,
                    ]
                )

                result = bam_handler.process_frame(BAMHandler.TP_CM_PGN, control_data, source)
                assert result is None  # Control messages don't return data

        # Verify session count is within limits
        assert bam_handler.get_active_session_count() <= bam_handler.max_concurrent_sessions

        # Verify mapping consistency
        total_mapped = sum(len(pgns) for pgns in bam_handler.source_to_sessions.values())
        assert total_mapped == len(bam_handler.sessions), "Session mapping inconsistency detected!"

    def test_bam_reassembly_accuracy_under_load(self, bam_handler):
        """
        Test that BAM message reassembly remains accurate under load.

        Ensures that the O(1) optimization doesn't affect message integrity.
        """
        # Create a test message to reassemble
        test_message = b"This is a test message for BAM reassembly validation testing."
        packets = self._split_message_into_packets(test_message)

        source_address = 0x42
        target_pgn = 0x1FEF2

        # Start BAM session
        control_data = bytes(
            [
                0x20,  # BAM control byte
                len(test_message) & 0xFF,
                (len(test_message) >> 8) & 0xFF,
                len(packets),  # Number of packets
                0xFF,  # Reserved
                target_pgn & 0xFF,
                (target_pgn >> 8) & 0xFF,
                (target_pgn >> 16) & 0xFF,
            ]
        )

        result = bam_handler.process_frame(BAMHandler.TP_CM_PGN, control_data, source_address)
        assert result is None

        # Send data packets (out of order to test robustness)
        packet_order = list(range(1, len(packets) + 1))
        packet_order.reverse()  # Send in reverse order

        for seq_num in packet_order[:-1]:  # All but the last packet
            data_frame = bytes([seq_num]) + packets[seq_num - 1]
            result = bam_handler.process_frame(BAMHandler.TP_DT_PGN, data_frame, source_address)
            assert result is None  # Should not complete yet

        # Send final packet
        seq_num = packet_order[-1]
        data_frame = bytes([seq_num]) + packets[seq_num - 1]
        result = bam_handler.process_frame(BAMHandler.TP_DT_PGN, data_frame, source_address)

        # Verify message was reassembled correctly
        assert result is not None, "Message should be complete"
        reassembled_pgn, reassembled_data = result

        assert reassembled_pgn == target_pgn
        assert reassembled_data == test_message, (
            f"Message corruption detected!\nExpected: {test_message}\nGot: {reassembled_data}"
        )

    def _split_message_into_packets(self, message: bytes) -> list[bytes]:
        """Split a message into 7-byte packets (as per J1939 TP.DT format)."""
        packets = []
        packet_size = 7

        for i in range(0, len(message), packet_size):
            packet = message[i : i + packet_size]
            # Pad to 7 bytes if necessary
            if len(packet) < packet_size:
                packet += b"\x00" * (packet_size - len(packet))
            packets.append(packet)

        return packets


if __name__ == "__main__":
    # Allow running individual safety tests
    pytest.main([__file__, "-v", "--tb=short"])
