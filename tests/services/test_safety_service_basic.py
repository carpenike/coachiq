"""
Basic tests for SafetyService implementation.

Tests core safety functionality without complex mocking.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services.feature_models import FeatureState, SafetyClassification
from backend.services.safety_service import SafetyInterlock, SafetyService


@pytest.fixture
def mock_feature_manager():
    """Create a basic mock feature manager."""
    manager = Mock()
    manager.features = {}
    manager.check_system_health = AsyncMock(return_value={
        "status": "healthy",
        "features": {},
        "failed_critical": []
    })
    manager.get_feature = Mock(return_value=None)
    return manager


@pytest.fixture
def safety_service(mock_feature_manager):
    """Create a SafetyService instance."""
    return SafetyService(
        feature_manager=mock_feature_manager,
        health_check_interval=1.0,
        watchdog_timeout=3.0,
    )


class TestSafetyServiceBasics:
    """Test basic SafetyService functionality."""

    def test_initialization(self, safety_service):
        """Test SafetyService initializes correctly."""
        assert safety_service.health_check_interval == 1.0
        assert safety_service.watchdog_timeout == 3.0
        assert safety_service._emergency_stop_active is False
        assert len(safety_service._interlocks) == 3

        # Verify default system state is safe
        state = safety_service._system_state
        assert state["vehicle_speed"] == 0.0
        assert state["parking_brake"] is True
        assert state["leveling_jacks_down"] is True
        assert state["engine_running"] is False
        assert state["transmission_gear"] == "PARK"
        assert state["all_slides_retracted"] is True

    @pytest.mark.asyncio
    async def test_initialization_no_emergency_stop(self, safety_service):
        """Test that initialization state doesn't trigger emergency stop."""
        # Check all interlocks with initial state
        results = await safety_service.check_safety_interlocks()

        # All interlocks should be satisfied
        for name, (satisfied, reason) in results.items():
            assert satisfied, f"Interlock {name} not satisfied at startup: {reason}"

        # Verify no emergency stop
        assert not safety_service._emergency_stop_active
        assert not safety_service._in_safe_state

    def test_update_system_state(self, safety_service):
        """Test system state updates."""
        state = {
            "vehicle_speed": 30,
            "engine_running": True,
            "parking_brake": False,
        }
        safety_service.update_system_state(state)

        assert safety_service._system_state["vehicle_speed"] == 30
        assert safety_service._system_state["engine_running"] is True
        assert safety_service._system_state["parking_brake"] is False

    @pytest.mark.asyncio
    async def test_interlock_evaluation(self, safety_service):
        """Test interlock condition evaluation."""
        # Create a simple interlock
        interlock = SafetyInterlock(
            name="test_interlock",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving", "parking_brake_engaged"],
        )

        # Test unsafe condition
        system_state = {"vehicle_speed": 10, "parking_brake": False}
        conditions_met, reason = await interlock.check_conditions(system_state)
        assert conditions_met is False
        assert "vehicle_not_moving" in reason

        # Test safe condition
        system_state = {"vehicle_speed": 0, "parking_brake": True}
        conditions_met, reason = await interlock.check_conditions(system_state)
        assert conditions_met is True

    @pytest.mark.asyncio
    async def test_emergency_stop(self, safety_service):
        """Test emergency stop activation."""
        # Should start inactive
        assert safety_service._emergency_stop_active is False

        # Activate emergency stop
        await safety_service.emergency_stop("Test emergency")

        # Should now be active
        assert safety_service._emergency_stop_active is True
        assert safety_service._in_safe_state is True

        # Check audit log
        audit_log = safety_service.get_audit_log()
        assert any("emergency_stop" in entry["event_type"] for entry in audit_log)

    @pytest.mark.asyncio
    async def test_emergency_stop_reset(self, safety_service):
        """Test emergency stop reset."""
        # Activate emergency stop
        await safety_service.emergency_stop("Test")
        assert safety_service._emergency_stop_active is True

        # Try reset with wrong code
        success = await safety_service.reset_emergency_stop("WRONG", "user")
        assert success is False
        assert safety_service._emergency_stop_active is True

        # Reset with correct code
        success = await safety_service.reset_emergency_stop("SAFETY_OVERRIDE_ADMIN", "admin")
        assert success is True
        assert safety_service._emergency_stop_active is False

    def test_audit_log(self, safety_service):
        """Test audit log functionality."""
        # Add some audit entries
        for i in range(5):
            safety_service._audit_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": f"test_event_{i}",
                "details": {"index": i}
            })

        # Get recent entries
        log = safety_service.get_audit_log(max_entries=3)
        assert len(log) == 3
        assert log[-1]["event_type"] == "test_event_4"

    def test_safety_status(self, safety_service):
        """Test getting safety status."""
        # Set some state
        safety_service._emergency_stop_active = True
        safety_service._last_watchdog_kick = 123456.0

        # Get status
        status = safety_service.get_safety_status()

        assert status["emergency_stop_active"] is True
        assert status["watchdog_timeout"] == 3.0
        assert "interlocks" in status
        assert len(status["interlocks"]) == 3

    @pytest.mark.asyncio
    async def test_check_safety_interlocks(self, safety_service):
        """Test checking all safety interlocks."""
        # Set vehicle moving
        safety_service.update_system_state({
            "vehicle_speed": 30,
            "parking_brake": False,
            "engine_running": True,
        })

        # Check interlocks
        results = await safety_service.check_safety_interlocks()

        # All should fail (vehicle moving)
        for interlock_name, (conditions_met, reason) in results.items():
            assert conditions_met is False
            assert "vehicle_not_moving" in reason

    @pytest.mark.asyncio
    async def test_monitoring_tasks(self, safety_service):
        """Test starting and stopping monitoring tasks."""
        # Start monitoring
        await safety_service.start_monitoring()

        assert safety_service._health_monitor_task is not None
        assert safety_service._watchdog_task is not None

        # Stop monitoring
        await safety_service.stop_monitoring()

        assert safety_service._health_monitor_task is None
        assert safety_service._watchdog_task is None


