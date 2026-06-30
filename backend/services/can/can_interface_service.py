"""
CAN Interface Service

Service for managing CAN interface mappings and resolution.
Provides logical interface name mapping to physical interfaces.
"""

import asyncio
import logging
import platform
from typing import Any, cast

from backend.core.config import get_settings
from backend.models.can import CANInterfaceStats

CAN_SUPPORTED = platform.system() == "Linux"
if CAN_SUPPORTED:
    try:
        from pyroute2 import IPRoute as _IPRoute  # type: ignore[reportMissingTypeStubs]
    except ImportError:
        IPRoute = None
    else:
        IPRoute = _IPRoute
else:
    IPRoute = None

logger = logging.getLogger(__name__)

CAN_STATE_MAP = {
    0: "ERROR-ACTIVE",
    1: "ERROR-WARNING",
    2: "ERROR-PASSIVE",
    3: "BUS-OFF",
    4: "STOPPED",
    5: "SLEEPING",
}


def socketcan_telemetry_available() -> bool:
    """Return true when SocketCAN telemetry can be read through pyroute2."""
    return CAN_SUPPORTED and IPRoute is not None


def read_socketcan_links() -> list[Any]:
    """Read CAN links with pyroute2 using an explicit selector loop."""
    if IPRoute is None:
        return []

    loop = asyncio.SelectorEventLoop()
    try:
        iproute_factory = cast("Any", IPRoute)
        with iproute_factory(use_event_loop=loop) as ipr:
            return list(ipr.get_links(kind="can"))
    finally:
        loop.close()


class CANInterfaceService:
    """Service for managing CAN interface mappings and resolution."""

    def __init__(self):
        self.settings = get_settings()
        self._interface_mappings = self._load_interface_mappings()

    def _load_interface_mappings(self) -> dict[str, str]:
        """Load interface mappings from settings."""
        return self.settings.can.interface_mappings.copy()

    def resolve_interface(self, logical_name: str) -> str:
        """
        Resolve logical interface name to physical interface.

        Args:
            logical_name: Logical interface name (e.g., 'house', 'chassis')

        Returns:
            Physical interface name (e.g., 'can0', 'can1')

        Raises:
            ValueError: If logical interface is not mapped
        """
        # If it's already physical, return as-is
        if logical_name.startswith(("can", "vcan")):
            return logical_name

        if logical_name in self._interface_mappings:
            return self._interface_mappings[logical_name]

        msg = f"Unknown logical CAN interface: {logical_name}"
        raise ValueError(msg)

    def get_all_mappings(self) -> dict[str, str]:
        """Get all current interface mappings."""
        return self._interface_mappings.copy()

    async def get_interfaces(self) -> list[str]:
        """Get CAN interfaces reported by the local SocketCAN stack."""
        return sorted(await self._get_socketcan_stats())

    async def get_interface_details(self) -> dict[str, dict[str, Any]]:
        """Get detailed SocketCAN telemetry for all discovered CAN interfaces."""
        stats = await self._get_socketcan_stats()
        return {name: interface.model_dump() for name, interface in stats.items()}

    async def get_interface_stats(self) -> dict[str, dict[str, Any]]:
        """Get cumulative SocketCAN counters for all discovered CAN interfaces."""
        return await self.get_interface_details()

    async def _get_socketcan_stats(self) -> dict[str, CANInterfaceStats]:
        """Read SocketCAN interface telemetry from pyroute2 when available."""
        if not socketcan_telemetry_available():
            logger.debug("SocketCAN telemetry unavailable on %s", platform.system())
            return {}

        try:
            can_links = await asyncio.to_thread(read_socketcan_links)
        except Exception as exc:
            logger.warning("Failed to read SocketCAN interface telemetry: %s", exc)
            return {}

        interfaces: dict[str, CANInterfaceStats] = {}
        for link in can_links:
            interface_name = _get_attr(link, "IFLA_IFNAME")
            if not isinstance(interface_name, str):
                logger.debug("Skipping CAN link without string interface name: %r", interface_name)
                continue

            try:
                interfaces[interface_name] = _stats_from_pyroute2_link(link)
            except Exception as exc:
                logger.warning(
                    "Failed to parse SocketCAN telemetry for %s: %s", interface_name, exc
                )
                interfaces[interface_name] = CANInterfaceStats(
                    name=interface_name,
                    state="Exception/Pyroute2Error",
                    notes="Failed to parse pyroute2 telemetry",
                )

        return interfaces

    def update_mapping(self, logical_name: str, physical_interface: str) -> None:
        """Update interface mapping (runtime only)."""
        self._interface_mappings[logical_name] = physical_interface
        logger.info("Updated interface mapping: %s -> %s", logical_name, physical_interface)

    def validate_mapping(self, mappings: dict[str, str]) -> dict[str, Any]:
        """Validate interface mappings."""
        issues = []

        # Check for duplicate physical interfaces
        physical_interfaces = list(mappings.values())
        if len(physical_interfaces) != len(set(physical_interfaces)):
            issues.append("Duplicate physical interfaces detected")

        # Validate physical interface names
        issues.extend(
            f"Invalid physical interface: {physical}"
            for physical in mappings.values()
            if not physical.startswith(("can", "vcan"))
        )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "mapping": mappings,
        }


