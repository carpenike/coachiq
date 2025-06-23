"""
Integration tests for ServiceRegistry dependency resolution.

This test suite validates that all services can be resolved correctly
through the ServiceRegistry and dependencies_v2.py, serving as a
regression test during the migration phases.
"""

import asyncio
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.dependencies import (
    get_service_registry,
    get_service_with_fallback,
)
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import EnhancedServiceRegistry, ServiceStatus


@pytest.fixture
async def mock_service_registry():
    """Create a mock service registry with test services."""
    registry = EnhancedServiceRegistry()

    # Helper to create mock services with async start_background_tasks
    def create_mock_service(name: str):
        mock = MagicMock()
        # Set the name attribute explicitly so it's not a Mock
        mock.name = name
        # Make start_background_tasks return an async function
        mock.start_background_tasks = AsyncMock()
        return mock

    # Register test services
    registry.register_service(
        name="database_manager",
        init_func=lambda: create_mock_service("database_manager"),
        dependencies=[],
        description="Test database manager",
    )

    registry.register_service(
        name="performance_monitor",
        init_func=lambda: create_mock_service("performance_monitor"),
        dependencies=[],
        description="Test performance monitor",
    )

    registry.register_service(
        name="entity_repository",
        init_func=lambda: create_mock_service("entity_repository"),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Test entity repository",
    )

    registry.register_service(
        name="entity_service",
        init_func=lambda: create_mock_service("entity_service"),
        dependencies=[
            ServiceDependency("entity_repository", DependencyType.REQUIRED),
        ],
        description="Test entity service",
    )

    # Start all services
    await registry.startup_all()

    yield registry

    await registry.shutdown()


@pytest.fixture
def mock_request(mock_service_registry):
    """Create a mock request with service registry."""
    request = MagicMock()

    # Use a regular object for app.state to avoid MagicMock's hasattr issues
    class MockAppState:
        def __init__(self):
            self.service_registry = mock_service_registry

    request.app.state = MockAppState()
    return request


class TestServiceRegistryIntegration:
    """Test service resolution through ServiceRegistry."""

    async def test_all_services_start_successfully(self, mock_service_registry):
        """Test that all registered services start successfully."""
        # Check service status
        assert mock_service_registry._service_status["database_manager"] == ServiceStatus.HEALTHY
        assert mock_service_registry._service_status["performance_monitor"] == ServiceStatus.HEALTHY
        assert mock_service_registry._service_status["entity_repository"] == ServiceStatus.HEALTHY
        assert mock_service_registry._service_status["entity_service"] == ServiceStatus.HEALTHY

        # Verify all services are accessible
        assert mock_service_registry.get_service("database_manager") is not None
        assert mock_service_registry.get_service("performance_monitor") is not None
        assert mock_service_registry.get_service("entity_repository") is not None
        assert mock_service_registry.get_service("entity_service") is not None

    async def test_dependency_resolution_order(self, mock_service_registry):
        """Test that services are started in correct dependency order."""
        # Get startup order
        startup_order = mock_service_registry.get_startup_order()

        # Verify dependency order
        db_idx = startup_order.index("database_manager")
        perf_idx = startup_order.index("performance_monitor")
        repo_idx = startup_order.index("entity_repository")
        service_idx = startup_order.index("entity_service")

        # Dependencies should be started before dependents
        assert db_idx < repo_idx
        assert perf_idx < repo_idx
        assert repo_idx < service_idx

    def test_get_service_from_registry(self, mock_request):
        """Test service resolution through ServiceRegistry."""
        # Get service registry
        registry = get_service_registry(mock_request)
        assert registry is not None

        # Test successful resolution
        entity_service = registry.get_service("entity_service")
        assert entity_service is not None
        assert entity_service.name == "entity_service"

        # Test non-existent service
        with pytest.raises(LookupError, match="Service 'nonexistent' not found"):
            registry.get_service("nonexistent")

    def test_get_service_with_fallback(self, mock_request):
        """Test service resolution with fallback through dependencies_v2."""
        # Test service from registry
        entity_service = get_service_with_fallback(mock_request, "entity_service")
        assert entity_service is not None
        assert entity_service.name == "entity_service"

        # Test fallback to app.state attribute
        legacy_mock = MagicMock()
        legacy_mock.name = "legacy_service"
        mock_request.app.state.legacy_service = legacy_mock
        legacy_service = get_service_with_fallback(
            mock_request, "legacy_service", fallback_attr="legacy_service"
        )
        assert legacy_service is not None
        assert legacy_service.name == "legacy_service"

        # Test failure when neither exists
        # First, ensure the service doesn't exist in registry
        assert not mock_request.app.state.service_registry.has_service("missing")
        # And ensure it doesn't exist in app.state
        assert not hasattr(mock_request.app.state, "missing")

        with pytest.raises(RuntimeError, match="Service 'missing' not available"):
            get_service_with_fallback(mock_request, "missing")

    async def test_service_health_checks(self, mock_service_registry):
        """Test service health check functionality."""
        # Add health check to a service
        healthy_check = lambda: True
        unhealthy_check = lambda: False

        mock_service_registry._service_definitions["database_manager"].health_check = healthy_check
        mock_service_registry._service_definitions["entity_service"].health_check = unhealthy_check

        # Check health
        db_health = await mock_service_registry.check_service_health("database_manager")
        assert db_health == ServiceStatus.HEALTHY

        entity_health = await mock_service_registry.check_service_health("entity_service")
        assert entity_health == ServiceStatus.DEGRADED

    def test_dependency_visualization(self, mock_service_registry):
        """Test dependency diagram generation."""
        diagram = mock_service_registry.export_dependency_diagram()

        # Verify diagram contains expected elements
        assert "graph TD" in diagram
        assert "database_manager" in diagram
        assert "entity_repository" in diagram
        assert "entity_service" in diagram

        # Verify relationships
        assert "database_manager --> entity_repository" in diagram
        assert "performance_monitor --> entity_repository" in diagram
        assert "entity_repository --> entity_service" in diagram

    def test_service_timing_metrics(self, mock_service_registry):
        """Test service startup timing metrics."""
        metrics = mock_service_registry.get_enhanced_metrics()

        # Verify metrics structure
        assert "total_startup_time_ms" in metrics
        assert "service_count" in metrics
        assert metrics["service_count"] == 4
        assert "slowest_services" in metrics
        assert "service_timings" in metrics

        # Verify all services have timings
        timings = metrics["service_timings"]
        assert "database_manager" in timings
        assert "performance_monitor" in timings
        assert "entity_repository" in timings
        assert "entity_service" in timings


