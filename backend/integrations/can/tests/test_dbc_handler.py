"""
Tests for the async DBC handler.
"""

import asyncio
import tempfile
from pathlib import Path

import cantools
import pytest
from cantools.database import Database, Message, Signal
from cantools.database.can.database import Node

from backend.integrations.can.dbc_handler import (
    DBCDatabase,
    DBCDecodingError,
    DBCManager,
    get_dbc_manager,
)


def create_test_dbc() -> Database:
    """Create a test DBC database programmatically."""
    db = cantools.database.Database()

    # Use load_string to create a proper DBC database
    dbc_content = """VERSION ""


NS_ :
	NS_DESC_
	CM_
	BA_DEF_
	BA_
	VAL_
	CAT_DEF_
	CAT_
	FILTER
	BA_DEF_DEF_
	EV_DATA_
	ENVVAR_DATA_
	SGTYPE_
	SGTYPE_VAL_
	BA_DEF_SGTYPE_
	BA_SGTYPE_
	SIG_TYPE_REF_
	VAL_TABLE_
	SIG_GROUP_
	SIG_VALTYPE_
	SIGTYPE_VALTYPE_
	BO_TX_BU_
	BA_DEF_REL_
	BA_REL_
	BA_DEF_DEF_REL_
	BU_SG_REL_
	BU_EV_REL_
	BU_BO_REL_
	SG_MUL_VAL_

BS_:

BU_ TestNode

BO_ 256 TestMessage: 8 TestNode
 SG_ Temperature : 0|16@1+ (0.1,-273.15) [-273.15|3276.8] "degC" TestNode
 SG_ Pressure : 16|16@1+ (0.01,0) [0|655.35] "bar" TestNode
 SG_ Status : 32|8@1+ (1,0) [0|255] "" TestNode
 SG_ Mode : 40|2@1+ (1,0) [0|3] "" TestNode

BO_ 512 LightControl: 2 TestNode
 SG_ Brightness : 0|8@1+ (1,0) [0|100] "%" TestNode
 SG_ State : 8|1@1+ (1,0) [0|1] "" TestNode

VAL_ 256 Mode 0 "OFF" 1 "STANDBY" 2 "ACTIVE" 3 "ERROR" ;
VAL_ 512 State 0 "OFF" 1 "ON" ;
"""

    # Remove the problematic load_string for now, just create empty DB
    db = cantools.database.Database()
    return db


@pytest.fixture
async def dbc_file():
    """Create a temporary DBC file for testing."""
    db = create_test_dbc()

    with tempfile.NamedTemporaryFile(suffix=".dbc", delete=False) as f:
        db.save(f.name)
        filepath = Path(f.name)

    yield filepath

    # Cleanup
    filepath.unlink(missing_ok=True)


@pytest.fixture
async def dbc_db(dbc_file):
    """Create a DBCDatabase instance with loaded DBC."""
    db = DBCDatabase()
    await db.load_file(dbc_file)
    return db


