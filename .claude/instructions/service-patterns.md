# Service Access Patterns

## 🚨 CRITICAL: Target Architecture Only (Pre-Release)

**IMPORTANT**: We are in pre-release development. Use ONLY the target patterns. Delete legacy code on sight.

### Target State:
- ✅ Repository injection only (no app_state)
- ✅ Direct service implementations (no compatibility adapters)
- ✅ Clean dependency injection everywhere
- ✅ No backward compatibility code
- ✅ Value-adding facades OK (complexity abstraction)
- ❌ No compatibility facades (legacy support)

## Service Access Pattern Evolution

### ✅ Modern Pattern (REQUIRED for all new code)
```python
# Use backend.core.dependencies for all service access
from backend.core.dependencies import (
    get_entity_service,
    get_can_service,
    get_auth_manager,
    get_settings
)
from typing import Annotated
from fastapi import Depends

@router.get("/endpoint")
async def endpoint(
    settings: Annotated[Any, Depends(get_settings)],
    entity_service: Annotated[Any, Depends(get_entity_service)]
):
    # Services are automatically injected by FastAPI
    pass
```

### ❌ Legacy Patterns (DO NOT USE)
```python
# DON'T use get_*_from_request functions
from backend.core.dependencies import get_entity_service_from_request  # ❌

# DON'T access app.state directly
entity_service = request.app.state.entity_service  # ❌

# DON'T create global service instances
global_service = MyService()  # ❌

# DON'T use get_*_from_request functions
entity_service = get_entity_service_from_request(request)  # ❌

# DON'T use FeatureManager at all - it has been removed
from backend.services.feature_manager import FeatureManager  # ❌
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
import logging

logger = logging.getLogger(__name__)

class MyService:
    def __init__(
        self,
        # Required repositories/dependencies first
        repository1: Repository1,
        repository2: Repository2,
        # Optional configuration
        config: dict[str, Any] | None = None,
        # DEPRECATED - app_state should be last if needed for compatibility
        app_state: Any | None = None,
    ):
        """
        Initialize service with repository injection.

        Args:
            repository1: First repository dependency
            repository2: Second repository dependency
            config: Optional configuration
            app_state: DEPRECATED - Use repositories instead
        """
        if app_state is not None:
            logger.warning(
                "MyService initialized with deprecated app_state parameter. "
                "Please use repository injection instead."
            )

        self.repository1 = repository1
        self.repository2 = repository2
        self.config = config or {}

    async def initialize(self) -> None:
        """Optional async initialization"""
        await self.repository1.connect()

    async def shutdown(self) -> None:
        """Cleanup resources"""
        await self.repository1.disconnect()

    def get_health(self) -> dict[str, Any]:
        """Required for health monitoring"""
        return {
            "healthy": self.repository1.is_connected,
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
# Create proxied dependency with caching (future enhancement)
# Note: ServiceProxy pattern is planned but not yet implemented
# For now, use standard dependency injection:
from backend.core.dependencies import get_service_with_fallback

def get_expensive_service(request: Request) -> Any:
    return get_service_with_fallback(request, "expensive_service")
```

## Target Service Architecture

### Clean Service Implementation
```python
# backend/services/my_service.py
class MyService:
    def __init__(
        self,
        repository1: Repository1,
        repository2: Repository2,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize service with repository injection ONLY.
        NO app_state parameter!
        """
        self.repository1 = repository1
        self.repository2 = repository2
        self.config = config or {}
```

### Direct Service Registration
```python
# In backend/main.py - No adapters!
service_registry.register_service(
    name="my_service",
    factory=lambda: MyService(
        repository1=service_registry.get_service("repository1"),
        repository2=service_registry.get_service("repository2"),
    ),
    dependencies=["repository1", "repository2"],
)
```

### Example Migration
```python
# OLD CODE ❌
from backend.core.dependencies import get_feature_manager_from_request

@router.get("/old-endpoint")
async def old_endpoint(request: Request):
    feature_manager = get_feature_manager_from_request(request)
    entity_service = request.app.state.entity_service

# NEW CODE ✅
from backend.core.dependencies import get_feature_manager, get_entity_service
from typing import Annotated
from fastapi import Depends

@router.get("/new-endpoint")
async def new_endpoint(
    feature_manager: Annotated[Any, Depends(get_feature_manager)],
    entity_service: Annotated[Any, Depends(get_entity_service)]
):
    # Services are automatically injected
```

