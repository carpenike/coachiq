"""
Tests for the BAM (Broadcast Announce Message) handler.
"""

from backend.integrations.rvc.bam_handler import BAMHandler


class TestBAMHandler:
    """Test the BAM handler functionality."""

    def test_bam_session_creation(self):
        """Test creating a BAM session from control message."""
        handler = BAMHandler()

        # Create a BAM control message (TP.CM)
        # Control byte = 0x20 (BAM)
        # Total size = 50 bytes (0x32, 0x00 in little endian)
        # Total packets = 8
        # Reserved = 0xFF
        # Target PGN = 0x1FEF2 (Product ID) = F2 FE 01 in little endian
        control_data = bytes([0x20, 0x32, 0x00, 0x08, 0xFF, 0xF2, 0xFE, 0x01])

        result = handler.process_frame(BAMHandler.TP_CM_PGN, control_data, source_address=0x42)

        # Should return None (no complete message yet)
        assert result is None

        # Should have created a session
        assert handler.get_active_session_count() == 1

        # Verify session details
        session_info = handler.get_session_info()[0]
        assert session_info["source_address"] == "42"
        assert session_info["target_pgn"] == "1FEF2"
        assert session_info["total_packets"] == 8
        assert session_info["total_size"] == 50

    def test_bam_message_reassembly(self):
        """Test reassembling a complete BAM message."""
        handler = BAMHandler()

        # Start a BAM session
        control_data = bytes(
            [0x20, 0x15, 0x00, 0x03, 0xFF, 0xF2, 0xFE, 0x01]
        )  # 21 bytes, 3 packets
        handler.process_frame(BAMHandler.TP_CM_PGN, control_data, source_address=0x42)

        # Send data packets
        # Packet 1: sequence=1, data="Hello, "
        packet1 = bytes([0x01]) + b"Hello, "
        result1 = handler.process_frame(BAMHandler.TP_DT_PGN, packet1, source_address=0x42)
        assert result1 is None  # Not complete yet

        # Packet 2: sequence=2, data="World! "
        packet2 = bytes([0x02]) + b"World! "
        result2 = handler.process_frame(BAMHandler.TP_DT_PGN, packet2, source_address=0x42)
        assert result2 is None  # Not complete yet

        # Packet 3: sequence=3, data="123\x00\x00\x00\x00"
        packet3 = bytes([0x03]) + b"123\x00\x00\x00\x00"
        result3 = handler.process_frame(BAMHandler.TP_DT_PGN, packet3, source_address=0x42)

        # Should have a complete message now
        assert result3 is not None
        target_pgn, reassembled_data = result3
        assert target_pgn == 0x1FEF2
        assert reassembled_data == b"Hello, World! 123\x00\x00\x00\x00"[:21]  # Trimmed to 21 bytes

        # Session should be cleaned up
        assert handler.get_active_session_count() == 0

    def test_bam_invalid_sequence(self):
        """Test handling invalid sequence numbers."""
        handler = BAMHandler()

        # Start a BAM session
        control_data = bytes(
            [0x20, 0x0E, 0x00, 0x02, 0xFF, 0xF2, 0xFE, 0x01]
        )  # 14 bytes, 2 packets
        handler.process_frame(BAMHandler.TP_CM_PGN, control_data, source_address=0x42)

        # Send packet with invalid sequence number (should be 1-2, not 5)
        invalid_packet = bytes([0x05]) + b"Invalid"
        result = handler.process_frame(BAMHandler.TP_DT_PGN, invalid_packet, source_address=0x42)

        assert result is None
        assert handler.get_active_session_count() == 1  # Session still active

    def test_bam_session_timeout(self):
        """Test that stale sessions are cleaned up."""
        handler = BAMHandler(session_timeout=0.1)  # Very short timeout for testing

        # Start a BAM session
        control_data = bytes([0x20, 0x0E, 0x00, 0x02, 0xFF, 0xF2, 0xFE, 0x01])
        handler.process_frame(BAMHandler.TP_CM_PGN, control_data, source_address=0x42)

        assert handler.get_active_session_count() == 1

        # Wait for timeout
        import time

        time.sleep(0.2)

        # Trigger cleanup by processing another frame
        dummy_control = bytes([0x20, 0x0E, 0x00, 0x02, 0xFF, 0xF3, 0xFE, 0x01])
        handler.process_frame(BAMHandler.TP_CM_PGN, dummy_control, source_address=0x43)

        # Original session should be cleaned up, only new one remains
        sessions = handler.get_session_info()
        assert len(sessions) == 1
        assert sessions[0]["source_address"] == "43"

    def test_bam_concurrent_sessions(self):
        """Test handling multiple concurrent BAM sessions."""
        handler = BAMHandler()

        # Start first session from source 0x42
        control1 = bytes([0x20, 0x0E, 0x00, 0x02, 0xFF, 0xF2, 0xFE, 0x01])
        handler.process_frame(BAMHandler.TP_CM_PGN, control1, source_address=0x42)

        # Start second session from source 0x43
        control2 = bytes([0x20, 0x15, 0x00, 0x03, 0xFF, 0xF3, 0xFE, 0x01])
        handler.process_frame(BAMHandler.TP_CM_PGN, control2, source_address=0x43)

        assert handler.get_active_session_count() == 2

        # Send data for first session
        packet1_1 = bytes([0x01]) + b"First  "
        handler.process_frame(BAMHandler.TP_DT_PGN, packet1_1, source_address=0x42)

        # Send data for second session
        packet2_1 = bytes([0x01]) + b"Second "
        handler.process_frame(BAMHandler.TP_DT_PGN, packet2_1, source_address=0x43)

        # Both sessions should still be active
        assert handler.get_active_session_count() == 2

        # Complete first session
        packet1_2 = bytes([0x02]) + b"Message"
        result1 = handler.process_frame(BAMHandler.TP_DT_PGN, packet1_2, source_address=0x42)

        assert result1 is not None
        _pgn1, data1 = result1
        assert data1 == b"First  Message"

        # Only second session should remain
        assert handler.get_active_session_count() == 1
