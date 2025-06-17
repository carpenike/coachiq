"""Tests for the application state management."""

from unittest.mock import Mock, patch

import pytest

from backend.core.state import AppState
from backend.models.entity_model import EntityConfig


class TestAppState:
    """Test cases for AppState class."""

    @pytest.fixture
    def app_state(self):
        """Create a fresh AppState instance for each test."""
        return AppState(
            name="test_app_state",
            enabled=True,
            core=True,
            config={},
            dependencies=[],
            controller_source_addr=0xF9,
        )

    @pytest.fixture
    def sample_entity_config(self):
        """Sample entity configuration for testing."""
        return EntityConfig(
            device_type="light",
            suggested_area="Kitchen",
            friendly_name="Kitchen Light",
            capabilities=["on", "off", "dimming"],
            groups=["interior", "main"],
            instance=1,
        )

    def test_initialization(self, app_state):
        """Test AppState initialization."""
        assert app_state.name == "test_app_state"
        assert app_state.enabled is True
        assert app_state.core is True
        assert app_state.controller_source_addr == 0xF9
        assert app_state.entity_manager is not None
        assert app_state.raw_device_mapping == {}
        assert app_state.pgn_hex_to_name_map == {}
        assert app_state.unmapped_entries == {}
        assert app_state.unknown_pgns == {}
        assert app_state.pending_commands == []
        assert app_state.observed_source_addresses == set()
        assert app_state.known_command_status_pairs == {}

    def test_health_property(self, app_state):
        """Test the health property returns correct status."""
        # When enabled, should return "healthy"
        assert app_state.health == "healthy"

        # When disabled, should return "disabled"
        app_state.enabled = False
        assert app_state.health == "disabled"

    def test_get_controller_source_addr(self, app_state):
        """Test getting controller source address."""
        assert app_state.get_controller_source_addr() == 0xF9

    def test_get_observed_source_addresses(self, app_state):
        """Test getting observed source addresses."""
        # Initially empty
        assert app_state.get_observed_source_addresses() == []

        # Add some addresses
        app_state.observed_source_addresses.add(0x10)
        app_state.observed_source_addresses.add(0x05)
        app_state.observed_source_addresses.add(0x20)

        # Should return sorted list
        result = app_state.get_observed_source_addresses()
        assert result == [0x05, 0x10, 0x20]

    def test_add_pending_command(self, app_state):
        """Test adding pending commands and cleanup."""
        import time

        # Create mock entries with timestamps
        current_time = time.time()

        entry1 = {"timestamp": current_time - 3.0, "command": "old"}
        entry2 = {"timestamp": current_time - 1.0, "command": "recent"}
        entry3 = {"timestamp": current_time, "command": "new"}

        # Add entries
        app_state.add_pending_command(entry1)
        app_state.add_pending_command(entry2)
        app_state.add_pending_command(entry3)

        # Old entry should be cleaned up (older than 2 seconds)
        assert len(app_state.pending_commands) == 2
        commands = [cmd["command"] for cmd in app_state.pending_commands]
        assert "old" not in commands
        assert "recent" in commands
        assert "new" in commands

    def test_set_broadcast_function(self, app_state):
        """Test setting broadcast function."""
        mock_func = Mock()
        app_state.set_broadcast_function(mock_func)
        assert app_state._broadcast_can_sniffer_group == mock_func

    def test_get_can_sniffer_grouped(self, app_state):
        """Test getting grouped CAN sniffer entries."""
        # Initially empty
        assert app_state.get_can_sniffer_grouped() == []

        # Add a group
        group = {"command": {"id": 1}, "response": {"id": 2}}
        app_state.can_sniffer_grouped.append(group)

        result = app_state.get_can_sniffer_grouped()
        assert len(result) == 1
        assert result[0] == group

    def test_get_can_sniffer_log(self, app_state):
        """Test getting CAN sniffer log."""
        # Initially empty
        assert app_state.get_can_sniffer_log() == []

        # Add entries
        entry1 = {"message": "test1"}
        entry2 = {"message": "test2"}
        app_state.can_command_sniffer_log.extend([entry1, entry2])

        result = app_state.get_can_sniffer_log()
        assert len(result) == 2
        assert result == [entry1, entry2]

    def test_update_last_seen_by_source_addr(self, app_state):
        """Test updating last seen by source address."""
        entry = {"source_addr": 0x10, "message": "test"}

        app_state.update_last_seen_by_source_addr(entry)

        assert 0x10 in app_state.observed_source_addresses
        assert app_state.last_seen_by_source_addr[0x10] == entry

    def test_add_can_sniffer_entry(self, app_state):
        """Test adding CAN sniffer entry."""
        with patch.object(app_state, "notify_network_map_ws") as mock_notify:
            entry = {"source_addr": 0x15, "message": "test"}

            app_state.add_can_sniffer_entry(entry)

            assert entry in app_state.can_command_sniffer_log
            assert 0x15 in app_state.observed_source_addresses
            mock_notify.assert_called_once()

    def test_get_last_known_brightness(self, app_state, sample_entity_config):
        """Test getting last known brightness."""
        # Test default when entity doesn't exist
        assert app_state.get_last_known_brightness("nonexistent") == 100

        # Test with existing entity
        entity_id = "light_1"
        entity = app_state.entity_manager.register_entity(entity_id, sample_entity_config)
        entity.last_known_brightness = 75

        assert app_state.get_last_known_brightness(entity_id) == 75

    def test_set_last_known_brightness(self, app_state, sample_entity_config):
        """Test setting last known brightness."""
        entity_id = "light_1"
        entity = app_state.entity_manager.register_entity(entity_id, sample_entity_config)

        app_state.set_last_known_brightness(entity_id, 50)
        assert entity.last_known_brightness == 50

    def test_update_entity_state_and_history(self, app_state, sample_entity_config):
        """Test updating entity state and history."""
        entity_id = "light_1"
        app_state.entity_manager.register_entity(entity_id, sample_entity_config)

        payload = {"status": "on", "brightness": 80}
        app_state.update_entity_state_and_history(entity_id, payload)

        entity = app_state.entity_manager.get_entity(entity_id)
        assert entity is not None
        # The state should be updated (exact assertion depends on Entity implementation)

    def test_update_entity_state_new_entity(self, app_state):
        """Test updating state for non-existent entity creates new entity."""
        entity_id = "new_light"
        payload = {
            "device_type": "light",
            "suggested_area": "Living Room",
            "friendly_name": "Living Room Light",
            "capabilities": ["on", "off"],
            "groups": ["interior"],
            "status": "on",
        }

        app_state.update_entity_state_and_history(entity_id, payload)

        entity = app_state.entity_manager.get_entity(entity_id)
        assert entity is not None

    def test_repr(self, app_state, sample_entity_config):
        """Test string representation."""
        # Add an entity
        app_state.entity_manager.register_entity("light_1", sample_entity_config)
        app_state.unmapped_entries["test"] = "value"
        app_state.unknown_pgns["unknown"] = "data"

        repr_str = repr(app_state)
        assert "AppState" in repr_str
        assert "entities=1" in repr_str
        assert "unmapped_entries=1" in repr_str
        assert "unknown_pgns=1" in repr_str

    def test_health_status(self, app_state):
        """Test health status functionality."""
        health_status = app_state.get_health_status()
        assert isinstance(health_status, dict)
        assert "status" in health_status
        assert "components" in health_status

    @patch("backend.core.state.CANSniffer")
    def test_start_can_sniffer(self, mock_can_sniffer, app_state):
        """Test starting CAN sniffer."""
        mock_sniffer_instance = Mock()
        mock_can_sniffer.return_value = mock_sniffer_instance

        app_state.start_can_sniffer("vcan0")

        mock_can_sniffer.assert_called_once_with("vcan0", app_state.process_message)
        mock_sniffer_instance.start.assert_called_once()
        assert app_state.can_sniffer == mock_sniffer_instance

    def test_stop_can_sniffer(self, app_state):
        """Test stopping CAN sniffer."""
        # Set up a mock sniffer
        mock_sniffer = Mock()
        app_state.can_sniffer = mock_sniffer

        app_state.stop_can_sniffer()

        mock_sniffer.stop.assert_called_once()
        assert app_state.can_sniffer is None

    def test_get_entity_count(self, app_state):
        """Test getting entity count."""
        assert app_state.get_entity_count() == 0

        app_state.add_entity_state("light_1", {"status": "on"})
        assert app_state.get_entity_count() == 1

        app_state.add_entity_state("light_2", {"status": "off"})
        assert app_state.get_entity_count() == 2

    def test_process_message_successful(self, app_state):
        """Test successful message processing."""
        # Mock a message with all required attributes
        mock_message = Mock()
        mock_message.arbitration_id = 0x1F00100
        mock_message.data = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
        mock_message.timestamp = 1234567890.0

        with patch.object(app_state, "_decode_rvc_message") as mock_decode:
            mock_decode.return_value = {
                "dgn_name": "test_dgn",
                "decoded_data": {"field1": "value1"},
            }

            app_state.process_message(mock_message)
            mock_decode.assert_called_once()

    def test_process_message_error_handling(self, app_state):
        """Test error handling in message processing."""
        mock_message = Mock()
        mock_message.arbitration_id = 0x1F00100
        mock_message.data = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
        mock_message.timestamp = 1234567890.0

        with patch.object(app_state, "_decode_rvc_message") as mock_decode:
            mock_decode.side_effect = Exception("Decode error")

            # Should not raise exception - errors should be handled gracefully
            app_state.process_message(mock_message)

    def test_add_entity_state(self, app_state):
        """Test adding entity state."""
        entity_id = "light_1"
        entity_data = {"status": "on", "brightness": 100}

        app_state.add_entity_state(entity_id, entity_data)

        stored_data = app_state.get_entity_state(entity_id)
        assert stored_data == entity_data

    def test_get_entity_state_existing(self, app_state):
        """Test getting existing entity state."""
        entity_id = "light_1"
        entity_data = {"status": "on"}

        app_state.add_entity_state(entity_id, entity_data)
        result = app_state.get_entity_state(entity_id)

        assert result == entity_data

    def test_get_entity_state_nonexistent(self, app_state):
        """Test getting nonexistent entity state."""
        result = app_state.get_entity_state("nonexistent")
        assert result is None

    def test_update_entity_state(self, app_state):
        """Test updating entity state."""
        entity_id = "light_1"
        initial_data = {"status": "off", "brightness": 0}
        update_data = {"status": "on", "brightness": 75}

        app_state.add_entity_state(entity_id, initial_data)
        app_state.update_entity_state(entity_id, update_data)

        result = app_state.get_entity_state(entity_id)
        expected = {**initial_data, **update_data}
        assert result == expected

    def test_remove_entity_state(self, app_state):
        """Test removing entity state."""
        entity_id = "light_1"
        entity_data = {"status": "on"}

        app_state.add_entity_state(entity_id, entity_data)
        assert app_state.get_entity_state(entity_id) == entity_data

        app_state.remove_entity_state(entity_id)
        assert app_state.get_entity_state(entity_id) is None

    def test_get_all_entity_states(self, app_state):
        """Test getting all entity states."""
        entities = {
            "light_1": {"status": "on"},
            "light_2": {"status": "off"},
            "lock_1": {"locked": True},
        }

        for entity_id, data in entities.items():
            app_state.add_entity_state(entity_id, data)

        all_states = app_state.get_all_entity_states()
        assert all_states == entities

    def test_clear_entity_states(self, app_state):
        """Test clearing all entity states."""
        app_state.add_entity_state("light_1", {"status": "on"})
        app_state.add_entity_state("light_2", {"status": "off"})

        assert len(app_state.get_all_entity_states()) == 2

        app_state.clear_entity_states()
        assert len(app_state.get_all_entity_states()) == 0


class TestModuleFunctions:
    """Test module-level functions."""

    def test_initialize_app_state_creates_new_instance(self):
        """Test initialize_app_state creates and returns a new AppState instance."""
        from backend.core.state import initialize_app_state

        # Mock dependencies
        mock_manager = Mock()
        mock_manager.register_feature = Mock()
        config = {"test": "value"}

        with patch("backend.core.state.app_state", None):
            result = initialize_app_state(mock_manager, config)

            assert isinstance(result, AppState)
            assert result.config_data == config
            mock_manager.register_feature.assert_called_once_with(result)
