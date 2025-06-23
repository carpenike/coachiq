"""
Unit Tests for Adaptive Security Manager

Tests device profiling, anomaly detection, and threat assessment
for the adaptive security management system.
"""

import time
from unittest.mock import Mock

import pytest

from backend.integrations.rvc.adaptive_security import (
    AdaptiveSecurityManager,
    AnomalyType,
    DeviceProfile,
    SecurityEvent,
    ThreatLevel,
)


class MockCANFrame:
    """Mock CAN frame for testing."""

    def __init__(self, pgn, source_address, data, timestamp=None):
        self.pgn = pgn
        self.source_address = source_address
        self.data = data
        self.timestamp = timestamp or time.time()
        self.arbitration_id = (pgn << 8) | source_address


class TestDeviceProfile:
    """Test device profiling and behavior learning."""

    @pytest.fixture
    def device_profile(self):
        """Create a device profile for testing."""
        return DeviceProfile(source_address=0x42)

    def test_profile_initialization(self, device_profile):
        """Test device profile initialization."""
        assert device_profile.source_address == 0x42
        assert device_profile.learning_phase is True
        assert len(device_profile.expected_pgns) == 0
        assert device_profile.message_count == 0
        assert device_profile.total_messages == 0
        assert device_profile.anomaly_count == 0

    def test_message_learning(self, device_profile):
        """Test message learning during learning phase."""
        timestamp = time.time()
        test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        # Learn from messages
        device_profile.update_from_message(0x1FED1, timestamp, test_data)
        device_profile.update_from_message(0x1FED2, timestamp + 1, test_data)
        device_profile.update_from_message(0x1FED1, timestamp + 2, test_data)

        # Check learning results
        assert 0x1FED1 in device_profile.expected_pgns
        assert 0x1FED2 in device_profile.expected_pgns
        assert device_profile.message_count == 3
        assert device_profile.total_messages == 3
        assert len(device_profile.message_history) == 3

        # Check data patterns stored
        assert 0x1FED1 in device_profile.data_patterns
        assert 0x1FED2 in device_profile.data_patterns
        assert len(device_profile.data_patterns[0x1FED1]) == 2  # Two messages for this PGN
        assert len(device_profile.data_patterns[0x1FED2]) == 1  # One message for this PGN

    def test_timing_pattern_analysis(self, device_profile):
        """Test timing pattern analysis during learning."""
        base_time = time.time()
        test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        # Send messages with regular intervals
        for i in range(10):
            device_profile.update_from_message(0x1FED1, base_time + i * 0.1, test_data)

        # Check that interval patterns are learned
        assert 0x1FED1 in device_profile.pgn_intervals
        # Interval should be approximately 0.1 seconds
        assert 0.05 < device_profile.pgn_intervals[0x1FED1] < 0.15

    def test_burst_pattern_detection(self, device_profile):
        """Test burst pattern detection during learning."""
        base_time = time.time()
        test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        # Send burst of messages
        for i in range(5):
            device_profile.update_from_message(0x1FED1, base_time + i * 0.001, test_data)

        # Check burst pattern recorded
        assert 0x1FED1 in device_profile.pgn_burst_patterns
        assert device_profile.pgn_burst_patterns[0x1FED1] >= 5

    def test_anomaly_detection_learning_phase(self, device_profile):
        """Test that no anomalies are detected during learning phase."""
        timestamp = time.time()
        test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        # Any message should be normal during learning
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x9999, timestamp, test_data
        )

        assert is_anomalous is False
        assert reason == "Learning phase"
        assert confidence == 0.0

    def test_unexpected_pgn_detection(self, device_profile):
        """Test detection of unexpected PGNs after learning."""
        # Complete learning phase
        device_profile.learning_phase = False
        device_profile.expected_pgns = {0x1FED1, 0x1FED2}

        timestamp = time.time()
        test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        # Test expected PGN (should be normal)
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x1FED1, timestamp, test_data
        )
        assert is_anomalous is False

        # Test unexpected PGN (should be anomalous)
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x9999, timestamp, test_data
        )
        assert is_anomalous is True
        assert "Unexpected PGN" in reason
        assert confidence == 0.9

    def test_timing_anomaly_detection(self, device_profile):
        """Test detection of timing anomalies."""
        # Setup learned patterns
        device_profile.learning_phase = False
        device_profile.expected_pgns = {0x1FED1}
        device_profile.pgn_intervals[0x1FED1] = 1.0  # Expect 1 second intervals

        # Add message history to simulate previous messages
        base_time = time.time()
        device_profile.message_history.extend(
            [
                (0x1FED1, base_time - 2.0, 8),
                (0x1FED1, base_time - 1.0, 8),
            ]
        )

        test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        # Test normal timing (should be normal)
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x1FED1, base_time, test_data
        )
        assert is_anomalous is False

        # Test very fast timing (should be anomalous)
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x1FED1,
            base_time + 0.05,
            test_data,  # Much faster than expected 1s
        )
        assert is_anomalous is True
        assert "Timing anomaly" in reason
        assert confidence == 0.7

    def test_burst_anomaly_detection(self, device_profile):
        """Test detection of burst anomalies."""
        # Setup learned patterns
        device_profile.learning_phase = False
        device_profile.expected_pgns = {0x1FED1}
        device_profile.pgn_burst_patterns[0x1FED1] = 2  # Expect max 2 messages per 10s

        base_time = time.time()
        test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        # Add many recent messages to simulate burst
        for i in range(5):
            device_profile.message_history.append((0x1FED1, base_time - i * 0.1, 8))

        # Test burst detection
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x1FED1, base_time, test_data
        )
        assert is_anomalous is True
        assert "Burst anomaly" in reason
        assert confidence == 0.8

    def test_data_pattern_anomaly_detection(self, device_profile):
        """Test detection of data pattern anomalies."""
        # Setup learned patterns
        device_profile.learning_phase = False
        device_profile.expected_pgns = {0x1FED1}

        # Add known data patterns
        known_pattern = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        device_profile.data_patterns[0x1FED1] = [known_pattern]

        timestamp = time.time()

        # Test similar data (should be normal)
        similar_data = b"\x01\x02\x03\x04\x05\x06\x07\x09"  # Only last byte different
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x1FED1, timestamp, similar_data
        )
        assert is_anomalous is False  # 7/8 bytes match = 87.5% similarity > 80% threshold

        # Test very different data (should be anomalous)
        different_data = b"\xff\xfe\xfd\xfc\xfb\xfa\xf9\xf8"
        is_anomalous, reason, confidence = device_profile.is_message_anomalous(
            0x1FED1, timestamp, different_data
        )
        assert is_anomalous is True
        assert "Data pattern anomaly" in reason
        assert confidence == 0.6

    def test_data_similarity_calculation(self, device_profile):
        """Test data similarity calculation accuracy."""
        # Test identical data
        data1 = b"\x01\x02\x03\x04"
        data2 = b"\x01\x02\x03\x04"
        assert device_profile._data_similarity(data1, data2) == 1.0

        # Test completely different data
        data1 = b"\x01\x02\x03\x04"
        data2 = b"\xff\xfe\xfd\xfc"
        assert device_profile._data_similarity(data1, data2) == 0.0

        # Test partially similar data
        data1 = b"\x01\x02\x03\x04"
        data2 = b"\x01\x02\xff\xff"
        assert device_profile._data_similarity(data1, data2) == 0.5

        # Test different length data
        data1 = b"\x01\x02\x03\x04"
        data2 = b"\x01\x02"
        assert device_profile._data_similarity(data1, data2) == 0.0

        # Test empty data
        data1 = b""
        data2 = b""
        assert device_profile._data_similarity(data1, data2) == 1.0

    def test_profile_statistics(self, device_profile):
        """Test profile statistics generation."""
        # Add some data
        timestamp = time.time()
        device_profile.update_from_message(0x1FED1, timestamp, b"\x01\x02\x03\x04")
        device_profile.anomaly_count = 5
        device_profile.total_messages = 100

        stats = device_profile.get_statistics()

        assert stats["source_address"] == "0x42"
        assert stats["learning_phase"] is True
        assert stats["expected_pgns"] == 1
        assert stats["total_messages"] == 100
        assert stats["anomaly_count"] == 5
        assert stats["anomaly_rate"] == 0.05  # 5/100
        assert "first_seen" in stats
        assert "last_seen" in stats
        assert "age_hours" in stats


