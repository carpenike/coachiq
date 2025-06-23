#!/usr/bin/env python3
"""
CoreServices removal migration script.

This script helps identify and update code that needs to be changed
when removing the CoreServices class.
"""

import logging

logger = logging.getLogger(__name__)


# Mapping of old CoreServices methods to new ServiceRegistry approach
MIGRATION_GUIDE = {
    "get_core_services()": "Use ServiceRegistry to get individual services",
    "core_services.persistence": "service_registry.get_service('persistence_service')",
    "core_services.database_manager": "service_registry.get_service('database_manager')",
    "initialize_core_services()": "Services are initialized by ServiceRegistry.startup_all()",
    "shutdown_core_services()": "Services are shutdown by ServiceRegistry.shutdown()",
    "CoreServices": "No longer needed - use ServiceRegistry",
    "app.state.core_services": "Use app.state.service_registry to get individual services",
}


def get_migration_instructions():
    """Get instructions for migrating away from CoreServices."""
    instructions = """
# CoreServices Removal Migration Guide

The CoreServices class has been removed. All services are now managed by ServiceRegistry.

## Key Changes:

1. **Getting Services**
   ```python
   # OLD:
   from backend.core.services import get_core_services
   core_services = get_core_services()
   persistence = core_services.persistence
   db_manager = core_services.database_manager

   # NEW:
   from backend.core.dependencies import get_service_registry
   service_registry = get_service_registry(request)
   persistence = service_registry.get_service('persistence_service')
   db_manager = service_registry.get_service('database_manager')
   ```

2. **In Lifespan/Startup**
   ```python
   # OLD:
   from backend.core.services import initialize_core_services
   core_services = await initialize_core_services()

   # NEW:
   # Services are registered with ServiceRegistry
   # No separate initialization needed
   ```

3. **In Tests**
   ```python
   # OLD:
   core_services = MagicMock()
   core_services.persistence = mock_persistence
   core_services.database_manager = mock_db

   # NEW:
   service_registry = MagicMock()
   service_registry.get_service.side_effect = lambda name: {
       'persistence_service': mock_persistence,
       'database_manager': mock_db
   }.get(name)
   ```

4. **Feature Manager**
   ```python
   # OLD:
   feature_manager.set_core_services(core_services)

   # NEW:
   feature_manager.set_dependencies(
       persistence_service=service_registry.get_service('persistence_service'),
       database_manager=service_registry.get_service('database_manager')
   )
   ```

## Services Previously in CoreServices:
- persistence_service: Data persistence layer
- database_manager: Database connection management

Both are now registered directly with ServiceRegistry during startup.
"""
    return instructions


def check_file_for_core_services(file_path: str) -> list[str]:
    """Check a file for CoreServices usage."""
    issues = []

    try:
        with open(file_path) as f:
            content = f.read()

        # Check for various CoreServices patterns
        patterns = [
            ("from backend.core.services import", "Import of core.services module"),
            ("get_core_services()", "Usage of get_core_services()"),
            ("initialize_core_services", "Usage of initialize_core_services"),
            ("shutdown_core_services", "Usage of shutdown_core_services"),
            ("CoreServices", "Reference to CoreServices class"),
            (".core_services", "Access to core_services attribute"),
            ("core_services.", "Access to core_services methods"),
        ]

        for pattern, description in patterns:
            if pattern in content:
                # Count occurrences
                count = content.count(pattern)
                issues.append(f"{description} ({count} occurrence{'s' if count > 1 else ''})")

    except Exception as e:
        logger.error(f"Error checking file {file_path}: {e}")

    return issues


if __name__ == "__main__":
    print(get_migration_instructions())