class TestSafetyInterlocks:
    """Test safety interlock functionality."""

    @pytest.mark.asyncio
    async def test_interlock_engagement(self):
        """Test interlock engagement and disengagement."""
        interlock = SafetyInterlock(
            name="test",
            feature_name="test_feature",
            interlock_conditions=["vehicle_not_moving"],
        )

        # Should start disengaged
        assert interlock.is_engaged is False

        # Engage
        await interlock.engage("Test reason")
        assert interlock.is_engaged is True
        assert interlock.engagement_reason == "Test reason"
        assert interlock.engagement_time is not None

        # Disengage
        await interlock.disengage("All clear")
        assert interlock.is_engaged is False
        assert interlock.engagement_time is None

    @pytest.mark.asyncio
    async def test_interlock_conditions(self):
        """Test various interlock conditions."""
        interlock = SafetyInterlock(
            name="complex",
            feature_name="test",
            interlock_conditions=[
                "vehicle_not_moving",
                "parking_brake_engaged",
                "engine_not_running",
                "transmission_in_park",
            ],
        )

        # All conditions must be met
        test_cases = [
            ({"vehicle_speed": 0, "parking_brake": True, "engine_running": False, "transmission_gear": "PARK"}, True),
            ({"vehicle_speed": 5, "parking_brake": True, "engine_running": False, "transmission_gear": "PARK"}, False),
            ({"vehicle_speed": 0, "parking_brake": False, "engine_running": False, "transmission_gear": "PARK"}, False),
            ({"vehicle_speed": 0, "parking_brake": True, "engine_running": True, "transmission_gear": "PARK"}, False),
            ({"vehicle_speed": 0, "parking_brake": True, "engine_running": False, "transmission_gear": "D"}, False),
        ]

        for state, expected in test_cases:
            conditions_met, _ = await interlock.check_conditions(state)
            assert conditions_met == expected, f"Failed for state: {state}"