## Fixing Legacy Patterns (DELETE and REPLACE)

### 1. Direct app.state Access
```python
# LEGACY ❌ - DELETE THIS
feature_manager = request.app.state.feature_manager

# TARGET ✅ - REPLACE WITH THIS
feature_manager: Annotated[FeatureManager, Depends(get_feature_manager)]
```

### 2. Service with app_state
```python
# LEGACY ❌ - DELETE ENTIRE CLASS
class MyService:
    def __init__(self, app_state: AppState):
        self.app_state = app_state

# TARGET ✅ - REWRITE FROM SCRATCH
class MyService:
    def __init__(
        self,
        required_repository: Repository,
        other_repository: Repository,
    ):
        self.required_repository = required_repository
        self.other_repository = other_repository
```

### 3. Migration Adapters
```python
# LEGACY ❌ - DELETE ENTIRE FILE
class MyServiceMigrationAdapter(MyService):
    def __init__(self, feature_manager, ...):
        if feature_manager.is_enabled("USE_V2"):
            self._service = MyServiceV2(...)
        else:
            self._service = MyService(...)

# TARGET ✅ - USE V2 DIRECTLY
# Just use MyServiceV2 everywhere, delete adapter
```

## Facade Pattern Guidelines

### ✅ PREFERRED Facades (Use These by Default)

**Safety-Critical Coordination Facades** - These should be your default choice:

```python
# RV-C Protocol Facade - PREFERRED for real-time safety
class RVCProtocolFacade:
    """
    Unified facade for all RV-C protocol operations.
    Coordinates CAN routing, decoding, security, safety events.
    """
    def __init__(self, can_manager, rvc_decoder, security_validator, audit_logger):
        # Centralized protocol processing pipeline

    async def process_can_frame(self, frame) -> ProcessedMessage:
        # 1. Security validation
        # 2. Protocol routing (BAM vs single-frame)
        # 3. Decoding (RV-C vs J1939)
        # 4. Safety event extraction
        # 5. Audit logging

# Safety Operations Facade - PREFERRED for critical operations
class SafetyOperationsFacade:
    """Centralized facade for all safety-critical operations."""
    def __init__(self, safety_service, pin_manager, audit_logger):
        # Ensures authorization, validation, audit trails

    async def execute_safety_operation(self, operation, auth_context):
        # 1. PIN authorization
        # 2. Safety validation
        # 3. Rate limiting
        # 4. Operation execution
        # 5. Audit logging
        # 6. Emergency response coordination

# Entity Control Facade - PREFERRED for coordinated operations
class EntityControlFacade:
    """
    Unified facade for entity operations with safety validation.
    Coordinates state management, protocol routing, real-time updates.
    """
    def __init__(self, entity_repo, safety_validator, can_service, websocket_service):
        # Multi-service coordination

    async def control_entity(self, entity_id, command, authorization):
        # 1. Authorization validation
        # 2. Safety interlock checking
        # 3. Protocol-specific message creation
        # 4. Optimistic state updates
        # 5. CAN message transmission
        # 6. WebSocket broadcasting
        # 7. Audit logging
```

**Complex Subsystem Facades** - Good for abstracting complexity:

```python
# DatabaseManager - Abstracts database complexity
class DatabaseManager:
    """Abstracts SQLAlchemy, connection pooling, migrations."""

# AuthManager - Unifies authentication modes
class AuthManager:
    """Abstracts JWT, sessions, MFA, magic links into one interface."""
```

### When Facades Are PREFERRED:
1. **Safety-Critical Operations** - Emergency stops, interlocks, vehicle control
2. **Real-Time Protocol Coordination** - CAN/RV-C/J1939 processing
3. **Multi-Service Audit Trails** - Security events spanning services
4. **Complex State Management** - Entity control with multiple protocols
5. **Service Orchestration** - System lifecycle with dependencies

