"""
Tests for the EntityManager class.

This module tests the core functionality of the EntityManager including
entity registration, retrieval, filtering, state updates, and bulk operations.
"""

import time
from unittest.mock import MagicMock

import pytest

from backend.core.entity_manager import EntityManager
from backend.models.entity_model import Entity, EntityConfig


@pytest.fixture
def entity_manager():
    """Create a fresh EntityManager instance for testing."""
    return EntityManager()


@pytest.fixture
def sample_light_config():
    """Sample configuration for a light entity."""
    return EntityConfig(
        device_type="light",
        suggested_area="Kitchen",
        friendly_name="Kitchen Light",
        capabilities=["brightness", "on_off"],
        groups=["kitchen", "lights"],
        instance=1,
        command_dgn="command_light",
        status_dgn="status_light",
    )


@pytest.fixture
def sample_lock_config():
    """Sample configuration for a lock entity."""
    return EntityConfig(
        device_type="lock",
        suggested_area="Entry",
        friendly_name="Front Door Lock",
        capabilities=["lock", "unlock"],
        groups=["entry", "security"],
        instance=2,
        command_dgn="command_lock",
        status_dgn="status_lock",
    )


@pytest.fixture
def sample_sensor_config():
    """Sample configuration for a sensor entity."""
    return EntityConfig(
        device_type="sensor",
        suggested_area="Living Room",
        friendly_name="Temperature Sensor",
        capabilities=["temperature"],
        groups=["sensors", "climate"],
        instance=3,
    )


class TestEntityManagerInitialization:
    """Test EntityManager initialization."""

    @pytest.mark.unit
    def test_init_creates_empty_state(self):
        """Test that EntityManager initializes with empty state."""
        manager = EntityManager()

        assert manager.entities == {}
        assert manager.unmapped_entries == {}
        assert manager.unknown_pgns == {}
        assert manager.light_entity_ids == []
        assert manager.device_lookup == {}
        assert manager.status_lookup == {}


class TestEntityRegistration:
    """Test entity registration functionality."""

    @pytest.mark.unit
    def test_register_entity_success(self, entity_manager, sample_light_config):
        """Test successful entity registration."""
        entity_id = "kitchen_light_1"

        entity = entity_manager.register_entity(entity_id, sample_light_config)

        assert isinstance(entity, Entity)
        assert entity.entity_id == entity_id
        assert entity.config == sample_light_config
        assert entity_id in entity_manager.entities
        assert entity_manager.entities[entity_id] is entity

    @pytest.mark.unit
    def test_register_light_entity_tracks_id(self, entity_manager, sample_light_config):
        """Test that registering a light entity adds it to light_entity_ids."""
        entity_id = "kitchen_light_1"

        entity_manager.register_entity(entity_id, sample_light_config)

        assert entity_id in entity_manager.light_entity_ids

    @pytest.mark.unit
    def test_register_non_light_entity_doesnt_track_id(self, entity_manager, sample_lock_config):
        """Test that registering a non-light entity doesn't add it to light_entity_ids."""
        entity_id = "front_door_lock"

        entity_manager.register_entity(entity_id, sample_lock_config)

        assert entity_id not in entity_manager.light_entity_ids
        assert len(entity_manager.light_entity_ids) == 0

    @pytest.mark.unit
    def test_register_multiple_entities(
        self, entity_manager, sample_light_config, sample_lock_config
    ):
        """Test registering multiple entities."""
        light_id = "kitchen_light_1"
        lock_id = "front_door_lock"

        light_entity = entity_manager.register_entity(light_id, sample_light_config)
        lock_entity = entity_manager.register_entity(lock_id, sample_lock_config)

        assert len(entity_manager.entities) == 2
        assert entity_manager.entities[light_id] is light_entity
        assert entity_manager.entities[lock_id] is lock_entity
        assert len(entity_manager.light_entity_ids) == 1
        assert light_id in entity_manager.light_entity_ids


