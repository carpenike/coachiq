"""Regression tests for HOF-051 guardrail rename and command-halt behavior."""

from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.guardrail_interfaces import GuardrailTier
from backend.core.guardrail_runtime_coordinator import GuardrailRuntimeCoordinator
from backend.services.can.can_facade import CANFacade
from backend.services.guardrails.command_guardrail_service import CommandGuardrailService

pytestmark = [pytest.mark.unit, pytest.mark.safety]


class _Monitor:
    """Passthrough performance monitor for facade tests."""

    def monitor_service_method(self, **_kwargs):
        """Return a decorator that leaves methods unchanged."""
        return lambda method: method


class _AuthService:
    """Auth-like service that must not be stopped by command halt."""

    def __init__(self) -> None:
        self.stop = AsyncMock()


class _CanFacadeService:
    """CAN-facade-like command-halt participant."""

    def __init__(self) -> None:
        self.halt_command_emission = AsyncMock()


@pytest.mark.asyncio
async def test_guardrail_halt_does_not_stop_auth_manager() -> None:
    """Health-critical auth is not a command-halt participant."""
    coordinator = GuardrailRuntimeCoordinator()
    auth_service = _AuthService()
    can_facade = _CanFacadeService()

    coordinator.add_guardrail_service(
        "auth_manager",
        auth_service,
        GuardrailTier.CRITICAL,
        command_halt_participant=False,
    )
    coordinator.add_guardrail_service(
        "can_facade",
        can_facade,
        GuardrailTier.CRITICAL,
        command_halt_participant=True,
    )

    result = await coordinator.halt_command_emission("test", "pytest")

    assert result == {"can_facade": True}
    auth_service.stop.assert_not_called()
    can_facade.halt_command_emission.assert_awaited_once_with("test")


@pytest.mark.asyncio
async def test_can_facade_halts_command_emitters_once() -> None:
    """CANFacade is the single halt target and fans out to command emitters once."""
    bus_service = Mock()
    bus_service.halt_command_emission = AsyncMock()
    bus_service.start = AsyncMock()
    bus_service.stop = AsyncMock()

    injector = Mock()
    injector.halt_command_emission = AsyncMock()
    injector.start = AsyncMock()
    injector.stop = AsyncMock()

    message_filter = Mock()
    message_filter.halt_command_emission = AsyncMock()
    message_filter.start = AsyncMock()
    message_filter.stop = AsyncMock()

    recorder = Mock()
    recorder.halt_command_emission = AsyncMock()
    recorder.start = AsyncMock()
    recorder.stop = AsyncMock()

    analyzer = Mock()
    analyzer.start = AsyncMock()
    analyzer.stop = AsyncMock()

    anomaly_detector = Mock()
    anomaly_detector.stop = AsyncMock()

    interface_service = Mock()
    facade = CANFacade(
        bus_service=bus_service,
        injector=injector,
        message_filter=message_filter,
        recorder=recorder,
        analyzer=analyzer,
        anomaly_detector=anomaly_detector,
        interface_service=interface_service,
        performance_monitor=_Monitor(),
    )

    await facade.halt_command_emission("test")

    bus_service.halt_command_emission.assert_awaited_once_with("test")
    injector.halt_command_emission.assert_awaited_once_with("test")
    recorder.halt_command_emission.assert_awaited_once_with("test")
    message_filter.halt_command_emission.assert_not_called()
    analyzer.stop.assert_awaited_once()
    anomaly_detector.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_command_halt_restores_guardrail_state() -> None:
    """Command halt can be cleared and resets in-memory guardrail state."""
    service = CommandGuardrailService()

    activated = await service.halt_command_emission("test", "pytest")
    status = service.get_guardrail_status()
    cleared = await service.clear_command_halt("SAFETY_OVERRIDE_ADMIN", "pytest")
    cleared_status = service.get_guardrail_status()

    assert activated is True
    assert status["command_halt_active"] is True
    assert status["in_command_halt_state"] is True
    assert status["active_guardrail_actions"]
    assert cleared is True
    assert cleared_status["command_halt_active"] is False
    assert cleared_status["in_command_halt_state"] is False
    assert cleared_status["active_guardrail_actions"] == []


@pytest.mark.asyncio
async def test_pin_gating_preserved_for_command_halt() -> None:
    """PIN authorization is still required for PIN-based command halt."""
    pin_manager = Mock()
    pin_manager.authorize_operation = AsyncMock(return_value=False)
    service = CommandGuardrailService(pin_manager=pin_manager)

    rejected = await service.halt_command_emission_with_pin(
        pin_session_id="bad", reason="test", triggered_by="pytest"
    )

    assert rejected is False
    pin_manager.authorize_operation.assert_awaited_once_with(
        session_id="bad", operation="halt_command_emission", user_id="pytest"
    )
    assert service.get_guardrail_status()["command_halt_active"] is False
