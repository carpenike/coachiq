# Health Check & Monitoring Guide

## Overview

The CoachIQ system provides comprehensive health monitoring through multiple endpoints and patterns, leveraging the ServiceRegistry for centralized health aggregation. This guide covers the health check architecture implemented in Phase 2D of the startup optimization project.

## Health Check Endpoints

### 1. Legacy Health Endpoints (main.py)

#### `/health` - Human-Readable Diagnostic
- **Purpose**: Development and debugging
- **Response**: Always 200 OK with diagnostic information
- **Use Case**: Manual inspection during development

#### `/healthz` - Kubernetes Liveness Probe
- **Purpose**: Basic process health verification
- **Response Time Target**: <5ms
- **Checks**:
  - Process is alive
  - Event loop is responsive
- **Use Case**: Container orchestration liveness checks

#### `/startupz` - Startup Probe
- **Purpose**: Hardware initialization verification
- **Checks**:
  - CAN interface configuration
  - CAN transceiver initialization
- **Use Case**: Kubernetes startup probe to delay traffic

#### `/readyz` - Readiness Probe
- **Purpose**: Comprehensive dependency checking
- **Enhanced with ServiceRegistry**: ✅
- **Checks**:
  - ServiceRegistry health (min 3 healthy services)
  - Hardware initialization
  - Core services operational
  - Entity discovery
  - Protocol systems
  - Safety-critical systems
- **Use Case**: Load balancer health checks

### 2. Enhanced Health API (health.py) - NEW in Phase 2D

#### `/api/health` - Comprehensive Health Check
- **Purpose**: Complete system health with ServiceRegistry integration
- **Features**:
  - IETF health+json compliant
  - ServiceRegistry aggregation
  - Component-level health details
  - Startup metrics
  - Configurable detail levels
- **Query Parameters**:
  - `include_registry`: Include ServiceRegistry details (default: true)
  - `include_metrics`: Include startup metrics (default: true)
  - `include_components`: Include component health (default: true)

**Example Response**:
```json
{
  "status": "pass",
  "version": "1",
  "service_id": "coachiq-production",
  "description": "All systems operational",
  "timestamp": "2025-01-17T12:00:00Z",
  "service_registry": {
    "total_services": 15,
    "service_counts": {
      "HEALTHY": 14,
      "DEGRADED": 1,
      "FAILED": 0
    },
    "services": [
      {
        "name": "persistence_service",
        "status": "HEALTHY",
        "health": "pass"
      }
    ]
  },
  "startup_metrics": {
    "startup_time_seconds": 0.12,
    "total_services": 15,
    "health_check_duration_ms": 15.3
  },
  "checks": {
    "service_registry": {
      "component_name": "service_registry",
      "status": "pass",
      "message": "All 15 services healthy"
    }
  }
}
```

#### `/api/health/services` - Individual Service Health
- **Purpose**: Granular service health information
- **Features**:
  - Filter by service name
  - Filter by status
  - Service metadata
- **Use Case**: Debugging specific service issues

#### `/api/health/ready` - Lightweight Readiness
- **Purpose**: High-frequency readiness monitoring
- **Features**:
  - Minimal overhead
  - Configurable minimum healthy services
  - ServiceRegistry-based
- **Use Case**: Load balancer health checks (alternative to /readyz)

#### `/api/health/startup` - Startup Metrics
- **Purpose**: Startup performance analysis
- **Features**:
  - Service initialization order
  - Startup timing breakdown
  - Current uptime
- **Use Case**: Performance optimization

## Health Check Patterns

### 1. Service Health States (ServiceRegistry)

```python
class ServiceStatus(Enum):
    PENDING = "PENDING"      # Not yet initialized
    STARTING = "STARTING"    # Currently initializing
    HEALTHY = "HEALTHY"      # Fully operational
    DEGRADED = "DEGRADED"    # Partially functional
    FAILED = "FAILED"        # Not operational
```

### 2. IETF Health Status Mapping

- `ServiceStatus.HEALTHY` → `HealthStatus.PASS`
- `ServiceStatus.DEGRADED/STARTING` → `HealthStatus.WARN`
- `ServiceStatus.FAILED/PENDING` → `HealthStatus.FAIL`

### 3. Health Check Implementation Pattern

Services should implement health checks following this pattern:

```python
class MyService(Feature):
    async def check_health(self) -> None:
        """Perform health check, raise exception if unhealthy."""
        if not self._connection:
            raise RuntimeError("Database connection lost")

        # Perform actual health verification
        await self._connection.execute("SELECT 1")

    @property
    def health_details(self) -> Dict[str, Any]:
        """Return detailed health metadata."""
        return {
            "connection_pool_size": self._pool.size,
            "active_connections": self._pool.active_count,
            "last_query_time": self._last_query_time,
        }
```

## Monitoring Guidelines

### 1. Health Check Frequency

- **Liveness**: Every 10 seconds (Kubernetes default)
- **Readiness**: Every 10 seconds during startup, 30 seconds when stable
- **Comprehensive**: Every 30-60 seconds for monitoring dashboards

### 2. Alerting Thresholds

**Critical Alerts**:
- Any safety-critical service in FAILED state
- ServiceRegistry showing < 3 healthy services
- /readyz returning 503 for > 30 seconds

**Warning Alerts**:
- Any service in DEGRADED state for > 5 minutes
- Startup time > 30 seconds
- Entity discovery showing 0 entities for > 60 seconds

### 3. Performance Monitoring

Track these metrics from `/api/health/startup`:
- `startup_time_seconds`: Target < 5 seconds
- `service_counts.HEALTHY`: Should equal total_services
- `health_check_duration_ms`: Target < 50ms

### 4. Integration with Monitoring Systems

**Prometheus Metrics**:
```python
# Exposed at /metrics endpoint
coachiq_health_probe_duration_seconds
coachiq_health_probe_status
coachiq_core_service_up
```

**Grafana Dashboard Queries**:
```promql
# Service health overview
sum(coachiq_core_service_up) by (service)

# Health check performance
histogram_quantile(0.99, coachiq_health_probe_duration_seconds)

# Readiness success rate
rate(coachiq_health_probe_status{endpoint="readyz",status="pass"}[5m])
```

## Best Practices

### 1. Service Implementation

- Always implement `check_health()` for critical services
- Keep health checks lightweight (< 10ms execution time)
- Use caching for expensive checks
- Provide meaningful error messages

### 2. Health Check Design

- Fail fast for critical issues
- Use degraded state for partial functionality
- Include remediation hints in error messages
- Log health state transitions

### 3. Production Deployment

- Configure Kubernetes probes appropriately:
  ```yaml
  livenessProbe:
    httpGet:
      path: /healthz
      port: 8080
    initialDelaySeconds: 10
    periodSeconds: 10

  readinessProbe:
    httpGet:
      path: /readyz
      port: 8080
    initialDelaySeconds: 5
    periodSeconds: 10

  startupProbe:
    httpGet:
      path: /startupz
      port: 8080
    initialDelaySeconds: 0
    periodSeconds: 5
    failureThreshold: 30
  ```

- Use `/api/health/ready` for load balancers requiring faster responses
- Monitor `/api/health` comprehensive endpoint for dashboards
- Set up alerts based on service-specific health details

### 4. Debugging Workflow

1. Check `/api/health` for overall system status
2. Use `/api/health/services?status=FAILED` to identify failed services
3. Check service logs for detailed error messages
4. Use `/api/health/startup` to verify initialization order
5. Monitor `/metrics` for performance trends

## Migration from Legacy Patterns

The new health check system (Phase 2D) enhances but does not replace existing endpoints:

1. **Keep using** `/healthz`, `/readyz`, `/startupz` for Kubernetes
2. **Add monitoring** via `/api/health` endpoints for dashboards
3. **Leverage ServiceRegistry** for centralized health aggregation
4. **Implement** `check_health()` in new services
5. **Migrate gradually** from feature-based to ServiceRegistry-based health

## Security Considerations

- Health endpoints expose system internals - use with caution
- Consider authentication for detailed health endpoints in production
- Sanitize error messages to avoid information leakage
- Rate limit health endpoints to prevent abuse

## Future Enhancements

Based on Phase 2D learnings, future improvements could include:

1. **Historical Health Tracking**: Store health transitions for trend analysis
2. **Dependency Health Propagation**: Cascade health states through dependencies
3. **Custom Health Metrics**: Allow services to define custom health KPIs
4. **Health Check Scheduling**: Adaptive check frequency based on stability
5. **Circuit Breaker Integration**: Automatic degradation based on health
