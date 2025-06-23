#!/usr/bin/env python3
"""
Test script for service startup and registration.
"""

import asyncio
import logging

from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import EnhancedServiceRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_basic_startup():
    """Test basic service startup."""
    registry = EnhancedServiceRegistry()

    # Register a simple service with no dependencies
    def create_simple_service():
        return "simple_test_service"

    registry.register_service(
        name="simple_service",
        init_func=create_simple_service,
        dependencies=[],
        description="Simple test service",
    )

    print(f"Service definitions: {list(registry._service_definitions.keys())}")
    print(f"Has simple_service (before startup): {registry.has_service('simple_service')}")

    # Start services
    await registry.startup_all()

    print(f"Services after startup: {list(registry._services.keys())}")
    print(f"Has simple_service (after startup): {registry.has_service('simple_service')}")

    # Test getting the service
    service = registry.get_service("simple_service")
    print(f"Retrieved service: {service}")

    await registry.shutdown()


async def test_app_state_service():
    """Test registering app_state_service specifically."""
    registry = EnhancedServiceRegistry()

    # Mock dependencies
    def create_mock_repo(name):
        class MockRepo:
            def __init__(self):
                self.name = name

        return MockRepo()

    def create_mock_monitor():
        class MockMonitor:
            pass

        return MockMonitor()

    # Register dependencies first
    registry.register_service(
        name="entity_state_repository",
        init_func=lambda: create_mock_repo("entity_state"),
        dependencies=[],
        description="Mock entity state repository",
    )

    registry.register_service(
        name="rvc_config_repository",
        init_func=lambda: create_mock_repo("rvc_config"),
        dependencies=[],
        description="Mock RVC config repository",
    )

    registry.register_service(
        name="can_tracking_repository",
        init_func=lambda: create_mock_repo("can_tracking"),
        dependencies=[],
        description="Mock CAN tracking repository",
    )

    registry.register_service(
        name="diagnostics_repository",
        init_func=lambda: create_mock_repo("diagnostics"),
        dependencies=[],
        description="Mock diagnostics repository",
    )

    registry.register_service(
        name="performance_monitor",
        init_func=create_mock_monitor,
        dependencies=[],
        description="Mock performance monitor",
    )

    # Create a simplified AppStateService
    def create_app_state_service(
        entity_state_repository,
        rvc_config_repository,
        can_tracking_repository,
        diagnostics_repository,
        performance_monitor,
    ):
        class MockAppStateService:
            def __init__(self, **kwargs):
                self.dependencies = kwargs

        return MockAppStateService(
            entity_state_repository=entity_state_repository,
            rvc_config_repository=rvc_config_repository,
            can_tracking_repository=can_tracking_repository,
            diagnostics_repository=diagnostics_repository,
            performance_monitor=performance_monitor,
        )

    registry.register_service(
        name="app_state_service",
        init_func=create_app_state_service,
        dependencies=[
            ServiceDependency("entity_state_repository", DependencyType.REQUIRED),
            ServiceDependency("rvc_config_repository", DependencyType.REQUIRED),
            ServiceDependency("can_tracking_repository", DependencyType.REQUIRED),
            ServiceDependency("diagnostics_repository", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Mock application state service",
    )

    print("Registered services:")
    for name in registry._service_definitions:
        print(f"  - {name}")

    print("\nStarting services...")
    await registry.startup_all()

    print(f"\nRunning services: {list(registry._services.keys())}")
    print(f"Has app_state_service: {registry.has_service('app_state_service')}")

    if registry.has_service("app_state_service"):
        service = registry.get_service("app_state_service")
        print(f"App state service dependencies: {list(service.dependencies.keys())}")

    await registry.shutdown()


async def main():
    """Run all tests."""
    print("=== Testing Basic Service Startup ===")
    await test_basic_startup()

    print("\n=== Testing App State Service ===")
    await test_app_state_service()


if __name__ == "__main__":
    asyncio.run(main())