def _get_attr(source: Any, *names: str) -> Any:
    """Best-effort netlink attribute lookup for pyroute2 objects and dicts."""
    get_attr = getattr(source, "get_attr", None)
    for name in names:
        if callable(get_attr):
            value = get_attr(name)
            if value is not None:
                return value
        if isinstance(source, dict):
            value = source.get(name)
            if value is not None:
                return value
    return None


def _numeric_value(value: Any) -> int | None:
    """Return an integer counter value when pyroute2 decoded one."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _sample_point_value(value: Any) -> float | None:
    """Normalize CAN sample-point values from pyroute2/iproute2 formats."""
    if value is None:
        return None
    try:
        sample_point = float(value)
    except (TypeError, ValueError):
        return None
    return sample_point / 1000.0 if sample_point > 1 else sample_point


def _state_value(value: Any, fallback: str | None) -> str | None:
    """Normalize CAN controller state values from pyroute2/iproute2 formats."""
    if isinstance(value, int):
        return CAN_STATE_MAP.get(value, fallback)
    if isinstance(value, str):
        return value.replace("_", "-").upper()
    return fallback


def _set_counter(stats: CANInterfaceStats, field_name: str, value: Any) -> None:
    """Set a nullable integer counter only when pyroute2 decoded it."""
    counter = _numeric_value(value)
    if counter is not None:
        setattr(stats, field_name, counter)


def _stats_from_pyroute2_link(link: Any) -> CANInterfaceStats:
    """Build CAN interface telemetry from a pyroute2 CAN link object."""
    interface_name = _get_attr(link, "IFLA_IFNAME")
    stats = CANInterfaceStats(name=interface_name)

    stats.state = _state_value(_get_attr(link, "IFLA_OPERSTATE"), stats.state)
    if _get_attr(link, "IFLA_LINKMODE") == 1:
        stats.state = "DORMANT"

    link_stats = _get_attr(link, "IFLA_STATS64", "IFLA_STATS")
    if isinstance(link_stats, dict):
        for field_name in (
            "rx_packets",
            "tx_packets",
            "rx_bytes",
            "tx_bytes",
            "rx_errors",
            "tx_errors",
            "rx_dropped",
            "tx_dropped",
        ):
            _set_counter(stats, field_name, link_stats.get(field_name))

    linkinfo = link.get("linkinfo") if isinstance(link, dict) else None
    if linkinfo is not None and _get_attr(linkinfo, "IFLA_INFO_KIND") == "can":
        stats.link_type = "can"
        _populate_can_info(stats, linkinfo)

    for field_name, attr_name in (
        ("promiscuity", "IFLA_PROMISCUITY"),
        ("allmulti", "IFLA_ALLMULTI"),
        ("minmtu", "IFLA_MIN_MTU"),
        ("maxmtu", "IFLA_MAX_MTU"),
    ):
        _set_counter(stats, field_name, _get_attr(link, attr_name))

    parentbus = _get_attr(link, "IFLA_PARENTBUS")
    parentdev = _get_attr(link, "IFLA_PARENTDEV")
    stats.parentbus = parentbus if isinstance(parentbus, str) else None
    stats.parentdev = parentdev if isinstance(parentdev, str) else None

    return stats


def _populate_can_info(stats: CANInterfaceStats, linkinfo: Any) -> None:
    """Populate CAN-specific details decoded by pyroute2."""
    info_data = linkinfo.get("info_data") if isinstance(linkinfo, dict) else None
    if info_data is not None:
        bittiming = _get_attr(info_data, "IFLA_CAN_BITTIMING", "CAN_BITTIMING")
        if isinstance(bittiming, dict):
            for field_name in (
                "bitrate",
                "tq",
                "prop_seg",
                "phase_seg1",
                "phase_seg2",
                "sjw",
                "brp",
            ):
                _set_counter(stats, field_name, bittiming.get(field_name))
            stats.sample_point = _sample_point_value(bittiming.get("sample_point"))

        bitrate = _get_attr(info_data, "CAN_BITTIMING_BITRATE")
        if bitrate is not None:
            _set_counter(stats, "bitrate", bitrate)

        sample_point = _get_attr(info_data, "CAN_BITTIMING_SAMPLE_POINT")
        if sample_point is not None:
            stats.sample_point = _sample_point_value(sample_point)

        restart_ms = _get_attr(info_data, "IFLA_CAN_RESTART_MS", "CAN_RESTART_MS")
        _set_counter(stats, "restart_ms", restart_ms)
        _set_counter(stats, "clock_freq", _get_attr(info_data, "IFLA_CAN_CLOCK", "clock"))

        stats.state = _state_value(_get_attr(info_data, "IFLA_CAN_STATE", "CAN_STATE"), stats.state)

    xstats = linkinfo.get("info_xstats") if isinstance(linkinfo, dict) else None
    if isinstance(xstats, dict):
        _set_counter(stats, "restarts", xstats.get("restarts"))
        _set_counter(stats, "bus_errors", xstats.get("bus_error", xstats.get("bus_errors")))
        _set_counter(stats, "arbitration_lost", xstats.get("arbitration_lost"))
        _set_counter(stats, "error_warning", xstats.get("error_warning"))
        _set_counter(stats, "error_passive", xstats.get("error_passive"))
        _set_counter(stats, "bus_off", xstats.get("bus_off"))
