# Repository Pattern Architecture

## Overview

The CoachIQ system has migrated from a monolithic `AppState` pattern to a modern repository pattern with dependency injection. This architecture provides better separation of concerns, improved testability, and enhanced maintainability.

## Architecture Components

### 1. Repository Layer

Repositories provide data access abstraction with specific interfaces:

- **EntityStateRepository**: Manages entity state and configuration
- **RVCConfigRepository**: Handles RV-C specification data
- **CANTrackingRepository**: Tracks CAN messages and statistics
- **SystemStateRepository**: System-wide configuration and state

### 2. Service Layer

Services use repositories through dependency injection:

```python
class ConfigService:
    def __init__(
        self,
        entity_state_repository: EntityStateRepository | None = None,
        rvc_config_repository: RVCConfigRepository | None = None,
        system_state_repository: SystemStateRepository | None = None,
        app_state: Any = None  # For backward compatibility only
    ):
        # Services now use repositories instead of app_state
```

### 3. Dependency Injection

Modern FastAPI dependency injection through `backend.core.dependencies_v2`:

```python
from typing import Annotated
from fastapi import Depends
from backend.core.dependencies_v2 import get_config_service

@router.get("/config")
async def get_config(
    config_service: Annotated[ConfigService, Depends(get_config_service)]
):
    # Service is injected with all repositories configured
```

## Migration Strategy

### Feature Flag Configuration

The migration is controlled by feature flags in `backend/services/feature_flags.yaml`:

```yaml
repository_pattern:
  enabled: true
  core: false
  depends_on: []
  description: "Repository pattern for state management"
  # Migration settings
  use_repositories_for_config: true
  use_repositories_for_can: true
  use_repositories_for_websocket: true
  fallback_to_app_state: true
  migration_mode: "gradual"  # Options: strict, gradual, compatibility
```

### Migration Modes

1. **Strict Mode**: Only repositories, no app_state fallback
2. **Gradual Mode**: Repositories with app_state fallback (default)
3. **Compatibility Mode**: Prefer app_state, repositories as backup

### Migration Service

The `RepositoryMigrationService` manages the rollout:

- Monitors usage patterns
- Provides health metrics
- Enables gradual migration
- Tracks errors and fallbacks

## API Endpoints

Monitor migration progress through these endpoints:

- `GET /api/repository-migration/status` - Overall migration status
- `GET /api/repository-migration/metrics` - Detailed usage metrics
- `GET /api/repository-migration/health` - Health status
- `POST /api/repository-migration/reset-stats` - Reset statistics

## Best Practices

### 1. Service Development

```python
# DO: Use repositories through dependency injection
class MyService:
    def __init__(
        self,
        entity_state_repository: EntityStateRepository,
        system_state_repository: SystemStateRepository
    ):
        self._entity_repo = entity_state_repository
        self._system_repo = system_state_repository

# DON'T: Store app_state
class MyService:
    def __init__(self, app_state: AppState):
        self.app_state = app_state  # Anti-pattern
```

### 2. Router Development

```python
# DO: Use modern dependency injection
from backend.core.dependencies_v2 import get_my_service

@router.get("/endpoint")
async def my_endpoint(
    service: Annotated[MyService, Depends(get_my_service)]
):
    return await service.do_something()

# DON'T: Use old dependencies
from backend.core.dependencies import get_app_state  # Legacy
```

### 3. Testing

```python
# Easy to test with mocked repositories
def test_my_service():
    mock_entity_repo = MagicMock()
    mock_system_repo = MagicMock()

    service = MyService(
        entity_state_repository=mock_entity_repo,
        system_state_repository=mock_system_repo
    )

    # Test with full control over dependencies
```

## Performance Considerations

### Real-time Operations

- Repository operations maintain <1ms latency for CAN operations
- Thread-safe implementations for concurrent access
- Bounded collections prevent memory growth

### Caching Strategy

- Repositories implement appropriate caching
- Service-level caching for computed values
- Cache invalidation on state changes

## Migration Checklist

When migrating code:

1. ✅ Replace `app_state` imports with repository imports
2. ✅ Update service constructors to accept repositories
3. ✅ Use `dependencies_v2` instead of `dependencies`
4. ✅ Test with migration modes (strict, gradual, compatibility)
5. ✅ Update unit tests to use repository mocks
6. ✅ Verify performance metrics remain stable

## Troubleshooting

### Common Issues

1. **"Repository not found" errors**
   - Ensure ServiceRegistry initialization includes all repositories
   - Check feature flag configuration

2. **Performance degradation**
   - Monitor `/api/repository-migration/metrics`
   - Check for excessive fallbacks to app_state

3. **Test failures**
   - Update mocks to use repository pattern
   - Ensure proper repository initialization in tests

## Future Enhancements

1. **Complete app_state removal** (target: Q2 2025)
2. **Enhanced repository interfaces** with async operations
3. **Repository-level caching improvements**
4. **Distributed repository support** for scaling
