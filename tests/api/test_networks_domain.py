"""Tests for the v2 networks domain API."""

from collections.abc import Generator
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.domains.networks import create_networks_router
from backend.api.routers.can import verify_can_interface_enabled
from backend.core.dependencies import get_can_network_telemetry_service, get_verified_can_facade

pytestmark = pytest.mark.api


class FakeCANFacade:
    """Minimal facade test double for the networks domain router."""

    def __init__(self) -> None:
        self.bus_statistics_called = False
        self.interface_details_called = False

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

    async def get_interface_details(self) -> dict[str, dict[str, Any]]:
        """Return real per-interface telemetry shaped like CANInterfaceStats dumps."""
        self.interface_details_called = True
        return {
            "can0": {
                "state": "ERROR-ACTIVE",
                "bitrate": 250000,
                "rx_packets": 100,
                "tx_packets": 25,
                "rx_bytes": 800,
                "tx_bytes": 200,
                "rx_errors": 1,
                "tx_errors": 0,
                "rx_dropped": 2,
                "tx_dropped": 3,
                "bus_errors": 4,
                "restarts": 0,
                "arbitration_lost": 5,
                "error_warning": 6,
                "error_passive": 7,
                "bus_off": 8,
            },
            "can1": {
                "state": "ERROR-WARNING",
                "bitrate": 250000,
                "rx_packets": 50,
                "tx_packets": 10,
                "rx_bytes": 400,
                "tx_bytes": 80,
                "rx_errors": 2,
                "tx_errors": 1,
                "rx_dropped": 0,
                "tx_dropped": 1,
                "bus_errors": None,
                "restarts": None,
                "arbitration_lost": None,
                "error_warning": None,
                "error_passive": None,
                "bus_off": None,
            },
        }

    async def get_bus_statistics(self) -> dict[str, Any]:
        """Return bus statistics now that HOF-002 implements telemetry."""
        self.bus_statistics_called = True
        return {
            "interfaces": await self.get_interface_details(),
            "queue": await self.get_queue_status(),
            "analyzer": {},
            "performance": {"uptime_seconds": 123.0},
            "summary": {
                "total_messages": 185,
                "total_errors": 4,
                "message_rate": 0.0,
                "error_rate_percent": 2.1621621621621623,
                "uptime": 123.0,
            },
        }


class FakeTelemetryService:
    """Minimal rolling telemetry test double for the networks router."""

    def get_rolling_telemetry(self) -> dict[str, dict[str, Any]]:
        """Return nullable rolling telemetry keyed by physical interface."""
        return {
            "can0": {
                "message_rate": 83.0,
                "bus_load_percent": 10.0,
                "last_activity": "2026-06-26T12:00:02+00:00",
            },
            "can1": {
                "message_rate": None,
                "bus_load_percent": None,
                "last_activity": None,
            },
        }


@pytest.fixture
def networks_client() -> Generator[tuple[TestClient, FakeCANFacade], None, None]:
    """TestClient with the networks router wired to a fake CAN facade."""
    app = FastAPI()
    fake_can_facade = FakeCANFacade()
    fake_telemetry_service = FakeTelemetryService()

    app.include_router(create_networks_router(), prefix="/api/v1/networks")
    app.dependency_overrides[get_verified_can_facade] = lambda: fake_can_facade  # type: ignore[attr-defined]
    app.dependency_overrides[get_can_network_telemetry_service] = lambda: fake_telemetry_service  # type: ignore[attr-defined]
    app.dependency_overrides[verify_can_interface_enabled] = lambda: None  # type: ignore[attr-defined]

    with TestClient(app=app) as client:  # type: ignore[arg-type]
        yield client, fake_can_facade


