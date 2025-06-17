# ServiceProxy Pattern Documentation

## Overview

The ServiceProxy pattern provides an enhanced abstraction layer for service access in CoachIQ, adding resilience features like caching, health checks, circuit breakers, and performance monitoring. This pattern eliminates direct dependencies on FastAPI Request objects and provides a more testable, maintainable service access layer.

**Phase 2O: Service Proxy Pattern Implementation**

## Key Features

- **Lazy Loading**: Services are loaded on-demand and cached for performance
- **Caching**: Configurable TTL-based caching (default 5 minutes)
- **Circuit Breaker**: Automatic failure detection with recovery mechanisms
- **Health Checks**: Proactive service health validation
- **Metrics**: Performance monitoring and success/failure tracking
- **Fallbacks**: Graceful degradation when services are unavailable
- **Thread Safety**: Async-safe operations with proper locking

## Architecture

```python
# Core Components
ServiceProvider      # Abstract service resolution interface
ServiceProxy         # Main proxy with caching and circuit breaker
ServiceProxyManager  # Centralized proxy lifecycle management

# Provider Implementations
ServiceRegistry_Provider   # Uses ServiceRegistry for resolution
AppState_Provider         # Legacy fallback to app.state
CompositeServiceProvider  # Tries multiple providers in order
```

## Usage

### Basic ServiceProxy Usage

```python
from backend.core.service_proxy import create_service_proxy, CircuitBreakerConfig

# Create a service proxy
proxy = create_service_proxy(
    service_name="feature_manager",
    service_registry_getter=lambda: get_service_registry(request),
    app_state_getter=lambda: request.app.state,
    cache_ttl=60.0,  # 1 minute cache
    circuit_config=CircuitBreakerConfig(failure_threshold=3)
)

# Get service (async)
service = await proxy.get()

# Get service with fallback
service = await proxy.get_with_fallback(lambda: create_default_service())

# Check health
is_healthy = await proxy.check_health()

# Get metrics
metrics = proxy.get_metrics()
print(f"Success rate: {metrics.success_rate}%")
```

### Enhanced Dependencies (dependencies_v2)

```python
from backend.core.dependencies_v2 import (
    get_feature_manager_proxied,
    get_entity_service_proxied,
    create_proxied_service_dependency
)

# Use enhanced dependencies with ServiceProxy
@router.get("/example")
async def example_endpoint(
    feature_manager = Depends(get_feature_manager_proxied),
    entity_service = Depends(get_entity_service_proxied),
):
    # Services are cached and circuit-breaker protected
    if feature_manager.is_enabled("example_feature"):
        return await entity_service.get_entities()

# Create custom proxied dependency
proxied_custom_service = create_proxied_service_dependency(
    service_name="custom_service",
    cache_ttl=30.0,  # 30 second cache
    enable_circuit_breaker=True
)

@router.get("/custom")
async def custom_endpoint(
    custom_service = Depends(proxied_custom_service)
):
    return custom_service.do_something()
```

### Management and Monitoring

```python
from backend.core.dependencies_v2 import (
    get_service_proxy_metrics,
    invalidate_all_service_caches,
    reset_all_circuit_breakers
)

# Get proxy metrics and health status
metrics = get_service_proxy_metrics()
print("Service Metrics:", metrics["metrics"])
print("Health Status:", metrics["health"])

# Cache management (useful for development)
invalidate_all_service_caches()

# Circuit breaker management (useful for recovery)
reset_all_circuit_breakers()
```

## Configuration

### Circuit Breaker Configuration

```python
from backend.core.service_proxy import CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=5,      # Failures before opening circuit
    recovery_timeout=30.0,    # Seconds before trying half-open
    success_threshold=3,      # Successes to close circuit from half-open
    timeout=5.0               # Timeout for service calls
)
```

### Cache Configuration

- **Default TTL**: 5 minutes (300 seconds)
- **Feature Manager**: 1 minute (frequently accessed)
- **Entity Service**: 30 seconds (real-time data)
- **Config Service**: 5 minutes (stable configuration)
- **Security Services**: 30 seconds (security-sensitive)

## Circuit Breaker States

1. **CLOSED**: Normal operation, requests pass through
2. **OPEN**: Service failing, requests blocked immediately
3. **HALF_OPEN**: Testing if service recovered, limited requests allowed

## Metrics and Monitoring

Each ServiceProxy tracks:

```python
@dataclass
class ServiceMetrics:
    total_requests: int           # Total requests processed
    successful_requests: int      # Successful requests
    failed_requests: int          # Failed requests
    avg_response_time: float      # Average response time
    last_success_time: float      # Timestamp of last success
    last_failure_time: float      # Timestamp of last failure
    cache_hits: int              # Cache hit count
    cache_misses: int            # Cache miss count

    @property
    def success_rate(self) -> float  # Success rate percentage
    def failure_rate(self) -> float  # Failure rate percentage
```

## Integration with Existing Code

The ServiceProxy pattern integrates seamlessly with existing dependency injection:

### Standard Pattern (Current)
```python
from backend.core.dependencies_v2 import get_feature_manager

@router.get("/standard")
async def standard_endpoint(
    feature_manager = Depends(get_feature_manager)
):
    return feature_manager.get_features()
```

### Enhanced Pattern (With ServiceProxy)
```python
from backend.core.dependencies_v2 import get_feature_manager_proxied

@router.get("/enhanced")
async def enhanced_endpoint(
    feature_manager = Depends(get_feature_manager_proxied)
):
    # Same interface, enhanced resilience
    return feature_manager.get_features()
```

## Benefits

1. **Resilience**: Circuit breakers prevent cascade failures
2. **Performance**: Caching reduces redundant service lookups
3. **Monitoring**: Built-in metrics for service health tracking
4. **Testability**: Clean abstraction without FastAPI dependencies
5. **Compatibility**: Works alongside existing dependency patterns
6. **Flexibility**: Configurable caching and circuit breaker behavior

## When to Use ServiceProxy

**Recommended for:**
- Production deployments requiring high availability
- Services with expensive initialization or network calls
- Critical services that need circuit breaker protection
- Systems requiring detailed service metrics

**Standard dependencies sufficient for:**
- Development environments
- Non-critical services
- Services with fast, reliable access patterns
- Simple CRUD operations

## Implementation Status

✅ **Phase 2O Complete**
- ServiceProxy core implementation with caching and circuit breakers
- Integration with dependencies_v2 module
- Enhanced dependency functions for key services
- Comprehensive metrics and monitoring capabilities
- Type-safe implementation with full async support

The ServiceProxy pattern is now available as an optional enhancement to the existing dependency injection system, providing additional resilience and monitoring capabilities for production deployments while maintaining full backward compatibility.
