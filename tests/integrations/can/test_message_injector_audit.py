"""Tests for CAN message injection audit logging.

Regression coverage for the silent audit no-op: the composition root wires an
async audit callback into CANMessageInjector, so the injector must await it,
and SecurityAuditService must expose log_injection for the callback to call.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from backend.integrations.can.message_injector import (
    CANMessageInjector,
    InjectionMode,
    InjectionRequest,
    InjectionResult,
    SafetyLevel,
)
from backend.services.security.security_audit_service import (
    SecurityAuditService,
    SecurityEventSeverity,
    SecurityEventType,
)

pytestmark = pytest.mark.can


def _request(**overrides) -> InjectionRequest:
    defaults = {
        "can_id": 0x18FEF100,
        "data": b"\x01\x02",
        "interface": "can1",
        "mode": InjectionMode.SINGLE,
        "user": "test-user",
        "reason": "unit test",
    }
    defaults.update(overrides)
    return InjectionRequest(**defaults)


class TestRunAuditCallback:
    """The injector must await async callbacks (the composition root passes one)."""

    @pytest.mark.asyncio
    async def test_awaits_async_callback(self):
        calls = []

        async def audit_callback(request, result):
            calls.append((request, result))

        injector = CANMessageInjector(
            safety_level=SafetyLevel.MODERATE, audit_callback=audit_callback
        )
        request = _request()
        result = InjectionResult(success=True, messages_sent=1)

        await injector._run_audit_callback(request, result)

        assert calls == [(request, result)]

    @pytest.mark.asyncio
    async def test_supports_sync_callback(self):
        callback = Mock(return_value=None)
        injector = CANMessageInjector(safety_level=SafetyLevel.MODERATE, audit_callback=callback)
        request = _request()
        result = InjectionResult(success=True, messages_sent=1)

        await injector._run_audit_callback(request, result)

        callback.assert_called_once_with(request, result)

    @pytest.mark.asyncio
    async def test_callback_error_does_not_propagate(self):
        async def audit_callback(request, result):
            raise RuntimeError("audit store down")

        injector = CANMessageInjector(
            safety_level=SafetyLevel.MODERATE, audit_callback=audit_callback
        )

        await injector._run_audit_callback(_request(), InjectionResult(success=True))

    @pytest.mark.asyncio
    async def test_command_halt_emits_audit_record(self):
        calls = []

        async def audit_callback(request, result):
            calls.append((request, result))

        injector = CANMessageInjector(
            safety_level=SafetyLevel.MODERATE, audit_callback=audit_callback
        )

        await injector.halt_command_emission("test halt")

        assert len(calls) == 1
        halt_request, halt_result = calls[0]
        assert halt_request.user == "SYSTEM"
        assert "COMMAND_HALT" in halt_request.reason
        assert halt_result.success is True


class TestLogInjection:
    """SecurityAuditService.log_injection persists injection audit events."""

    def _service(self) -> tuple[SecurityAuditService, AsyncMock]:
        repository = AsyncMock()
        monitor = Mock()
        monitor.monitor_service_method.return_value = lambda func: func
        service = SecurityAuditService(
            security_audit_repository=repository, performance_monitor=monitor
        )
        return service, repository

    @pytest.mark.asyncio
    async def test_persists_audit_event(self):
        service, repository = self._service()
        request = _request()
        result = InjectionResult(success=True, messages_sent=1)

        event_id = await service.log_injection(request, result)

        assert event_id
        repository.store_audit_event.assert_awaited_once()
        event = repository.store_audit_event.await_args.args[0]
        assert event.event_type == SecurityEventType.CAN_MESSAGE_INJECTION
        assert event.severity == SecurityEventSeverity.MEDIUM
        assert event.user_id == "test-user"
        assert event.safety_impact == "direct_can_bus_write"
        assert event.details["can_id"] == "0x18FEF100"
        assert event.details["data"] == "0102"
        assert event.details["interface"] == "can1"
        assert event.details["messages_sent"] == 1

    @pytest.mark.asyncio
    async def test_failed_injection_logged_high_severity(self):
        service, repository = self._service()
        result = InjectionResult(success=False, messages_failed=1, error="bus off")

        await service.log_injection(_request(), result)

        event = repository.store_audit_event.await_args.args[0]
        assert event.severity == SecurityEventSeverity.HIGH
        assert event.details["success"] is False
        assert event.details["error"] == "bus off"

    @pytest.mark.asyncio
    async def test_injection_with_warnings_logged_high_severity(self):
        service, repository = self._service()
        result = InjectionResult(success=True, messages_sent=1, warnings=["dangerous message"])

        await service.log_injection(_request(), result)

        event = repository.store_audit_event.await_args.args[0]
        assert event.severity == SecurityEventSeverity.HIGH
        assert event.details["warnings"] == ["dangerous message"]
