"""
Tests for RVC Phase 1 improvements.

This module tests the enhanced RVC functionality including:
- RVC Encoder
- Message Validator
- Security Manager
- Performance Handler
"""

import asyncio
import contextlib
import time
from unittest.mock import Mock, patch

import pytest

from backend.integrations.rvc.encoder import EncodingError, RVCEncoder
from backend.integrations.rvc.performance import MessagePriority, PriorityMessageHandler
from backend.integrations.rvc.security import SecurityManager
from backend.integrations.rvc.validator import MessageValidator
from backend.models.entity import ControlCommand


class TestRVCEncoder:
    """Test the RVC Encoder functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.controller_source_addr = "0xF9"
        settings.rvc_spec_path = None
        settings.rvc_coach_mapping_path = None
        return settings

    @pytest.fixture
    def encoder(self, mock_settings):
        """Create an RVC encoder for testing."""
        # The decoder/encoder were refactored from a 10-element tuple
        # (load_config_data) to a structured Pydantic model
        # (load_config_data_v2 returning RVCConfiguration). Patch the new
        # entry point and return a populated config object.
        from backend.models.common import CoachInfo
        from backend.models.rvc_config import RVCConfiguration, RVCSpecMeta

        mock_config = RVCConfiguration(
            dgn_dict={
                0x1FFB1: {
                    "pgn": "1FFB1",
                    "signals": [{"name": "instance", "start_bit": 0, "length": 8}],
                },
                # encode_entity_command needs the COMMAND DGN's spec too;
                # 1FFB2 is the command pair for 1FFB1.
                0x1FFB2: {
                    "pgn": "1FFB2",
                    "signals": [
                        {"name": "instance", "start_bit": 0, "length": 8},
                        {
                            "name": "brightness",
                            "start_bit": 8,
                            "length": 8,
                            "scale": 1,
                            "offset": 0,
                        },
                    ],
                },
            },
            spec_meta=RVCSpecMeta(version="test", source="test", rvc_version="test"),
            mapping_dict={},
            entity_map={
                ("1FFB1", "1"): {"device_type": "light", "entity_id": "test_light"}
            },
            entity_ids={"test_light"},
            inst_map={"test_light": {"dgn_hex": "1FFB1", "instance": "1"}},
            unique_instances={},
            pgn_hex_to_name_map={},
            dgn_pairs={"1FFB2": "1FFB1"},  # command -> status
            coach_info=CoachInfo(
                make="Test",
                model="TestCoach",
                year=None,
                trim=None,
                filename=None,
                notes=None,
            ),
        )

        with patch(
            "backend.integrations.rvc.encoder.load_config_data_v2",
            return_value=mock_config,
        ):
            return RVCEncoder(mock_settings)

    def test_encoder_initialization(self, encoder):
        """Test encoder initializes correctly."""
        assert encoder.is_ready()
        assert encoder.coach_info.make == "Test"

    def test_validate_command_valid(self, encoder):
        """Test command validation with valid command."""
        command = ControlCommand(command="set", state="on", brightness=50)
        is_valid, error_msg = encoder.validate_command("test_light", command)

        assert is_valid
        assert error_msg == ""

    def test_validate_command_invalid_entity(self, encoder):
        """Test command validation with invalid entity."""
        command = ControlCommand(command="set", state="on")
        is_valid, error_msg = encoder.validate_command("unknown_entity", command)

        assert not is_valid
        assert "Unknown entity ID" in error_msg

    def test_validate_command_invalid_brightness(self, encoder):
        """Test command validation with invalid brightness."""
        # ControlCommand uses Pydantic v2 ge=0/le=100 on brightness, so the
        # value is rejected at MODEL CONSTRUCTION TIME, not at validate_command.
        # This is fine for our purposes -- the validation still happens, just
        # earlier in the request lifecycle.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ControlCommand(command="set", state="on", brightness=150)

    def test_encode_entity_command(self, encoder):
        """Test encoding a basic entity command."""
        command = ControlCommand(command="set", state="on", brightness=75)

        # Mock the command DGN lookup
        with patch.object(encoder, "_get_command_dgn", return_value="1FFB2"):
            messages = encoder.encode_entity_command("test_light", command)

        assert len(messages) == 1
        message = messages[0]
        assert message.extended is True
        assert len(message.data) == 8
        # Instance should be in byte 0
        assert message.data[0] == 1

    def test_get_supported_entities(self, encoder):
        """Test getting list of supported entities."""
        with patch.object(encoder, "_get_command_dgn", return_value="1FFB2"):
            supported = encoder.get_supported_entities()
            assert "test_light" in supported


class TestMessageValidator:
    """Test the Message Validator functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.rvc_spec_path = None
        settings.rvc_coach_mapping_path = None
        # validate_source_permissions does int(controller_source_addr, 16),
        # so this must be a hex string -- not a Mock auto-attribute.
        settings.controller_source_addr = "0xF9"
        return settings

    @pytest.fixture
    def validator(self, mock_settings):
        """Create a message validator for testing."""
        # Same refactor story as the encoder: load_config_data (10-tuple) was
        # replaced by load_config_data_v2 (RVCConfiguration). Patch the
        # current entry point.
        from backend.models.common import CoachInfo
        from backend.models.rvc_config import RVCConfiguration, RVCSpecMeta

        mock_config = RVCConfiguration(
            dgn_dict={
                0x1FFB1: {
                    "pgn": "1FFB1",
                    "signals": [
                        {
                            "name": "brightness",
                            "start_bit": 8,
                            "length": 8,
                            "scale": 1,
                            "offset": 0,
                        },
                        {"name": "instance", "start_bit": 0, "length": 8},
                    ],
                }
            },
            spec_meta=RVCSpecMeta(version="test", source="test", rvc_version="test"),
            mapping_dict={},
            entity_map={},
            entity_ids=set(),
            inst_map={},
            unique_instances={},
            pgn_hex_to_name_map={},
            dgn_pairs={},
            coach_info=CoachInfo(
                make=None, model=None, year=None, trim=None, filename=None, notes=None
            ),
        )

        with patch(
            "backend.integrations.rvc.validator.load_config_data_v2",
            return_value=mock_config,
        ):
            return MessageValidator(mock_settings)

    def test_validator_initialization(self, validator):
        """Test validator initializes correctly."""
        assert validator._config_loaded

    def test_validate_signal_range_valid(self, validator):
        """Test signal range validation with valid value."""
        signal = {"name": "brightness", "length": 8, "scale": 1, "offset": 0}
        result = validator.validate_signal_range(signal, 50)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_signal_range_invalid(self, validator):
        """Test signal range validation with invalid value."""
        signal = {"name": "brightness", "length": 8, "scale": 1, "offset": 0}
        result = validator.validate_signal_range(signal, 300)  # Exceeds 8-bit max

        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_dependencies(self, validator):
        """Test dependency validation."""
        decoded_signals = {
            "brightness": 50,
            "state": "off",  # Conflict: brightness > 0 but state is off
        }

        errors = validator.validate_dependencies(decoded_signals)
        # Should detect the brightness/state conflict
        assert len(errors) > 0

    def test_validate_source_permissions(self, validator):
        """Test source address validation."""
        # Valid source address
        assert validator.validate_source_permissions(0x80, 0x1FFB1)

        # Invalid source address (out of range)
        assert not validator.validate_source_permissions(0xFA, 0x1FFB1)

    def test_complete_message_validation(self, validator):
        """Test complete message validation."""
        decoded_signals = {"brightness": 50, "instance": 1}
        raw_data = bytes([1, 50, 0, 0, 0, 0, 0, 0])

        result = validator.validate_message_complete(0x1FFB1, 0x80, decoded_signals, raw_data)
        assert result.is_valid


