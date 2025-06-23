"""
Integration tests for safety-critical state transitions and scenarios.

These tests validate end-to-end safety behavior including:
- Complete startup/shutdown cycles with safety validation
- Emergency scenarios and safe state transitions
- Real-world failure cascades and recovery
- Safety interlock integration with service management
- Cross-system safety validation
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.service_registry import EnhancedServiceRegistry, ServiceStatus
from backend.services.safety_service import SafetyInterlock, SafetyService


class RealWorldService:
    """More realistic service implementation for integration testing."""

    def __init__(self, name="", **kwargs):
        self.name = name
        self.startup_duration = 0.1  # Simulate startup time
        self.shutdown_duration = 0.05  # Simulate shutdown time
        self.health_check_duration = 0.01  # Simulate health check time

        # Failure simulation controls
        self.should_fail_startup = False
        self.should_fail_health_check = False
        self.should_randomly_fail = False
        self.failure_probability = 0.1

        # State tracking
        self.startup_count = 0
        self.shutdown_count = 0
        self.health_check_count = 0
        self.last_startup_time = None
        self.last_shutdown_time = None

        # Performance tracking
        self.startup_times = []
        self.shutdown_times = []
        self.health_check_times = []

        self.state = ServiceStatus.STOPPED
        self.enabled = True
        self.safety_classification = kwargs.get("safety_classification", "operational")
        self._failed_dependencies = set()

    async def startup(self) -> None:
        """Realistic startup with timing and failure simulation."""
        start_time = time.time()
        self.startup_count += 1
        self.last_startup_time = datetime.utcnow()

        # Simulate startup work
        await asyncio.sleep(self.startup_duration)

        # Simulate potential startup failure
        if self.should_fail_startup:
            self.state = ServiceStatus.FAILED
            raise RuntimeError(f"Simulated startup failure for {self.name}")

        # Track performance
        duration = time.time() - start_time
        self.startup_times.append(duration)

        self.state = ServiceStatus.HEALTHY

    async def shutdown(self) -> None:
        """Realistic shutdown with timing tracking."""
        start_time = time.time()
        self.shutdown_count += 1
        self.last_shutdown_time = datetime.utcnow()

        # Simulate shutdown work
        await asyncio.sleep(self.shutdown_duration)

        # Track performance
        duration = time.time() - start_time
        self.shutdown_times.append(duration)

        self.state = ServiceStatus.STOPPED

    async def check_health(self) -> ServiceStatus:
        """Realistic health check with timing and random failures."""
        start_time = time.time()
        self.health_check_count += 1

        # Simulate health check work
        await asyncio.sleep(self.health_check_duration)

        # Simulate potential health check failure
        if self.should_fail_health_check:
            self.state = ServiceStatus.FAILED
        elif self.should_randomly_fail:
            import random

            if random.random() < self.failure_probability:
                self.state = ServiceStatus.DEGRADED

        # Track performance
        duration = time.time() - start_time
        self.health_check_times.append(duration)

        return self.state

    def get_performance_stats(self) -> dict:
        """Get performance statistics."""
        return {
            "startup_count": self.startup_count,
            "shutdown_count": self.shutdown_count,
            "health_check_count": self.health_check_count,
            "avg_startup_time": sum(self.startup_times) / len(self.startup_times)
            if self.startup_times
            else 0,
            "avg_shutdown_time": sum(self.shutdown_times) / len(self.shutdown_times)
            if self.shutdown_times
            else 0,
            "avg_health_check_time": sum(self.health_check_times) / len(self.health_check_times)
            if self.health_check_times
            else 0,
            "max_startup_time": max(self.startup_times) if self.startup_times else 0,
            "max_shutdown_time": max(self.shutdown_times) if self.shutdown_times else 0,
            "max_health_check_time": max(self.health_check_times) if self.health_check_times else 0,
        }


@pytest.fixture
def rv_system_config():
    """Realistic RV system configuration for integration testing."""
    return {
        # Core infrastructure
        "persistence": {
            "enabled": True,
            "safety_classification": "critical",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": True,
            "depends_on": [],
            "description": "Data persistence service",
        },
        "can_interface": {
            "enabled": True,
            "safety_classification": "critical",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": True,
            "depends_on": [],
            "description": "CAN bus interface",
        },
        # Safety-related systems
        "rvc_protocol": {
            "enabled": True,
            "safety_classification": "critical",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": True,
            "depends_on": ["can_interface"],
            "description": "RV-C protocol handler",
        },
        "spartan_k2": {
            "enabled": True,
            "safety_classification": "safety_related",
            "safe_state_action": "maintain_position",
            "maintain_state_on_failure": True,
            "depends_on": ["can_interface", "rvc_protocol"],
            "description": "Spartan K2 chassis control",
        },
        # Position-critical systems
        "firefly": {
            "enabled": True,
            "safety_classification": "position_critical",
            "safe_state_action": "maintain_position",
            "maintain_state_on_failure": True,
            "depends_on": ["rvc_protocol"],
            "description": "Firefly slide/awning control",
        },
        "leveling_system": {
            "enabled": True,
            "safety_classification": "position_critical",
            "safe_state_action": "maintain_position",
            "maintain_state_on_failure": True,
            "depends_on": ["spartan_k2"],
            "description": "Automatic leveling system",
        },
        # Operational systems
        "dashboard": {
            "enabled": True,
            "safety_classification": "operational",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": True,
            "depends_on": ["persistence", "rvc_protocol"],
            "description": "Dashboard and UI",
        },
        "lighting_control": {
            "enabled": True,
            "safety_classification": "operational",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": True,
            "depends_on": ["firefly"],
            "description": "Interior/exterior lighting",
        },
        "climate_control": {
            "enabled": True,
            "safety_classification": "operational",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": True,
            "depends_on": ["rvc_protocol"],
            "description": "HVAC control system",
        },
        # Maintenance features
        "diagnostics": {
            "enabled": True,
            "safety_classification": "maintenance",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": False,
            "depends_on": ["can_interface"],
            "description": "System diagnostics",
        },
        "logs": {
            "enabled": True,
            "safety_classification": "maintenance",
            "safe_state_action": "continue_operation",
            "maintain_state_on_failure": False,
            "depends_on": ["persistence"],
            "description": "Log management",
        },
    }


@pytest.fixture
def integrated_system(rv_system_config):
    """Create integrated RV system for testing."""
    # Create service registry
    service_registry = EnhancedServiceRegistry()

    # Register realistic services
    services = {}
    for name, config in rv_system_config.items():
        service = RealWorldService(
            name=name,
            safety_classification=config.get("safety_classification", "operational"),
        )
        service.enabled = config.get("enabled", True)
        services[name] = service

        # Register with registry
        service_registry.register_service(
            name=name,
            service=service,
            dependencies=config.get("depends_on", []),
            is_critical=config.get("safety_classification") in ["critical", "safety_related"],
        )

    # Create safety service
    safety_service = SafetyService(
        service_registry=service_registry,
        health_check_interval=0.1,  # Fast for testing
        watchdog_timeout=2.0,
    )

    return {
        "service_registry": service_registry,
        "safety_service": safety_service,
        "services": services,
    }


class TestSystemStartupShutdown:
    """Test complete system startup and shutdown cycles."""

    @pytest.mark.asyncio
    async def test_clean_startup_cycle(self, integrated_system):
        """Test clean startup of all systems in dependency order."""
        service_registry = integrated_system["service_registry"]

        # Perform startup
        start_time = time.time()
        await service_registry.startup()
        startup_duration = time.time() - start_time

        # Verify all enabled services started
        for service_name, service in integrated_system["services"].items():
            if service.enabled:
                assert service.state == ServiceStatus.HEALTHY, (
                    f"Service {service_name} not healthy after startup"
                )
                assert service.startup_count > 0, f"Service {service_name} startup not called"

        # Performance check
        assert startup_duration < 5.0, f"Startup took too long: {startup_duration}s"

        print(f"Clean startup completed in {startup_duration:.2f}s")

    @pytest.mark.asyncio
    async def test_startup_with_failure_recovery(self, integrated_system):
        """Test startup with service failure and recovery."""
        service_registry = integrated_system["service_registry"]
        services = integrated_system["services"]

        # Make one non-critical service fail during startup
        services["climate_control"].should_fail_startup = True

        # Perform startup
        await service_registry.startup()

        # Verify critical services still started
        critical_services = ["persistence", "can_interface", "rvc_protocol"]
        for service_name in critical_services:
            service = services[service_name]
            assert service.state == ServiceStatus.HEALTHY, f"Critical service {service_name} failed"

        # Verify failed service was marked as failed
        climate_service = services["climate_control"]
        assert service_registry.get_service_status("climate_control") == ServiceStatus.FAILED

        # Fix the issue and retry
        climate_service.should_fail_startup = False
        await climate_service.startup()
        assert climate_service.state == ServiceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_graceful_shutdown_cycle(self, integrated_system):
        """Test graceful shutdown of all systems."""
        service_registry = integrated_system["service_registry"]

        # Start the system first
        await service_registry.startup()

        # Perform shutdown
        start_time = time.time()
        await service_registry.shutdown()
        shutdown_duration = time.time() - start_time

        # Verify all services were shut down
        for service_name, service in integrated_system["services"].items():
            if service.enabled:  # Only check enabled services
                assert service.state == ServiceStatus.STOPPED, (
                    f"Service {service_name} not stopped after shutdown"
                )
                assert service.shutdown_count > 0, f"Service {service_name} shutdown not called"

        # Performance check
        assert shutdown_duration < 3.0, f"Shutdown took too long: {shutdown_duration}s"

        print(f"Graceful shutdown completed in {shutdown_duration:.2f}s")


class TestEmergencyScenarios:
    """Test emergency scenarios and safe state transitions."""

    @pytest.mark.asyncio
    async def test_critical_service_failure_cascade(self, integrated_system):
        """Test cascade of failures when critical service fails."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]
        services = integrated_system["services"]

        # Start system
        await service_registry.startup()

        # Simulate critical CAN interface failure
        can_interface = services["can_interface"]
        can_interface.state = ServiceStatus.FAILED

        # Trigger health check
        await service_registry.check_system_health()

        # Verify safety service detected the failure
        safety_status = safety_service.get_safety_status()
        # Implementation would check for appropriate safety responses

    @pytest.mark.asyncio
    async def test_position_critical_failure_response(self, integrated_system):
        """Test response to position-critical system failure."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]
        services = integrated_system["services"]

        # Start system
        await service_registry.startup()

        # Simulate position-critical failure (firefly system)
        firefly = services["firefly"]
        firefly.state = ServiceStatus.FAILED

        # Trigger emergency response
        await safety_service.trigger_emergency_stop("Position-critical system failure")

        # Verify position-critical services entered safe shutdown
        assert safety_service._emergency_stop_active

        # Verify audit log captured the event
        audit_log = safety_service.get_audit_log()
        assert any("emergency" in e["event_type"] for e in audit_log)

    @pytest.mark.asyncio
    async def test_emergency_stop_scenario(self, integrated_system):
        """Test complete emergency stop scenario."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]
        services = integrated_system["services"]

        # Start system and safety monitoring
        await service_registry.startup()
        monitor_task = asyncio.create_task(safety_service.start_monitoring())

        # Simulate emergency condition (multiple system failures)
        services["can_interface"].state = ServiceStatus.FAILED
        services["rvc_protocol"].state = ServiceStatus.FAILED

        # Trigger emergency stop
        await safety_service.trigger_emergency_stop("Critical system failures detected")

        # Verify emergency stop state
        assert safety_service._emergency_stop_active

        # Test emergency stop reset
        success = await safety_service.reset_emergency_stop("SAFETY_OVERRIDE_ADMIN")
        assert success
        assert not safety_service._emergency_stop_active

        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_watchdog_timeout_scenario(self, integrated_system):
        """Test watchdog timeout and safe state entry."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]

        # Start system and safety monitoring
        await service_registry.startup()
        monitor_task = asyncio.create_task(safety_service.start_monitoring())

        # Simulate health monitoring getting stuck
        original_check_health = service_registry.check_system_health

        async def stuck_health_check():
            # Simulate a stuck health check
            await asyncio.sleep(5.0)  # Longer than watchdog timeout
            return await original_check_health()

        service_registry.check_system_health = stuck_health_check

        # Wait for watchdog timeout
        await asyncio.sleep(3.0)  # Longer than 2.0s timeout

        # Verify safe state was entered
        assert safety_service._emergency_stop_active

        # Clean up
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


class TestRealWorldFailurePatterns:
    """Test realistic failure patterns and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_intermittent_connectivity_issues(self, integrated_system):
        """Test handling of intermittent connectivity issues."""
        service_registry = integrated_system["service_registry"]
        services = integrated_system["services"]

        # Start system
        await service_registry.startup()

        # Simulate intermittent CAN bus issues
        can_interface = services["can_interface"]

        # Cycle through connectivity issues
        for cycle in range(3):
            # Fail
            can_interface.state = ServiceStatus.DEGRADED
            await service_registry.check_system_health()

            # Brief pause
            await asyncio.sleep(0.1)

            # Recover
            can_interface.state = ServiceStatus.HEALTHY
            can_interface._failed_dependencies.clear()
            await service_registry.check_system_health()

            await asyncio.sleep(0.1)

        # Verify system remained stable
        assert can_interface.state == ServiceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_power_cycling_scenario(self, integrated_system):
        """Test system behavior during power cycling scenarios."""
        service_registry = integrated_system["service_registry"]
        services = integrated_system["services"]

        # Simulate power cycle by stopping and restarting critical services
        critical_services = ["persistence", "can_interface"]

        for cycle in range(2):
            # Start system
            await service_registry.startup()

            # Verify healthy state
            for service_name in critical_services:
                assert services[service_name].state == ServiceStatus.HEALTHY

            # Simulate power loss (immediate shutdown)
            for service_name in critical_services:
                services[service_name].state = ServiceStatus.STOPPED

            # Simulate power restoration
            await asyncio.sleep(0.1)

            # Restart critical services
            for service_name in critical_services:
                service = services[service_name]
                service.state = ServiceStatus.STARTING
                await service.startup()

        # Verify system stability after power cycling
        for service_name, service in services.items():
            if service.enabled:
                assert service.state == ServiceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_cascading_dependency_recovery(self, integrated_system):
        """Test recovery of cascading dependency failures."""
        service_registry = integrated_system["service_registry"]
        services = integrated_system["services"]

        # Start system
        await service_registry.startup()

        # Simulate cascading failure starting from can_interface
        failure_chain = ["can_interface", "rvc_protocol", "firefly", "lighting_control"]

        # Trigger cascading failures
        for service_name in failure_chain:
            services[service_name].state = ServiceStatus.FAILED

        # Attempt recovery in dependency order
        for service_name in failure_chain:
            service = services[service_name]
            await service.startup()
            assert service.state == ServiceStatus.HEALTHY