class TestEntityRetrieval:
    """Test entity retrieval functionality."""

    @pytest.mark.unit
    def test_get_entity_success(self, entity_manager, sample_light_config):
        """Test successful entity retrieval."""
        entity_id = "kitchen_light_1"
        registered_entity = entity_manager.register_entity(entity_id, sample_light_config)

        retrieved_entity = entity_manager.get_entity(entity_id)

        assert retrieved_entity is registered_entity
        assert retrieved_entity.entity_id == entity_id

    @pytest.mark.unit
    def test_get_entity_not_found(self, entity_manager):
        """Test getting a non-existent entity returns None."""
        result = entity_manager.get_entity("non_existent_entity")

        assert result is None

    @pytest.mark.unit
    def test_get_all_entities_empty(self, entity_manager):
        """Test getting all entities when none are registered."""
        result = entity_manager.get_all_entities()

        assert result == {}

    @pytest.mark.unit
    def test_get_all_entities_with_data(
        self, entity_manager, sample_light_config, sample_lock_config
    ):
        """Test getting all entities when some are registered."""
        light_id = "kitchen_light_1"
        lock_id = "front_door_lock"

        light_entity = entity_manager.register_entity(light_id, sample_light_config)
        lock_entity = entity_manager.register_entity(lock_id, sample_lock_config)

        result = entity_manager.get_all_entities()

        assert len(result) == 2
        assert result[light_id] is light_entity
        assert result[lock_id] is lock_entity

    @pytest.mark.unit
    def test_get_entity_ids_empty(self, entity_manager):
        """Test getting entity IDs when none are registered."""
        result = entity_manager.get_entity_ids()

        assert result == []

    @pytest.mark.unit
    def test_get_entity_ids_with_data(
        self, entity_manager, sample_light_config, sample_lock_config
    ):
        """Test getting entity IDs when some are registered."""
        light_id = "kitchen_light_1"
        lock_id = "front_door_lock"

        entity_manager.register_entity(light_id, sample_light_config)
        entity_manager.register_entity(lock_id, sample_lock_config)

        result = entity_manager.get_entity_ids()

        assert len(result) == 2
        assert light_id in result
        assert lock_id in result


class TestEntityFiltering:
    """Test entity filtering functionality."""

    @pytest.fixture
    def setup_multiple_entities(self, entity_manager):
        """Setup multiple entities for filtering tests."""
        # Kitchen light
        kitchen_light_config = EntityConfig(
            device_type="light", suggested_area="Kitchen", friendly_name="Kitchen Light"
        )

        # Living room light
        living_light_config = EntityConfig(
            device_type="light", suggested_area="Living Room", friendly_name="Living Room Light"
        )

        # Kitchen lock
        kitchen_lock_config = EntityConfig(
            device_type="lock", suggested_area="Kitchen", friendly_name="Kitchen Lock"
        )

        # Entry sensor
        entry_sensor_config = EntityConfig(
            device_type="sensor", suggested_area="Entry", friendly_name="Entry Sensor"
        )

        entity_manager.register_entity("kitchen_light", kitchen_light_config)
        entity_manager.register_entity("living_light", living_light_config)
        entity_manager.register_entity("kitchen_lock", kitchen_lock_config)
        entity_manager.register_entity("entry_sensor", entry_sensor_config)

        return entity_manager

    @pytest.mark.unit
    def test_filter_entities_by_device_type(self, setup_multiple_entities):
        """Test filtering entities by device type."""
        entity_manager = setup_multiple_entities

        lights = entity_manager.filter_entities(device_type="light")
        locks = entity_manager.filter_entities(device_type="lock")
        sensors = entity_manager.filter_entities(device_type="sensor")

        assert len(lights) == 2
        assert "kitchen_light" in lights
        assert "living_light" in lights

        assert len(locks) == 1
        assert "kitchen_lock" in locks

        assert len(sensors) == 1
        assert "entry_sensor" in sensors

    @pytest.mark.unit
    def test_filter_entities_by_area(self, setup_multiple_entities):
        """Test filtering entities by area."""
        entity_manager = setup_multiple_entities

        kitchen_entities = entity_manager.filter_entities(area="Kitchen")
        living_entities = entity_manager.filter_entities(area="Living Room")
        entry_entities = entity_manager.filter_entities(area="Entry")

        assert len(kitchen_entities) == 2
        assert "kitchen_light" in kitchen_entities
        assert "kitchen_lock" in kitchen_entities

        assert len(living_entities) == 1
        assert "living_light" in living_entities

        assert len(entry_entities) == 1
        assert "entry_sensor" in entry_entities

    @pytest.mark.unit
    def test_filter_entities_by_device_type_and_area(self, setup_multiple_entities):
        """Test filtering entities by both device type and area."""
        entity_manager = setup_multiple_entities

        kitchen_lights = entity_manager.filter_entities(device_type="light", area="Kitchen")
        kitchen_locks = entity_manager.filter_entities(device_type="lock", area="Kitchen")
        living_lights = entity_manager.filter_entities(device_type="light", area="Living Room")

        assert len(kitchen_lights) == 1
        assert "kitchen_light" in kitchen_lights

        assert len(kitchen_locks) == 1
        assert "kitchen_lock" in kitchen_locks

        assert len(living_lights) == 1
        assert "living_light" in living_lights

    @pytest.mark.unit
    def test_filter_entities_no_matches(self, setup_multiple_entities):
        """Test filtering entities with no matches."""
        entity_manager = setup_multiple_entities

        result = entity_manager.filter_entities(device_type="nonexistent")
        assert result == {}

        result = entity_manager.filter_entities(area="Nonexistent Area")
        assert result == {}

        result = entity_manager.filter_entities(device_type="light", area="Entry")
        assert result == {}

    @pytest.mark.unit
    def test_filter_entities_no_filters(self, setup_multiple_entities):
        """Test filtering entities with no filters returns all entities."""
        entity_manager = setup_multiple_entities

        result = entity_manager.filter_entities()

        assert len(result) == 4
        assert "kitchen_light" in result
        assert "living_light" in result
        assert "kitchen_lock" in result
        assert "entry_sensor" in result