class TestSecurityManager:
    """Test the Security Manager functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.controller_source_addr = "0xF9"
        return settings

    @pytest.fixture
    def security_manager(self, mock_settings):
        """Create a security manager for testing."""
        return SecurityManager(mock_settings)

    def test_security_manager_initialization(self, security_manager):
        """Test security manager initializes correctly."""
        assert security_manager._controller_addr == 0xF9
        assert len(security_manager._rate_limits) > 0

    def test_validate_source_address_valid(self, security_manager):
        """Test source address validation with valid address."""
        assert security_manager.validate_source_address(0x80, 0x1FFB1)
        assert security_manager.validate_source_address(0xF9, 0x1FFB1)  # Controller

    def test_validate_source_address_invalid(self, security_manager):
        """Test source address validation with invalid address."""
        assert not security_manager.validate_source_address(0xFA, 0x1FFB1)  # Out of range

    def test_rate_limiting(self, security_manager):
        """Test rate limiting functionality."""
        source_addr = 0x80
        dgn = 0x1FFB1

        # First few messages should be allowed
        for _ in range(5):
            assert security_manager.rate_limit_commands(source_addr, dgn)

        # Rapid messages should eventually be rate limited
        # This test may need adjustment based on actual rate limits
        allowed_count = 0
        for _ in range(100):
            if security_manager.rate_limit_commands(source_addr, dgn):
                allowed_count += 1

        # Should have some rate limiting effect
        assert allowed_count < 100

    def test_anomaly_detection(self, security_manager):
        """Test anomaly detection."""
        current_time = time.time()

        # Create messages that should trigger flooding detection
        messages = []
        for _ in range(150):  # More than threshold
            messages.append(
                {
                    "source_address": 0x80,
                    "dgn": 0x1FFB1,
                    "data": bytes([1, 2, 3, 4, 5, 6, 7, 8]),
                    "timestamp": current_time,
                }
            )

        anomalies = security_manager.detect_anomalous_traffic(messages)

        # Should detect message flooding
        assert len(anomalies) > 0
        assert any(a.anomaly_type == "message_flooding" for a in anomalies)

    def test_security_status(self, security_manager):
        """Test security status reporting."""
        status = security_manager.get_security_status()

        assert "status" in status
        assert "active_sources" in status
        assert "total_anomalies" in status


class TestPriorityMessageHandler:
    """Test the Priority Message Handler functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        return settings

    @pytest.fixture
    def handler(self, mock_settings):
        """Create a priority message handler for testing.

        Disables the per-priority rate limiter so tests can queue many
        messages back-to-back without hitting the production thresholds
        (which are tuned for sustained traffic, not test microbursts).
        """
        h = PriorityMessageHandler(mock_settings, max_queue_size=1000)
        # Replace _check_rate_limit with a no-op so tests aren't subject to
        # production rate limiting timing.
        h._check_rate_limit = lambda priority: True  # type: ignore[method-assign]
        return h

    def test_handler_initialization(self, handler):
        """Test handler initializes correctly."""
        assert len(handler._priority_queues) == len(MessagePriority)
        assert handler.max_queue_size == 1000

    def test_message_priority_classification(self, handler):
        """Test message priority classification."""
        # Critical message
        priority = handler.categorize_message_priority(0x1FECA)  # DM_RV
        assert priority == MessagePriority.CRITICAL

        # High priority message
        priority = handler.categorize_message_priority(0x1FF01)  # Engine temp
        assert priority == MessagePriority.HIGH

        # Normal priority message
        priority = handler.categorize_message_priority(0x1FFB1)  # Light command
        assert priority == MessagePriority.NORMAL

    def test_should_process_immediately(self, handler):
        """Test immediate processing determination."""
        # Critical messages should be processed immediately
        assert handler.should_process_immediately(0x1FECA)

        # High priority should be processed immediately
        assert handler.should_process_immediately(0x1FF01)

        # Normal priority should not
        assert not handler.should_process_immediately(0x1FFB1)

    def test_queue_by_priority(self, handler):
        """Test priority-based queuing."""
        # Queue messages of different priorities
        assert handler.queue_by_priority(0x1FECA, 0x80, b"critical", 0x12345678)  # Critical
        assert handler.queue_by_priority(0x1FFB1, 0x80, b"normal", 0x12345679)  # Normal
        assert handler.queue_by_priority(0x1FF01, 0x80, b"high", 0x1234567A)  # High

        # Get messages - should come out in priority order
        msg1 = handler.get_next_message()
        msg2 = handler.get_next_message()
        msg3 = handler.get_next_message()

        assert msg1.priority == MessagePriority.CRITICAL
        assert msg2.priority == MessagePriority.HIGH
        assert msg3.priority == MessagePriority.NORMAL

    def test_get_messages_batch(self, handler):
        """Test batch message retrieval."""
        # Queue several messages
        for i in range(10):
            handler.queue_by_priority(0x1FFB1 + i, 0x80, f"msg{i}".encode(), 0x12345678 + i)

        batch = handler.get_messages_batch(5)
        assert len(batch) == 5

        # Should respect max batch size
        batch = handler.get_messages_batch(20)
        assert len(batch) == 5  # Only 5 remaining

    def test_performance_metrics(self, handler):
        """Test performance metrics collection."""
        # Queue and process some messages
        handler.queue_by_priority(0x1FFB1, 0x80, b"test", 0x12345678)
        handler.get_next_message()

        # Record processing time
        handler.record_processing_time(0.001)  # 1ms

        metrics = handler.get_performance_metrics()

        assert "messages_processed" in metrics
        assert "average_processing_time_ms" in metrics
        assert "current_queue_size" in metrics
        assert metrics["average_processing_time_ms"] == 1.0  # 1ms

    def test_queue_management(self, handler):
        """Test queue management functions."""
        # Fill queue
        for i in range(10):
            handler.queue_by_priority(0x1FFB1, 0x80, f"msg{i}".encode(), 0x12345678)

        assert handler.get_total_queue_size() == 10

        # Clear specific priority
        cleared = handler.clear_queue_by_priority(MessagePriority.NORMAL)
        assert cleared == 10
        assert handler.get_total_queue_size() == 0

    @pytest.mark.asyncio
    async def test_continuous_processing(self, handler):
        """Test continuous queue processing."""
        processed_messages = []

        async def mock_processor(messages):
            processed_messages.extend(messages)

        # Queue some messages
        for i in range(5):
            handler.queue_by_priority(0x1FFB1, 0x80, f"msg{i}".encode(), 0x12345678)

        # Start processing task
        task = asyncio.create_task(
            handler.process_queue_continuously(mock_processor, batch_size=10, sleep_interval=0.001)
        )

        # Let it process for a short time
        await asyncio.sleep(0.01)

        # Stop processing
        handler.stop_processing()

        # Wait for task to complete
        await asyncio.sleep(0.01)
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Should have processed some messages
        assert len(processed_messages) > 0


