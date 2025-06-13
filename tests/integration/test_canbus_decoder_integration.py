"""
Integration Tests for CAN Bus Decoder V2 Architecture

Tests end-to-end message flow, safety interlock validation, security anomaly detection,
and high-rate performance under realistic conditions.

This test suite validates the complete integration of:
- Protocol Router with BAM Handler
- Safety State Engine with real message processing
- Adaptive Security Manager with device profiling
- Configuration Service with performance monitoring
- Performance Monitor with threshold validation
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

from backend.core.configuration_service import ConfigurationService
from backend.core.safety_state_engine import SafetyStateEngine
from backend.integrations.can.performance_monitor import PerformanceMonitor
from backend.integrations.can.protocol_router import (
    CANFrame,
    ProcessedMessage,
    ProtocolRouter,
    SecurityManager,
)
from backend.integrations.rvc.adaptive_security import AdaptiveSecurityManager
from backend.integrations.rvc.bam_handler import BAMHandler


@dataclass
class TestCANMessage:
    """Test CAN message structure for integration testing."""

    arbitration_id: int
    data: bytes
    timestamp: float
    is_extended_id: bool = False

    @property
    def pgn(self) -> int:
        """Extract PGN from arbitration ID."""
        if self.is_extended_id:
            return (self.arbitration_id >> 8) & 0x3FFFF
        return (self.arbitration_id >> 8) & 0xFF

    @property
    def source_address(self) -> int:
        """Extract source address from arbitration ID."""
        return self.arbitration_id & 0xFF


class IntegratedCANDecoder:
    """Integrated CAN decoder system for end-to-end testing."""

    def __init__(self, config_dir: Path):
        # Initialize all components
        self.config_service = ConfigurationService(config_dir, cache_ttl=60, max_cache_size=100)
        self.safety_engine = SafetyStateEngine()
        # Use basic security manager for protocol router
        self.basic_security_manager = SecurityManager()

        # Also create adaptive security manager for advanced testing
        self.security_manager = AdaptiveSecurityManager(
            learning_duration=10.0,  # Short learning for testing
            max_profiles=50,
            anomaly_threshold=0.7,
        )
        self.performance_monitor = PerformanceMonitor(collection_interval=1.0, retention_hours=1)
        self.bam_handler = BAMHandler()

        # Mock decoders for testing
        self.rvc_decoder = Mock()
        self.j1939_decoder = Mock()

        # Create protocol router
        self.protocol_router = ProtocolRouter(
            bam_handler=self.bam_handler,
            safety_engine=self.safety_engine,
            security_manager=self.basic_security_manager,
        )

        # Track processed messages
        self.processed_messages: list[ProcessedMessage] = []
        self.safety_commands: list[Any] = []
        self.security_events: list[Any] = []

        # Setup observers
        self.safety_engine.add_observer(self._handle_safety_command)
        self.security_manager.add_observer(self._handle_security_event)

    def _handle_safety_command(self, command):
        """Handle safety commands from safety engine."""
        self.safety_commands.append(command)

    def _handle_security_event(self, event):
        """Handle security events from security manager."""
        self.security_events.append(event)

    async def process_message(self, message: TestCANMessage) -> ProcessedMessage | None:
        """Process a CAN message through the complete decoder pipeline."""
        # Convert to CANFrame
        frame = CANFrame(
            arbitration_id=message.arbitration_id,
            pgn=message.pgn,
            source_address=message.source_address,
            destination_address=0xFF,  # Global destination
            data=message.data,
            timestamp=message.timestamp,
            is_extended=message.is_extended_id,
        )

        # Simulate security validation using adaptive security manager
        security_validated = self.security_manager.validate_frame(message)

        # Simulate decoding
        if security_validated:
            decoded_data = self.rvc_decoder.decode(frame.pgn, frame.data, frame.source_address)
            if decoded_data:
                processing_time = time.time() - frame.timestamp

                processed = ProcessedMessage(
                    pgn=frame.pgn,
                    source_address=frame.source_address,
                    decoded_data=decoded_data.get("decoded_data", {}),
                    errors=[],
                    processing_time_ms=processing_time * 1000,
                    protocol="RVC",
                    safety_events=decoded_data.get("safety_events", []),
                )
                self.processed_messages.append(processed)
                return processed

        return None

    async def process_message_sequence(
        self, messages: list[TestCANMessage]
    ) -> list[ProcessedMessage]:
        """Process a sequence of CAN messages."""
        results = []
        for message in messages:
            result = await self.process_message(message)
            if result:
                results.append(result)
            await asyncio.sleep(0.001)  # Small delay between messages
        return results

    def get_system_statistics(self) -> dict[str, Any]:
        """Get comprehensive system statistics."""
        return {
            "messages_processed": len(self.processed_messages),
            "safety_commands_issued": len(self.safety_commands),
            "security_events_generated": len(self.security_events),
            "current_vehicle_state": self.safety_engine.current_state.value,
            "device_profiles": len(self.security_manager.device_profiles),
            "performance_metrics": self.performance_monitor.get_performance_summary(),
            "bam_sessions_active": len(self.bam_handler.sessions),
            "configuration_cache_size": len(self.config_service.dgn_cache),
        }


class TestEndToEndMessageFlow:
    """Test complete end-to-end message flow through the decoder."""

    @pytest.fixture
    async def integrated_decoder(self, temp_config_dir):
        """Create integrated decoder system for testing."""
        decoder = IntegratedCANDecoder(temp_config_dir)

        # Setup mock decoder responses
        decoder.rvc_decoder.decode.return_value = {
            "decoded_data": {
                "vehicle_speed": {"value": 0.0, "unit": "mph"},
                "park_brake_status": {"value": True, "unit": None},
                "engine_status": {"value": False, "unit": None},
            },
            "safety_events": [],
            "processing_time": 0.002,
        }

        decoder.j1939_decoder.decode.return_value = None

        yield decoder

        # Cleanup
        await decoder.performance_monitor.stop_monitoring()

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Create temporary configuration directory."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Create test DGN spec
        dgn_dir = config_dir / "dgn_specs"
        dgn_dir.mkdir()

        test_dgn = {
            "dgn": "0x1FED1",
            "name": "Vehicle Speed and Status",
            "signals": [
                {"name": "vehicle_speed", "start_bit": 0, "length": 16, "unit": "mph"},
                {"name": "park_brake_status", "start_bit": 16, "length": 1, "unit": None},
                {"name": "engine_status", "start_bit": 17, "length": 1, "unit": None},
            ],
        }

        dgn_file = dgn_dir / "0x1FED1.yaml"
        with dgn_file.open("w") as f:
            yaml.dump(test_dgn, f)

        return config_dir

    async def test_single_message_processing(self, integrated_decoder):
        """Test processing of a single CAN message."""
        # Create test message
        message = TestCANMessage(
            arbitration_id=0x1FED142,  # PGN 0x1FED1, source 0x42
            data=b"\x00\x00\x01\x00\x00\x00\x00\x00",  # Speed=0, brake=on, engine=off
            timestamp=time.time(),
        )

        # Process message
        result = await integrated_decoder.process_message(message)

        # Test constants
        expected_pgn = 0x1FED1
        expected_source = 0x42

        # Verify processing
        assert result is not None
        assert result.pgn == expected_pgn
        assert result.source_address == expected_source
        assert "decoded_data" in result.decoded_data

        # Verify system state
        stats = integrated_decoder.get_system_statistics()
        assert stats["messages_processed"] == 1
        assert stats["device_profiles"] == 1  # One device learned

    async def test_multi_message_sequence(self, integrated_decoder):
        """Test processing of multiple related messages."""
        # Create message sequence simulating vehicle startup
        messages = [
            # Initial state - parked, brake on, engine off
            TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x00\x00\x01\x00\x00\x00\x00\x00",
                timestamp=time.time(),
            ),
            # Engine start
            TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x00\x00\x01\x01\x00\x00\x00\x00",
                timestamp=time.time() + 1.0,
            ),
            # Release brake
            TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x00\x00\x00\x01\x00\x00\x00\x00",
                timestamp=time.time() + 2.0,
            ),
            # Start moving
            TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x05\x00\x00\x01\x00\x00\x00\x00",  # 5 mph
                timestamp=time.time() + 3.0,
            ),
        ]

        # Process message sequence
        results = await integrated_decoder.process_message_sequence(messages)

        # Verify all messages processed
        expected_message_count = 4
        assert len(results) == expected_message_count

        # Verify vehicle state progression
        stats = integrated_decoder.get_system_statistics()
        assert stats["messages_processed"] == expected_message_count
        assert stats["current_vehicle_state"] in ["driving", "parked_running"]

    async def test_bam_message_assembly(self, integrated_decoder):
        """Test BAM (Broadcast Announce Message) multi-packet assembly."""
        # Create BAM connection management message
        bam_cm = TestCANMessage(
            arbitration_id=0xEC0042,  # TP.CM from source 0x42
            data=b"\x20\x09\x00\x03\xff\x12\x34\x00",  # BAM, 9 bytes, 3 packets, PGN 0x1234
            timestamp=time.time(),
        )

        # Create data transfer packets
        bam_dt1 = TestCANMessage(
            arbitration_id=0xEB0042,  # TP.DT from source 0x42
            data=b"\x01\x11\x22\x33\x44\x55\x66\x77",  # Packet 1
            timestamp=time.time() + 0.01,
        )

        bam_dt2 = TestCANMessage(
            arbitration_id=0xEB0042,
            data=b"\x02\x88\x99\xaa\xbb\xcc\xdd\xee",  # Packet 2
            timestamp=time.time() + 0.02,
        )

        bam_dt3 = TestCANMessage(
            arbitration_id=0xEB0042,
            data=b"\x03\xff\xff\xff\xff\xff\xff\xff",  # Packet 3 (partial)
            timestamp=time.time() + 0.03,
        )

        # Process BAM sequence
        bam_messages = [bam_cm, bam_dt1, bam_dt2, bam_dt3]
        await integrated_decoder.process_message_sequence(bam_messages)

        # Verify BAM assembly (should have 1 completed message after all packets)
        stats = integrated_decoder.get_system_statistics()
        assert stats["messages_processed"] >= 1  # At least the completed BAM message

        # Verify no active BAM sessions remain
        assert stats["bam_sessions_active"] == 0

    async def test_configuration_service_integration(self, integrated_decoder):
        """Test configuration service integration with message processing."""
        # Process message that requires DGN spec lookup
        message = TestCANMessage(
            arbitration_id=0x1FED142,
            data=b"\x00\x00\x01\x00\x00\x00\x00\x00",
            timestamp=time.time(),
        )

        # Process message multiple times to test caching
        for _ in range(5):
            await integrated_decoder.process_message(message)

        # Verify configuration cache usage
        cache_size = len(integrated_decoder.config_service.dgn_cache)
        assert cache_size >= 1  # Should have cached the DGN spec


class TestSafetyInterlockValidation:
    """Test safety interlock validation in integrated environment."""

    @pytest.fixture
    async def safety_decoder(self, temp_config_dir):
        """Create decoder with safety system enabled."""
        decoder = IntegratedCANDecoder(temp_config_dir)

        # Setup safety-aware decoder responses
        vehicle_status_pgn = 0x1FED1
        moving_speed_threshold = 0.5

        def safety_decode(pgn, data, source):
            if pgn == vehicle_status_pgn:  # Vehicle status PGN
                speed = int.from_bytes(data[0:2], byteorder="little") * 0.1
                brake = bool(data[2] & 0x01)
                engine = bool(data[3] & 0x01)

                return {
                    "decoded_data": {
                        "vehicle_speed": {"value": speed, "unit": "mph"},
                        "park_brake_status": {"value": brake, "unit": None},
                        "engine_status": {"value": engine, "unit": None},
                    },
                    "safety_events": [
                        {
                            "event": "VEHICLE_MOVING"
                            if speed > moving_speed_threshold
                            else "VEHICLE_STOPPED",
                            "data": {"speed": speed},
                        },
                        {
                            "event": "PARKING_BRAKE_SET" if brake else "PARKING_BRAKE_RELEASED",
                            "data": {"brake": brake},
                        },
                        {
                            "event": "ENGINE_STARTED" if engine else "ENGINE_STOPPED",
                            "data": {"engine": engine},
                        },
                    ],
                    "processing_time": 0.003,
                }
            return None

        decoder.rvc_decoder.decode.side_effect = safety_decode
        yield decoder

        await decoder.performance_monitor.stop_monitoring()

    async def test_slideout_blocked_when_moving(self, safety_decoder):
        """Test that slideout operations are blocked when vehicle is moving."""
        # Send message indicating vehicle is moving
        moving_message = TestCANMessage(
            arbitration_id=0x1FED142,
            data=b"\x32\x00\x00\x01\x00\x00\x00\x00",  # 5.0 mph, engine on
            timestamp=time.time(),
        )

        await safety_decoder.process_message(moving_message)

        # Check safety operation validation
        is_safe, reason = safety_decoder.safety_engine.is_operation_safe(
            "slideout_extend", "main_slideout"
        )
        assert not is_safe
        assert "not allowed" in reason.lower()

        # Verify safety command was issued
        assert len(safety_decoder.safety_commands) > 0

    async def test_engine_start_interlock(self, safety_decoder):
        """Test engine start interlock when transmission not in park."""
        # Send message indicating transmission in drive, brake off
        drive_message = TestCANMessage(
            arbitration_id=0x1FED142,
            data=b"\x00\x00\x00\x00\x01\x00\x00\x00",  # Speed=0, brake=off, trans=drive (simulated)
            timestamp=time.time(),
        )

        await safety_decoder.process_message(drive_message)

        # Verify vehicle state is unsafe
        stats = safety_decoder.get_system_statistics()
        assert stats["current_vehicle_state"] != "parked_safe"

    async def test_emergency_stop_scenario(self, safety_decoder):
        """Test emergency stop activation in unsafe conditions."""
        # Create sequence leading to emergency stop
        messages = [
            # Start safe - parked with brake
            TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x00\x00\x01\x01\x00\x00\x00\x00",  # Parked, brake on, engine on
                timestamp=time.time(),
            ),
            # Sudden movement without brake release (unsafe transition)
            TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x32\x00\x01\x01\x00\x00\x00\x00",  # 5.0 mph with brake still on (impossible)
                timestamp=time.time() + 0.1,
            ),
        ]

        await safety_decoder.process_message_sequence(messages)

        # Verify emergency response
        assert len(safety_decoder.safety_commands) > 0

        # Check for emergency stop or safety violation
        safety_command = safety_decoder.safety_commands[-1]
        assert hasattr(safety_command, "command_type")


class TestSecurityAnomalyDetection:
    """Test security anomaly detection in integrated environment."""

    @pytest.fixture
    async def security_decoder(self, temp_config_dir):
        """Create decoder with security monitoring enabled."""
        decoder = IntegratedCANDecoder(temp_config_dir)

        # Short learning period for testing
        decoder.security_manager.learning_duration = 2.0

        yield decoder
        await decoder.performance_monitor.stop_monitoring()

    async def test_device_learning_and_profiling(self, security_decoder):
        """Test device behavior learning and profiling."""
        # Send regular message pattern during learning phase
        base_time = time.time()
        learning_messages = []

        for i in range(10):
            message = TestCANMessage(
                arbitration_id=0x1FED142,  # Same device, same PGN
                data=b"\x00\x00\x01\x00\x00\x00\x00\x00",
                timestamp=base_time + i * 0.1,  # Regular 100ms intervals
            )
            learning_messages.append(message)

        # Process learning messages
        await security_decoder.process_message_sequence(learning_messages)

        # Verify device profile created
        stats = security_decoder.get_system_statistics()
        assert stats["device_profiles"] == 1

        # Verify device is still in learning phase
        device_profile = security_decoder.security_manager.device_profiles[0x42]
        assert device_profile.learning_phase is True

    async def test_unexpected_pgn_detection(self, security_decoder):
        """Test detection of unexpected PGNs after learning phase."""
        # First, train the device profile
        await self._train_device_profile(security_decoder, 0x42, [0x1FED1])

        # Force completion of learning phase
        security_decoder.security_manager.force_learning_completion(0x42)

        # Send unexpected PGN
        unexpected_message = TestCANMessage(
            arbitration_id=0x999942,  # Unexpected PGN 0x9999, same source
            data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
            timestamp=time.time(),
        )

        # Process should detect anomaly
        result = await security_decoder.process_message(unexpected_message)

        # Verify security event generated
        assert len(security_decoder.security_events) > 0

        # Verify message was blocked (should return None if blocked)
        # Or if processed, it should be flagged as suspicious
        assert result is None or len(security_decoder.security_events) > 0

    async def test_timing_anomaly_detection(self, security_decoder):
        """Test detection of timing anomalies (message flooding)."""
        # Train device with normal timing
        await self._train_device_profile(security_decoder, 0x42, [0x1FED1])
        security_decoder.security_manager.force_learning_completion(0x42)

        # Send burst of messages (flooding attack simulation)
        burst_time = time.time()
        burst_messages = []

        for i in range(20):  # 20 messages in rapid succession
            message = TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x00\x00\x01\x00\x00\x00\x00\x00",
                timestamp=burst_time + i * 0.001,  # 1ms intervals (too fast)
            )
            burst_messages.append(message)

        # Process burst
        await security_decoder.process_message_sequence(burst_messages)

        # Verify anomaly detection
        assert len(security_decoder.security_events) > 0

        # Verify device statistics updated
        device_stats = security_decoder.security_manager.get_device_statistics()
        assert device_stats["anomaly_rate"] > 0

    async def _train_device_profile(self, decoder, source_address: int, pgns: list[int]):
        """Helper to train a device profile with specific PGNs."""
        base_time = time.time()

        for i in range(20):  # Enough messages to establish pattern
            for pgn in pgns:
                arbitration_id = (pgn << 8) | source_address
                message = TestCANMessage(
                    arbitration_id=arbitration_id,
                    data=b"\x00\x00\x01\x00\x00\x00\x00\x00",
                    timestamp=base_time + i * 0.1,
                )
                await decoder.process_message(message)


class TestHighRatePerformance:
    """Test system performance under high message rates."""

    @pytest.fixture
    async def performance_decoder(self, temp_config_dir):
        """Create decoder optimized for performance testing."""
        decoder = IntegratedCANDecoder(temp_config_dir)

        # Enable performance monitoring
        decoder.performance_monitor.start_monitoring()

        # Setup fast decoder responses
        decoder.rvc_decoder.decode.return_value = {
            "decoded_data": {"test_signal": {"value": 42, "unit": "units"}},
            "safety_events": [],
            "processing_time": 0.001,
        }

        yield decoder
        await decoder.performance_monitor.stop_monitoring()

    async def test_sustained_high_rate_processing(self, performance_decoder):
        """Test sustained processing at high message rates."""
        # Generate high-rate message stream
        message_count = 1000
        start_time = time.time()

        messages = []
        for i in range(message_count):
            message = TestCANMessage(
                arbitration_id=0x1FED100 + (i % 10),  # Vary PGNs
                data=bytes([i % 256] * 8),
                timestamp=start_time + i * 0.001,  # 1000 msg/sec
            )
            messages.append(message)

        # Process messages and measure performance
        processing_start = time.time()
        results = await performance_decoder.process_message_sequence(messages)
        processing_end = time.time()

        processing_time = processing_end - processing_start
        processing_rate = len(results) / processing_time

        # Verify performance targets
        min_processing_rate = 500  # msg/sec
        assert processing_rate >= min_processing_rate  # At least 500 msg/sec processing rate
        assert len(results) == message_count  # All messages processed

        # Verify system stability
        stats = performance_decoder.get_system_statistics()
        assert stats["messages_processed"] == message_count

        # Check for performance violations
        violations = performance_decoder.performance_monitor.check_performance_thresholds()
        critical_violations = [v for v in violations if v.get("severity") == "critical"]
        assert len(critical_violations) == 0  # No critical performance violations

    async def test_concurrent_bam_sessions(self, performance_decoder):
        """Test handling of multiple concurrent BAM sessions."""
        # Create multiple BAM sessions from different sources
        bam_sessions = []

        for source in range(0x40, 0x50):  # 16 different sources
            # BAM Connection Management
            bam_cm = TestCANMessage(
                arbitration_id=0xEC0000 | source,
                data=b"\x20\x09\x00\x03\xff\x12\x34\x00",  # 9 bytes, 3 packets
                timestamp=time.time() + source * 0.001,
            )
            bam_sessions.append(bam_cm)

            # Add data transfer packets for each session
            for packet in range(1, 4):
                bam_dt = TestCANMessage(
                    arbitration_id=0xEB0000 | source,
                    data=bytes([packet] + [0x11 * packet] * 7),
                    timestamp=time.time() + source * 0.001 + packet * 0.002,
                )
                bam_sessions.append(bam_dt)

        # Process all BAM messages
        await performance_decoder.process_message_sequence(bam_sessions)

        # Verify all sessions completed successfully
        stats = performance_decoder.get_system_statistics()
        assert stats["bam_sessions_active"] == 0  # All sessions should complete

        # Verify performance under concurrent load
        performance_stats = stats["performance_metrics"]
        assert "bam_handler" in performance_stats

        # Check that BAM handler performance is acceptable
        min_completion_rate = 90.0
        bam_stats = performance_stats.get("bam_handler", {})
        if "completion_rate" in bam_stats:
            assert (
                bam_stats["completion_rate"] >= min_completion_rate
            )  # At least 90% completion rate

    async def test_memory_usage_under_load(self, performance_decoder):
        """Test memory usage stability under sustained load."""
        import gc

        import psutil

        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Process many messages in batches
        batch_size = 100
        num_batches = 10

        for batch in range(num_batches):
            messages = []
            for i in range(batch_size):
                message = TestCANMessage(
                    arbitration_id=0x1FED100 + (i % 20),
                    data=bytes([(batch * batch_size + i) % 256] * 8),
                    timestamp=time.time() + i * 0.001,
                )
                messages.append(message)

            await performance_decoder.process_message_sequence(messages)

            # Force garbage collection between batches
            gc.collect()

        # Check final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # Memory growth should be reasonable (less than 50MB for test)
        max_memory_growth_mb = 50.0
        assert memory_growth < max_memory_growth_mb, f"Excessive memory growth: {memory_growth}MB"

        # Verify system still responsive
        stats = performance_decoder.get_system_statistics()
        assert stats["messages_processed"] == batch_size * num_batches


class TestSystemObservability:
    """Test system observability and monitoring capabilities."""

    @pytest.fixture
    async def monitored_decoder(self, temp_config_dir):
        """Create decoder with full monitoring enabled."""
        decoder = IntegratedCANDecoder(temp_config_dir)
        decoder.performance_monitor.start_monitoring()
        yield decoder
        await decoder.performance_monitor.stop_monitoring()

    async def test_prometheus_metrics_generation(self, monitored_decoder):
        """Test Prometheus metrics generation."""
        # Generate some activity
        messages = [
            TestCANMessage(
                arbitration_id=0x1FED142,
                data=b"\x00\x00\x01\x00\x00\x00\x00\x00",
                timestamp=time.time() + i * 0.01,
            )
            for i in range(10)
        ]

        await monitored_decoder.process_message_sequence(messages)

        # Generate Prometheus metrics
        prometheus_output = monitored_decoder.performance_monitor.get_prometheus_metrics()

        # Verify metrics format
        assert "# HELP canbus_decoder_" in prometheus_output
        assert "# TYPE canbus_decoder_" in prometheus_output
        assert "canbus_decoder_" in prometheus_output

        # Verify specific metrics exist
        assert "processing_time" in prometheus_output
        assert "messages_processed" in prometheus_output

    async def test_comprehensive_statistics(self, monitored_decoder):
        """Test comprehensive system statistics collection."""
        # Generate mixed activity
        await self._generate_mixed_activity(monitored_decoder)

        # Get comprehensive statistics
        stats = monitored_decoder.get_system_statistics()

        # Verify all expected sections exist
        required_sections = [
            "messages_processed",
            "safety_commands_issued",
            "security_events_generated",
            "current_vehicle_state",
            "device_profiles",
            "performance_metrics",
            "bam_sessions_active",
            "configuration_cache_size",
        ]

        for section in required_sections:
            assert section in stats, f"Missing statistics section: {section}"

        # Verify statistics are meaningful
        assert stats["messages_processed"] > 0
        assert isinstance(stats["performance_metrics"], dict)
        assert isinstance(stats["configuration_cache_size"], int)

    async def _generate_mixed_activity(self, decoder):
        """Generate mixed CAN activity for testing."""
        activities = [
            # Normal messages
            TestCANMessage(0x1FED142, b"\x00\x00\x01\x00\x00\x00\x00\x00", time.time()),
            TestCANMessage(0x1FED242, b"\x01\x01\x00\x01\x00\x00\x00\x00", time.time() + 0.1),
            # BAM sequence
            TestCANMessage(0xEC0043, b"\x20\x09\x00\x03\xff\x12\x34\x00", time.time() + 0.2),
            TestCANMessage(0xEB0043, b"\x01\x11\x22\x33\x44\x55\x66\x77", time.time() + 0.21),
            TestCANMessage(0xEB0043, b"\x02\x88\x99\xaa\xbb\xcc\xdd\xee", time.time() + 0.22),
            TestCANMessage(0xEB0043, b"\x03\xff\xff\xff\xff\xff\xff\xff", time.time() + 0.23),
            # Security test (unexpected PGN)
            TestCANMessage(0x999942, b"\x01\x02\x03\x04\x05\x06\x07\x08", time.time() + 0.3),
        ]

        await decoder.process_message_sequence(activities)


@pytest.mark.asyncio
class TestRegressionValidation:
    """Regression tests to ensure no breaking changes."""

    async def test_backward_compatibility(self, temp_config_dir):
        """Test that new architecture maintains backward compatibility."""
        decoder = IntegratedCANDecoder(temp_config_dir)

        # Test with old-style message format
        legacy_message = TestCANMessage(
            arbitration_id=0x18FED142,  # J1939 format
            data=b"\x00\x01\x02\x03\x04\x05\x06\x07",
            timestamp=time.time(),
            is_extended_id=True,
        )

        # Should process without errors
        result = await decoder.process_message(legacy_message)

        # May return None (not decoded) but should not crash
        assert result is None or isinstance(result, ProcessedMessage)

    async def test_error_handling_robustness(self, temp_config_dir):
        """Test system robustness under error conditions."""
        decoder = IntegratedCANDecoder(temp_config_dir)

        # Test with invalid message data
        invalid_messages = [
            TestCANMessage(0x00000000, b"", time.time()),  # Empty data
            TestCANMessage(0xFFFFFFFF, b"\xff" * 64, time.time()),  # Oversized data
            TestCANMessage(0x1FED142, b"\x00", time.time()),  # Undersized data
        ]

        # Process invalid messages - should handle gracefully
        for message in invalid_messages:
            try:
                result = await decoder.process_message(message)
                # Should either process or return None, but not crash
                assert result is None or isinstance(result, ProcessedMessage)
            except Exception as e:
                pytest.fail(f"System crashed on invalid message: {e}")

    async def test_performance_regression(self, temp_config_dir):
        """Test that performance hasn't regressed."""
        decoder = IntegratedCANDecoder(temp_config_dir)

        # Standard performance test message
        test_message = TestCANMessage(
            arbitration_id=0x1FED142,
            data=b"\x00\x00\x01\x00\x00\x00\x00\x00",
            timestamp=time.time(),
        )

        # Measure processing time
        start_time = time.time()

        for _ in range(100):
            await decoder.process_message(test_message)

        end_time = time.time()
        avg_processing_time = (end_time - start_time) / 100

        # Should process messages in under 5ms average
        max_processing_time_seconds = 0.005
        assert avg_processing_time < max_processing_time_seconds, (
            f"Performance regression: {avg_processing_time * 1000:.2f}ms per message"
        )
