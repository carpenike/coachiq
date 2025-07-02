# AppState to Repository Pattern Migration Guide

## Overview

This guide helps developers migrate code from the legacy `AppState` pattern to the modern repository pattern with dependency injection.

## Quick Start

### Before (Legacy Pattern)
```python
from backend.core.dependencies import get_app_state
from fastapi import Depends

@router.get("/entities")
async def get_entities(app_state = Depends(get_app_state)):
    return app_state.entity_manager.get_all_entities()
```

### After (Repository Pattern)
```python
from backend.core.dependencies_v2 import get_entity_service
from typing import Annotated
from fastapi import Depends

@router.get("/entities")
async def get_entities(
    entity_service: Annotated[EntityService, Depends(get_entity_service)]
):
    return await entity_service.get_all_entities()
```

## Step-by-Step Migration

### 1. Update Imports

Replace old dependency imports:
```python
# OLD
from backend.core.dependencies import (
    get_app_state,
    get_entity_service,
    get_config_service
)

# NEW
from backend.core.dependencies_v2 import (
    get_entity_service,
    get_config_service,
    get_all_repositories
)
```

### 2. Update Service Classes

Transform services to use repositories:

```python
# OLD
class MyService:
    def __init__(self, app_state: AppState):
        self.app_state = app_state

    def get_entity(self, entity_id: str):
        return self.app_state.entity_manager.get_entity(entity_id)

# NEW
class MyService:
    def __init__(
        self,
        entity_state_repository: EntityStateRepository,
        system_state_repository: SystemStateRepository | None = None
    ):
        self._entity_repo = entity_state_repository
        self._system_repo = system_state_repository

    async def get_entity(self, entity_id: str):
        return await self._entity_repo.get_entity(entity_id)
```

### 3. Update Router Endpoints

Use modern type annotations:

```python
# OLD
@router.post("/control")
async def control_entity(
    request: ControlRequest,
    app_state = Depends(get_app_state),
    can_service = Depends(get_can_service)
):
    # Direct app_state access
    entity = app_state.entity_manager.get_entity(request.entity_id)

# NEW
@router.post("/control")
async def control_entity(
    request: ControlRequest,
    entity_service: Annotated[EntityService, Depends(get_entity_service)],
    can_service: Annotated[CANService, Depends(get_can_service)]
):
    # Service-based access
    entity = await entity_service.get_entity(request.entity_id)
```

### 4. Update Tests

Replace app_state mocks with repository mocks:

```python
# OLD
def test_my_service():
    mock_app_state = MagicMock()
    mock_app_state.entity_manager.get_entity.return_value = test_entity

    service = MyService(app_state=mock_app_state)

# NEW
def test_my_service():
    mock_entity_repo = MagicMock()
    mock_entity_repo.get_entity.return_value = test_entity

    service = MyService(entity_state_repository=mock_entity_repo)
```

## Common Patterns

### Accessing Entity Data

```python
# OLD
entities = app_state.entity_manager.get_all_entities()
entity = app_state.entity_manager.get_entity(entity_id)

# NEW (with repository)
entities = await entity_repo.get_all_entities()
entity = await entity_repo.get_entity(entity_id)

# NEW (with service)
entities = await entity_service.get_all_entities()
entity = await entity_service.get_entity(entity_id)
```

### Accessing Configuration

```python
# OLD
rvc_spec = app_state.rvc_spec_manager.get_spec()
controller_addr = app_state.get_controller_source_addr()

# NEW
rvc_spec = await rvc_config_repo.get_full_spec()
controller_addr = system_state_repo.get_controller_source_addr()
```

### CAN Message Tracking

```python
# OLD
app_state.add_can_sniffer_entry(entry)
entries = app_state.get_can_sniffer_grouped()

# NEW
await can_tracking_repo.add_sniffer_entry(entry)
entries = await can_tracking_repo.get_grouped_entries()
```

## Testing Migration

### 1. Enable Gradual Mode

Start with gradual mode in your development environment:

```yaml
# backend/services/feature_flags.yaml
repository_pattern:
  enabled: true
  migration_mode: "gradual"
  fallback_to_app_state: true
```

### 2. Monitor Metrics

Check migration metrics during development:

```bash
curl http://localhost:8080/api/repository-migration/status
```

### 3. Test Strict Mode

Before deploying, test with strict mode:

```yaml
repository_pattern:
  enabled: true
  migration_mode: "strict"
  fallback_to_app_state: false
```

## Gotchas and Solutions

### 1. Circular Dependencies

**Problem**: Service A depends on Service B which depends on Service A

**Solution**: Use repository interfaces to break cycles
```python
# Instead of service dependencies
class ServiceA:
    def __init__(self, service_b: ServiceB):  # Circular!

# Use repositories
class ServiceA:
    def __init__(self, shared_repository: SharedRepository):
```

### 2. Missing Repositories

**Problem**: "Repository not found" errors

**Solution**: Ensure ServiceRegistry initialization
```python
# In dependencies_v2.py
service_registry.register_repository(
    "my_repository",
    MyRepository(settings)
)
```

### 3. Async/Await

**Problem**: Forgetting async/await with repository methods

**Solution**: Repository methods are async by design
```python
# Wrong
entity = entity_repo.get_entity(id)  # Missing await!

# Correct
entity = await entity_repo.get_entity(id)
```

## Performance Tips

1. **Batch Operations**: Use repository batch methods
   ```python
   # Instead of multiple calls
   for id in entity_ids:
       entity = await repo.get_entity(id)

   # Use batch method
   entities = await repo.get_entities_batch(entity_ids)
   ```

2. **Caching**: Repositories implement caching
   ```python
   # First call fetches from storage
   spec = await rvc_config_repo.get_full_spec()

   # Subsequent calls use cache
   spec = await rvc_config_repo.get_full_spec()  # Cached!
   ```

3. **Connection Pooling**: Repositories manage connections efficiently

## Verification Checklist

After migration, verify:

- [ ] No imports from `backend.core.dependencies`
- [ ] No `app_state` instance variables in services
- [ ] All repository methods use async/await
- [ ] Tests use repository mocks, not app_state mocks
- [ ] Feature flags configured correctly
- [ ] Migration metrics show expected patterns
- [ ] Performance metrics remain stable

## Need Help?

- Check `/api/repository-migration/status` for current state
- Review logs for migration warnings
- Run tests in strict mode to find issues
- Consult `docs/architecture/repository-pattern.md` for design details
