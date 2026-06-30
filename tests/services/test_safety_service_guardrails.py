"""Behavior tests for CommandGuardrailService API guardrail decisions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.services.guardrails.command_guardrail_service import (
    CommandGuardrailService,
    CommandPrecondition,
    SystemOperationalMode,
)

pytestmark = [pytest.mark.unit, pytest.mark.safety]


async def test_safety_interlock_known_conditions_and_unknown_fail_closed() -> None:
    """Interlocks pass known safe state and fail closed on unknown conditions."""
    interlock = CommandPrecondition(
        name="slide_room",
        feature_name="firefly",
        interlock_conditions=[
            "vehicle_not_moving",
            "parking_brake_engaged",
            "leveling_jacks_deployed",
            "engine_not_running",
            "transmission_in_park",
            "slide_rooms_retracted",
        ],
    )

    passed, reason = await interlock.check_conditions(
        {
            "vehicle_speed": 0.0,
            "parking_brake": True,
            "leveling_jacks_down": True,
            "engine_running": False,
            "transmission_gear": "PARK",
            "all_slides_retracted": True,
        }
    )
    assert passed is True
    assert reason == "All conditions satisfied"

    unknown = CommandPrecondition("unknown", "feature", ["not_a_real_condition"])
    passed, reason = await unknown.check_conditions({})
    assert passed is False
    assert "not_a_real_condition" in reason


async def test_safety_interlock_override_expires_and_reenables_checks() -> None:
    """Expired interlock overrides are cleared before conditions are evaluated."""
    interlock = CommandPrecondition(
        name="awning",
        feature_name="firefly",
        interlock_conditions=["parking_brake_engaged"],
    )
    await interlock.override(
        session_id="pin-session",
        reason="service work",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        overridden_by="tech",
    )

    passed, reason = await interlock.check_conditions({"parking_brake": False})

    assert passed is False
    assert "parking_brake_engaged" in reason
    assert interlock.get_override_info() is None


async def test_check_command_preconditions_engages_and_disengages_with_audit() -> None:
    """CommandGuardrailService interlock checks engage on bad state and disengage when fixed."""
    service = CommandGuardrailService()
    service.update_system_state({"vehicle_speed": 5.0, "parking_brake": False})

    first = await service.check_command_preconditions()
    assert first["slide_room_precondition"][0] is False
    assert first["awning_precondition"][0] is False
    assert service._interlocks["slide_room_precondition"].is_engaged is True
    assert any(entry["event_type"] == "interlock_engaged" for entry in service.get_audit_log())

    service.update_system_state({"vehicle_speed": 0.0, "parking_brake": True})
    second = await service.check_command_preconditions()

    assert second["slide_room_precondition"][0] is True
    assert service._interlocks["slide_room_precondition"].is_engaged is False
    assert any(entry["event_type"] == "interlock_disengaged" for entry in service.get_audit_log())


async def test_halt_command_emission_sets_state_and_runs_actions() -> None:
    """Explicit command halt records forensic state and command-halt state."""
    service = CommandGuardrailService()

    activated = await service.halt_command_emission("operator request", "admin")
    activated_again = await service.halt_command_emission("duplicate", "admin")

    assert activated is True
    assert activated_again is False
    assert service.get_guardrail_status()["command_halt_active"] is True
    assert service.get_guardrail_status()["in_command_halt_state"] is True
    assert service.get_guardrail_status()["halt_command_emission_reason"] == "operator request"


async def test_clear_command_halt_requires_authorization_and_clears_state() -> None:
    """Command-halt clear refuses bad auth and clears state with legacy auth."""
    service = CommandGuardrailService()
    await service.halt_command_emission("stop", "admin")

    assert await service.clear_command_halt("bad", reset_by="admin") is False
    assert service.get_guardrail_status()["command_halt_active"] is True

    assert await service.clear_command_halt("SAFETY_OVERRIDE_ADMIN", reset_by="admin") is True
    status = service.get_guardrail_status()
    assert status["command_halt_active"] is False
    assert status["halt_command_emission_reason"] is None


async def test_halt_command_emission_with_pin_authorization_paths() -> None:
    """PIN command halt succeeds only when the PIN manager authorizes the operation."""
    pin_manager = AsyncMock()
    service = CommandGuardrailService(pin_manager=pin_manager)

    pin_manager.authorize_operation.return_value = False
    assert await service.halt_command_emission_with_pin("bad", "reason", "user") is False
    assert service.get_guardrail_status()["command_halt_active"] is False

    pin_manager.authorize_operation.return_value = True
    assert await service.halt_command_emission_with_pin("good", "reason", "user") is True
    assert service.get_guardrail_status()["command_halt_active"] is True


async def test_validate_guardrail_operation_enforces_rate_limit() -> None:
    """Guardrail operation validation blocks rate-limit failures and logs allowed operations."""
    audit_service = AsyncMock()
    service = CommandGuardrailService(security_audit_service=audit_service)

    audit_service.check_rate_limit.return_value = False
    blocked = await service.validate_guardrail_operation(
        "control", user_id="user", source_ip="10.0.0.1", entity_id="light_1"
    )
    assert blocked is False
    audit_service.log_security_event.assert_awaited_with(
        event_type="rate_limit_exceeded",
        severity="medium",
        user_id="user",
        source_ip="10.0.0.1",
        details={
            "operation_type": "control",
            "category": "guardrail",
            "entity_id": "light_1",
            "blocked_reason": "rate_limit_exceeded",
        },
    )

    audit_service.reset_mock()
    audit_service.check_rate_limit.return_value = True
    allowed = await service.validate_guardrail_operation(
        "command_halt", user_id="admin", is_admin=True, details={"reason": "test"}
    )

    assert allowed is True
    audit_service.log_security_event.assert_awaited_once()
    assert audit_service.log_security_event.await_args.kwargs["severity"] == "high"


def test_mode_expiration_reverts_to_normal_and_clears_session() -> None:
    """Expired maintenance/diagnostic sessions return to normal mode."""
    service = CommandGuardrailService()
    service._operational_mode = SystemOperationalMode.MAINTENANCE
    service._mode_session_id = "session"
    service._mode_entered_by = "tech"
    service._mode_entered_at = datetime.now(UTC) - timedelta(minutes=10)
    service._mode_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    service._active_overrides = {"awning_precondition": datetime.now(UTC) + timedelta(minutes=1)}

    service.check_mode_expiration()

    assert service._operational_mode == SystemOperationalMode.NORMAL
    assert service._mode_session_id is None
    assert service._active_overrides == {}


def test_add_and_clear_interlock_override() -> None:
    """Clearing an active interlock override updates service tracking and audit log."""
    service = CommandGuardrailService()
    interlock = service._interlocks["awning_precondition"]
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    interlock._is_overridden = True
    interlock._override_session_id = "session"
    interlock._override_reason = "test"
    interlock._override_expires_at = expires_at
    interlock._override_by = "tech"
    service._active_overrides["awning_precondition"] = expires_at

    assert service.clear_interlock_override("missing") is False
    assert service.clear_interlock_override("awning_precondition") is True
    assert interlock.get_override_info() is None
    assert "awning_precondition" not in service._active_overrides
    assert service.get_audit_log()[0]["event_type"] == "interlock_override_cleared"


def test_get_health_and_status_reports_guardrail_state() -> None:
    """Health/status snapshots expose guardrail state without physical-safety claims."""
    service = CommandGuardrailService(health_check_interval=1.5, watchdog_timeout=2.5)
    service._in_command_halt_state = True
    service._command_halt_active = True
    service._halt_command_emission_reason = "test"
    service._active_guardrail_actions.append("halt_command_emission")

    health = service.get_health_status()
    status = service.get_guardrail_status()

    assert health["healthy"] is False
    assert health["command_halt_active"] is True
    assert status["in_command_halt_state"] is True
    assert status["halt_command_emission_reason"] == "test"
    assert "halt_command_emission" in status["active_guardrail_actions"]
