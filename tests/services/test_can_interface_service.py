"""Tests for SocketCAN telemetry in CANInterfaceService."""

from typing import Any

import pytest

import backend.services.can.can_interface_service as can_interface_module
from backend.services.can.can_interface_service import CANInterfaceService

pytestmark = pytest.mark.can


class FakeNetlink(dict[str, Any]):
    """Small pyroute2-like mapping with get_attr support."""

    def __init__(self, attrs: dict[str, Any] | None = None, **values: Any) -> None:
        super().__init__(**values)
        self._attrs = attrs or {}

    def get_attr(self, name: str) -> Any:
        """Return a fake pyroute2 netlink attribute."""
        return self._attrs.get(name)


class FakeIPRoute:
    """Context manager test double for pyroute2.IPRoute."""

    def __init__(self, links: list[FakeNetlink]) -> None:
        self._links = links

    def __enter__(self) -> "FakeIPRoute":
        """Enter the fake IPRoute context."""
        return self

    def __exit__(self, *_args: Any) -> None:
        """Exit the fake IPRoute context."""

    def get_links(self, kind: str) -> list[FakeNetlink]:
        """Return fake CAN links."""
        assert kind == "can"
        return self._links


@pytest.mark.asyncio
async def test_socketcan_stats_parse_decoded_counters(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider parses decoded cumulative counters and nullable controller xstats."""
    link = FakeNetlink(
        attrs={
            "IFLA_IFNAME": "can0",
            "IFLA_OPERSTATE": "UP",
            "IFLA_STATS64": {
                "rx_packets": 100,
                "tx_packets": 25,
                "rx_bytes": 800,
                "tx_bytes": 200,
                "rx_errors": 2,
                "tx_errors": 1,
                "rx_dropped": 3,
                "tx_dropped": 4,
            },
            "IFLA_PROMISCUITY": 0,
            "IFLA_PARENTBUS": "spi",
            "IFLA_PARENTDEV": "spi0.1",
        },
        linkinfo=FakeNetlink(
            attrs={"IFLA_INFO_KIND": "can"},
            info_data=FakeNetlink(
                attrs={
                    "IFLA_CAN_BITTIMING": {
                        "bitrate": 250000,
                        "sample_point": 875,
                        "tq": 250,
                        "prop_seg": 6,
                        "phase_seg1": 7,
                        "phase_seg2": 2,
                        "sjw": 1,
                        "brp": 2,
                    },
                    "IFLA_CAN_RESTART_MS": 0,
                    "IFLA_CAN_CLOCK": 8000000,
                    "IFLA_CAN_STATE": 0,
                }
            ),
            info_xstats={
                "restarts": 5,
                "bus_error": 6,
                "arbitration_lost": 7,
                "error_warning": 8,
                "error_passive": 9,
                "bus_off": 10,
            },
        ),
    )
    monkeypatch.setattr(can_interface_module, "CAN_SUPPORTED", True)
    monkeypatch.setattr(can_interface_module, "IPRoute", lambda: FakeIPRoute([link]))

    stats = await CANInterfaceService().get_interface_stats()

    assert list(stats) == ["can0"]
    can0 = stats["can0"]
    assert can0["state"] == "ERROR-ACTIVE"
    assert can0["bitrate"] == 250000
    assert can0["sample_point"] == 0.875
    assert can0["rx_packets"] == 100
    assert can0["tx_packets"] == 25
    assert can0["rx_errors"] == 2
    assert can0["tx_errors"] == 1
    assert can0["rx_dropped"] == 3
    assert can0["tx_dropped"] == 4
    assert can0["restarts"] == 5
    assert can0["bus_errors"] == 6
    assert can0["arbitration_lost"] == 7
    assert can0["error_warning"] == 8
    assert can0["error_passive"] == 9
    assert can0["bus_off"] == 10
    assert can0["parentbus"] == "spi"
    assert can0["parentdev"] == "spi0.1"


@pytest.mark.asyncio
async def test_socketcan_stats_leave_raw_xstats_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider does not parse raw xstats blobs or fabricate controller counters."""
    link = FakeNetlink(
        attrs={"IFLA_IFNAME": "can0", "IFLA_STATS64": {}},
        linkinfo=FakeNetlink(
            attrs={"IFLA_INFO_KIND": "can"},
            info_data=FakeNetlink(attrs={"IFLA_CAN_STATE": 3}),
            info_xstats=b"\x00\x00\x00\x00",
        ),
    )
    monkeypatch.setattr(can_interface_module, "CAN_SUPPORTED", True)
    monkeypatch.setattr(can_interface_module, "IPRoute", lambda: FakeIPRoute([link]))

    stats = await CANInterfaceService().get_interface_stats()

    can0 = stats["can0"]
    assert can0["state"] == "BUS-OFF"
    assert can0["bus_errors"] is None
    assert can0["error_warning"] is None
    assert can0["error_passive"] is None
    assert can0["bus_off"] is None


@pytest.mark.asyncio
async def test_socketcan_stats_degrade_empty_when_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider returns empty telemetry on non-Linux or pyroute2-absent paths."""
    monkeypatch.setattr(can_interface_module, "CAN_SUPPORTED", False)
    monkeypatch.setattr(can_interface_module, "IPRoute", None)

    service = CANInterfaceService()

    assert await service.get_interfaces() == []
    assert await service.get_interface_details() == {}
    assert await service.get_interface_stats() == {}
