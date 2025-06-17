# FeatureManager-ServiceRegistry Integration Guide

## Overview

Phase 2C introduces a unified service management approach that combines:
- **ServiceRegistry**: Efficient staged startup with dependency injection
- **FeatureManager**: Safety-critical features with ISO 26262 patterns

This guide explains how to use the new integrated system.

## Architecture

### 1. Unified Service Interface (`backend/core/unified_service.py`)

The `UnifiedService` protocol defines a common interface:

```python
@runtime_checkable
class UnifiedService(Protocol):
    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def check_health(self) -> None: ...
```

Services can implement this in three ways:
1. **Extend Feature class** (safety-critical services)
2. **Implement UnifiedService protocol** (standard services)
3. **Simple async functions** (basic services)

### 2. Service Adapter Pattern

The `ServiceAdapter` class makes Feature instances compatible with ServiceRegistry:

```python
adapter = ServiceAdapter(feature)
# Adapter provides:
# - initialize() → feature.startup()
# - cleanup() → feature.shutdown()
# - to_service_status() → converts FeatureState to ServiceStatus
```

### 3. Integrated Feature Manager (`backend/services/feature_manager_v2.py`)

The `IntegratedFeatureManager` extends standard FeatureManager to:
- Register features with both systems
- Use ServiceRegistry's staged startup
- Maintain safety-critical capabilities
- Provide unified health monitoring

## Migration Steps

### Step 1: Update main.py Imports

```python
# Add new imports
from backend.services.feature_manager_v2 import (
    IntegratedFeatureManager,
    migrate_to_integrated_manager
)
```

### Step 2: Create Integrated Manager

Replace standard FeatureManager creation with:

```python
async def initialize_services(app: FastAPI) -> None:
    """Initialize all services with unified management."""

    # 1. Create ServiceRegistry
    service_registry = ServiceRegistry()
    app.state.service_registry = service_registry

    # 2. Create IntegratedFeatureManager
    feature_manager = IntegratedFeatureManager.create_integrated(
        yaml_path="backend/services/feature_flags.yaml",
        service_registry=service_registry,
    )
    app.state.feature_manager = feature_manager

    # 3. Register core services with ServiceRegistry
    service_registry.register_startup_stage([
        ("persistence_service", init_persistence, []),
        ("database_manager", init_database, []),
    ], stage=0)

    # 4. Features are automatically registered via IntegratedFeatureManager
    # They will be started in the correct order with parallelization

    # 5. Start all services via ServiceRegistry
    await service_registry.startup_all()
```

### Step 3: Progressive Migration

If you have an existing FeatureManager, use the migration helper:

```python
# Existing code
feature_manager = FeatureManager.from_yaml("feature_flags.yaml")

# Migration
integrated = migrate_to_integrated_manager(
    app=app,
    feature_manager=feature_manager,
    service_registry=service_registry,
)
```

### Step 4: Update Feature Registration

Features are now automatically registered with ServiceRegistry:

```python
# Before
feature_manager.register_feature(my_feature)

# After - same API, but also registers with ServiceRegistry
feature_manager.register_feature(my_feature)
# Automatically:
# - Calculates startup stage based on dependencies
# - Registers with ServiceRegistry
# - Sets up health monitoring
```

## Benefits

### 1. Staged Parallel Startup

Features with no interdependencies start in parallel:

```
Stage 0: [persistence, database, config] - start in parallel
Stage 1: [entity_service, auth] - start in parallel after stage 0
Stage 2: [websocket, api_features] - start in parallel after stage 1
```

### 2. Unified Health Monitoring

```python
# Get combined health status
health = feature_manager.get_unified_health_status()
# Returns:
{
    "feature_manager": {
        "total_features": 15,
        "healthy_features": 14
    },
    "service_registry": {
        "total_services": 20,
        "service_status": {
            "HEALTHY": 19,
            "DEGRADED": 1
        }
    }
}
```

### 3. Dependency Injection

Services can be accessed through either system:

```python
# Via FeatureManager (for features)
entity_service = feature_manager.get_feature("entity_service")

# Via ServiceRegistry (for all services)
entity_service = service_registry.get_service("entity_service")

# In API endpoints
@router.get("/status")
async def get_status(
    entity_service: EntityService = Depends(get_entity_service)
):
    # Dependency injection works seamlessly
```

## Safety Considerations

### Safety-Critical Features

Features with safety classifications are handled specially:

```python
# Safety-critical features:
# - Cannot be toggled at runtime without authorization
# - Transition through SAFE_SHUTDOWN state
# - Health failures propagate to dependents
# - Audit logging for all state transitions
```

### State Transitions

The integrated system maintains FeatureState validation:

```
STOPPED → INITIALIZING → HEALTHY
                      ↘ DEGRADED → FAILED
                                → SAFE_SHUTDOWN
```

## Example: Complete Integration

```python
# main.py
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan with unified service management."""

    # Initialize metrics first
    initialize_backend_metrics()

    # Create registries
    service_registry = ServiceRegistry()
    app.state.service_registry = service_registry

    # Create integrated feature manager
    feature_manager = IntegratedFeatureManager.create_integrated(
        yaml_path="backend/services/feature_flags.yaml",
        service_registry=service_registry,
    )
    app.state.feature_manager = feature_manager

    # Register core services
    service_registry.register_startup_stage([
        ("settings", lambda: get_settings(), []),
    ], stage=0)

    service_registry.register_startup_stage([
        ("persistence", init_persistence_service, []),
        ("database", init_database_manager, []),
    ], stage=1)

    # Features are auto-registered by IntegratedFeatureManager
    # with appropriate stages based on dependencies

    try:
        # Start everything via ServiceRegistry
        await service_registry.startup_all()

        # Health check
        health = feature_manager.get_unified_health_status()
        logger.info(f"System started: {health}")

        yield

    finally:
        # Shutdown in reverse order
        await service_registry.shutdown_all()
```

## Backward Compatibility

The integration maintains full backward compatibility:

1. **Existing Feature API works unchanged**
2. **FeatureManager methods still available**
3. **Progressive migration supported**
4. **No changes required to Feature implementations**

## Testing

```python
async def test_integrated_startup():
    """Test unified startup process."""

    # Create test instances
    registry = ServiceRegistry()
    manager = IntegratedFeatureManager(
        config_set=test_config,
        service_registry=registry,
    )

    # Register test feature
    test_feature = TestFeature(name="test", enabled=True)
    manager.register_feature(test_feature)

    # Verify registration
    assert registry.has_service("test")
    assert "test" in manager._features

    # Start via ServiceRegistry
    await registry.startup_all()

    # Verify started
    assert test_feature._state == FeatureState.HEALTHY
```

## Troubleshooting

### Issue: Features not starting

Check startup stages:
```python
# Debug startup order
for stage, services in service_registry._startup_stages.items():
    print(f"Stage {stage}: {[s[0] for s in services]}")
```

### Issue: Dependency conflicts

The system uses topological sorting - circular dependencies will raise errors:
```python
# This will fail during registration
feature_a.dependencies = ["feature_b"]
feature_b.dependencies = ["feature_a"]  # Circular!
```

### Issue: Health check failures

Use unified health endpoint:
```bash
curl http://localhost:8080/api/health
# Shows both FeatureManager and ServiceRegistry health
```

## Future Enhancements

1. **Dynamic Feature Loading**: Load features at runtime
2. **Feature Versioning**: Support multiple versions of features
3. **Distributed Mode**: Multi-process feature coordination
4. **Metrics Integration**: Prometheus metrics for all services
