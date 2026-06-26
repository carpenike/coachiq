"""Tests for the v2 networks domain API."""

from collections.abc import Generator
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.domains.networks import create_networks_router
from backend.api.routers.can import verify_can_interface_enabled
from backend.core.dependencies import get_verified_can_facade

pytestmark = pytest.mark.api


class FakeCANFacade:
    """Minimal facade test double for the networks domain router."""

    def __init__(self) -> None:
        self.bus_statistics_called = False

    async def get_interface_mappings(self) -> dict[str, str]:
        """Return configured logical-to-physical interface mappings."""
        return {"house": "can0", "chassis": "can1"}

    async def get_interface_status(self) -> dict[str, Any]:
        """Return service-level CAN health, not per-interface telemetry."""
        return {
            "service": "CANBusService",
            "healthy": True,
            "running": True,
            "interfaces": ["can0", "can1"],
        }

    async def get_queue_status(self) -> dict[str, Any]:
        """Return facade-reported queue status."""
        return {
            "queue_length": 0,
            "queue_capacity": 1000,
            "messages_processed": 0,
            "messages_dropped": 0,
            "queue_full_events": 0,
            "status": "operational",
        }

    async def get_bus_statistics(self) -> dict[str, Any]:
        """Fail if the networks router reaches the deferred telemetry path."""
        self.bus_statistics_called = True
        raise AssertionError("networks v2 must not call get_bus_statistics in HOF-001")


@pytest.fixture
def networks_client() -> Generator[tuple[TestClient, FakeCANFacade], None, None]:
    """TestClient with the networks router wired to a fake CAN facade."""
    app = FastAPI()
    fake_can_facade = FakeCANFacade()

    app.include_router(create_networks_router(), prefix="/api/v2/networks")
    app.dependency_overrides[get_verified_can_facade] = lambda: fake_can_facade  # type: ignore[attr-defined]
    app.dependency_overrides[verify_can_interface_enabled] = lambda: None  # type: ignore[attr-defined]

    with TestClient(app=app) as client:  # type: ignore[arg-type]
        yield client, fake_can_facade


def test_interfaces_return_configured_mappings(
    networks_client: tuple[TestClient, FakeCANFacade],
) -> None:
    """Interfaces expose only configured logical-to-physical mappings."""
    client, fake_can_facade = networks_client

    response = client.get("/api/v2/networks/interfaces")

    assert response.status_code == 200
    assert response.json() == [
        {"logical_name": "chassis", "physical_interface": "can1"},
        {"logical_name": "house", "physical_interface": "can0"},
    ]
    assert fake_can_facade.bus_statistics_called is False


def test_status_uses_truthful_sources(networks_client: tuple[TestClient, FakeCANFacade]) -> None:
    """Status combines mappings, service health, and queue status only."""
    client, fake_can_facade = networks_client

    response = client.get("/api/v2/networks/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_interfaces"] == 2
    assert payload["interfaces"] == [
        {"logical_name": "chassis", "physical_interface": "can1"},
        {"logical_name": "house", "physical_interface": "can0"},
    ]
    assert payload["can_service_health"]["service"] == "CANBusService"
    assert payload["can_service_health"]["healthy"] is True
    assert payload["queue_status"]["status"] == "operational"
    assert "total_messages" not in payload
    assert "message_count" not in payload["interfaces"][0]
    assert fake_can_facade.bus_statistics_called is False


def test_statistics_returns_queue_status_only(
    networks_client: tuple[TestClient, FakeCANFacade],
) -> None:
    """Statistics returns only facade-reported queue status."""
    client, fake_can_facade = networks_client

    response = client.get("/api/v2/networks/statistics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_length"] == 0
    assert payload["queue_capacity"] == 1000
    assert "summary" not in payload
    assert fake_can_facade.bus_statistics_called is False


def test_schemas_include_statistics(networks_client: tuple[TestClient, FakeCANFacade]) -> None:
    """Schemas lists the new statistics endpoint."""
    client, _fake_can_facade = networks_client

    response = client.get("/api/v2/networks/schemas")

    assert response.status_code == 200
    assert "/statistics" in response.json()["available_endpoints"]


def test_health_timestamp_is_current_iso_value(
    networks_client: tuple[TestClient, FakeCANFacade],
) -> None:
    """Health uses a real timestamp instead of the old frozen literal."""
    client, _fake_can_facade = networks_client

    response = client.get("/api/v2/networks/health")

    assert response.status_code == 200
    timestamp = response.json()["timestamp"]
    assert timestamp != "2025-01-11T00:00:00Z"
    datetime.fromisoformat(timestamp)