class TestEntityStateUpdates:
    """Test entity state update functionality."""

    @pytest.mark.unit
    def test_update_entity_state_success(self, entity_manager, sample_light_config):
        """Test successful entity state update."""
        entity_id = "kitchen_light_1"
        entity_manager.register_entity(entity_id, sample_light_config)

        new_state = {
            "value": {"operating_status": "1"},
            "raw": {"operating_status": 1},
            "state": "on",
            "timestamp": time.time(),
        }

        result = entity_manager.update_entity_state(entity_id, new_state)

        assert result is not None
        assert isinstance(result, Entity)
        assert result.current_state.state == "on"
        assert result.current_state.value == {"operating_status": "1"}

    @pytest.mark.unit
    def test_update_entity_state_not_found(self, entity_manager):
        """Test updating state for non-existent entity returns None."""
        new_state = {"state": "on"}

        result = entity_manager.update_entity_state("non_existent", new_state)

        assert result is None

    @pytest.mark.unit
    def test_update_entity_state_preserves_entity(self, entity_manager, sample_light_config):
        """Test that state update preserves the same entity instance."""
        entity_id = "kitchen_light_1"
        original_entity = entity_manager.register_entity(entity_id, sample_light_config)

        new_state = {"state": "on"}
        updated_entity = entity_manager.update_entity_state(entity_id, new_state)

        assert updated_entity is original_entity


class TestBulkOperations:
    """Test bulk operations functionality."""

    @pytest.mark.unit
    def test_bulk_load_entities_empty(self, entity_manager):
        """Test bulk loading with empty configuration."""
        entity_manager.bulk_load_entities({})

        assert len(entity_manager.entities) == 0
        assert len(entity_manager.light_entity_ids) == 0

    @pytest.mark.unit
    def test_bulk_load_entities_with_data(self, entity_manager):
        """Test bulk loading with entity configurations."""
        configs = {
            "light1": EntityConfig(
                device_type="light", suggested_area="Kitchen", friendly_name="Kitchen Light"
            ),
            "light2": EntityConfig(
                device_type="light", suggested_area="Living Room", friendly_name="Living Room Light"
            ),
            "lock1": EntityConfig(
                device_type="lock", suggested_area="Entry", friendly_name="Front Door Lock"
            ),
        }

        entity_manager.bulk_load_entities(configs)

        assert len(entity_manager.entities) == 3
        assert len(entity_manager.light_entity_ids) == 2
        assert "light1" in entity_manager.entities
        assert "light2" in entity_manager.entities
        assert "lock1" in entity_manager.entities
        assert "light1" in entity_manager.light_entity_ids
        assert "light2" in entity_manager.light_entity_ids
        assert "lock1" not in entity_manager.light_entity_ids

    @pytest.mark.unit
    def test_bulk_load_entities_replaces_existing(self, entity_manager, sample_light_config):
        """Test that bulk loading replaces existing entities."""
        # Register an initial entity
        entity_manager.register_entity("existing_entity", sample_light_config)
        assert len(entity_manager.entities) == 1

        # Bulk load new entities
        new_configs = {
            "new_entity": EntityConfig(
                device_type="sensor", suggested_area="Kitchen", friendly_name="Kitchen Sensor"
            )
        }

        entity_manager.bulk_load_entities(new_configs)

        assert len(entity_manager.entities) == 1
        assert "existing_entity" not in entity_manager.entities
        assert "new_entity" in entity_manager.entities
        assert len(entity_manager.light_entity_ids) == 0


