"""Tests for passive discovery and the coach node directory (friendly names)."""

from unittest.mock import Mock, patch

import can

from backend.services.discovery.device_discovery_service import DeviceDiscoveryService

NODES = {
    0x75: {"name": "Aspire Head Unit", "device_type": "infotainment", "notes": "dash"},
    0x4F: {"name": "Transfer Switch (ATS)", "device_type": "ats"},
}


def make_service() -> DeviceDiscoveryService:
    config = Mock()
    config.device_discovery = {}
    config.rvc_enabled = True
    config.j1939 = None
    config.j1939_enabled = False
    config.controller_source_addr = "0xF9"
    with patch.object(DeviceDiscoveryService, "_load_node_directory", return_value=dict(NODES)):
        return DeviceDiscoveryService(can_facade=None, config=config)


def frame(arbitration_id: int, data: bytes = bytes(8)) -> can.Message:
    return can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)


class TestPassiveDiscovery:
    def test_message_creates_named_device(self):
        service = make_service()
        # DATE_TIME-ish frame from the head unit.
        service.process_can_message(frame(0x19FFFE75))
        device = service.topology.devices[0x75]
        assert device.friendly_name == "Aspire Head Unit"
        assert device.device_type == "infotainment"
        assert device.notes == "dash"
        assert device.status == "online"

    def test_unnamed_address_still_tracked(self):
        service = make_service()
        service.process_can_message(frame(0x19FEDA8E))
        device = service.topology.devices[0x8E]
        assert device.friendly_name is None
        # 17-bit DGN mask regression: 1FEDA (DC_DIMMER_STATUS_3) classifies
        # the device as a light; the old 16-bit mask made this unreachable.
        assert device.device_type == "light"

    def test_own_source_address_skipped(self):
        service = make_service()
        service.process_can_message(frame(0x19FFFFF9))
        assert 0xF9 not in service.topology.devices

    def test_topology_response_carries_names(self):
        import asyncio

        service = make_service()
        service.process_can_message(frame(0x0DFFAD4F))  # ATS_AC_STATUS_1 from the ATS
        topology = asyncio.get_event_loop().run_until_complete(service.get_network_topology())
        devices = [d for group in topology["devices"].values() for d in group]
        ats = next(d for d in devices if d["source_address"] == 0x4F)
        assert ats["friendly_name"] == "Transfer Switch (ATS)"


class TestNodeDirectoryParsing:
    def test_hex_and_decimal_keys(self):
        config = Mock()
        config.device_discovery = {}
        config.rvc_enabled = True
        config.j1939 = None
        config.j1939_enabled = False
        config.controller_source_addr = "0xF9"
        yaml_content = {"nodes": {"0x75": {"name": "Head Unit"}, "156": "Firefly", "bad": {}}}
        with (
            patch(
                "backend.integrations.rvc.config_loader.get_default_paths",
                return_value=("spec", "mapping.yml"),
            ),
            patch("builtins.open"),
            patch("yaml.safe_load", return_value=yaml_content),
        ):
            service = DeviceDiscoveryService(can_facade=None, config=config)
        assert service._node_directory[0x75] == {"name": "Head Unit"}
        assert service._node_directory[156] == {"name": "Firefly"}
        # Unparseable keys are skipped per-entry, never failing the rest.
        assert len(service._node_directory) == 2
