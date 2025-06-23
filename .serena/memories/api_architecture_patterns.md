# API Architecture Patterns

## Critical Patterns for Frontend-Backend Communication

### 1. Domain API v2 (PREFERRED for new development)
- **Pattern**: `/api/v2/{domain}` endpoints
- **Examples**:
  - `/api/v2/entities` - Entity management with bulk operations
  - `/api/v2/analytics` - Analytics and reporting
  - `/api/v2/diagnostics` - System diagnostics
- **Features**: Caching, rate limiting, bulk operations, monitoring

### 2. Unified Entity API (MANDATORY)
- **Pattern**: Always use `/api/entities`, NEVER `/api/lights`, `/api/locks`
- **Endpoints**:
  ```
  GET    /api/entities                    # List all
  GET    /api/entities?device_type=light  # Filter
  GET    /api/entities/{id}               # Get one
  POST   /api/entities/{id}/control       # Control
  PUT    /api/entities/{id}               # Update config
  DELETE /api/entities/{id}               # Remove
  ```

### 3. Health Endpoints
- **Pattern**: Root level, NOT under /api
- **Correct**: `/healthz`, `/readyz`, `/metrics`
- **Wrong**: `/api/healthz`, `/api/health`

### 4. WebSocket Connections
- **Endpoint**: `/ws/entities` for real-time updates
- **Message Types**:
  - `entity_update` - State changes
  - `system_status` - System events
  - `safety_alert` - Critical alerts

### 5. Entity Control Commands
```typescript
interface EntityControlCommand {
  command: "set" | "toggle" | "brightness_up" | "brightness_down" | "custom";
  state?: boolean;
  brightness?: number;
  parameters?: Record<string, any>;
}
```

### 6. Response Format Changes
- **NEW**: Use `status` field: "success" | "error" | "pending" | "safety_blocked"
- **OLD**: Avoid boolean `success` field
- **Example**:
  ```json
  {
    "status": "success",
    "entity_id": "light_001",
    "result": { ... }
  }
  ```

### 7. Authentication Headers
- **JWT**: `Authorization: Bearer <token>`
- **API Key**: `X-API-Key: <key>`
- **Session**: Cookie-based (legacy)

### 8. Error Response Format
```json
{
  "detail": "Human-readable error",
  "status_code": 400,
  "error_code": "VALIDATION_ERROR",
  "validation_errors": { ... }
}
```

### 9. Bulk Operations (Domain API v2)
```typescript
// Request
POST /api/v2/entities/bulk/control
{
  "entity_ids": ["light_001", "light_002"],
  "command": { "command": "set", "state": false }
}

// Response
{
  "successful": ["light_001"],
  "failed": {
    "light_002": "Device offline"
  }
}
```

### 10. Modern Service Access (Backend)
- Import from `backend.core.dependencies`
- Use `Annotated[Type, Depends(get_service)]`
- Never access `app.state` directly
- ServiceRegistry manages lifecycles

## Frontend API Client Patterns

### React Query Keys
```typescript
// Domain API v2
['entities-v2', filters]
['entity-v2', entityId]

// Legacy API
['entities', filters]
['entity', entityId]
```

### Optimistic Updates
```typescript
// Use optimistic updates for entity control
onMutate: async (data) => {
  // Cancel queries
  // Update cache optimistically
  // Return rollback context
}
```

### API Client Location
- Domain v2: `frontend/src/api/domains/`
- Legacy: `frontend/src/api/endpoints.ts`
- Hooks: `frontend/src/hooks/domains/`
