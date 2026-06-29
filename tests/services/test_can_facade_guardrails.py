"""Additional guardrail behavior tests for CANFacade."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.safety_interfaces import SafetyStatus
from backend.services.can.can_facade import CANFacade

pytestmark = [pytest.mark.unit, pytest.mark.can]


@pytest.fixture
def can_facade_dependencies() -> dict[str, Any]:
    """Create CANFacade dependencies with explicit delegation surfaces."""
    bus_service = AsyncMock()
    bus_service.start = AsyncMock()
    bus_service.stop = AsyncMock()
    bus_service.emergency_stop = AsyncMock()
    bus_service.get_health_status = Mock(return_value={"healthy": True, "status": "ok"})

    injector = AsyncMock()
    injector.inject_message = AsyncMock(return_value={"success": True, "tx_id": "abc"})
    injector.emergency_stop = AsyncMock()

    message_filter = AsyncMock()
    message_filter.start = AsyncMock()
    message_filter.stop = AsyncMock()
    message_filter.emergency_stop = AsyncMock()
    message_filter.get_health_status = Mock(return_value={"healthy": True})

    recorder = AsyncMock()
    recorder.start = AsyncMock()
    recorder.stop = AsyncMock()
    recorder.emergency_stop = AsyncMock()
    recorder.get_health_status = AsyncMock(return_value={"healthy": True})
    recorder.get_queue_status = AsyncMock(return_value={"length": 3, "status": "busy"})
    recorder.get_recent_messages = AsyncMock(return_value=[{"arbitration_id": 0x123}])

    analyzer = AsyncMock()
    analyzer.start = AsyncMock()
    analyzer.stop = AsyncMock()
    analyzer.get_health_status = Mock(return_value={"healthy": True})
    analyzer.get_statistics = AsyncMock(return_value={"decoded": 4})

    anomaly_detector = AsyncMock()
    anomaly_detector.stop = AsyncMock()

    interface_service = Mock()
    interface_service.resolve_interface = Mock(return_value="can0")
    interface_service.get_health_status = Mock(return_value={"healthy": True})
    interface_service.get_interfaces = AsyncMock(return_value=["can0", "can1"])
    interface_service.get_interface_details = AsyncMock(
        return_value={"can0": {"state": "ERROR-ACTIVE"}}
    )
    interface_service.get_all_mappings = Mock(return_value={"house": "can0"})
    interface_service.get_interface_stats = AsyncMock(
        return_value={"can0": {"rx_packets": 12, "tx_packets": 8, "rx_errors": 1}}
    )

    performance_monitor = Mock()
    performance_monitor.monitor_service_method = Mock(return_value=lambda func: func)
    performance_monitor.get_service_metrics = AsyncMock(return_value={"latency_ms": 12})
    performance_monitor.get_performance_baselines = AsyncMock(
        return_value={
            "uptime_seconds": 10.0,
            "summary": {"CANFacade.send_message": {"count": 7200}},
        }
    )

    return {
        "bus_service": bus_service,
        "injector": injector,
        "message_filter": message_filter,
        "recorder": recorder,
        "analyzer": analyzer,
        "anomaly_detector": anomaly_detector,
        "interface_service": interface_service,
        "performance_monitor": performance_monitor,
    }


@pytest.fixture
def can_facade(can_facade_dependencies: dict[str, Any]) -> CANFacade:
    """Create a CANFacade with explicit mocks."""
    return CANFacade(**can_facade_dependencies)


async def test_start_and_stop_coordinate_underlying_services(
    can_facade: CANFacade, can_facade_dependencies: dict[str, Any]
) -> None:
    """Start and stop call the underlying services in the facade boundary."""
    await can_facade.start()
    assert can_facade._health_task is not None

    await can_facade.stop()

    can_facade_dependencies["bus_service"].start.assert_awaited_once()
    can_facade_dependencies["recorder"].start.assert_awaited_once()
    can_facade_dependencies["message_filter"].start.assert_awaited_once()
    can_facade_dependencies["analyzer"].start.assert_awaited_once()
    can_facade_dependencies["analyzer"].stop.assert_awaited_once()
    can_facade_dependencies["message_filter"].stop.assert_awaited_once()
    can_facade_dependencies["recorder"].stop.assert_awaited_once()
    can_facade_dependencies["bus_service"].stop.assert_awaited_once()


async def test_send_message_resolves_logical_interface_and_delegates_to_injector(
    can_facade: CANFacade, can_facade_dependencies: dict[str, Any]
) -> None:
    """CANFacade is the only send boundary and delegates through the injector."""
    result = await can_facade.send_message("house", 0x18FEDB00, b"\x01\x02")

    assert result == {"success": True, "tx_id": "abc"}
    can_facade_dependencies["interface_service"].resolve_interface.assert_called_once_with("house")
    can_facade_dependencies["injector"].inject_message.assert_awaited_once_with(
        interface="can0", can_id=0x18FEDB00, data=b"\x01\x02"
    )


async def test_send_raw_message_wraps_success_and_failure(can_facade: CANFacade) -> None:
    """Raw sends preserve safety checks and normalize response shape."""
    success = await can_facade.send_raw_message(0x123, b"\x0a\x0b", "house")
    assert success["status"] == "sent"
    assert success["arbitration_id_hex"] == "0x00000123"
    assert success["data"] == "0A0B"

    can_facade._set_emergency_stop_active(True)
    failure = await can_facade.send_raw_message(0x123, b"\x0a", "house")
    assert failure["status"] == "error"
    assert "Safety interlock" in failure["error"]


async def test_getters_delegate_to_underlying_services(
    can_facade: CANFacade, can_facade_dependencies: dict[str, Any]
) -> None:
    """Facade read methods stay on the unified CAN boundary."""
    assert await can_facade.get_queue_status() == {"length": 3, "status": "busy"}
    assert await can_facade.get_recent_messages(limit=1) == [{"arbitration_id": 0x123}]
    assert await can_facade.get_interfaces() == ["can0", "can1"]
    assert await can_facade.get_interface_details() == {"can0": {"state": "ERROR-ACTIVE"}}
    assert await can_facade.get_interface_mappings() == {"house": "can0"}

    can_facade_dependencies["recorder"].get_recent_messages.assert_awaited_once_with(1)


async def test_get_queue_status_has_default_when_recorder_lacks_method(
    can_facade: CANFacade,
) -> None:
    """Missing optional recorder queue API degrades to an operational default."""
    can_facade._recorder = object()

    status = await can_facade.get_queue_status()

    assert status["queue_length"] == 0
    assert status["queue_capacity"] == 1000
    assert status["status"] == "operational"


async def test_get_comprehensive_health_collects_sync_async_and_error_states(
    can_facade: CANFacade,
) -> None:
    """Health aggregation tolerates mixed sync/async health providers and failures."""
    can_facade._filter.get_health_status = AsyncMock(side_effect=RuntimeError("filter down"))

    health = await can_facade.get_comprehensive_health()

    assert health["facade_status"] == SafetyStatus.SAFE.value
    assert health["services"]["bus_service"] == {"healthy": True, "status": "ok"}
    assert health["services"]["recorder"] == {"healthy": True}
    assert health["services"]["filter"] == {"healthy": False, "error": "filter down"}
    assert health["performance"] == {"latency_ms": 12}


async def test_bus_statistics_includes_message_rate_from_performance_summary(
    can_facade: CANFacade,
) -> None:
    """Bus statistics combine interface counters, queue, analyzer, and performance data."""
    stats = await can_facade.get_bus_statistics()

    assert stats["summary"]["total_messages"] == 20
    assert stats["summary"]["total_errors"] == 1
    assert stats["summary"]["message_rate"] == 2.0
    assert stats["summary"]["uptime"] == 10.0


async def test_health_status_reports_degraded_as_healthy(can_facade: CANFacade) -> None:
    """ServiceRegistry health treats SAFE and DEGRADED as service-healthy states."""
    can_facade._set_safety_status(SafetyStatus.DEGRADED)

    health = can_facade.get_health_status()

    assert health["healthy"] is True
    assert health["safety_status"] == SafetyStatus.DEGRADED.value