class TestPhase1Integration:
    """Test integration of Phase 1 components."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.controller_source_addr = "0xF9"
        settings.rvc_spec_path = None
        settings.rvc_coach_mapping_path = None
        return settings

    def test_components_integration(self, mock_settings):
        """Test that all Phase 1 components work together."""
        # Patch the v2 config loader on each module that imports it. The
        # old single-name load_config_data was replaced when the spec
        # loader was structured into RVCConfiguration.
        from backend.models.common import CoachInfo
        from backend.models.rvc_config import RVCConfiguration, RVCSpecMeta

        empty_config = RVCConfiguration(
            dgn_dict={},
            spec_meta=RVCSpecMeta(version="test", source="test", rvc_version="test"),
            mapping_dict={},
            entity_map={},
            entity_ids=set(),
            inst_map={},
            unique_instances={},
            pgn_hex_to_name_map={},
            dgn_pairs={},
            coach_info=CoachInfo(
                make=None, model=None, year=None, trim=None, filename=None, notes=None
            ),
        )

        with (
            patch(
                "backend.integrations.rvc.encoder.load_config_data_v2",
                return_value=empty_config,
            ),
            patch(
                "backend.integrations.rvc.validator.load_config_data_v2",
                return_value=empty_config,
            ),
        ):
            # Initialize all components
            encoder = RVCEncoder(mock_settings)
            validator = MessageValidator(mock_settings)
            security_manager = SecurityManager(mock_settings)
            performance_handler = PriorityMessageHandler(mock_settings)

            # Test that they can all coexist
            assert encoder is not None
            assert validator is not None
            assert security_manager is not None
            assert performance_handler is not None

    def test_error_handling(self, mock_settings):
        """Test graceful error handling in components."""
        # Test with invalid configuration: a v2 config loader that fails
        # should propagate as an EncodingError on encoder construction.
        with (
            patch(
                "backend.integrations.rvc.encoder.load_config_data_v2",
                side_effect=Exception("Config error"),
            ),
            pytest.raises(EncodingError),
        ):
            RVCEncoder(mock_settings)


# Note: test_rvc_feature_with_phase1 was removed in the dead-Feature-pattern
# cleanup -- backend.integrations.rvc.feature no longer exists, and the
# RVCFeature class it defined was orphaned (no live callers) by the
# ServiceRegistry refactor. The Phase 1 components themselves are exercised
# above via TestRVCEncoder, TestMessageValidator, and TestPriorityMessageHandler.
