# Service Access Patterns

## 🚨 CRITICAL: Modern Service Access Patterns (Updated)

**IMPORTANT**: The codebase has completed a major architectural transformation. All new code MUST follow these modern patterns.

## Service Access Pattern Evolution

### ✅ Modern Pattern (REQUIRED for all new code)
```python
# Use dependencies_v2 for all service access
from backend.core.dependencies_v2 import (
    get_feature_manager,
    get_entity_service,
    get_can_service,
    get_auth_manager
)
from typing import Annotated
from fastapi import Depends

@router.get("/endpoint")
async def endpoint(
    feature_manager: Annotated[Any, Depends(get_feature_manager)],
    entity_service: Annotated[Any, Depends(get_entity_service)]
):
    # Services are automatically injected by FastAPI
    pass
```

### ❌ Legacy Patterns (DO NOT USE)
```python
# DON'T use old dependencies.py
from backend.core.dependencies import get_feature_manager_from_request  # ❌

# DON'T access app.state directly
entity_service = request.app.state.entity_service  # ❌

# DON'T create global service instances
global_service = MyService()  # ❌

# DON'T use get_*_from_request functions
feature_manager = get_feature_manager_from_request(request)  # ❌
```

## Service Registry Architecture

The application uses a centralized ServiceRegistry with:
- Automatic dependency resolution
- Startup ordering based on dependencies
- Health monitoring and metrics
- O(1) service lookup performance

### ServiceRegistry Features
```python
# Services are registered with dependencies
service_registry.register_service(
    name="entity_service",
    factory=lambda: EntityService(deps...),
    dependencies=["websocket_manager", "rvc_config"],
    health_check=lambda s: {"healthy": s.is_connected}
)

# Automatic topological ordering ensures proper initialization
# Services with dependencies are started after their dependencies
```

## Available Service Dependencies

All services are available through `backend.core.dependencies_v2`:

### Core Services
- `get_app_state()` - Application state and metadata
- `get_settings()` - Configuration settings
- `get_feature_manager()` - Feature flag management
- `get_service_registry()` - Direct registry access

### Domain Services
- `get_entity_service()` - Entity state management
- `get_can_service()` - CAN bus operations
- `get_rvc_service()` - RV-C protocol handling
- `get_safety_service()` - Safety system management
- `get_entity_domain_service()` - Domain API v2 entity service

### Infrastructure Services
- `get_websocket_manager()` - WebSocket connections
- `get_auth_manager()` - Authentication services
- `get_notification_manager()` - Notification system
- `get_can_interface_service()` - CAN interface management

### Analytics & Monitoring
- `get_analytics_service()` - Analytics and reporting
- `get_dashboard_service()` - Dashboard data aggregation
- `get_security_audit_service()` - Security event auditing
- `get_predictive_maintenance_service()` - Maintenance predictions

### Data Repositories
- `get_entity_state_repository()` - Entity persistence
- `get_diagnostics_repository()` - System diagnostics
- `get_analytics_repository()` - Analytics data storage
- `get_can_tracking_repository()` - CAN message tracking
- `get_rvc_config_repository()` - RV-C configuration

### Specialized Services
- `get_can_analyzer_service()` - CAN bus analysis
- `get_can_filter_service()` - Message filtering
- `get_can_recorder_service()` - Message recording
- `get_dbc_service()` - DBC file handling
- `get_pattern_analysis_service()` - Pattern detection
- `get_security_monitoring_service()` - Security monitoring
- `get_pin_manager()` - PIN authentication
- `get_network_security_service()` - Network security

## Context-Specific Patterns

### REST API Endpoints
```python
# Standard FastAPI dependency injection
@router.get("/entities")
async def get_entities(
    entity_service: Annotated[Any, Depends(get_entity_service)]
):
    entities = await entity_service.list_entities()
    return entities
```

### WebSocket Handlers
```python
# WebSocket handlers don't have Request context
async def websocket_handler(websocket: WebSocket):
    # Access app from WebSocket scope
    app = getattr(websocket, 'app', None)
    if not app and hasattr(websocket, 'scope'):
        app = websocket.scope.get('app')  # type: ignore

    if app and hasattr(app.state, 'service_registry'):
        service_registry = app.state.service_registry
        service = service_registry.get_service('service_name')
```

### Middleware
```python
# Middleware uses ServiceRegistry-first pattern
async def dispatch(self, request: Request, call_next):
    # Try ServiceRegistry first
    if hasattr(request.app.state, "service_registry"):
        service_registry = request.app.state.service_registry
        if service_registry.has_service("auth_manager"):
            auth_manager = service_registry.get_service("auth_manager")

    # Legacy fallback (for compatibility)
    elif hasattr(request.app.state, "auth_manager"):
        auth_manager = request.app.state.auth_manager
```

