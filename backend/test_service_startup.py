#!/usr/bin/env python3
"""
Test script for modern ServiceRegistry patterns (post-CoreServices removal).
"""

import asyncio
import logging

from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import EnhancedServiceRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_basic_startup():
    """Test basic service startup with modern ServiceRegistry."""
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


async def test_repository_service_patterns():
    """Test modern repository injection patterns with ServiceRegistry."""
    registry = EnhancedServiceRegistry()

    # Mock repositories following modern patterns
    def create_mock_repo(name):
        class MockRepository:
            def __init__(self):
                self.name = name
                self.initialized = True

            async def startup(self):
                print(f"Starting {self.name} repository")

            async def shutdown(self):
                print(f"Shutting down {self.name} repository")

        return MockRepository()

    def create_mock_service(entity_repo, config_repo):
        class MockEntityService:
            def __init__(self, entity_repository, config_repository):
                self.entity_repository = entity_repository
                self.config_repository = config_repository

            async def startup(self):
                print("Starting mock entity service")

            async def shutdown(self):
                print("Shutting down mock entity service")

        return MockEntityService(entity_repo, config_repo)

    # Register repositories (no dependencies)
    registry.register_service(
        name="entity_repository",
        init_func=lambda: create_mock_repo("entity"),
        dependencies=[],
        description="Mock entity repository",
    )

    registry.register_service(
        name="config_repository",
        init_func=lambda: create_mock_repo("config"),
        dependencies=[],
        description="Mock config repository",
    )

    # Register service that depends on repositories
    def create_entity_service(entity_repository, config_repository):
        return create_mock_service(entity_repository, config_repository)
    
    registry.register_service(
        name="entity_service",
        init_func=create_entity_service,
        dependencies=[
            ServiceDependency("entity_repository", DependencyType.REQUIRED),
            ServiceDependency("config_repository", DependencyType.REQUIRED),
        ],
        description="Mock entity service with repository dependencies",
    )

    print("Modern ServiceRegistry pattern test:")
    print(f"Registered services: {list(registry._service_definitions.keys())}")

    print("\nStarting services...")
    await registry.startup_all()

    print(f"\nRunning services: {list(registry._services.keys())}")

    # Test dependency injection worked correctly
    entity_service = registry.get_service("entity_service")
    print(f"Entity service has entity_repository: {hasattr(entity_service, 'entity_repository')}")
    print(f"Entity service has config_repository: {hasattr(entity_service, 'config_repository')}")

    await registry.shutdown()


async def main():
    """Run all tests for modern ServiceRegistry patterns."""
    print("=== Testing Basic Service Startup ===")
    await test_basic_startup()

    print("\n=== Testing Repository Injection Patterns ===")
    await test_repository_service_patterns()


if __name__ == "__main__":
    asyncio.run(main())
