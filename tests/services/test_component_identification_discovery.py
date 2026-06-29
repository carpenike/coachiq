"""Tests for J1939 Component Identification discovery ingestion."""

from collections.abc import Iterable
from unittest.mock import Mock

import pytest

from backend.integrations.can.protocol_router import CANFrame, ProtocolRouter
from backend.integrations.rvc import BAMHandler
from backend.integrations.rvc.decoder_core import decode_component_id
from backend.services.can.can_bus_service import CANBusService
from backend.services.discovery.device_discovery_service import DeviceDiscoveryService

pytestmark = [pytest.mark.can, pytest.mark.rvc]

COMPONENT_ID_PGN = 0xFEEB
TP_CM_CAN_ID = 0x18ECFF9E
TP_DT_CAN_ID = 0x18EBFF9E
AQUA_HOT_PAYLOAD = b"Aqua-Hot*Reporter 2v1a*A400D-200710*23*"
CAPTURED_COMPONENT_IDS = [
    (
        b"Southwire Company LLC*ATS-40450r5.08*756490*af0e52bc*",
        "Southwire Company LLC",
        "ATS-40450r5.08",
        "756490",
        "af0e52bc",
    ),
    (
        b"Spyder Controls*DC Dimmer Cntlr 6v8c*0000000*01*",
        "Spyder Controls",
        "DC Dimmer Cntlr 6v8c",
        "0000000",
        "01",
    ),
    (
        b"Spyder Controls*DC Dimmer Cntlr 6v8*0000000*46*",
        "Spyder Controls",
        "DC Dimmer Cntlr 6v8",
        "0000000",
        "46",
    ),
    (
        b"Spyder Controls*Switch Panel 6v8*0000000*11*",
        "Spyder Controls",
        "Switch Panel 6v8",
        "0000000",
        "11",
    ),
    (
        b"Spyder Controls*Switch Panel 6v8*0000000*06*",
        "Spyder Controls",
        "Switch Panel 6v8",
        "0000000",
        "06",
    ),
    (
        b"Spyder Controls*C Logic Controller 6v11e1*0000000*21*",
        "Spyder Controls",
        "C Logic Controller 6v11e1",
        "0000000",
        "21",
    ),
    (
        b"Spyder Controls*7in Color LCD 1v6g*0000000*20*",
        "Spyder Controls",
        "7in Color LCD 1v6g",
        "0000000",
        "20",
    ),
    (
        b"Spyder Controls*C Logic Controller 6v11e1*0000000*21*",
        "Spyder Controls",
        "C Logic Controller 6v11e1",
        "0000000",
        "21",
    ),
    (
        b"Spyder Controls*Monitor Panel 6v11*0000000*20*",
        "Spyder Controls",
        "Monitor Panel 6v11",
        "0000000",
        "20",
    ),
    (
        b"Spyder Controls*C Logic Controller 6v11e1*0000000*21*",
        "Spyder Controls",
        "C Logic Controller 6v11e1",
        "0000000",
        "21",
    ),
    (
        b"Spyder Controls*Switch Panel 6v8*0000000*02*",
        "Spyder Controls",
        "Switch Panel 6v8",
        "0000000",
        "02",
    ),
    (
        b"Spyder Controls*C Logic Controller 6v11e1*0000000*01*",
        "Spyder Controls",
        "C Logic Controller 6v11e1",
        "0000000",
        "01",
    ),
    (
        b"Spyder Controls*Switch Panel 6v8*0000000*01*",
        "Spyder Controls",
        "Switch Panel 6v8",
        "0000000",
        "01",
    ),
    (AQUA_HOT_PAYLOAD, "Aqua-Hot", "Reporter 2v1a", "A400D-200710", "23"),
    (b"VALIDMFG*VEC06A020-16 *04654*0*\xff\xff\xff\xff", "VALIDMFG", "VEC06A020-16", "04654", "0"),
]


class FakeRegistry:
    """Minimal ServiceRegistry test double for CANBusService runtime lookup."""

    def __init__(self, discovery_service: DeviceDiscoveryService):
        """Initialize with the device discovery service to return."""
        self.discovery_service = discovery_service

    def has_service(self, service_name: str) -> bool:
        """Return whether the requested service is available."""
        return service_name == "device_discovery_service"

    def get_service(self, service_name: str) -> DeviceDiscoveryService:
        """Return the requested service."""
        if service_name != "device_discovery_service":
            msg = f"unexpected service {service_name}"
            raise RuntimeError(msg)
        return self.discovery_service


def make_bam_frames(payload: bytes, source_address: int = 0x9E) -> Iterable[tuple[int, bytes]]:
    """Build an addressed BAM Component-ID transfer."""
    packet_count = (len(payload) + 6) // 7
    control = bytes(
        [
            0x20,
            len(payload) & 0xFF,
            (len(payload) >> 8) & 0xFF,
            packet_count,
            0xFF,
            COMPONENT_ID_PGN & 0xFF,
            (COMPONENT_ID_PGN >> 8) & 0xFF,
            (COMPONENT_ID_PGN >> 16) & 0xFF,
        ]
    )
    yield (0x18ECFF00 | source_address, control)

    for packet_number in range(1, packet_count + 1):
        start = (packet_number - 1) * 7
        chunk = payload[start : start + 7].ljust(7, b"\xff")
        yield (0x18EBFF00 | source_address, bytes([packet_number]) + chunk)


def test_decode_component_id_uses_captured_field_shape() -> None:
    """Captured 0xFEEB payloads decode as Make/Model/Serial/Unit fields."""
    for payload, make, model, serial, unit in CAPTURED_COMPONENT_IDS:
        decoded = decode_component_id(payload)

        assert decoded == {
            "make": make,
            "model": model.strip(),
            "serial": serial,
            "unit": unit,
        }


@pytest.mark.asyncio
async def test_can_bus_reassembles_component_id_and_dedupes_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrored 0xFEEB BAM completions update one discovered device."""
    discovery_service = DeviceDiscoveryService(config=Mock())
    service = CANBusService(can_tracking_repository=Mock(), system_state_repository=Mock())
    service.bam_handler = BAMHandler()

    from backend.core import dependencies

    monkeypatch.setattr(
        dependencies, "get_service_registry", lambda: FakeRegistry(discovery_service)
    )

    for interface in ("can0", "can1"):
        for arbitration_id, data in make_bam_frames(AQUA_HOT_PAYLOAD):
            await service._process_message(
                {"arbitration_id": arbitration_id, "data": data, "interface": interface}
            )

    device = discovery_service.topology.devices[0x9E]
    assert len(discovery_service.topology.devices) == 1
    assert device.manufacturer == "Aqua-Hot"
    assert device.product_id == "Reporter 2v1a"
    assert device.serial_number == "A400D-200710"
    assert device.unit_number == "23"
    assert device.protocol == "j1939"
    assert device.response_count == 1
    assert "component_identification" in device.capabilities


@pytest.mark.asyncio
async def test_protocol_router_normalizes_addressed_tp_pgn() -> None:
    """ProtocolRouter recognizes addressed TP.CM frames by normalized PGN."""
    router = ProtocolRouter(BAMHandler(), safety_engine=Mock())
    control_frame = CANFrame(
        arbitration_id=TP_CM_CAN_ID,
        pgn=0xECFF,
        source_address=0x9E,
        destination_address=0xFF,
        data=next(iter(make_bam_frames(AQUA_HOT_PAYLOAD)))[1],
        timestamp=0.0,
    )

    result = await router.route_frame(control_frame)

    assert result is None
    assert router.bam_handler.get_active_session_count() == 1