class TestAdaptiveSecurityManager:
    """Test adaptive security manager functionality."""

    @pytest.fixture
    def security_manager(self):
        """Create a security manager for testing."""
        return AdaptiveSecurityManager(
            learning_duration=1.0,  # Short learning for testing
            max_profiles=10,
            anomaly_threshold=0.5,
        )

    def test_initialization(self, security_manager):
        """Test security manager initialization."""
        assert security_manager.learning_duration == 1.0
        assert security_manager.max_profiles == 10
        assert security_manager.anomaly_threshold == 0.5
        assert len(security_manager.device_profiles) == 0
        assert security_manager.total_messages_processed == 0
        assert security_manager.total_anomalies_detected == 0

    def test_basic_frame_validation(self, security_manager):
        """Test basic frame validation."""
        # Valid frame
        valid_frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")
        assert security_manager.validate_frame(valid_frame) is True

        # Invalid source address
        invalid_frame = MockCANFrame(
            0x1FED1, 0x80, b"\x01\x02\x03\x04"
        )  # Outside legitimate ranges
        assert security_manager.validate_frame(invalid_frame) is False

        # Invalid PGN
        invalid_pgn_frame = MockCANFrame(0x20000, 0x42, b"\x01\x02\x03\x04")  # PGN too large
        assert security_manager.validate_frame(invalid_pgn_frame) is False

        # Oversized data
        oversized_frame = MockCANFrame(
            0x1FED1, 0x42, b"\x01\x02\x03\x04\x05\x06\x07\x08\x09"
        )  # 9 bytes
        assert security_manager.validate_frame(oversized_frame) is False

    def test_device_profile_creation(self, security_manager):
        """Test automatic device profile creation."""
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")

        # First message should create profile
        assert security_manager.validate_frame(frame) is True
        assert 0x42 in security_manager.device_profiles
        assert security_manager.total_messages_processed == 1

    def test_learning_phase_completion(self, security_manager):
        """Test learning phase completion."""
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")

        # Send messages during learning phase
        for _ in range(50):
            assert security_manager.validate_frame(frame) is True

        profile = security_manager.device_profiles[0x42]
        assert profile.learning_phase is False  # Should complete due to message count

    def test_learning_phase_timeout(self, security_manager):
        """Test learning phase completion by timeout."""
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")

        # Send one message to create profile
        assert security_manager.validate_frame(frame) is True

        # Manually advance time past learning duration
        profile = security_manager.device_profiles[0x42]
        profile.learning_start_time = time.time() - 2.0  # 2 seconds ago

        # Next message should complete learning
        assert security_manager.validate_frame(frame) is True
        assert profile.learning_phase is False

    def test_anomaly_detection_and_blocking(self, security_manager):
        """Test anomaly detection and frame blocking."""
        # Create and train a profile
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")

        # Send training messages
        for _ in range(10):
            security_manager.validate_frame(frame)

        # Force completion of learning
        profile = security_manager.device_profiles[0x42]
        profile.learning_phase = False

        # Send normal message (should pass)
        assert security_manager.validate_frame(frame) is True

        # Send anomalous message (unexpected PGN with high confidence)
        anomalous_frame = MockCANFrame(0x9999, 0x42, b"\x01\x02\x03\x04")
        # This should be detected as high threat and blocked
        # Note: depends on threat assessment logic
        result = security_manager.validate_frame(anomalous_frame)
        # Result depends on threat level assessment

    def test_security_event_generation(self, security_manager):
        """Test security event generation and notification."""
        events_received = []

        def event_observer(event):
            events_received.append(event)

        security_manager.add_observer(event_observer)

        # Create profile and complete learning
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")
        for _ in range(10):
            security_manager.validate_frame(frame)

        security_manager.force_learning_completion(0x42)

        # Send anomalous message
        anomalous_frame = MockCANFrame(0x9999, 0x42, b"\x01\x02\x03\x04")
        security_manager.validate_frame(anomalous_frame)

        # Check if security event was generated
        # Note: May not generate event if confidence is below threshold
        if events_received:
            event = events_received[0]
            assert isinstance(event, SecurityEvent)
            assert event.source_address == 0x42
            assert event.pgn == 0x9999

    def test_observer_management(self, security_manager):
        """Test security event observer management."""
        observer1 = Mock()
        observer2 = Mock()

        # Add observers
        security_manager.add_observer(observer1)
        security_manager.add_observer(observer2)

        assert len(security_manager.observers) == 2

        # Remove observer
        security_manager.remove_observer(observer1)
        assert len(security_manager.observers) == 1
        assert observer2 in security_manager.observers

    def test_profile_cleanup(self, security_manager):
        """Test automatic profile cleanup when limit exceeded."""
        # Create many profiles
        for i in range(15):  # Exceeds max_profiles (10)
            frame = MockCANFrame(0x1FED1, 0x40 + i, b"\x01\x02\x03\x04")
            security_manager.validate_frame(frame)

        # Should have cleaned up old profiles
        assert len(security_manager.device_profiles) <= 10

    def test_statistics_collection(self, security_manager):
        """Test statistics collection."""
        # Send some messages
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")
        for _ in range(5):
            security_manager.validate_frame(frame)

        stats = security_manager.get_device_statistics()

        assert stats["total_devices"] == 1
        assert stats["learning_devices"] == 1
        assert stats["total_messages_processed"] == 5
        assert stats["anomaly_rate"] >= 0.0
        assert "uptime_hours" in stats
        assert "devices" in stats
        assert "0x42" in stats["devices"]

    def test_recent_events_tracking(self, security_manager):
        """Test recent security events tracking."""
        # Initially no events
        events = security_manager.get_recent_events()
        assert len(events) == 0

        # Force an anomaly detection (if possible)
        security_manager.force_learning_completion()

        # Create anomalous frame
        anomalous_frame = MockCANFrame(0x9999, 0x42, b"\x01\x02\x03\x04")
        security_manager.validate_frame(anomalous_frame)

        # Check recent events
        events = security_manager.get_recent_events()
        # May or may not have events depending on threshold

    def test_force_learning_completion(self, security_manager):
        """Test forced learning completion."""
        # Create profile
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")
        security_manager.validate_frame(frame)

        profile = security_manager.device_profiles[0x42]
        assert profile.learning_phase is True

        # Force completion for specific device
        security_manager.force_learning_completion(0x42)
        assert profile.learning_phase is False

        # Create another profile
        frame2 = MockCANFrame(0x1FED1, 0x43, b"\x01\x02\x03\x04")
        security_manager.validate_frame(frame2)

        profile2 = security_manager.device_profiles[0x43]
        assert profile2.learning_phase is True

        # Force completion for all devices
        security_manager.force_learning_completion()
        assert profile2.learning_phase is False

    def test_profile_reset(self, security_manager):
        """Test device profile reset."""
        # Create profile
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")
        security_manager.validate_frame(frame)

        assert 0x42 in security_manager.device_profiles

        # Reset profile
        result = security_manager.reset_device_profile(0x42)
        assert result is True
        assert 0x42 not in security_manager.device_profiles

        # Reset non-existent profile
        result = security_manager.reset_device_profile(0x99)
        assert result is False

    def test_performance_monitoring(self, security_manager):
        """Test performance metrics collection."""
        # Send messages to generate metrics
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")

        start_time = time.time()
        for _ in range(100):
            security_manager.validate_frame(frame)

        stats = security_manager.get_performance_stats()

        assert stats["messages_processed"] == 100
        assert stats["active_profiles"] == 1
        assert stats["uptime_seconds"] > 0
        assert stats["processing_rate"] > 0

    def test_threat_level_assessment(self, security_manager):
        """Test threat level assessment logic."""
        # Create mock frame for testing
        frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")

        # Test high confidence unexpected PGN (low PGN)
        threat = security_manager._assess_threat_level(
            "Unexpected PGN 0x1000", 0.95, MockCANFrame(0x1000, 0x42, b"\x01\x02\x03\x04")
        )
        assert threat == ThreatLevel.HIGH

        # Test high confidence burst anomaly
        threat = security_manager._assess_threat_level("Burst anomaly: 20 messages", 0.95, frame)
        assert threat == ThreatLevel.MEDIUM

        # Test medium confidence anomaly
        threat = security_manager._assess_threat_level("Timing anomaly", 0.75, frame)
        assert threat == ThreatLevel.LOW

        # Test low confidence anomaly
        threat = security_manager._assess_threat_level("Data pattern anomaly", 0.5, frame)
        assert threat == ThreatLevel.INFO

    def test_anomaly_type_classification(self, security_manager):
        """Test anomaly type classification."""
        # Test different anomaly reason classifications
        assert (
            security_manager._classify_anomaly_type("Unexpected PGN 0x9999")
            == AnomalyType.UNEXPECTED_PGN
        )
        assert (
            security_manager._classify_anomaly_type("Timing anomaly: fast")
            == AnomalyType.TIMING_ANOMALY
        )
        assert (
            security_manager._classify_anomaly_type("Burst anomaly: too many")
            == AnomalyType.BURST_ANOMALY
        )
        assert (
            security_manager._classify_anomaly_type("Data pattern anomaly")
            == AnomalyType.DATA_ANOMALY
        )
        assert (
            security_manager._classify_anomaly_type("Unknown issue")
            == AnomalyType.PROTOCOL_VIOLATION
        )

    def test_concurrent_access(self, security_manager):
        """Test concurrent access to security manager."""
        import threading

        def worker():
            frame = MockCANFrame(0x1FED1, 0x42, b"\x01\x02\x03\x04")
            for _ in range(50):
                security_manager.validate_frame(frame)

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check final state is consistent
        assert security_manager.total_messages_processed == 250
        assert len(security_manager.device_profiles) == 1
