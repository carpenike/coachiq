"""Tests for the Victron protocol service (MQTT transport is faked)."""

from typing import Any

import pytest

from backend.core.config import VictronSettings
from backend.core.entity_manager import EntityManager
from backend.integrations.victron.topics import VictronUpdate
from backend.services.victron.victron_service import VictronService

PORTAL = "d41243d318d2"


class FakeEntityManagerService:
    def __init__(self) -> None:
        self._entity_manager = EntityManager()

    def get_entity_manager(self) -> EntityManager:
        return self._entity_manager


class FakeEventBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        self.published.append((event, data))


class FakeStateRepository:
    def __init__(self) -> None:
        self.saved: dict[str, dict[str, Any]] = {}

    async def save_entity_state(self, entity_id: str, state: dict[str, Any]) -> None:
        self.saved[entity_id] = state


class FakeMqttClient:
    """Stands in for VictronMqttClient in control-path tests."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str, str, Any]] = []
        self.connected = True
        self.portal_id = PORTAL

    async def write_value(self, service_type: str, instance: str, path: str, value: Any) -> None:
        self.writes.append((service_type, instance, path, value))


def make_service() -> tuple[
    VictronService, FakeEntityManagerService, FakeEventBroker, FakeStateRepository
]:
    settings = VictronSettings(enabled=True, host="cerbo.test")
    entity_manager_service = FakeEntityManagerService()
    event_broker = FakeEventBroker()
    state_repository = FakeStateRepository()
    service = VictronService(
        settings=settings,
        entity_manager_service=entity_manager_service,
        entity_state_repository=state_repository,
        event_broker=event_broker,
    )
    # Register catalog entities without opening an MQTT session.
    entity_manager = entity_manager_service.get_entity_manager()
    from backend.integrations.victron.catalog import DEFS_BY_SERVICE_TYPE

    for entity_def in DEFS_BY_SERVICE_TYPE.values():
        service._register_entity(entity_manager, entity_def, entity_def.key)
    return service, entity_manager_service, event_broker, state_repository


def vebus_update(path: str, value: Any, **kwargs: Any) -> VictronUpdate:
    return VictronUpdate(
        portal_id=PORTAL, service_type="vebus", instance="276", path=path, value=value, **kwargs
    )


class TestEntityRegistration:
    def test_catalog_entities_registered_with_victron_protocol(self):
        _, entity_manager_service, _, _ = make_service()
        entity_manager = entity_manager_service.get_entity_manager()
        for entity_id in (
            "victron_inverter_charger",
            "victron_battery",
            "victron_solar",
            "victron_power_system",
        ):
            entity = entity_manager.get_entity(entity_id)
            assert entity is not None, entity_id
            assert entity.get_state().protocol == "victron"

    def test_inverter_charger_exposes_control_capabilities(self):
        _, entity_manager_service, _, _ = make_service()
        entity = entity_manager_service.get_entity_manager().get_entity("victron_inverter_charger")
        assert entity is not None
        capabilities = entity.get_state().capabilities
        assert "set_mode" in capabilities
        assert "set_input_current_limit" in capabilities


class TestUpdateFlow:
    async def test_update_and_flush_reaches_entity_repo_and_event_broker(self):
        service, entity_manager_service, event_broker, state_repository = make_service()

        await service._handle_update(vebus_update("Ac/ActiveIn/L1/P", 372))
        await service._handle_update(vebus_update("State", 3))
        await service._flush_entity("victron_inverter_charger")

        entity = entity_manager_service.get_entity_manager().get_entity("victron_inverter_charger")
        assert entity is not None
        state = entity.get_state()
        assert state.value["ac_in_l1_power"] == 372
        assert state.value["vebus_state"] == 3
        assert state.state == "bulk"
        # The v2 entities API exposes only the raw dict, so the derived human
        # label must ride along in both signal dicts as `status`.
        assert state.value["status"] == "bulk"
        assert state.raw["status"] == "bulk"

        assert "victron_inverter_charger" in state_repository.saved
        assert len(event_broker.published) == 1
        event, payload = event_broker.published[0]
        assert event == "entity_update"
        assert payload["entity_id"] == "victron_inverter_charger"
        assert payload["entity_data"]["value"]["ac_in_l1_power"] == 372

    async def test_flush_merges_over_previous_values(self):
        service, entity_manager_service, _, _ = make_service()

        await service._handle_update(vebus_update("Ac/ActiveIn/L1/P", 372))
        await service._flush_entity("victron_inverter_charger")
        await service._handle_update(vebus_update("Ac/ActiveIn/L2/P", 1715))
        await service._flush_entity("victron_inverter_charger")

        entity = entity_manager_service.get_entity_manager().get_entity("victron_inverter_charger")
        assert entity is not None
        # Earlier signal survives a flush that only carried the L2 update.
        assert entity.get_state().value["ac_in_l1_power"] == 372
        assert entity.get_state().value["ac_in_l2_power"] == 1715

    async def test_unknown_paths_and_services_ignored(self):
        service, _, _, _ = make_service()
        await service._handle_update(vebus_update("Devices/0/Version", 1234))
        await service._handle_update(
            VictronUpdate(
                portal_id=PORTAL,
                service_type="ble",
                instance="0",
                path="State",
                value=1,
            )
        )
        assert service._pending == {}

    async def test_second_instance_gets_suffixed_entity(self):
        service, entity_manager_service, _, _ = make_service()

        def solar_update(instance: str) -> VictronUpdate:
            return VictronUpdate(
                portal_id=PORTAL,
                service_type="solarcharger",
                instance=instance,
                path="Yield/Power",
                value=100.0,
            )

        await service._handle_update(solar_update("279"))
        await service._handle_update(solar_update("280"))

        assert service._instance_bindings[("solarcharger", "279")] == "victron_solar"
        assert service._instance_bindings[("solarcharger", "280")] == "victron_solar_280"
        assert (
            entity_manager_service.get_entity_manager().get_entity("victron_solar_280") is not None
        )

    async def test_temperature_sensor_derives_fahrenheit_and_custom_name(self):
        service, entity_manager_service, _, _ = make_service()
        for path, value in (
            ("Temperature", 30.0),
            ("Humidity", 81.65),
            ("CustomName", "Outside"),
        ):
            await service._handle_update(
                VictronUpdate(
                    portal_id=PORTAL,
                    service_type="temperature",
                    instance="21",
                    path=path,
                    value=value,
                )
            )
        await service._flush_entity("victron_temperature")

        entity = entity_manager_service.get_entity_manager().get_entity("victron_temperature")
        assert entity is not None
        state = entity.get_state()
        # Climate page reads current_temp_f; RuuviTag custom name becomes the label.
        assert state.value["current_temp_f"] == 86.0
        assert state.value["humidity"] == 81.65
        assert state.friendly_name == "Outside"
        assert state.state == "ok"

    async def test_battery_state_derivation(self):
        service, entity_manager_service, _, _ = make_service()
        await service._handle_update(
            VictronUpdate(
                portal_id=PORTAL,
                service_type="battery",
                instance="512",
                path="Dc/0/Current",
                value=-12.5,
            )
        )
        await service._flush_entity("victron_battery")
        entity = entity_manager_service.get_entity_manager().get_entity("victron_battery")
        assert entity is not None
        assert entity.get_state().state == "discharging"


class TestControlPath:
    async def test_set_inverter_mode_by_name_and_code(self):
        service, _, _, _ = make_service()
        service._client = FakeMqttClient()
        await service._handle_update(vebus_update("State", 3))

        result = await service.set_inverter_mode("charger_only")
        assert result == {"mode": 1, "mode_name": "charger_only"}
        result = await service.set_inverter_mode(3)
        assert result == {"mode": 3, "mode_name": "on"}
        assert service._client.writes == [
            ("vebus", "276", "Mode", 1),
            ("vebus", "276", "Mode", 3),
        ]

    async def test_set_inverter_mode_rejects_invalid(self):
        service, _, _, _ = make_service()
        service._client = FakeMqttClient()
        await service._handle_update(vebus_update("State", 3))
        with pytest.raises(ValueError, match="Invalid inverter mode"):
            await service.set_inverter_mode("warp_speed")
        with pytest.raises(ValueError, match="Invalid inverter mode"):
            await service.set_inverter_mode(7)
        assert service._client.writes == []

    async def test_set_inverter_mode_without_discovered_vebus(self):
        service, _, _, _ = make_service()
        service._client = FakeMqttClient()
        with pytest.raises(RuntimeError, match="No VE.Bus device"):
            await service.set_inverter_mode("on")

    async def test_current_limit_validated_against_broker_range(self):
        service, _, _, _ = make_service()
        service._client = FakeMqttClient()
        await service._handle_update(
            vebus_update("Ac/ActiveIn/CurrentLimit", 45.0, minimum=0.0, maximum=50.0)
        )

        result = await service.set_input_current_limit(30.0)
        assert result == {"input_current_limit": 30.0}
        assert service._client.writes == [("vebus", "276", "Ac/ActiveIn/CurrentLimit", 30.0)]
        with pytest.raises(ValueError, match="outside adjustable range"):
            await service.set_input_current_limit(80.0)

    async def test_current_limit_uses_default_range_before_discovery(self):
        service, _, _, _ = make_service()
        service._client = FakeMqttClient()
        await service._handle_update(vebus_update("State", 3))
        with pytest.raises(ValueError, match="outside adjustable range"):
            await service.set_input_current_limit(150.0)


class TestHealth:
    def test_health_reports_bindings_and_connection(self):
        service, _, _, _ = make_service()
        service._client = FakeMqttClient()
        service._running = True
        health = service.get_health_status()
        assert health["healthy"] is True
        assert health["connected"] is True
        assert health["portal_id"] == PORTAL