class TestLightEntityMethods:
    """Test light entity specific methods."""

    @pytest.mark.unit
    def test_get_light_entity_ids_empty(self, entity_manager):
        """Test getting light entity IDs when none exist."""
        result = entity_manager.get_light_entity_ids()

        assert result == []

    @pytest.mark.unit
    def test_get_light_entity_ids_with_lights(self, entity_manager):
        """Test getting light entity IDs when lights exist.

        Updated 2026-05-13: production's ``register_entity`` mutates the
        passed-in config in place (sets ``config['physical_id']`` to the
        entity_id when missing), and then deduplicates by physical_id
        (see ``backend/core/entity_manager.py:43``). The previous version
        of this test passed the SAME ``light_config`` dict for both
        ``light1`` and ``light2`` -- the second call therefore matched
        the first call's now-set physical_id and was deduplicated,
        leaving only one light registered.

        Fix: build a distinct config dict per entity so the test
        actually exercises 'multiple lights are tracked', not
        'deduplication path is hit'.
        """
        light_config_1 = EntityConfig(
            device_type="light", suggested_area="Kitchen", friendly_name="Kitchen Light"
        )
        light_config_2 = EntityConfig(
            device_type="light", suggested_area="Kitchen", friendly_name="Kitchen Light 2"
        )
        lock_config = EntityConfig(
            device_type="lock", suggested_area="Entry", friendly_name="Entry Lock"
        )

        entity_manager.register_entity("light1", light_config_1)
        entity_manager.register_entity("light2", light_config_2)
        entity_manager.register_entity("lock1", lock_config)

        result = entity_manager.get_light_entity_ids()

        assert len(result) == 2
        assert "light1" in result
        assert "light2" in result
        assert "lock1" not in result

    @pytest.mark.unit
    def test_preseed_light_states(self, entity_manager):
        """Test pre-seeding light states.

        Updated 2026-05-13: same shared-config dedup issue as
        ``test_get_light_entity_ids_with_lights`` -- using the same
        EntityConfig dict for both lights deduplicates them down to
        one. Build distinct configs.
        """
        # Setup light entities with distinct configs to avoid the
        # deduplication-by-physical_id path.
        light_config_1 = EntityConfig(
            device_type="light",
            suggested_area="Kitchen",
            friendly_name="Kitchen Light",
            capabilities=["brightness", "on_off"],
            groups=["kitchen", "lights"],
        )
        light_config_2 = EntityConfig(
            device_type="light",
            suggested_area="Kitchen",
            friendly_name="Kitchen Light 2",
            capabilities=["brightness", "on_off"],
            groups=["kitchen", "lights"],
        )

        entity_manager.register_entity("light1", light_config_1)
        entity_manager.register_entity("light2", light_config_2)

        # Mock decode function and device mapping
        mock_decode_func = MagicMock()
        device_mapping = {"test": "mapping"}

        # Pre-seed states
        entity_manager.preseed_light_states(mock_decode_func, device_mapping)

        # Verify entities have been updated
        light1 = entity_manager.get_entity("light1")
        light2 = entity_manager.get_entity("light2")

        assert light1 is not None
        assert light2 is not None
        assert light1.current_state.state == "off"
        assert light2.current_state.state == "off"
        assert light1.current_state.value == {"operating_status": "0"}
        assert light2.current_state.value == {"operating_status": "0"}

    @pytest.mark.unit
    def test_preseed_light_states_missing_entity(self, entity_manager, caplog):
        """Test pre-seeding with missing entity logs warning."""
        # Add entity ID to light_entity_ids without registering entity
        entity_manager.light_entity_ids.append("missing_light")

        mock_decode_func = MagicMock()
        device_mapping = {}

        entity_manager.preseed_light_states(mock_decode_func, device_mapping)

        assert "Pre-seeding: Entity not found: missing_light" in caplog.text