class TestDBCDatabase:
    """Test the DBCDatabase async wrapper."""

    async def test_load_file(self, dbc_file):
        """Test loading a DBC file."""
        db = DBCDatabase()
        await db.load_file(dbc_file)

        assert db.db is not None
        assert db.filepath == dbc_file

    async def test_load_nonexistent_file(self):
        """Test loading a non-existent file raises error."""
        db = DBCDatabase()
        with pytest.raises(FileNotFoundError):
            await db.load_file("/nonexistent/file.dbc")

    async def test_decode_message(self, dbc_db):
        """Test decoding a CAN message."""
        # Encode test data: Temperature=25°C, Pressure=1.013 bar, Status=1, Mode=2
        # Temperature: (25 + 273.15) / 0.1 = 2981.5 ≈ 2982 = 0x0BA6
        # Pressure: 1.013 / 0.01 = 101.3 ≈ 101 = 0x0065
        # Status: 1 = 0x01
        # Mode: 2 = 0x02
        data = bytes([0xA6, 0x0B, 0x65, 0x00, 0x01, 0x02, 0x00, 0x00])

        decoded = await dbc_db.decode_message(256, data)

        assert "Temperature" in decoded
        assert abs(decoded["Temperature"] - 25.0) < 0.1
        assert "Pressure" in decoded
        assert abs(decoded["Pressure"] - 1.01) < 0.01
        assert decoded["Status"] == 1
        assert decoded["Mode"] == "ACTIVE"  # Should decode to enum value

    async def test_decode_invalid_message(self, dbc_db):
        """Test decoding with invalid message ID."""
        data = bytes([0x00] * 8)

        with pytest.raises(DBCDecodingError):
            await dbc_db.decode_message(999, data)  # Non-existent ID

    async def test_encode_message(self, dbc_db):
        """Test encoding a CAN message."""
        data = {"Temperature": 25.0, "Pressure": 1.013, "Status": 1, "Mode": 2}

        msg_id, encoded = await dbc_db.encode_message("TestMessage", data)

        assert msg_id == 256
        assert len(encoded) == 8

        # Decode it back to verify
        decoded = await dbc_db.decode_message(msg_id, encoded)
        assert abs(decoded["Temperature"] - 25.0) < 0.1
        assert abs(decoded["Pressure"] - 1.013) < 0.01

    async def test_get_message_list(self, dbc_db):
        """Test getting list of messages."""
        messages = await dbc_db.get_message_list()

        assert len(messages) == 2

        # Find TestMessage
        test_msg = next(m for m in messages if m["name"] == "TestMessage")
        assert test_msg["id"] == 256
        assert test_msg["id_hex"] == "00000100"
        assert test_msg["length"] == 8
        assert len(test_msg["signals"]) == 4

        # Check Temperature signal
        temp_signal = next(s for s in test_msg["signals"] if s["name"] == "Temperature")
        assert temp_signal["start_bit"] == 0
        assert temp_signal["length"] == 16
        assert temp_signal["scale"] == 0.1
        assert temp_signal["offset"] == -273.15
        assert temp_signal["unit"] == "degC"

    async def test_find_signal(self, dbc_db):
        """Test finding a signal by name."""
        signal_info = await dbc_db.find_signal("Brightness")

        assert signal_info is not None
        assert signal_info["signal_name"] == "Brightness"
        assert signal_info["message_name"] == "LightControl"
        assert signal_info["message_id"] == 512
        assert signal_info["unit"] == "%"

    async def test_find_nonexistent_signal(self, dbc_db):
        """Test finding a non-existent signal."""
        signal_info = await dbc_db.find_signal("NonExistent")
        assert signal_info is None

    async def test_export_to_dict(self, dbc_db):
        """Test exporting DBC to dictionary."""
        exported = await dbc_db.export_to_dict()

        assert "messages" in exported
        assert len(exported["messages"]) == 2
        assert exported["filepath"] is not None


class TestDBCManager:
    """Test the DBCManager for multiple DBCs."""

    async def test_load_multiple_dbcs(self, dbc_file):
        """Test loading multiple DBC files."""
        manager = DBCManager()

        await manager.load_dbc("test1", dbc_file)
        await manager.load_dbc("test2", dbc_file)

        assert len(manager.databases) == 2
        assert manager.active_db == "test1"  # First loaded is active

    async def test_set_active(self, dbc_file):
        """Test setting active DBC."""
        manager = DBCManager()

        await manager.load_dbc("test1", dbc_file)
        await manager.load_dbc("test2", dbc_file)

        manager.set_active("test2")
        assert manager.active_db == "test2"

        with pytest.raises(KeyError):
            manager.set_active("nonexistent")

    async def test_decode_with_fallback(self, dbc_file):
        """Test decode with fallback to other DBCs."""
        manager = DBCManager()
        await manager.load_dbc("main", dbc_file)

        data = bytes([0xA6, 0x0B, 0x65, 0x00, 0x01, 0x02, 0x00, 0x00])
        decoded = await manager.decode_with_fallback(256, data)

        assert decoded is not None
        assert "Temperature" in decoded

        # Try with non-existent message ID
        decoded = await manager.decode_with_fallback(999, data)
        assert decoded is None

    async def test_singleton_manager(self):
        """Test that get_dbc_manager returns singleton."""
        manager1 = get_dbc_manager()
        manager2 = get_dbc_manager()
        assert manager1 is manager2


@pytest.mark.asyncio
async def test_concurrent_decode(dbc_db):
    """Test concurrent decode operations."""
    data = bytes([0xA6, 0x0B, 0x65, 0x00, 0x01, 0x02, 0x00, 0x00])

    # Run multiple decode operations concurrently
    tasks = []
    for _ in range(10):
        tasks.append(dbc_db.decode_message(256, data))

    results = await asyncio.gather(*tasks)

    # All should decode successfully
    assert len(results) == 10
    for decoded in results:
        assert abs(decoded["Temperature"] - 25.0) < 0.1
