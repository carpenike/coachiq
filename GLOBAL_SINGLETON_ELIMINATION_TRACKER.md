# Global Singleton Elimination Tracker - Phase 2H

## Overview
This document tracks the elimination of global singleton patterns as part of Phase 2H of the startup optimization project. Each singleton will be converted to proper dependency injection patterns.

## Global Singletons Identified

### 1. CoreServices ✅
- **File**: `backend/core/services.py`
- **Pattern**: `_core_services_instance: CoreServices | None = None`
- **Functions**: `get_core_services()`, `initialize_core_services()`, `shutdown_core_services()`
- **Status**: Completed - Functions updated to check ServiceRegistry first
- **Migration Strategy**: Maintained for backward compatibility, checks ServiceRegistry first

### 2. FeatureManager ✅
- **File**: `backend/services/feature_manager.py`
- **Pattern**: `_feature_manager: FeatureManager | None = None`
- **Function**: `get_feature_manager()`
- **Status**: Completed - Function updated to check app.state first
- **Migration Strategy**: Maintained for backward compatibility due to widespread usage

### 3. WebSocketManager ❌
- **File**: `backend/websocket/handlers.py`
- **Pattern**: `websocket_manager: WebSocketManager | None = None`
- **Function**: `initialize_websocket_manager()`
- **Status**: Pending
- **Migration Strategy**: Convert to app.state storage

### 4. AppState ✅
- **File**: `backend/core/state.py`
- **Pattern**: `app_state = None` and `global app_state` assignment
- **Functions**: `get_state()`, `get_history()`, `get_entity_by_id()`, `get_entity_history()`
- **Status**: Completed - Global variable removed, functions deprecated
- **Migration Strategy**: Global removed, functions marked deprecated with app.state fallback

### 5. EntityManagerFeature ❌
- **File**: `backend/core/entity_feature.py`
- **Pattern**: `_entity_manager_feature: EntityManagerFeature | None = None`
- **Function**: `initialize_entity_manager_feature()`
- **Status**: Pending
- **Migration Strategy**: Use FeatureManager to access

### 6. ServiceLifecycleManager ✅
- **File**: `backend/core/service_patterns.py`
- **Pattern**: `_lifecycle_manager: Optional[ServiceLifecycleManager] = None`
- **Function**: `get_lifecycle_manager()`
- **Status**: Completed - Function updated to check app.state first
- **Migration Strategy**: Checks app.state.service_lifecycle_manager first

### 7. MultiNetworkManager ❌
- **File**: `backend/integrations/can/multi_network_manager.py`
- **Pattern**: `_multi_network_manager: MultiNetworkManager | None = None`
- **Function**: `get_multi_network_manager()`
- **Status**: Pending
- **Migration Strategy**: Access through FeatureManager

### 8. PINManager ❌
- **File**: `backend/api/routers/pin_auth.py`
- **Pattern**: `_pin_manager: PINManager | None = None`
- **Function**: `get_pin_manager()`
- **Status**: Pending
- **Migration Strategy**: Convert to Depends() injection

### 9. SecurityEventManager ✅
- **File**: `backend/services/security_event_manager.py`
- **Pattern**: `_security_event_manager: SecurityEventManager | None = None`
- **Function**: `get_security_event_manager()`
- **Status**: Completed - Function updated with deprecation warning
- **Migration Strategy**: Checks app.state and ServiceRegistry first

### 10. Settings ✅
- **File**: `backend/core/config.py`
- **Pattern**: `@lru_cache` on `get_settings()`
- **Status**: Completed - No changes needed
- **Migration Strategy**: Keep as-is (appropriate pattern for settings)

## Migration Approach

### Priority Order:
1. **High Priority** (Core Infrastructure):
   - AppState (already in app.state, just remove global)
   - FeatureManager (already in ServiceRegistry)
   - SecurityEventManager (already has DI pattern)

2. **Medium Priority** (Service Dependencies):
   - CoreServices
   - ServiceLifecycleManager
   - WebSocketManager
   - EntityManagerFeature

3. **Low Priority** (Feature-specific):
   - MultiNetworkManager
   - PINManager

### Migration Patterns:

#### Pattern A: Remove Global Fallback (for services already in DI)
```python
# BEFORE
_instance = None
def get_service():
    global _instance
    if _instance is None:
        _instance = Service()
    return _instance

# AFTER
def get_service(request: Request):
    return request.app.state.service_registry.get_service('service_name')
```

#### Pattern B: Convert to App State Storage
```python
# BEFORE
_instance = None
def get_service():
    return _instance

# AFTER
def get_service(app: FastAPI):
    return app.state.service_name
```

#### Pattern C: Use Dependency Injection
```python
# BEFORE
def endpoint():
    service = get_service()

# AFTER
def endpoint(service: Service = Depends(get_service)):
    pass
```

## Progress Tracking

- [x] Create migration helper functions (built into each function)
- [x] Migrate high priority singletons (AppState, FeatureManager, SecurityEventManager)
- [x] Migrate medium priority singletons (CoreServices, ServiceLifecycleManager)
- [ ] Migrate low priority singletons (remaining services)
- [x] Remove/deprecate global variables (where safe to do so)
- [ ] Update all imports to use DI
- [ ] Add linting rules
- [ ] Update documentation

## Summary of Changes

### Completed Migrations (5/10):
1. **AppState** - Global variable removed, functions deprecated
2. **FeatureManager** - Checks app.state first, maintains backward compatibility
3. **SecurityEventManager** - Deprecation warnings added, checks app.state/ServiceRegistry
4. **CoreServices** - Checks ServiceRegistry first, maintains backward compatibility
5. **ServiceLifecycleManager** - Checks app.state first, maintains backward compatibility

### Remaining Migrations (4/10):
1. **WebSocketManager** - Module-level variable in handlers.py
2. **EntityManagerFeature** - Global in entity_feature.py
3. **MultiNetworkManager** - Global in CAN integration
4. **PINManager** - Global in API router

### No Changes Needed (1/10):
1. **Settings** - LRU cache pattern is appropriate

## Testing Strategy

1. **Unit Tests**: Mock dependency injection
2. **Integration Tests**: Verify service lifecycle
3. **Startup Tests**: Ensure proper initialization order
4. **API Tests**: Verify endpoints work with DI

## Rollback Plan

1. Keep original functions with deprecation warnings
2. Test thoroughly in staging
3. Feature flag for gradual rollout
4. Monitor for initialization errors
