"""Tests for the Victron entity catalog and state derivation."""

from backend.integrations.victron.catalog import (
    DEFS_BY_SERVICE_TYPE,
    VICTRON_ENTITY_DEFS,
    _battery_state,
    _solar_state,
    _system_state,
    _vebus_state,
)


class TestCatalogIntegrity:
    def test_entity_keys_unique(self):
        keys = [entity_def.key for entity_def in VICTRON_ENTITY_DEFS]
        assert len(keys) == len(set(keys))

    def test_service_types_unique(self):
        service_types = [entity_def.service_type for entity_def in VICTRON_ENTITY_DEFS]
        assert len(service_types) == len(set(service_types))

    def test_expected_services_covered(self):
        assert set(DEFS_BY_SERVICE_TYPE) == {"vebus", "battery", "solarcharger", "system"}

    def test_signal_names_unique_within_entity(self):
        for entity_def in VICTRON_ENTITY_DEFS:
            signals = list(entity_def.paths.values())
            assert len(signals) == len(set(signals)), entity_def.key


class TestStateDerivation:
    def test_vebus_states(self):
        assert _vebus_state({"vebus_state": 3}) == "bulk"
        assert _vebus_state({"vebus_state": 8}) == "passthru"
        assert _vebus_state({"vebus_state": 9}) == "inverting"
        assert _vebus_state({"vebus_state": 252}) == "external_control"
        assert _vebus_state({"vebus_state": 99}) == "state_99"
        assert _vebus_state({}) == "unknown"
        assert _vebus_state({"vebus_state": None}) == "unknown"

    def test_battery_state_from_current_sign(self):
        assert _battery_state({"current": 12.0}) == "charging"
        assert _battery_state({"current": -8.0}) == "discharging"
        assert _battery_state({"current": 0.0}) == "idle"
        assert _battery_state({"current": None}) == "unknown"
        assert _battery_state({}) == "unknown"

    def test_solar_state(self):
        assert _solar_state({"charge_state_code": 252}) == "external_control"
        assert _solar_state({"charge_state_code": 0}) == "off"

    def test_system_state_extends_vebus_enum(self):
        assert _system_state({"system_state": 256}) == "discharging"
        assert _system_state({"system_state": 9}) == "inverting"
