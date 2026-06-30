"""Tests for real v2 diagnostics data paths."""

from collections.abc import Generator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.api.domains import diagnostics as diagnostics_domain
from backend.core.config import Settings
from backend.integrations.diagnostics.handler import DiagnosticHandler
from backend.integrations.diagnostics.models import DTCSeverity, ProtocolType, SystemType
from backend.integrations.rvc import load_config_data_v2
from backend.main import app
from backend.services.can.can_bus_service import CANBusService

pytestmark = [pytest.mark.api, pytest.mark.can]

DM_RV_CAN_ID = 0x18FECA9A
DM_RV_CLEAR_HEARTBEAT = bytes.fromhex("0584FFFFFFFFFFFF")
DM_RV_ACTIVE_DTC = bytes.fromhex("1000D2042801FFFF")
DM_RV_ACTIVE_SPN = 1234
DM_RV_ACTIVE_FMI = 5
DM_RV_ACTIVE_CODE = (DM_RV_ACTIVE_SPN << 5) | DM_RV_ACTIVE_FMI


class FakeCANFacade:
    """Minimal CAN facade test double for diagnostics health."""

    def __init__(self, status: dict[str, object]):
        """Initialize with a static health status payload."""
        self._status = status

    def get_health_status(self) -> dict[str, object]:
        """Return CAN health status."""
        return self._status


@pytest.fixture
def diagnostic_handler() -> DiagnosticHandler:
    """Create a diagnostics handler for endpoint and CAN ingestion tests."""
    settings = Mock(spec=Settings)
    return DiagnosticHandler(settings)


@pytest.fixture
def can_bus_service(diagnostic_handler: DiagnosticHandler) -> CANBusService:
    """Create CANBusService with the real RV-C decoder map and diagnostics handler."""
    service = CANBusService(
        can_tracking_repository=Mock(),
        system_state_repository=Mock(),
        diagnostic_handler=diagnostic_handler,
    )
    rvc_config = load_config_data_v2()
    service.decoder_map = rvc_config.dgn_dict
    service.decoder_pgn_map = service._build_decoder_pgn_map(rvc_config.dgn_dict)
    return service


@pytest.fixture
def diagnostics_client(diagnostic_handler: DiagnosticHandler) -> Generator[TestClient, None, None]:
    """TestClient with diagnostics dependencies overridden."""
    app.dependency_overrides[diagnostics_domain.get_diagnostics_handler] = (  # type: ignore[attr-defined]
        lambda: diagnostic_handler
    )
    app.dependency_overrides[diagnostics_domain.get_optional_can_facade] = (  # type: ignore[attr-defined]
        lambda: FakeCANFacade(
            {"healthy": True, "guardrail_status": "safe", "command_halt_active": False}
        )
    )

    with TestClient(app=app) as client:
        yield client

    app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_dm_rv_clear_heartbeat_does_not_create_dtc(
    can_bus_service: CANBusService, diagnostic_handler: DiagnosticHandler
) -> None:
    """RECON-003 clean DM_RV sentinel is a clear heartbeat, not a DTC."""
    await can_bus_service._process_message(
        {"arbitration_id": DM_RV_CAN_ID, "data": DM_RV_CLEAR_HEARTBEAT, "interface": "can0"}
    )

    assert diagnostic_handler.get_active_dtcs() == []


@pytest.mark.asyncio
async def test_mirrored_dm_rv_frames_dedupe_by_source_spn_fmi(
    can_bus_service: CANBusService, diagnostic_handler: DiagnosticHandler
) -> None:
    """Mirrored can0/can1 DM_RV frames update one DTC keyed by source, SPN, and FMI."""
    await can_bus_service._process_message(
        {"arbitration_id": DM_RV_CAN_ID, "data": DM_RV_ACTIVE_DTC, "interface": "can0"}
    )
    await can_bus_service._process_message(
        {"arbitration_id": DM_RV_CAN_ID, "data": DM_RV_ACTIVE_DTC, "interface": "can1"}
    )

    active_dtcs = diagnostic_handler.get_active_dtcs()
    assert len(active_dtcs) == 1
    assert active_dtcs[0].code == DM_RV_ACTIVE_CODE
    assert active_dtcs[0].source_address == 0x9A
    assert active_dtcs[0].protocol == ProtocolType.J1939
    assert active_dtcs[0].metadata["spn"] == DM_RV_ACTIVE_SPN
    assert active_dtcs[0].metadata["fmi"] == DM_RV_ACTIVE_FMI
    assert active_dtcs[0].occurrence_count == 2


def test_v2_faults_report_handler_dtcs(
    diagnostics_client: TestClient, diagnostic_handler: DiagnosticHandler
) -> None:
    """The v2 faults endpoint reports DTCs from the registered diagnostics handler."""
    diagnostic_handler.process_dtc(
        code=DM_RV_ACTIVE_CODE,
        protocol=ProtocolType.J1939,
        system_type=SystemType.CHASSIS,
        source_address=0x9A,
        pgn=0xFECA,
        severity=DTCSeverity.CRITICAL,
        metadata={"spn": DM_RV_ACTIVE_SPN, "fmi": DM_RV_ACTIVE_FMI},
    )

    response = diagnostics_client.get("/api/v1/diagnostics/faults")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_faults"] == 1
    assert payload["total_faults"] == 1
    assert payload["critical_faults"] == 1
    assert payload["by_system"] == {"chassis": 1}
    assert payload["by_protocol"] == {"j1939": 1}


def test_v2_system_status_is_computed_not_hardcoded(
    diagnostics_client: TestClient, diagnostic_handler: DiagnosticHandler
) -> None:
    """The v2 system-status endpoint computes health from CAN and diagnostics state."""
    diagnostic_handler.process_dtc(
        code=DM_RV_ACTIVE_CODE,
        protocol=ProtocolType.J1939,
        system_type=SystemType.CHASSIS,
        source_address=0x9A,
        severity=DTCSeverity.HIGH,
    )

    response = diagnostics_client.get("/api/v1/diagnostics/system-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["health_score"] != 85.0
    assert "can_bus" in payload["active_systems"]
    assert "diagnostics" in payload["active_systems"]
    assert "diagnostics" in payload["degraded_systems"]