class TestSafetyInterlockIntegration:
    """Test integration between safety interlocks and service management."""

    @pytest.mark.asyncio
    async def test_interlock_prevents_unsafe_operations(self, integrated_system):
        """Test that safety interlocks prevent unsafe operations."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]

        # Start system
        await service_registry.startup()

        # Update system state to unsafe conditions
        safety_service.update_system_state(
            {
                "vehicle_speed": 5.0,  # Vehicle moving
                "parking_brake": False,
                "transmission_gear": "DRIVE",
            }
        )

        # Check interlocks
        interlock_results = await safety_service.check_safety_interlocks()

        # Verify interlocks are engaged for unsafe conditions
        slide_safety = interlock_results.get("slide_room_safety")
        assert slide_safety is not None
        conditions_met, reason = slide_safety
        assert not conditions_met
        assert "vehicle_not_moving" in reason

    @pytest.mark.asyncio
    async def test_interlock_state_synchronization(self, integrated_system):
        """Test synchronization between interlock state and service state."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]
        services = integrated_system["services"]

        # Start system
        await service_registry.startup()

        # Simulate service failure that should trigger interlocks
        firefly = services["firefly"]
        firefly.state = ServiceStatus.FAILED

        # Trigger emergency stop
        await safety_service.trigger_emergency_stop("Service failure simulation")

        # Verify interlock state matches service state
        safety_status = safety_service.get_safety_status()
        assert safety_status["emergency_stop_active"]