class TestApiResponse:
    """Test API response functionality."""

    @pytest.mark.unit
    def test_to_api_response_empty(self, entity_manager):
        """Test API response with no entities."""
        result = entity_manager.to_api_response()

        assert result == {}

    @pytest.mark.unit
    def test_to_api_response_with_entities(
        self, entity_manager, sample_light_config, sample_lock_config
    ):
        """Test API response with entities."""
        light_id = "kitchen_light"
        lock_id = "entry_lock"

        entity_manager.register_entity(light_id, sample_light_config)
        entity_manager.register_entity(lock_id, sample_lock_config)

        # Update one entity's state
        entity_manager.update_entity_state(light_id, {"state": "on", "brightness": 80})

        result = entity_manager.to_api_response()

        assert len(result) == 2
        assert light_id in result
        assert lock_id in result

        # Verify light entity data
        light_data = result[light_id]
        assert light_data["entity_id"] == light_id
        assert light_data["state"] == "on"
        assert light_data["suggested_area"] == "Kitchen"
        assert light_data["device_type"] == "light"
        assert light_data["friendly_name"] == "Kitchen Light"

        # Verify lock entity data
        lock_data = result[lock_id]
        assert lock_data["entity_id"] == lock_id
        assert lock_data["state"] == "unknown"  # Default state
        assert lock_data["suggested_area"] == "Entry"
        assert lock_data["device_type"] == "lock"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.unit
    def test_register_entity_returns_existing_when_physical_id_collides(
        self, entity_manager, sample_light_config
    ):
        """Test that re-registering the same physical_id returns the existing entity.

        Renamed and rewritten 2026-05-13. The previous test
        (``test_register_entity_overwrites_existing``) asserted that
        registering with the same entity_id overwrites the existing
        entity (``assert first_entity is not second_entity``). That
        contract is incompatible with production: ``register_entity``
        explicitly documents itself as deduplicating by physical_id
        and returning the existing instance when there is a collision
        (see ``backend/core/entity_manager.py:43`` docstring:
        '*The registered Entity instance (may be existing if
        physical_id matches)*' and the deduplication branch on lines
        70-91).

        We rewrite to test the contract production actually provides:
        a duplicate registration adds the new protocol as a secondary
        protocol on the existing entity rather than overwriting.
        """
        entity_id = "test_entity"

        first_entity = entity_manager.register_entity(
            entity_id, sample_light_config, protocol="rvc"
        )

        # Re-register the same entity_id with a different protocol.
        # Production should return the EXISTING entity (deduplication)
        # and add the new protocol as a secondary.
        second_entity = entity_manager.register_entity(
            entity_id, sample_light_config, protocol="j1939"
        )

        # Same instance -- production deduplicated by physical_id.
        assert first_entity is second_entity
        assert entity_manager.get_entity(entity_id) is first_entity

        # The secondary protocol should now be tracked.
        secondary_protocols = first_entity.config.get("secondary_protocols", [])
        assert "j1939" in secondary_protocols, (
            "Re-registering with a different protocol should add it as a secondary"
        )

    @pytest.mark.unit
    def test_filter_entities_with_none_values_in_config(self, entity_manager):
        """Test filtering entities when config has None values."""
        config = EntityConfig(device_type="light", friendly_name="Test Light")

        entity_manager.register_entity("test_light", config)

        # Filter by area None should match
        result = entity_manager.filter_entities(area=None)
        assert "test_light" in result

        # Filter by different area should not match
        result = entity_manager.filter_entities(area="Kitchen")
        assert "test_light" not in result

    @pytest.mark.unit
    def test_update_entity_state_partial_update(self, entity_manager, sample_light_config):
        """Test that partial state updates work correctly."""
        entity_id = "test_entity"
        entity_manager.register_entity(entity_id, sample_light_config)

        # First update
        entity_manager.update_entity_state(entity_id, {"state": "on", "brightness": 50})

        # Partial update - should preserve existing fields
        entity_manager.update_entity_state(entity_id, {"brightness": 75})

        entity = entity_manager.get_entity(entity_id)
        assert entity.current_state.state == "on"  # Should be preserved
        assert entity.current_state.brightness == 75  # Should be updated