### ❌ BAD Facades (Delete These)

**Compatibility Facades** that only exist for migration:

```python
# LEGACY PATTERN - DELETE THIS
class ServiceWithLegacySupport:
    def __init__(self, new_service=None, legacy_service=None):
        self._use_new = new_service is not None

    def operation(self):
        if self._use_new:
            return self._new_service.operation()
        else:
            return self._legacy_service.operation()

# Thin wrappers - DELETE THIS
class CANBusServiceWrapper(CANBusFeature):
    """Just wraps feature to look like service."""
    pass
```

These facades are BAD because they:
- Only exist for backward compatibility
- Add layers without simplifying
- Perpetuate technical debt
- Make debugging harder

## NO Migration Patterns!

**DO NOT CREATE MIGRATION ADAPTERS**

We are in pre-release development. When updating a service:

1. **DELETE** the old service completely
2. **DELETE** any migration adapters
3. **DELETE** any V1/V2 feature flags
4. **CREATE** clean V2 implementation only
5. **UPDATE** all callers to use the new service

Example:
```python
# ❌ DON'T DO THIS
if feature_flag:
    use_v2()
else:
    use_v1()

# ✅ DO THIS
use_v2()  # Only implementation
```

## Facades in Safety-Critical Systems

For RV control and other safety-critical paths, **facades should be the DEFAULT choice** for:

### ALWAYS Use Facades For:
1. **Vehicle Control Operations** - All commands affecting RV movement, braking, steering
2. **Emergency Systems** - Emergency stops, safety interlocks, critical alerts
3. **Multi-Protocol Coordination** - CAN/RV-C/J1939 operations requiring sync
4. **Security Operations** - PIN validation, authentication, audit logging
5. **Real-Time Safety** - Operations with timing constraints affecting safety

### Pattern: Safety-First Facade Design
```python
class VehicleControlFacade:
    """
    REQUIRED facade for all vehicle control operations.
    Ensures safety validation, audit trails, and proper coordination.
    """

    def __init__(
        self,
        safety_validator: SafetyValidator,
        can_service: CANService,
        audit_logger: AuditLogger,
        emergency_system: EmergencySystem
    ):
        self._safety = safety_validator
        self._can = can_service
        self._audit = audit_logger
        self._emergency = emergency_system

    async def execute_vehicle_command(self, command: VehicleCommand) -> CommandResult:
        # MANDATORY safety pipeline - cannot be bypassed
        if not await self._safety.validate_command(command):
            await self._emergency.trigger_safety_stop()
            raise SafetyViolation("Command failed safety validation")

        # Rate limiting for safety
        if not await self._safety.check_rate_limits(command):
            raise RateLimitExceeded("Command rate limit exceeded")

        # Execute with full audit trail
        result = await self._can.send_command(command)
        await self._audit.log_vehicle_command(command, result)

        return result
```

### Sometimes Use Facades For:
- **Complex Subsystems**: Database operations, authentication
- **Service Coordination**: When 3+ services must work together
- **Audit Boundaries**: Operations requiring compliance logging

### Avoid Facades For:
- **Simple CRUD**: Basic repository operations
- **Internal Utilities**: Logging, configuration, simple calculations
- **Performance-Critical Paths**: After profiling shows unacceptable overhead

### Decision Tree: Should I Use a Facade?

```
Is this a safety-critical operation?
├─ YES → Use facade (MANDATORY)
└─ NO → Does it coordinate 3+ services?
    ├─ YES → Use facade (PREFERRED)
    └─ NO → Does it abstract complex subsystem?
        ├─ YES → Use facade (GOOD)
        └─ NO → Use direct service (SIMPLE)
```

## Common Pitfalls to Avoid

1. **Don't access app.state directly** - Always use dependency injection
2. **Don't create services manually** - Let ServiceRegistry handle lifecycle
3. **Don't ignore type annotations** - Use Annotated[Type, Depends()] for clarity
4. **Don't bypass health checks** - All services must implement get_health()
5. **Don't use app_state in new services** - Use repository injection instead
6. **Don't create compatibility facades** - We're pre-release, break things!

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