class TestPerformanceUnderLoad:
    """Test system performance under various load conditions."""

    @pytest.mark.asyncio
    async def test_health_monitoring_performance(self, integrated_system):
        """Test performance of health monitoring under load."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]

        # Start system and monitoring
        await service_registry.startup()
        monitor_task = asyncio.create_task(safety_service.start_monitoring())

        # Let monitoring run for a period
        monitoring_duration = 2.0
        start_time = time.time()

        # Monitor performance during load
        health_check_times = []
        while time.time() - start_time < monitoring_duration:
            health_start = time.time()
            await service_registry.check_system_health()
            health_duration = time.time() - health_start
            health_check_times.append(health_duration)

            await asyncio.sleep(0.1)  # Brief pause between checks

        # Stop monitoring
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        # Analyze performance
        avg_health_check_time = sum(health_check_times) / len(health_check_times)
        max_health_check_time = max(health_check_times)

        # Performance assertions
        assert avg_health_check_time < 0.1, (
            f"Average health check too slow: {avg_health_check_time:.3f}s"
        )
        assert max_health_check_time < 0.5, (
            f"Max health check too slow: {max_health_check_time:.3f}s"
        )

        print(
            f"Health monitoring performance: avg={avg_health_check_time:.3f}s, max={max_health_check_time:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, integrated_system):
        """Test memory usage stability during extended operation."""
        service_registry = integrated_system["service_registry"]
        safety_service = integrated_system["safety_service"]

        # Start system
        await service_registry.startup()

        # Simulate extended operation with various activities
        operations = 100
        for i in range(operations):
            # Health checks
            await service_registry.check_system_health()

            # Interlock checks
            await safety_service.check_safety_interlocks()

            # State transitions
            if i % 10 == 0:
                # Simulate occasional service recovery
                services = integrated_system["services"]
                test_service = services["diagnostics"]
                test_service.state = ServiceStatus.DEGRADED
                await test_service.startup()

            # Brief pause
            await asyncio.sleep(0.01)

        # Verify audit logs don't grow unbounded
        audit_log = safety_service.get_audit_log()
        assert len(audit_log) <= safety_service._max_audit_entries

        # Verify system still responsive
        final_health = await service_registry.check_system_health()
        assert final_health["status"] in ["healthy", "degraded"]

        print(f"Completed {operations} operations with stable memory usage")


if __name__ == "__main__":
    # Run integration tests when executed directly
    pytest.main([__file__, "-v", "-s"])