class TestServiceRegistryWithRealServices:
    """Test ServiceRegistry with actual service implementations."""

    @pytest.fixture
    async def real_service_registry(self):
        """Create a service registry with real service implementations."""
        registry = EnhancedServiceRegistry()

        # Import real services
        from backend.main import (
            _init_app_settings,
            _init_core_services,
            _init_rvc_config_provider,
            _init_security_event_manager,
        )

        # Register real services
        registry.register_service(
            name="app_settings",
            init_func=_init_app_settings,
            dependencies=[],
            tags={"core", "config"},
            description="Application settings from environment",
        )

        registry.register_service(
            name="rvc_config",
            init_func=_init_rvc_config_provider,
            dependencies=[],
            tags={"core", "config"},
            description="RV-C configuration provider",
        )

        registry.register_service(
            name="core_services",
            init_func=_init_core_services,
            dependencies=[
                ServiceDependency("app_settings", DependencyType.REQUIRED),
            ],
            tags={"core"},
            description="Core services bundle (database, persistence)",
        )

        # Don't register security_event_manager as it has circular dependencies
        # This will be fixed in Phase 2

        yield registry

        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_real_services_startup(self, real_service_registry):
        """Test that real services can start successfully."""
        # Start services
        await real_service_registry.startup_all()

        # Verify core services started
        assert real_service_registry.has_service("app_settings")
        assert real_service_registry.has_service("rvc_config")
        assert real_service_registry.has_service("core_services")

        # Get services
        settings = real_service_registry.get_service("app_settings")
        assert settings is not None
        assert hasattr(settings, "app_name")

        rvc_config = real_service_registry.get_service("rvc_config")
        assert rvc_config is not None

        core_services = real_service_registry.get_service("core_services")
        assert core_services is not None
        assert hasattr(core_services, "database_manager")
        assert hasattr(core_services, "persistence")

    @pytest.mark.asyncio
    async def test_startup_shutdown_cycle(self, real_service_registry):
        """Test complete startup and shutdown cycle."""
        # Start services
        await real_service_registry.startup_all()

        # Verify services are healthy
        status_counts = real_service_registry.get_service_count_by_status()
        assert status_counts.get(ServiceStatus.HEALTHY, 0) > 0
        assert status_counts.get(ServiceStatus.FAILED, 0) == 0

        # Shutdown
        await real_service_registry.shutdown()

        # After shutdown, services should be in PENDING state or not reported
        # (since they've been cleaned up)

    def test_dependency_report_generation(self, real_service_registry):
        """Test dependency report for real services."""
        report = real_service_registry.get_dependency_report()

        # Verify report content
        assert "Service Dependency Report" in report
        assert "app_settings" in report
        assert "core_services" in report
        assert "Dependencies:" in report
        assert "app_settings" in report  # core_services depends on app_settings


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
