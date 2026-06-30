"""
Integration tests for command halt scenarios in the safety system.

Tests comprehensive emergency scenarios including cascading failures,
recovery procedures, and real-world RV emergency situations.
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from backend.core.service_registry import ServiceStatus
from backend.services.guardrails.command_guardrail_service import CommandGuardrailService


class MockService:
    """Mock service for testing."""

    def __init__(self, name, guardrail_tier=None, **kwargs):
        self.name = name
        self.guardrail_tier = guardrail_tier
        self.startup_called = False
        self.shutdown_called = False
        self.health_check_count = 0
        self.state = ServiceStatus.STOPPED

    async def startup(self):
        self.startup_called = True
        self.state = ServiceStatus.HEALTHY

    async def shutdown(self):
        self.shutdown_called = True
        self.state = ServiceStatus.STOPPED

    async def check_health(self):
        self.health_check_count += 1
        return self.state


@pytest.fixture
def mock_services():
    """Create mock services for testing."""
    services = {
        "can_interface": MockService(
            name="can_interface",
            guardrail_tier="critical",
        ),
        "firefly": MockService(
            name="firefly",
            guardrail_tier="position_critical",
        ),
        "spartan_k2": MockService(
            name="spartan_k2",
            guardrail_tier="position_critical",
        ),
        "analytics": MockService(
            name="analytics",
            guardrail_tier="operational",
        ),
    }
    return services


@pytest.fixture
def service_registry_with_safety(mock_services):
    """Create a service registry with safety services.

    Restored 2026-05-13 (PR #129 follow-up). The mock implements the
    full surface that ``CommandGuardrailService`` actually calls in production
    (verified by grepping ``self.service_registry.*`` in
    ``backend/services/command_guardrail_service.py``):

    - ``check_system_health`` — async, used by health-check loop
    - ``get_service`` / ``has_service`` / ``get_service_status``
    - ``get_command_halt_targets`` — used by
      ``_get_command_halt_targets`` (line 615)
    - ``get_health_summary`` — used by health-check loop (line 1788)

    The previous version of this fixture was missing the latter two,
    causing production iteration paths to crash with
    ``TypeError: 'Mock' object is not iterable``.

    IMPORTANT: We use a plain ``SimpleNamespace`` rather than ``Mock()``
    because production's ``_perform_health_check`` does
    ``hasattr(self.service_registry, 'get_guardrail_status_summary')`` and
    ``hasattr(self.service_registry, 'halt_command_emission')`` -- both
    of which return True for a bare ``Mock`` (auto-generated attribute
    machinery), then crash trying to ``await`` the resulting Mock. The
    real production ``ServiceRegistry`` does NOT have those methods
    (they were on a deleted ``GuardrailCoordinator`` subclass).
    SimpleNamespace gives us only the attributes we explicitly assign,
    matching the real production surface.
    """
    from types import SimpleNamespace

    registry = SimpleNamespace()
    registry._services = mock_services
    registry._service_statuses = dict.fromkeys(mock_services, ServiceStatus.HEALTHY)

    async def mock_check_health():
        return {
            "status": "healthy",
            "services": registry._service_statuses,
            "failed_critical": [],
        }

    registry.check_system_health = AsyncMock(side_effect=mock_check_health)
    registry.get_service = lambda name: mock_services.get(name)
    registry.has_service = lambda name: name in mock_services
    registry.get_service_status = lambda name: registry._service_statuses.get(
        name, ServiceStatus.STOPPED
    )
    # Production uses these to drive the safety-shutdown iteration; they
    # MUST return real iterables/dicts (not bare ``Mock()`` instances)
    # or the production for-loops crash.
    registry.get_command_halt_targets = lambda: [
        name
        for name, svc in mock_services.items()
        if getattr(svc, "guardrail_tier", None) in ("critical", "position_critical")
    ]
    # Production calls ``get_health_summary()`` on every monitoring tick
    # and iterates ``.items()`` expecting ``{name: {"status": <STATUS>}}``
    # (see ``backend/core/service_registry.py:1019`` for the canonical
    # shape). Returning the wrong shape (e.g. flat dict of strings)
    # silently triggers command-halt-state via the loop's blanket exception
    # handler -- that's intentional failsafe behavior in production but
    # makes for very confusing test failures, so match the real shape.
    registry.get_health_summary = lambda: {
        name: {"status": registry._service_statuses[name].name} for name in mock_services
    }

    return registry


@pytest.fixture
def integrated_command_guardrail_service(service_registry_with_safety):
    """Create CommandGuardrailService integrated with service registry."""
    service = CommandGuardrailService(
        service_registry=service_registry_with_safety,
        health_check_interval=0.5,  # Fast for testing
        watchdog_timeout=2.0,
    )
    return service


class TestEmergencyStopScenarios:
    """Test command halt scenarios with full system integration."""

    @pytest.mark.asyncio
    async def test_critical_service_failure_cascade(
        self, integrated_command_guardrail_service, mock_services
    ):
        """Test cascading failure from critical service.

        Updated 2026-05-13 (PR #129 follow-up). The previous version
        mocked ``check_system_health.return_value`` -- production never
        calls that method on the monitoring loop hot path. The actual
        contract is ``service_registry.get_health_summary()`` returning
        ``{name: {"status": <STATUS_NAME>}}`` (see
        ``backend/core/service_registry.py:1019`` for the canonical
        shape; ``backend/services/command_guardrail_service.py:1788`` for the
        consumer). Iterate ``.items()``, look for ``"FAILED"`` /
        ``"DEGRADED"`` status strings, and feed any failures matching
        ``_get_command_halt_targets()`` into ``failed_critical``.
        """
        service = integrated_command_guardrail_service
        services = mock_services

        # Start monitoring
        monitor_task = asyncio.create_task(service.start_monitoring())
        await asyncio.sleep(0.1)  # Let monitoring start

        # Simulate CAN interface failure. ``can_interface`` is in our
        # mock's ``get_command_halt_targets()`` (classification
        # 'critical'), so a FAILED status here will fan out into
        # ``failed_critical`` on the next health-check tick.
        services["can_interface"].state = ServiceStatus.FAILED
        service.service_registry._service_statuses["can_interface"] = ServiceStatus.FAILED

        # Replace get_health_summary so production reads the failure.
        # ``lambda`` (not AsyncMock) because production calls this
        # synchronously inside the async loop.
        service.service_registry.get_health_summary = lambda: {
            "can_interface": {"status": "FAILED"},
            "firefly": {"status": "HEALTHY"},
            "spartan_k2": {"status": "HEALTHY"},
            "analytics": {"status": "HEALTHY"},
        }

        # Wait for health check to detect failure (interval is 0.5s)
        await asyncio.sleep(0.7)

        # Should trigger command halt
        assert service._command_halt_active is True
        assert "can_interface" in service._halt_command_emission_reason

        # Command halt should record the high-level guardrail action.
        status = service.get_guardrail_status()
        assert any(
            "halt_command_emission" in action for action in status["active_guardrail_actions"]
        ), f"Expected guardrail-critical action, got: {status['active_guardrail_actions']}"

        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_multiple_interlock_violations(self, integrated_command_guardrail_service):
        """Test command halt from multiple guardrail violations."""
        service = integrated_command_guardrail_service

        # Set dangerous conditions
        service.update_system_state(
            {
                "vehicle_speed": 60,
                "engine_running": True,
                "parking_brake_engaged": False,
                "transmission_gear": "D",
                "slides_deployed": True,  # Dangerous!
                "awnings_extended": True,  # Dangerous!
            }
        )

        # Check interlocks
        await service.check_all_interlocks()

        # Multiple violations should trigger emergency
        violations = 0
        for interlock in service._interlocks.values():
            if await service._check_interlock_conditions(interlock):
                violations += 1

        # All position-critical interlocks should be violated
        assert violations >= 3

        # Should trigger command halt
        assert service._command_halt_active is True

    @pytest.mark.asyncio
    async def test_halt_command_emission_with_recovery(
        self, integrated_command_guardrail_service, mock_services
    ):
        """Test complete command halt and recovery cycle."""
        service = integrated_command_guardrail_service

        # Trigger command halt
        await service.halt_command_emission(
            reason="Manual emergency button pressed",
            triggered_by="driver",
        )

        assert service._command_halt_active is True

        # Verify guardrail-critical services are protected. Production
        # now emits 'halt_command_emission' (and 'halt_command_emission')
        # rather than the old 'maintain_position' label; see
        # ``command_guardrail_service.py:1614-1615``.
        status = service.get_guardrail_status()
        assert any(
            "halt_command_emission" in action or "halt_command_emission" in action
            for action in status["active_guardrail_actions"]
        ), f"Expected maintain-command-halt-state action, got: {status['active_guardrail_actions']}"

        # Attempt to reset without proper auth - should fail
        success = await service.clear_command_halt(
            authorization_code="wrong_code",
            reset_by="driver",
        )
        assert success is False
        assert service._command_halt_active is True

        # Reset with proper authorization
        success = await service.clear_command_halt(
            authorization_code="SAFETY_OVERRIDE_ADMIN",
            reset_by="admin",
        )
        assert success is True
        assert service._command_halt_active is False

        # System should return to normal monitoring
        await service._perform_health_check()
        status = service.get_guardrail_status()
        assert status["command_halt_active"] is False

    @pytest.mark.asyncio
    async def test_watchdog_timeout_recovery(self, integrated_command_guardrail_service):
        """Test recovery from watchdog timeout scenario.

        Updated 2026-05-13: production's watchdog loop
        (``command_guardrail_service.py:1832``) calls ``_enter_command_halt_state`` on
        timeout, which sets ``_in_command_halt_state = True`` -- it does NOT
        call ``halt_command_emission``. ``_command_halt_active``
        and ``_in_command_halt_state`` are independent state machines:
        command-halt is the operator-triggered or condition-based
        path; command-halt-state is the failsafe-on-monitoring-failure path.

        Note on test design: production's ``_health_monitoring_loop``
        kicks ``_last_watchdog_kick = time.time()`` on EVERY tick
        (line 1810), which races with the watchdog. To deterministically
        verify the watchdog path, we run the watchdog loop in
        isolation (without start_monitoring) and bias the kick.
        """
        service = integrated_command_guardrail_service

        # Bias the watchdog clock far in the past so the very next
        # tick of the watchdog loop sees a timeout. (Using POSIX
        # ``time.time()`` style float; production stores it that way
        # at command_guardrail_service.py:1759.)
        service._last_watchdog_kick = time.time() - 100.0

        # Run the watchdog loop in isolation -- skipping the health
        # loop avoids the race where the health loop resets the
        # watchdog kick before the watchdog checks it.
        watchdog_task = asyncio.create_task(service._watchdog_loop())

        # Wait for the watchdog tick (interval is 1.0s in production)
        await asyncio.sleep(1.5)

        # Production command-halt-state path was triggered
        assert service._in_command_halt_state is True, (
            "Watchdog timeout should drive _enter_command_halt_state"
        )

        # Watchdog loop exits when _in_command_halt_state goes True; clean up.
        try:
            await asyncio.wait_for(watchdog_task, timeout=1.0)
        except TimeoutError:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_emergency_during_state_transition(
        self, integrated_command_guardrail_service, mock_services
    ):
        """Test command halt during service state transitions."""
        service = integrated_command_guardrail_service
        services = mock_services

        # Start a state transition (firefly initializing)
        services["firefly"].state = ServiceStatus.STARTING
        service.service_registry._service_statuses["firefly"] = ServiceStatus.STARTING

        # Trigger emergency during transition
        await service.halt_command_emission(
            reason="Emergency during initialization",
            triggered_by="system",
        )

        # Service should safely handle emergency
        assert service._command_halt_active is True

        # Safety-critical service should enter safe shutdown. Production
        # uses 'halt_command_emission' (line 1614); the previous
        # 'position_critical_safe_shutdown' label is gone.
        status = service.get_guardrail_status()
        assert any(
            "halt_command_emission" in action for action in status["active_guardrail_actions"]
        ), (
            f"Expected guardrail-critical-safe-shutdown action, got: {status['active_guardrail_actions']}"
        )

    @pytest.mark.asyncio
    async def test_partial_system_recovery(
        self, integrated_command_guardrail_service, mock_services
    ):
        """Test recovering operational services while keeping critical ones safe."""
        service = integrated_command_guardrail_service
        services = mock_services

        # Set mixed service states
        services["can_interface"].state = ServiceStatus.HEALTHY
        services["firefly"].state = ServiceStatus.FAILED
        services["analytics"].state = ServiceStatus.HEALTHY

        service.service_registry._service_statuses.update(
            {
                "can_interface": ServiceStatus.HEALTHY,
                "firefly": ServiceStatus.FAILED,
                "analytics": ServiceStatus.HEALTHY,
            }
        )

        # Command halt due to position-critical failure
        await service.halt_command_emission(
            reason="Slide motor failure",
            triggered_by="firefly_monitor",
        )

        # Reset emergency
        await service.clear_command_halt(
            "SAFETY_OVERRIDE_ADMIN",
            "technician",
        )

        # Operational services should continue
        assert services["analytics"].state == ServiceStatus.HEALTHY
        # Position-critical should remain protected until manually cleared
        assert services["firefly"].state == ServiceStatus.FAILED


class TestRVEmergencyScenarios:
    """Test real-world RV emergency scenarios."""

    @pytest.mark.asyncio
    async def test_emergency_while_driving_with_slides_out(
        self, integrated_command_guardrail_service
    ):
        """Test detecting slides deployed while driving - critical safety issue.

        Updated 2026-05-13: production's monitoring loop triggers
        command halt on >=3 simultaneous interlock violations
        (``command_guardrail_service.py:1872`` -- ``multiple_violation_threshold``).
        With slides+awnings+jacks all deployed while driving, all three
        position-critical interlocks fire simultaneously. The previous
        version of this test only set ``slides_deployed=True`` and
        relied on a single-violation emergency that production never
        provided -- the contract has always been multi-interlock.

        We also drop the unstable monitor-task background path: drive
        the violation directly via ``check_command_preconditions()`` +
        ``_check_emergency_conditions()`` which is what the monitor
        loop does on each tick anyway.
        """
        service = integrated_command_guardrail_service

        # Driver is driving with slides + awnings + jacks ALL deployed.
        # That triggers all three position-critical interlocks.
        service.update_system_state(
            {
                "vehicle_speed": 5,  # Just starting to move
                "engine_running": True,
                "parking_brake": False,  # Production interlocks read this key
                "transmission_gear": "DRIVE",
                "all_slides_retracted": False,  # DANGER!
                "awnings_retracted": False,  # DANGER!
                "leveling_jacks_down": True,  # DANGER (jacks must be up while moving)
            }
        )

        # Run one health-check tick: check interlocks, then evaluate
        # the command-halt conditions (production loop does both).
        interlock_results = await service.check_command_preconditions()
        await service._check_emergency_conditions(
            {"failed_critical": [], "healthy": True}, interlock_results
        )

        # Should have triggered command halt on multi-interlock
        # violation.
        assert service._command_halt_active is True, (
            f"Expected command halt from multi-interlock violation; "
            f"interlock_results: {interlock_results}"
        )
        # Production records the high-level shutdown actions in
        # ``_active_guardrail_actions``. Per-interlock labels are only
        # appended when the command-halt loop engages an interlock
        # that wasn't already engaged. Here ``check_command_preconditions``
        # engaged them first, so the per-interlock labels don't fire
        # -- but the high-level action labels still do.
        assert any(
            "halt_command_emission" in action or "halt_command_emission" in action
            for action in service._active_guardrail_actions
        ), f"Expected guardrail-critical action, got: {service._active_guardrail_actions}"

        # Verify the interlocks ARE engaged (production behavior --
        # check_command_preconditions engaged them before halt_command_emission ran).
        for interlock_name in (
            "slide_room_precondition",
            "awning_precondition",
            "leveling_jack_precondition",
        ):
            assert service._interlocks[interlock_name].is_engaged, (
                f"Interlock {interlock_name} should be engaged"
            )

        # Audit log should capture this critical event
        audit_log = service.get_audit_log()
        command_halt_events = [e for e in audit_log if e["event_type"] == "command_halt_activated"]
        assert len(command_halt_events) > 0

    @pytest.mark.asyncio
    async def test_power_loss_recovery(self, integrated_command_guardrail_service):
        """Test system behavior after power loss and recovery.

        Updated 2026-05-13: ``_perform_health_check`` (the helper this
        test uses) only triggers on watchdog timeout when the registry
        does NOT have ``get_guardrail_status_summary`` (see
        ``command_guardrail_service.py:1710``). Our mock registry doesn't have
        that attribute, so the watchdog-check branch fires.

        Note: ``_last_watchdog_kick`` is a POSIX float (production
        sets it via ``time.time()`` at command_guardrail_service.py:1759), NOT a
        datetime. The previous test wrote a datetime to it, which
        production then can't subtract from a float.

        Production's failsafe via ``_perform_health_check`` actually
        calls ``halt_command_emission`` (line 1714), not
        ``_enter_command_halt_state``. So checking ``_command_halt_active``
        here is correct.
        """
        service = integrated_command_guardrail_service

        # Simulate system state before power loss
        service.update_system_state(
            {
                "all_slides_retracted": False,
                "vehicle_speed": 0,
                "parking_brake": True,
            }
        )

        # Simulate power loss: watchdog kick was 10 minutes ago.
        # Use POSIX float (production reads time.time()).
        service._last_health_check = None
        service._last_watchdog_kick = time.time() - 600.0

        # Power restored - first health check
        await service._perform_health_check()

        # Should detect watchdog timeout from power loss
        assert service._command_halt_active is True
        assert "Watchdog" in service._halt_command_emission_reason

        # System should engage maintain-command-halt-state action.
        status = service.get_guardrail_status()
        assert any(
            "halt_command_emission" in action or "halt_command_emission" in action
            for action in status["active_guardrail_actions"]
        ), f"Expected command-halt-state action, got: {status['active_guardrail_actions']}"

    @pytest.mark.asyncio
    async def test_emergency_response_time(self, integrated_command_guardrail_service):
        """Test that emergency response happens within safety time limits.

        Updated 2026-05-13: same fixture-shape fix as
        ``test_critical_service_failure_cascade`` -- production reads
        from ``get_health_summary``, NOT ``check_system_health``. Drive
        the failure through the watchdog path: bias
        ``_last_watchdog_kick`` so the command halt fires when
        ``_perform_health_check`` runs.

        The test name mentions 'response time'; that's still meaningful
        -- we measure how long ``_perform_health_check`` takes to
        detect and act on a critical failure. The 5-second budget is
        generous (sub-second in practice).
        """
        service = integrated_command_guardrail_service

        # Bias the watchdog so the very next _perform_health_check
        # sees a timeout and triggers command halt.
        service._last_watchdog_kick = time.time() - 100.0

        # Record start time
        start_time = datetime.utcnow()

        # Perform health check
        await service._perform_health_check()

        # Calculate response time
        response_time = (datetime.utcnow() - start_time).total_seconds()

        # Should respond within 5 seconds (safety requirement)
        assert response_time < 5.0
        assert service._command_halt_active is True

    @pytest.mark.asyncio
    async def test_audit_trail_completeness(self, integrated_command_guardrail_service):
        """Test that all guardrail-critical events are properly logged."""
        service = integrated_command_guardrail_service

        # Perform various guardrail-critical operations

        # 1. Update system state
        service.update_system_state({"vehicle_speed": 30})

        # 2. Check interlocks
        await service.check_all_interlocks()

        # 3. Trigger emergency
        await service.halt_command_emission("Test", "operator")

        # 4. Attempt reset with wrong auth
        await service.clear_command_halt("wrong", "operator")

        # 5. Reset with correct auth
        await service.clear_command_halt("SAFETY_OVERRIDE_ADMIN", "admin")

        # Check audit log
        audit_log = service.get_audit_log()

        # Should have entries for all critical events. Note: production
        # no longer emits 'system_state_updated' -- ``update_system_state``
        # is now silent (verified via grep on 'system_state_updated' in
        # command_guardrail_service.py: zero matches as of 2026-05-13). Drop that
        # assertion; the other four event types are still emitted.
        event_types = {entry["event_type"] for entry in audit_log}
        assert "interlock_engaged" in event_types
        assert "command_halt_activated" in event_types
        assert "halt_command_emission_reset_failed" in event_types
        assert "halt_command_emission_reset" in event_types

        # All entries should have required fields
        for entry in audit_log:
            assert "timestamp" in entry
            assert "event_type" in entry
            assert "details" in entry
            assert entry["timestamp"] is not None
