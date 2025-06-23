"""
Integration tests for emergency stop scenarios in the safety system.

Tests comprehensive emergency scenarios including cascading failures,
recovery procedures, and real-world RV emergency situations.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.core.service_registry import ServiceStatus
from backend.services.safety_service import SafetyService


class MockService:
    """Mock service for testing."""

    def __init__(self, name, safety_classification=None, **kwargs):
        self.name = name
        self.safety_classification = safety_classification
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
            safety_classification="critical",
        ),
        "firefly": MockService(
            name="firefly",
            safety_classification="position_critical",
        ),
        "spartan_k2": MockService(
            name="spartan_k2",
            safety_classification="position_critical",
        ),
        "analytics": MockService(
            name="analytics",
            safety_classification="operational",
        ),
    }
    return services


@pytest.fixture
def service_registry_with_safety(mock_services):
    """Create a service registry with safety services."""
    registry = Mock()
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

    return registry


@pytest.fixture
def integrated_safety_service(service_registry_with_safety):
    """Create SafetyService integrated with service registry."""
    service = SafetyService(
        service_registry=service_registry_with_safety,
        health_check_interval=0.5,  # Fast for testing
        watchdog_timeout=2.0,
    )
    return service


class TestEmergencyStopScenarios:
    """Test emergency stop scenarios with full system integration."""

    @pytest.mark.asyncio
    async def test_critical_service_failure_cascade(self, integrated_safety_service, mock_services):
        """Test cascading failure from critical service."""
        service = integrated_safety_service
        services = mock_services

        # Start monitoring
        monitor_task = asyncio.create_task(service.start_monitoring())
        await asyncio.sleep(0.1)  # Let monitoring start

        # Simulate CAN interface failure
        services["can_interface"].state = ServiceStatus.FAILED
        service._service_registry._service_statuses["can_interface"] = ServiceStatus.FAILED

        # Update health check to return failure
        service._service_registry.check_system_health.return_value = {
            "status": "critical",
            "services": service._service_registry._service_statuses,
            "failed_critical": ["can_interface"],
        }

        # Wait for health check to detect failure
        await asyncio.sleep(0.6)

        # Should trigger emergency stop
        assert service._emergency_stop_active is True
        assert "can_interface" in service._emergency_stop_reason

        # Position-critical services should be in safe shutdown
        status = await service.get_safety_status()
        assert "position_critical_safe_shutdown" in status["active_safety_actions"]

        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_multiple_interlock_violations(self, integrated_safety_service):
        """Test emergency stop from multiple safety violations."""
        service = integrated_safety_service

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
        for interlock in service._interlocks:
            if await service._check_interlock_conditions(interlock):
                violations += 1

        # All position-critical interlocks should be violated
        assert violations >= 3

        # Should trigger emergency stop
        assert service._emergency_stop_active is True

    @pytest.mark.asyncio
    async def test_emergency_stop_with_recovery(self, integrated_safety_service, mock_services):
        """Test complete emergency stop and recovery cycle."""
        service = integrated_safety_service

        # Trigger emergency stop
        await service.trigger_emergency_stop(
            reason="Manual emergency button pressed",
            triggered_by="driver",
        )

        assert service._emergency_stop_active is True

        # Verify position-critical services are protected
        status = await service.get_safety_status()
        assert "maintain_position" in str(status["active_safety_actions"])

        # Attempt to reset without proper auth - should fail
        success = await service.reset_emergency_stop(
            authorization_code="wrong_code",
            reset_by="driver",
        )
        assert success is False
        assert service._emergency_stop_active is True

        # Reset with proper authorization
        success = await service.reset_emergency_stop(
            authorization_code="SAFETY_OVERRIDE_ADMIN",
            reset_by="admin",
        )
        assert success is True
        assert service._emergency_stop_active is False

        # System should return to normal monitoring
        await service._perform_health_check()
        status = await service.get_safety_status()
        assert status["emergency_stop_active"] is False

    @pytest.mark.asyncio
    async def test_watchdog_timeout_recovery(self, integrated_safety_service):
        """Test recovery from watchdog timeout scenario."""
        service = integrated_safety_service

        # Start monitoring
        monitor_task = asyncio.create_task(service.start_monitoring())
        await asyncio.sleep(0.1)

        # Simulate watchdog timeout by not updating kick time
        service._last_watchdog_kick = datetime.utcnow() - timedelta(seconds=10)

        # Wait for watchdog check
        await asyncio.sleep(0.6)

        # Should trigger emergency stop
        assert service._emergency_stop_active is True
        assert "Watchdog timeout" in service._emergency_stop_reason

        # Reset emergency stop
        await service.reset_emergency_stop(
            "SAFETY_OVERRIDE_ADMIN",
            "technician",
        )

        # Monitoring should resume normally
        await asyncio.sleep(0.6)
        assert service._last_watchdog_kick > datetime.utcnow() - timedelta(seconds=1)

        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_emergency_during_state_transition(
        self, integrated_safety_service, mock_services
    ):
        """Test emergency stop during service state transitions."""
        service = integrated_safety_service
        services = mock_services

        # Start a state transition (firefly initializing)
        services["firefly"].state = ServiceStatus.STARTING
        service._service_registry._service_statuses["firefly"] = ServiceStatus.STARTING

        # Trigger emergency during transition
        await service.trigger_emergency_stop(
            reason="Emergency during initialization",
            triggered_by="system",
        )

        # Service should safely handle emergency
        assert service._emergency_stop_active is True

        # Position-critical service should enter safe shutdown
        status = await service.get_safety_status()
        assert "position_critical_safe_shutdown" in status["active_safety_actions"]

    @pytest.mark.asyncio
    async def test_partial_system_recovery(self, integrated_safety_service, mock_services):
        """Test recovering operational services while keeping critical ones safe."""
        service = integrated_safety_service
        services = mock_services

        # Set mixed service states
        services["can_interface"].state = ServiceStatus.HEALTHY
        services["firefly"].state = ServiceStatus.FAILED
        services["analytics"].state = ServiceStatus.HEALTHY

        service._service_registry._service_statuses.update(
            {
                "can_interface": ServiceStatus.HEALTHY,
                "firefly": ServiceStatus.FAILED,
                "analytics": ServiceStatus.HEALTHY,
            }
        )

        # Emergency stop due to position-critical failure
        await service.trigger_emergency_stop(
            reason="Slide motor failure",
            triggered_by="firefly_monitor",
        )

        # Reset emergency
        await service.reset_emergency_stop(
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
    async def test_emergency_while_driving_with_slides_out(self, integrated_safety_service):
        """Test detecting slides deployed while driving - critical safety issue."""
        service = integrated_safety_service

        # Initial safe state - parked
        service.update_system_state(
            {
                "vehicle_speed": 0,
                "engine_running": False,
                "slides_deployed": True,
                "parking_brake_engaged": True,
            }
        )

        # Start monitoring
        monitor_task = asyncio.create_task(service.start_monitoring())
        await asyncio.sleep(0.1)

        # Driver starts engine and begins driving with slides out!
        service.update_system_state(
            {
                "vehicle_speed": 5,  # Just starting to move
                "engine_running": True,
                "slides_deployed": True,  # DANGER!
                "parking_brake_engaged": False,
                "transmission_gear": "D",
            }
        )

        # Check interlocks immediately
        await service.check_all_interlocks()

        # Should immediately trigger emergency stop
        assert service._emergency_stop_active is True
        assert any("slide" in action.lower() for action in service._active_safety_actions)

        # Audit log should capture this critical event
        audit_log = service.get_audit_log()
        emergency_events = [e for e in audit_log if "emergency" in e["event_type"]]
        assert len(emergency_events) > 0

        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_power_loss_recovery(self, integrated_safety_service):
        """Test system behavior after power loss and recovery."""
        service = integrated_safety_service

        # Simulate system state before power loss
        service.update_system_state(
            {
                "slides_deployed": True,
                "awnings_extended": True,
                "jacks_deployed": True,
                "vehicle_speed": 0,
                "parking_brake_engaged": True,
            }
        )

        # Simulate power loss (reset service state)
        service._last_health_check = None
        service._last_watchdog_kick = datetime.utcnow() - timedelta(minutes=10)

        # Power restored - first health check
        await service._perform_health_check()

        # Should detect watchdog timeout from power loss
        assert service._emergency_stop_active is True

        # System should maintain position safety
        status = await service.get_safety_status()
        assert "maintain_position" in str(status["active_safety_actions"])

    @pytest.mark.asyncio
    async def test_emergency_response_time(self, integrated_safety_service):
        """Test that emergency response happens within safety time limits."""
        service = integrated_safety_service

        # Record start time
        start_time = datetime.utcnow()

        # Simulate critical failure
        service._service_registry.check_system_health.return_value = {
            "status": "critical",
            "services": {"can_interface": ServiceStatus.FAILED},
            "failed_critical": ["can_interface"],
        }

        # Perform health check
        await service._perform_health_check()

        # Calculate response time
        response_time = (datetime.utcnow() - start_time).total_seconds()

        # Should respond within 5 seconds (safety requirement)
        assert response_time < 5.0
        assert service._emergency_stop_active is True

    @pytest.mark.asyncio
    async def test_audit_trail_completeness(self, integrated_safety_service):
        """Test that all safety-critical events are properly logged."""
        service = integrated_safety_service

        # Perform various safety-critical operations

        # 1. Update system state
        service.update_system_state({"vehicle_speed": 30})

        # 2. Check interlocks
        await service.check_all_interlocks()

        # 3. Trigger emergency
        await service.trigger_emergency_stop("Test", "operator")

        # 4. Attempt reset with wrong auth
        await service.reset_emergency_stop("wrong", "operator")

        # 5. Reset with correct auth
        await service.reset_emergency_stop("SAFETY_OVERRIDE_ADMIN", "admin")

        # Check audit log
        audit_log = service.get_audit_log()

        # Should have entries for all critical events
        event_types = {entry["event_type"] for entry in audit_log}
        assert "system_state_updated" in event_types
        assert "interlock_engaged" in event_types
        assert "emergency_stop_triggered" in event_types
        assert "emergency_stop_reset_failed" in event_types
        assert "emergency_stop_reset" in event_types

        # All entries should have required fields
        for entry in audit_log:
            assert "timestamp" in entry
            assert "event_type" in entry
            assert "details" in entry
            assert entry["timestamp"] is not None