### Background Tasks
```python
# Background tasks should get services from app context
async def background_task(app: FastAPI):
    service_registry = app.state.service_registry
    entity_service = service_registry.get_service("entity_service")

    # Perform background operations
    await entity_service.sync_entities()
```

## Adding New Services

### 1. Create Service Class
```python
# backend/services/my_service.py
class MyService:
    def __init__(self, dependency1: Service1, dependency2: Service2):
        self.dep1 = dependency1
        self.dep2 = dependency2

    async def initialize(self) -> None:
        """Optional async initialization"""
        await self.dep1.connect()

    async def shutdown(self) -> None:
        """Cleanup resources"""
        await self.dep1.disconnect()

    def get_health(self) -> dict[str, Any]:
        """Required for health monitoring"""
        return {
            "healthy": self.dep1.is_connected,
            "status": "operational"
        }
```

### 2. Register in ServiceRegistry
```python
# In backend/main.py startup
service_registry.register_service(
    name="my_service",
    factory=lambda: MyService(
        dependency1=service_registry.get_service("dependency1"),
        dependency2=service_registry.get_service("dependency2")
    ),
    dependencies=["dependency1", "dependency2"],
    health_check=lambda s: s.get_health()
)
```

### 3. Add Dependency Function
```python
# In backend/core/dependencies_v2.py
def get_my_service(request: Request) -> MyService:
    """
    Get MyService instance using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The MyService instance

    Raises:
        RuntimeError: If the service is not initialized
    """
    return get_service_with_fallback(request, "my_service")
```

### 4. Use in Endpoints
```python
# In your router file
from backend.core.dependencies_v2 import get_my_service

@router.get("/my-endpoint")
async def my_endpoint(
    my_service: Annotated[MyService, Depends(get_my_service)]
):
    result = await my_service.do_something()
    return {"result": result}
```

## Performance Considerations

### ServiceProxy Pattern (Optional)
For expensive services, use the ServiceProxy pattern for additional features:
- Lazy loading
- TTL-based caching
- Circuit breaker pattern
- Health monitoring
- Performance metrics

```python
# Create proxied dependency with caching
from backend.core.dependencies_v2 import create_proxied_service_dependency

get_expensive_service = create_proxied_service_dependency(
    service_name="expensive_service",
    cache_ttl=300.0,  # 5 minute cache
    enable_circuit_breaker=True
)
```

## Migration Guide

### For Existing Code
1. **Update imports**: Replace `backend.core.dependencies` with `backend.core.dependencies_v2`
2. **Remove function suffixes**: Change `get_*_from_request()` to `get_*()`
3. **Use Annotated types**: Add proper type annotations with `Depends()`
4. **Remove app.state access**: Replace with dependency injection

### Example Migration
```python
# OLD CODE ❌
from backend.core.dependencies import get_feature_manager_from_request

@router.get("/old-endpoint")
async def old_endpoint(request: Request):
    feature_manager = get_feature_manager_from_request(request)
    entity_service = request.app.state.entity_service

# NEW CODE ✅
from backend.core.dependencies_v2 import get_feature_manager, get_entity_service
from typing import Annotated
from fastapi import Depends

@router.get("/new-endpoint")
async def new_endpoint(
    feature_manager: Annotated[Any, Depends(get_feature_manager)],
    entity_service: Annotated[Any, Depends(get_entity_service)]
):
    # Services are automatically injected
```

## Common Pitfalls to Avoid

1. **Don't mix old and new patterns** - Use only dependencies_v2
2. **Don't access app.state directly** - Always use dependency injection
3. **Don't create services manually** - Let ServiceRegistry handle lifecycle
4. **Don't ignore type annotations** - Use Annotated[Type, Depends()] for clarity
5. **Don't bypass health checks** - All services must implement get_health()

## Testing with New Patterns

```python
# In tests, mock the dependencies
from unittest.mock import Mock

@pytest.fixture
def mock_entity_service():
    service = Mock()
    service.list_entities.return_value = {"entity1": {...}}
    return service

async def test_endpoint(mock_entity_service):
    # Override dependency
    app.dependency_overrides[get_entity_service] = lambda: mock_entity_service

    # Test endpoint
    response = await client.get("/endpoint")
    assert response.status_code == 200
```

## Performance Monitoring

View service metrics and health:
```bash
# Check all service health
curl http://localhost:8080/health

# View startup metrics
curl http://localhost:8080/api/features/startup-metrics

# Check service proxy metrics (if using ServiceProxy)
curl http://localhost:8080/api/monitoring/service-proxy-metrics
```
