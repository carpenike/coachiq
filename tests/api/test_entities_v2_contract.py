"""Focused contract tests for the Domain API entity responses."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.domains import entities as entities_domain
from backend.core.dependencies import get_entity_service
from backend.schemas.entity_schemas import EntitySchemaV2

pytestmark = pytest.mark.api


class FakeEntityService:
    """Minimal entity service returning stable test payloads."""

    def __init__(self, entities: dict[str, dict[str, Any]]) -> None:
        self._entities = entities

    async def list_entities(self) -> dict[str, dict[str, Any]]:
        """Return configured entity payloads."""
        return self._entities


@pytest.fixture
def entity_payloads() -> dict[str, dict[str, Any]]:
    """Return controllable and read-only payloads with distinct timestamp semantics."""
    return {
        "ceiling_light": {
            "friendly_name": "Ceiling Light",
            "device_type": "light",
            "protocol": "rvc",
            "raw": {"operating_status": 120},
            "suggested_area": "interior.lounge",
            "available": False,
            "capabilities": ["on_off", "brightness", "telemetry_only"],
            "command_dgn": "1FEDB",
            "last_updated": "2026-07-11T12:00:00Z",
            "last_seen_at": "2026-07-11T11:59:58Z",
            "state_changed_at": "2026-07-11T11:59:30Z",
        },
        "fresh_water": {
            "friendly_name": "Fresh Water",
            "device_type": "tank",
            "protocol": "rvc",
            "raw": {"level": 72},
            "area": "utilities",
            "capabilities": ["level", "on_off"],
            "read_only": True,
            "last_updated": "2026-07-11T12:01:00Z",
        },
        "status_only_light": {
            "friendly_name": "Status-only Light",
            "device_type": "light",
            "protocol": "rvc",
            "raw": {"operating_status": 0},
            "capabilities": ["on_off", "brightness"],
            "last_updated": "2026-07-11T12:02:00Z",
        },
    }


@pytest.fixture
def entity_client(
    entity_payloads: dict[str, dict[str, Any]],
) -> Generator[TestClient, None, None]:
    """Mount the entity domain router with a controlled service payload."""
    app = FastAPI()
    app.include_router(entities_domain.create_entities_router(), prefix="/api/v1/entities")
    app.dependency_overrides[get_entity_service] = lambda: FakeEntityService(entity_payloads)

    with TestClient(app) as client:
        yield client


def test_router_uses_canonical_entity_schema() -> None:
    """The active router exports the single canonical EntitySchemaV2 class."""
    assert entities_domain.EntitySchemaV2 is EntitySchemaV2


def test_collection_serializes_configured_capabilities_and_commands(
    entity_client: TestClient,
) -> None:
    """Collection responses expose only commands implemented for configured capabilities."""
    response = entity_client.get("/api/v1/entities")

    assert response.status_code == 200
    payload = response.json()
    entities = {entity["entity_id"]: entity for entity in payload["entities"]}
    light = entities["ceiling_light"]
    tank = entities["fresh_water"]
    status_only_light = entities["status_only_light"]

    assert light["area"] == "interior.lounge"
    assert light["available"] is False
    assert light["capabilities"] == ["on_off", "brightness", "telemetry_only"]
    assert light["supported_commands"] == [
        "set",
        "toggle",
        "brightness_up",
        "brightness_down",
    ]
    assert tank["supported_commands"] == []
    assert tank["available"] is None
    assert status_only_light["capabilities"] == ["on_off", "brightness"]
    assert status_only_light["supported_commands"] == []


def test_detail_and_collection_share_timestamp_semantics(entity_client: TestClient) -> None:
    """Detail and collection preserve explicit timestamps without inventing change time."""
    collection = entity_client.get("/api/v1/entities").json()["entities"]
    collection_by_id = {entity["entity_id"]: entity for entity in collection}

    light = entity_client.get("/api/v1/entities/ceiling_light").json()
    tank = entity_client.get("/api/v1/entities/fresh_water").json()

    assert light == collection_by_id["ceiling_light"]
    assert light["last_seen_at"] == "2026-07-11T11:59:58Z"
    assert light["state_changed_at"] == "2026-07-11T11:59:30Z"
    assert tank == collection_by_id["fresh_water"]
    assert tank["last_seen_at"] == tank["last_updated"]
    assert tank["data_received_at"] == tank["last_updated"]
    assert tank["state_changed_at"] is None
