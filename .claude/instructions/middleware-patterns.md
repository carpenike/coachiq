# Middleware Architecture Patterns

## 🏗️ Edge Layer vs Application Layer Separation

**CRITICAL**: This RV-C vehicle control system uses a split middleware architecture for optimal performance, security, and maintainability.

### Architectural Principle: Context Awareness

**Edge Layer (Caddy)**: Handles tasks that are *application-agnostic* - operates on raw HTTP requests, connections, and IPs without understanding business logic.

**Application Layer (FastAPI)**: Handles tasks that are *context-aware* - understands users, permissions, application state, and RV-C command semantics.

## Current Middleware Distribution

### ✅ Moved to Caddy Edge Layer

#### 1. CORS Handling
```caddyfile
# Caddy handles CORS more efficiently than FastAPI
@options method OPTIONS
header @options {
    Access-Control-Allow-Origin "*"
    Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS"
    Access-Control-Allow-Headers "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, Cache-Control"
    Access-Control-Allow-Credentials "true"
}
respond @options 204
```

**Why Caddy**: Pure transport-level concern, no business logic required.

#### 2. Request ID Generation
```caddyfile
# Caddy generates UUID-based request IDs for tracing
reverse_proxy localhost:8000 {
    header_up X-Request-ID {http.request.uuid}
}
```

**Why Caddy**: Edge-layer tracing, consistent across all requests, better performance.

#### 3. IP-based Rate Limiting
```caddyfile
# First line of defense - IP-based limits
rate_limit {
    zone auth {
        key {http.request.remote.host}
        window 1m
        events 5  # 5 auth attempts per minute per IP
    }
}
```

**Why Caddy**: No application context needed, protects Python from DoS attacks.

#### 4. Response Compression
```caddyfile
# More efficient than Python-level compression
encode {
    gzip
}
```

**Why Caddy**: Better performance, offloads CPU-intensive work from Python.

#### 5. DDoS Protection
- **Handled by**: Caddy rate limiting zones
- **Replaced**: NetworkSecurityMiddleware (removed entirely)
- **Benefit**: Better performance, architectural clarity

### ✅ Remains in FastAPI Application Layer

#### 1. Authentication Middleware
```python
# Context-aware authentication with business logic
class AuthenticationMiddleware:
    async def dispatch(self, request: Request, call_next):
        # JWT validation, user context, session management
        # MUST remain in FastAPI for security context
```

**Why FastAPI**: Requires user context, business logic, ServiceRegistry integration.

#### 2. Runtime Validation Middleware
```python
# Safety-critical validation for RV-C commands
class RuntimeValidationMiddleware:
    async def dispatch(self, request: Request, call_next):
        # Pydantic schema validation for vehicle control
        # Type safety enforcement for safety-critical operations
```

**Why FastAPI**: Understands RV-C protocol semantics, safety-critical validation.

#### 3. User-aware Rate Limiting
```python
# SlowAPI with user/session context
from backend.middleware.rate_limiting import auth_limiter

@auth_rate_limit
async def login_endpoint():
    # Per-user, per-username rate limiting
    # Business logic dependent
```

**Why FastAPI**: Requires user context, safety-critical operation limits.

#### 4. Performance Middleware
```python
# Application-specific metrics and tracing
class PerformanceMiddleware:
    async def __call__(self, scope, receive, send):
        # Consumes X-Request-ID from Caddy or generates fallback
        # Application-level performance metrics
```

**Why FastAPI**: Application-specific metrics, request context propagation.

#### 5. Audit Context Middleware
```python
# User-aware audit logging
class AuditContextMiddleware:
    async def dispatch(self, request: Request, call_next):
        # User tracking, distributed tracing, compliance logging
```

**Why FastAPI**: Requires authenticated user context, business logic.

#### 6. Secure Authentication Middleware
```python
# Complex authentication flows
class SecureAuthenticationMiddleware:
    async def dispatch(self, request: Request, call_next):
        # HttpOnly cookies, token refresh, safety-critical endpoint protection
```

**Why FastAPI**: Complex business logic, ServiceRegistry integration.

## Migration Guidelines

### When to Move to Caddy
1. **Transport-level concerns** - No business logic required
2. **Performance critical** - CPU-intensive operations (compression, static files)
3. **First line of defense** - IP-based protection before hitting Python
4. **Application-agnostic** - Works the same regardless of application logic

### When to Keep in FastAPI
1. **Context-aware** - Requires user, session, or business context
2. **Safety-critical** - RV-C vehicle control validation
3. **ServiceRegistry dependent** - Needs access to application services
4. **Complex business logic** - Multi-step validation, state management

