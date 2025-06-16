"""
Tests for CAN message models.
"""

import pytest

from backend.models.can_message import CANMessage, CANMessageBatch, CANMessageFilter


class TestCANMessage:
    """Test the CANMessage model."""

    def test_can_message_creation(self):
        """Test creating a basic CAN message."""
        msg = CANMessage(
            can_id=0x18FEF100,
            data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
        )
        assert msg.can_id == 0x18FEF100
        assert msg.data == b"\x01\x02\x03\x04\x05\x06\x07\x08"
        assert msg.extended is True  # Default
        assert msg.dlc == 8
        assert msg.is_bam is False
        assert msg.target_pgn is None

    def test_can_message_with_optional_fields(self):
        """Test CAN message with all optional fields."""
        msg = CANMessage(
            can_id=0x123,
            data=b"\xAB\xCD",
            extended=False,
            is_bam=True,
            target_pgn=0x1234,
            interface="can0",
            timestamp=1234567890.123,
            is_error=False,
            is_remote=True,
        )
        assert msg.can_id == 0x123
        assert msg.data == b"\xAB\xCD"
        assert msg.extended is False
        assert msg.dlc == 2
        assert msg.is_bam is True
        assert msg.target_pgn == 0x1234
        assert msg.interface == "can0"
        assert msg.timestamp == 1234567890.123
        assert msg.is_error is False
        assert msg.is_remote is True

    def test_can_message_to_dict(self):
        """Test converting CAN message to dictionary."""
        msg = CANMessage(
            can_id=0x18FEF100,
            data=b"\x01\x02\x03\x04",
            interface="can1",
        )
        d = msg.to_dict()
        assert d["can_id"] == 0x18FEF100
        assert d["data"] == "01020304"  # Hex string uppercase
        assert d["extended"] is True
        assert d["interface"] == "can1"

    def test_rvc_properties(self):
        """Test RV-C specific properties."""
        # RV-C message with priority=6, PGN=0xFEF1, source=0x10
        can_id = (6 << 26) | (0xFEF1 << 8) | 0x10
        msg = CANMessage(
            can_id=can_id,
            data=b"\x00" * 8,
            extended=True,
        )
        assert msg.priority == 6
        assert msg.pgn == 0xFEF1
        assert msg.source_address == 0x10

    def test_standard_can_rvc_properties(self):
        """Test that RV-C properties return None for standard CAN."""
        msg = CANMessage(
            can_id=0x123,
            data=b"\x00",
            extended=False,
        )
        assert msg.priority is None
        assert msg.pgn is None
        assert msg.source_address is None

    def test_can_message_string_representation(self):
        """Test string representation of CAN message."""
        msg = CANMessage(
            can_id=0x18FEF100,
            data=b"\x01\x02\x03\x04",
            interface="can0",
        )
        s = str(msg)
        assert "CAN [can0]" in s
        assert "18FEF100" in s
        assert "01020304" in s
        assert "DLC: 4" in s

    def test_can_message_validation(self):
        """Test CAN message validation."""
        # Valid 29-bit extended ID
        msg = CANMessage(can_id=0x1FFFFFFF, data=b"")
        assert msg.can_id == 0x1FFFFFFF

        # Invalid CAN ID (too large)
        with pytest.raises(ValueError):
            CANMessage(can_id=0x20000000, data=b"")

        # Invalid data length for CAN 2.0
        with pytest.raises(ValueError):
            CANMessage(can_id=0x123, data=b"\x00" * 65)

        # Valid empty data
        msg = CANMessage(can_id=0x123, data=b"")
        assert msg.dlc == 0


class TestCANMessageBatch:
    """Test the CANMessageBatch model."""

    def test_batch_creation(self):
        """Test creating a batch of CAN messages."""
        messages = [
            CANMessage(can_id=0x100, data=b"\x01"),
            CANMessage(can_id=0x200, data=b"\x02"),
        ]
        batch = CANMessageBatch(messages=messages)
        assert len(batch.messages) == 2
        assert batch.interface is None

    def test_batch_with_interface(self):
        """Test batch with default interface."""
        messages = [CANMessage(can_id=0x100, data=b"\x01")]
        batch = CANMessageBatch(messages=messages, interface="can0")
        assert batch.interface == "can0"

    def test_batch_validation(self):
        """Test batch validation."""
        # Empty batch should fail
        with pytest.raises(ValueError):
            CANMessageBatch(messages=[])


class TestCANMessageFilter:
    """Test the CANMessageFilter model."""

    def test_filter_defaults(self):
        """Test filter with default values."""
        f = CANMessageFilter()
        assert f.can_id is None
        assert f.pgn is None
        assert f.source_address is None
        assert f.interface is None
        assert f.start_time is None
        assert f.end_time is None
        assert f.limit == 100

    def test_filter_with_criteria(self):
        """Test filter with specific criteria."""
        f = CANMessageFilter(
            can_id=0x18FEF100,
            pgn=0xFEF1,
            source_address=0x10,
            interface="can0",
            start_time=1234567890.0,
            end_time=1234567900.0,
            limit=50,
        )
        assert f.can_id == 0x18FEF100
        assert f.pgn == 0xFEF1
        assert f.source_address == 0x10
        assert f.interface == "can0"
        assert f.start_time == 1234567890.0
        assert f.end_time == 1234567900.0
        assert f.limit == 50

    def test_filter_limit_validation(self):
        """Test filter limit validation."""
        # Valid limits
        f = CANMessageFilter(limit=1)
        assert f.limit == 1

        f = CANMessageFilter(limit=10000)
        assert f.limit == 10000

        # Invalid limits
        with pytest.raises(ValueError):
            CANMessageFilter(limit=0)

        with pytest.raises(ValueError):
            CANMessageFilter(limit=10001)
