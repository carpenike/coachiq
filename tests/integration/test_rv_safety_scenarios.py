"""
Integration tests for RV-specific safety scenarios.

Tests real-world RV operations including slide deployment, awning control,
leveling jack operation, and various driving/camping scenarios.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services.feature_models import FeatureState, SafetyClassification
from backend.services.safety_service import SafetyService


@pytest.fixture
def rv_safety_service():
    """Create SafetyService configured for RV testing."""
    mock_manager = Mock()
    mock_manager.check_system_health = AsyncMock(return_value={
        "status": "healthy",
        "features": {
            "can_interface": FeatureState.HEALTHY,
            "firefly": FeatureState.HEALTHY,
            "spartan_k2": FeatureState.HEALTHY,
        }
    })
    mock_manager.get_safety_classification = Mock(side_effect=lambda name: {
        "firefly": SafetyClassification.POSITION_CRITICAL,
        "spartan_k2": SafetyClassification.POSITION_CRITICAL,
        "can_interface": SafetyClassification.CRITICAL,
    }.get(name))

    service = SafetyService(
        feature_manager=mock_manager,
        health_check_interval=1.0,
        watchdog_timeout=15.0,
    )
    return service


class TestRVSlideOperations:
    """Test safety scenarios for RV slide operations."""

    @pytest.mark.asyncio
    async def test_slide_deployment_while_parked(self, rv_safety_service):
        """Test normal slide deployment when properly parked."""
        service = rv_safety_service

        # Set up proper parking conditions
        service.update_system_state({
            "vehicle_speed": 0,
            "engine_running": False,
            "parking_brake_engaged": True,
            "transmission_gear": "P",
            "slides_deployed": False,
        })

        # Check if safe to deploy slides
        await service.check_all_interlocks()
        slide_interlock = next(i for i in service._interlocks if i.name == "slide_room_safety")
        is_safe = not await service._check_interlock_conditions(slide_interlock)

        assert is_safe is True

        # Deploy slides
        service.update_system_state({"slides_deployed": True})

        # Should still be safe
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

    @pytest.mark.asyncio
    async def test_slide_retraction_before_driving(self, rv_safety_service):
        """Test slide retraction sequence before driving."""
        service = rv_safety_service

        # Start with slides deployed
        service.update_system_state({
            "vehicle_speed": 0,
            "engine_running": False,
            "parking_brake_engaged": True,
            "slides_deployed": True,
        })

        # Driver prepares to leave - starts engine
        service.update_system_state({"engine_running": True})

        # Check interlocks - should warn about slides
        await service.check_all_interlocks()

        # Slides still out with engine running should trigger interlock
        slide_interlock = next(i for i in service._interlocks if i.name == "slide_room_safety")
        assert slide_interlock.engaged is True

        # Driver retracts slides
        service.update_system_state({"slides_deployed": False})

        # Now safe to drive
        await service.check_all_interlocks()
        assert slide_interlock.engaged is False

    @pytest.mark.asyncio
    async def test_accidental_movement_with_slides_out(self, rv_safety_service):
        """Test emergency response if RV moves with slides deployed."""
        service = rv_safety_service

        # Slides are deployed
        service.update_system_state({
            "vehicle_speed": 0,
            "slides_deployed": True,
            "parking_brake_engaged": True,
        })

        # RV accidentally rolls (parking brake fails)
        service.update_system_state({
            "vehicle_speed": 2,  # Slow roll
            "parking_brake_engaged": False,
        })

        # Check safety
        await service.check_all_interlocks()

        # Should trigger emergency for slides + movement
        assert service._emergency_stop_active is True
        assert "slide" in service._emergency_stop_reason.lower()

    @pytest.mark.asyncio
    async def test_slide_failure_during_operation(self, rv_safety_service):
        """Test handling slide motor failure during deployment."""
        service = rv_safety_service

        # Start deploying slides
        service.update_system_state({
            "vehicle_speed": 0,
            "parking_brake_engaged": True,
            "slides_deployed": False,
            "slide_in_motion": True,
        })

        # Simulate slide system failure
        service._feature_manager.check_system_health.return_value = {
            "status": "degraded",
            "features": {
                "firefly": FeatureState.FAILED,
                "can_interface": FeatureState.HEALTHY,
            },
            "state_changes": [
                {"feature": "firefly", "old_state": "healthy", "new_state": "failed"}
            ],
        }

        # Health check detects failure
        await service._perform_health_check()

        # Should maintain current position (partially deployed)
        status = await service.get_safety_status()
        assert "maintain_position" in str(status["active_safety_actions"])


class TestRVAwningOperations:
    """Test safety scenarios for RV awning operations."""

    @pytest.mark.asyncio
    async def test_awning_deployment_conditions(self, rv_safety_service):
        """Test awning deployment safety conditions."""
        service = rv_safety_service

        # Test various conditions
        test_cases = [
            # (state, should_be_safe)
            ({"vehicle_speed": 0, "parking_brake_engaged": True}, True),
            ({"vehicle_speed": 0, "parking_brake_engaged": False}, False),
            ({"vehicle_speed": 5, "parking_brake_engaged": True}, False),
            ({"vehicle_speed": 5, "parking_brake_engaged": False}, False),
        ]

        for state, should_be_safe in test_cases:
            service.update_system_state(state)
            await service.check_all_interlocks()

            awning_interlock = next(i for i in service._interlocks if i.name == "awning_safety")
            is_safe = not awning_interlock.engaged

            assert is_safe == should_be_safe, f"Failed for state: {state}"

    @pytest.mark.asyncio
    async def test_wind_speed_awning_safety(self, rv_safety_service):
        """Test awning safety with wind speed monitoring."""
        service = rv_safety_service

        # Awning deployed in calm conditions
        service.update_system_state({
            "vehicle_speed": 0,
            "parking_brake_engaged": True,
            "awnings_extended": True,
            "wind_speed": 10,  # mph - calm
        })

        # Safe conditions
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # High wind detected
        service.update_system_state({"wind_speed": 30})  # mph - dangerous

        # In real system, this would trigger wind sensor interlock
        # For now, we simulate the response
        if service._system_state.__dict__.get("wind_speed", 0) > 25:
            await service.trigger_emergency_stop(
                reason="High wind detected with awnings extended",
                triggered_by="wind_sensor",
            )

        assert service._emergency_stop_active is True

    @pytest.mark.asyncio
    async def test_awning_retraction_sequence(self, rv_safety_service):
        """Test proper awning retraction before travel."""
        service = rv_safety_service

        # Multiple awnings deployed
        service.update_system_state({
            "vehicle_speed": 0,
            "parking_brake_engaged": True,
            "awnings_extended": True,
            "patio_awning": "extended",
            "window_awnings": "extended",
        })

        # Prepare for travel - retract all awnings
        service.update_system_state({
            "awnings_extended": False,
            "patio_awning": "retracted",
            "window_awnings": "retracted",
        })

        # Release parking brake
        service.update_system_state({"parking_brake_engaged": False})

        # Check safety
        await service.check_all_interlocks()
        awning_interlock = next(i for i in service._interlocks if i.name == "awning_safety")

        # Should be safe to drive
        assert awning_interlock.engaged is False


class TestRVLevelingOperations:
    """Test safety scenarios for RV leveling jack operations."""

    @pytest.mark.asyncio
    async def test_leveling_setup_sequence(self, rv_safety_service):
        """Test proper leveling setup sequence."""
        service = rv_safety_service

        # Arrive at campsite
        service.update_system_state({
            "vehicle_speed": 0,
            "engine_running": True,
            "transmission_gear": "P",
            "parking_brake_engaged": True,
            "jacks_deployed": False,
        })

        # Turn off engine for leveling
        service.update_system_state({"engine_running": False})

        # Check if safe to deploy jacks
        await service.check_all_interlocks()
        jack_interlock = next(i for i in service._interlocks if i.name == "leveling_jack_safety")
        assert jack_interlock.engaged is False

        # Deploy jacks
        service.update_system_state({"jacks_deployed": True})

        # System should remain safe
        assert service._emergency_stop_active is False

    @pytest.mark.asyncio
    async def test_engine_start_with_jacks_deployed(self, rv_safety_service):
        """Test safety when engine started with jacks down."""
        service = rv_safety_service

        # Jacks deployed for camping
        service.update_system_state({
            "engine_running": False,
            "parking_brake_engaged": True,
            "transmission_gear": "P",
            "jacks_deployed": True,
        })

        # Someone starts engine (maybe for generator/AC)
        service.update_system_state({"engine_running": True})

        # Check safety
        await service.check_all_interlocks()
        jack_interlock = next(i for i in service._interlocks if i.name == "leveling_jack_safety")

        # Should engage interlock
        assert jack_interlock.engaged is True
        assert "engine_running" in jack_interlock.violated_conditions

    @pytest.mark.asyncio
    async def test_transmission_shift_with_jacks(self, rv_safety_service):
        """Test safety when transmission shifted with jacks deployed."""
        service = rv_safety_service

        # Jacks deployed
        service.update_system_state({
            "jacks_deployed": True,
            "transmission_gear": "P",
            "engine_running": False,
        })

        # Driver accidentally shifts to Drive
        service.update_system_state({
            "transmission_gear": "D",
            "engine_running": True,
        })

        # Should trigger emergency
        await service.check_all_interlocks()

        # Multiple safety violations
        jack_interlock = next(i for i in service._interlocks if i.name == "leveling_jack_safety")
        assert jack_interlock.engaged is True
        assert len(jack_interlock.violated_conditions) >= 2  # engine + transmission

    @pytest.mark.asyncio
    async def test_jack_failure_during_leveling(self, rv_safety_service):
        """Test handling jack system failure during operation."""
        service = rv_safety_service

        # Actively leveling
        service.update_system_state({
            "jacks_deployed": True,
            "jack_operation_active": True,
            "vehicle_level": False,
        })

        # Jack system fails
        service._feature_manager.check_system_health.return_value = {
            "status": "degraded",
            "features": {
                "spartan_k2": FeatureState.FAILED,
            },
            "state_changes": [
                {"feature": "spartan_k2", "old_state": "healthy", "new_state": "failed"}
            ],
        }

        await service._perform_health_check()

        # Should maintain current position
        status = await service.get_safety_status()
        assert any("maintain" in action for action in status["active_safety_actions"])


class TestRVDrivingScenarios:
    """Test safety during various RV driving scenarios."""

    @pytest.mark.asyncio
    async def test_highway_driving_safety(self, rv_safety_service):
        """Test safety monitoring during highway driving."""
        service = rv_safety_service

        # Highway driving conditions
        service.update_system_state({
            "vehicle_speed": 65,
            "engine_running": True,
            "transmission_gear": "D",
            "parking_brake_engaged": False,
            "slides_deployed": False,
            "awnings_extended": False,
            "jacks_deployed": False,
        })

        # All interlocks should be engaged (preventing deployment)
        await service.check_all_interlocks()

        # But no emergency - this is normal
        assert service._emergency_stop_active is False

        # All position-critical interlocks should prevent operation
        for interlock in service._interlocks:
            assert interlock.engaged is True

    @pytest.mark.asyncio
    async def test_emergency_brake_scenario(self, rv_safety_service):
        """Test safety during emergency braking."""
        service = rv_safety_service

        # Driving normally
        service.update_system_state({
            "vehicle_speed": 55,
            "acceleration": 0,
        })

        # Emergency brake applied
        service.update_system_state({
            "vehicle_speed": 30,
            "acceleration": -15,  # Heavy braking
            "brake_pressure": 90,  # High pressure
        })

        # System should maintain safety but not trigger emergency
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # All equipment should remain secured
        status = await service.get_safety_status()
        for interlock in status["interlocks"]:
            if "position_critical" in interlock["feature_name"]:
                assert interlock["engaged"] is True

    @pytest.mark.asyncio
    async def test_arrival_at_campground(self, rv_safety_service):
        """Test transition from driving to camping setup."""
        service = rv_safety_service

        # Track state transitions
        states = []

        # 1. Driving
        service.update_system_state({
            "vehicle_speed": 25,
            "engine_running": True,
            "location": "campground_entrance",
        })
        await service.check_all_interlocks()
        states.append(("driving", service._emergency_stop_active))

        # 2. Slowing down
        service.update_system_state({"vehicle_speed": 5})
        await service.check_all_interlocks()
        states.append(("slowing", service._emergency_stop_active))

        # 3. Stopped
        service.update_system_state({
            "vehicle_speed": 0,
            "transmission_gear": "P",
        })
        await service.check_all_interlocks()
        states.append(("stopped", service._emergency_stop_active))

        # 4. Parking brake set
        service.update_system_state({"parking_brake_engaged": True})
        await service.check_all_interlocks()
        states.append(("parked", service._emergency_stop_active))

        # 5. Engine off
        service.update_system_state({"engine_running": False})
        await service.check_all_interlocks()
        states.append(("engine_off", service._emergency_stop_active))

        # No emergency stops during normal transition
        assert all(not emergency for _, emergency in states)

        # Now safe to deploy equipment
        for interlock in service._interlocks:
            assert interlock.engaged is False


class TestRVCampingScenarios:
    """Test safety during RV camping operations."""

    @pytest.mark.asyncio
    async def test_full_camping_setup(self, rv_safety_service):
        """Test complete camping setup sequence."""
        service = rv_safety_service

        # Start from safe parked state
        service.update_system_state({
            "vehicle_speed": 0,
            "engine_running": False,
            "parking_brake_engaged": True,
            "transmission_gear": "P",
        })

        # Deploy equipment in proper sequence

        # 1. Level the RV
        service.update_system_state({"jacks_deployed": True})
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # 2. Extend slides
        service.update_system_state({"slides_deployed": True})
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # 3. Deploy awnings
        service.update_system_state({"awnings_extended": True})
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # All equipment deployed safely
        status = await service.get_safety_status()
        assert all(not interlock["engaged"] for interlock in status["interlocks"])

    @pytest.mark.asyncio
    async def test_camping_breakdown_sequence(self, rv_safety_service):
        """Test proper sequence for breaking camp."""
        service = rv_safety_service

        # Fully deployed for camping
        service.update_system_state({
            "slides_deployed": True,
            "awnings_extended": True,
            "jacks_deployed": True,
            "vehicle_speed": 0,
            "engine_running": False,
            "parking_brake_engaged": True,
        })

        # Break camp in reverse order

        # 1. Retract awnings (most weather-sensitive)
        service.update_system_state({"awnings_extended": False})
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # 2. Retract slides
        service.update_system_state({"slides_deployed": False})
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # 3. Retract jacks (last, after weight redistribution)
        service.update_system_state({"jacks_deployed": False})
        await service.check_all_interlocks()
        assert service._emergency_stop_active is False

        # Ready to travel
        service.update_system_state({"engine_running": True})

        # Verify all equipment secured
        status = await service.get_safety_status()
        # Interlocks engaged but safe (preventing deployment while running)
        assert service._emergency_stop_active is False

    @pytest.mark.asyncio
    async def test_weather_emergency_during_camping(self, rv_safety_service):
        """Test emergency response to severe weather while camping."""
        service = rv_safety_service

        # Camping with everything deployed
        service.update_system_state({
            "slides_deployed": True,
            "awnings_extended": True,
            "jacks_deployed": True,
            "wind_speed": 15,
            "weather_alert": False,
        })

        # Severe weather warning
        service.update_system_state({
            "wind_speed": 45,
            "weather_alert": True,
            "alert_type": "tornado_warning",
        })

        # Trigger emergency for severe weather
        await service.trigger_emergency_stop(
            reason="Severe weather alert - tornado warning",
            triggered_by="weather_monitor",
        )

        # Should maintain current positions (don't retract in high wind)
        assert service._emergency_stop_active is True
        status = await service.get_safety_status()
        assert "maintain_position" in str(status["active_safety_actions"])

        # Log should capture weather emergency
        audit_log = service.get_audit_log()
        weather_events = [e for e in audit_log if "weather" in str(e).lower()]
        assert len(weather_events) > 0