### Decision Tree
```
Is this middleware safety-critical for vehicle control?
├─ YES → Keep in FastAPI (MANDATORY)
└─ NO → Does it require user/business context?
    ├─ YES → Keep in FastAPI
    └─ NO → Does it improve performance if moved to edge?
        ├─ YES → Move to Caddy
        └─ NO → Evaluate based on architectural clarity
```

## Development vs Production

### Development Mode (FastAPI only)
- **CORS**: Handled by FastAPI fallback (middleware detects missing Caddy headers)
- **Request ID**: Generated locally if X-Request-ID header not present
- **Rate Limiting**: Full SlowAPI rate limiting active
- **Compression**: Handled by FastAPI if enabled

### Production Mode (Caddy + FastAPI)
- **CORS**: Handled by Caddy (FastAPI middleware disabled)
- **Request ID**: Generated by Caddy, consumed by FastAPI
- **Rate Limiting**: Split between Caddy (IP-based) and FastAPI (user-aware)
- **Compression**: Handled by Caddy

## Configuration Patterns

### Caddy Configuration
```caddyfile
# Always document the middleware separation strategy
# MIDDLEWARE SEPARATION STRATEGY:
# - CORS handling: Moved from FastAPI to Caddy (better performance)
# - Request ID generation: Moved from FastAPI to Caddy (edge-layer tracing)
# - Rate limiting: SPLIT ARCHITECTURE
#   * Caddy (IP-based): First line of defense
#   * FastAPI (User-aware): Context-aware limits for safety-critical ops
```

### FastAPI Configuration
```python
# Document what was moved to Caddy
# CORS handling moved to Caddy edge layer - see config/Caddyfile.example

# Update middleware to consume Caddy headers
# Extract request ID from Caddy or generate fallback for development
headers = Headers(scope=scope)
request_id = headers.get("X-Request-ID") or generate_request_id()
```

### SecurityConfigService Integration
```python
async def get_caddy_rate_limits(self) -> dict[str, Any]:
    """
    Get rate limit configuration for Caddy edge layer.

    These are IP-based limits that should be configured in Caddyfile.
    The FastAPI application handles user-aware limits separately.
    """
    # Return Caddy-compatible configuration
```

## Testing Considerations

### Development Testing
- **Ensure fallbacks work**: Test FastAPI without Caddy headers
- **Verify middleware order**: Ensure proper initialization sequence
- **Test rate limiting**: Verify both IP-based and user-aware limits

### Production Testing
- **End-to-end tracing**: Verify request IDs flow from Caddy through FastAPI
- **Rate limit coordination**: Test that Caddy + FastAPI limits work together
- **Performance validation**: Measure improvement from edge-layer processing

## Common Pitfalls

### ❌ Don't Do This
```python
# Don't hardcode assumptions about Caddy presence
if caddy_header_present:
    use_caddy_flow()
else:
    use_fastapi_flow()  # WRONG - creates brittle code
```

### ✅ Do This
```python
# Graceful fallback pattern
request_id = headers.get("X-Request-ID") or generate_request_id()
# Works in both development and production
```

### ❌ Don't Duplicate Logic
```python
# Don't implement the same rate limiting in both layers
caddy_rate_limit = True
fastapi_rate_limit = True  # REDUNDANT
```

### ✅ Split Responsibilities
```python
# Clear separation of concerns
# Caddy: IP-based rate limiting (transport layer)
# FastAPI: User-aware rate limiting (application layer)
```

## Security Implications

### Trust Boundary
- **Trust boundary**: Network interface of FastAPI container
- **Never blindly trust**: Caddy headers without validation (except informational ones)
- **Always verify**: Security-relevant headers like Authorization

### Attack Surface Reduction
- **Caddy shields FastAPI**: From transport-level attacks
- **FastAPI focuses**: On business logic security
- **Defense in depth**: Multiple layers of protection

## Monitoring and Observability

### Caddy Metrics
- **Transport-level**: Request counts, response codes, TLS handshake stats
- **Rate limiting**: IP-based rate limit violations
- **Performance**: Total request duration including network latency

### FastAPI Metrics
- **Business-level**: `rvc_commands_executed`, `active_websockets`
- **Application processing**: Time spent in Python excluding network
- **User context**: Authentication success/failure, user-specific metrics

This architecture provides optimal separation of concerns while maintaining safety-critical validation where it belongs - in the application layer with full business context.