def test_interfaces_return_configured_mappings(
    networks_client: tuple[TestClient, FakeCANFacade],
) -> None:
    """Interfaces expose configured mappings with real telemetry when available."""
    client, fake_can_facade = networks_client

    response = client.get("/api/v1/networks/interfaces")

    assert response.status_code == 200
    payload: list[dict[str, Any]] = response.json()
    assert payload[0]["logical_name"] == "chassis"
    assert payload[0]["physical_interface"] == "can1"
    assert payload[0]["state"] == "ERROR-WARNING"
    assert payload[0]["rx_packets"] == 50
    assert payload[0]["tx_dropped"] == 1
    assert payload[0]["bus_errors"] is None
    assert payload[0]["message_rate"] is None
    assert payload[0]["bus_load_percent"] is None
    assert payload[0]["last_activity"] is None
    assert payload[1]["logical_name"] == "house"
    assert payload[1]["physical_interface"] == "can0"
    assert payload[1]["state"] == "ERROR-ACTIVE"
    assert payload[1]["rx_packets"] == 100
    assert payload[1]["tx_packets"] == 25
    assert payload[1]["rx_dropped"] == 2
    assert payload[1]["tx_dropped"] == 3
    assert payload[1]["bus_errors"] == 4
    assert payload[1]["arbitration_lost"] == 5
    assert payload[1]["bus_off"] == 8
    assert payload[1]["message_rate"] == 83.0
    assert payload[1]["bus_load_percent"] == 10.0
    assert payload[1]["last_activity"] == "2026-06-26T12:00:02+00:00"
    assert fake_can_facade.interface_details_called is True
    assert fake_can_facade.bus_statistics_called is False


def test_status_uses_truthful_sources(networks_client: tuple[TestClient, FakeCANFacade]) -> None:
    """Status combines mappings, service health, queue status, and telemetry."""
    client, fake_can_facade = networks_client

    response = client.get("/api/v1/networks/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_interfaces"] == 2
    assert payload["interfaces"][0]["logical_name"] == "chassis"
    assert payload["interfaces"][0]["rx_packets"] == 50
    assert payload["interfaces"][0]["message_rate"] is None
    assert payload["interfaces"][1]["logical_name"] == "house"
    assert payload["interfaces"][1]["rx_packets"] == 100
    assert payload["interfaces"][1]["message_rate"] == 83.0
    assert payload["can_service_health"]["service"] == "CANBusService"
    assert payload["can_service_health"]["healthy"] is True
    assert payload["queue_status"]["status"] == "operational"
    assert "total_messages" not in payload
    assert "message_count" not in payload["interfaces"][0]
    assert fake_can_facade.interface_details_called is True
    assert fake_can_facade.bus_statistics_called is False


def test_statistics_returns_queue_status_and_bus_statistics(
    networks_client: tuple[TestClient, FakeCANFacade],
) -> None:
    """Statistics reaches the real bus-statistics path in HOF-002."""
    client, fake_can_facade = networks_client

    response = client.get("/api/v1/networks/statistics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_status"]["queue_length"] == 0
    assert payload["queue_status"]["queue_capacity"] == 1000
    assert payload["bus_statistics"]["summary"]["total_messages"] == 185
    assert payload["bus_statistics"]["summary"]["total_errors"] == 4
    assert fake_can_facade.bus_statistics_called is True


def test_schemas_include_statistics(networks_client: tuple[TestClient, FakeCANFacade]) -> None:
    """Schemas lists the new statistics endpoint."""
    client, _fake_can_facade = networks_client

    response = client.get("/api/v1/networks/schemas")

    assert response.status_code == 200
    assert "/statistics" in response.json()["available_endpoints"]


def test_health_timestamp_is_current_iso_value(
    networks_client: tuple[TestClient, FakeCANFacade],
) -> None:
    """Health uses a real timestamp instead of the old frozen literal."""
    client, _fake_can_facade = networks_client

    response = client.get("/api/v1/networks/health")

    assert response.status_code == 200
    timestamp = response.json()["timestamp"]
    assert timestamp != "2025-01-11T00:00:00Z"
    datetime.fromisoformat(timestamp)
