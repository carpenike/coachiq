# Domain API v1 Documentation

The Domain API v1 provides enhanced functionality over the legacy monolithic API, featuring domain-driven architecture, bulk operations, optimistic updates, and comprehensive monitoring.

## Overview

The Domain API v1 is organized around business domains rather than technical concerns, providing:

- **Enhanced Performance**: Intelligent caching, rate limiting, and optimized bulk operations
- **Better Security**: Fine-grained permissions, API key authentication, and comprehensive audit logging
- **Improved Developer Experience**: TypeScript-first design, comprehensive error handling, and real-time monitoring
- **Scalability**: Domain-specific scaling, caching strategies, and performance optimization

## Architecture

### Domain Structure

```
/api/v1/
├── entities/          # Entity management domain
│   ├── GET /          # List entities with filtering
│   ├── GET /{id}      # Get single entity
│   ├── POST /{id}/control  # Control single entity
│   ├── POST /bulk-control  # Bulk entity operations
│   ├── GET /schemas   # Export TypeScript schemas
│   ├── GET /health    # Domain health check
│   └── POST /cache/invalidate  # Cache management (admin)
├── diagnostics/       # Diagnostics domain (future)
└── analytics/         # Analytics domain (future)
```

### Authentication Methods

1. **JWT Bearer Token** (User authentication)
   ```
   Authorization: Bearer <jwt_token>
   ```

2. **API Key** (Service-to-service)
   ```
   X-API-Key: <api_key>
   ```

3. **Legacy Session** (Fallback)
   - Inherits from existing auth middleware

## Entities Domain API

### List Entities

**Endpoint**: `GET /api/v1/entities`

Retrieve a paginated list of entities with advanced filtering capabilities.

**Query Parameters**:
- `device_type` (string): Filter by device type (light, lock, sensor, etc.)
- `area` (string): Filter by area/zone
- `protocol` (string): Filter by communication protocol (rvc, j1939, etc.)
- `page` (integer): Page number (default: 1)
- `page_size` (integer): Items per page (default: 50, max: 100)

**Response**: `EntityCollectionSchema`
```json
{
  "entities": [
    {
      "entity_id": "light_living_room_001",
      "name": "Living Room Main Light",
      "device_type": "light",
      "protocol": "rvc",
      "state": {
        "state": "on",
        "brightness": 75,
        "color_temperature": 3000
      },
      "area": "living_room",
      "last_updated": "2024-01-15T10:30:00Z",
      "available": true
    }
  ],
  "total_count": 42,
  "page": 1,
  "page_size": 50,
  "has_next": false,
  "filters_applied": {
    "device_type": "light"
  }
}
```

**Example Request**:
```bash
curl -X GET "/api/v1/entities?device_type=light&area=living_room&page=1&page_size=10" \
  -H "Authorization: Bearer <token>"
```

**Cache Headers**:
- `X-Cache`: HIT/MISS
- `X-Cache-TTL`: Cache time-to-live in seconds
- `X-Response-Time`: Response time in milliseconds

### Get Single Entity

**Endpoint**: `GET /api/v1/entities/{entity_id}`

Retrieve detailed information for a specific entity.

**Path Parameters**:
- `entity_id` (string): Unique entity identifier

**Response**: `EntitySchema`
```json
{
  "entity_id": "light_living_room_001",
  "name": "Living Room Main Light",
  "device_type": "light",
  "protocol": "rvc",
  "state": {
    "state": "on",
    "brightness": 75,
    "color_temperature": 3000,
    "last_command": "set_brightness",
    "command_timestamp": "2024-01-15T10:29:45Z"
  },
  "area": "living_room",
  "last_updated": "2024-01-15T10:30:00Z",
  "available": true
}
```

**Error Responses**:
- `404 Not Found`: Entity not found
- `403 Forbidden`: Insufficient permissions

### Control Single Entity

**Endpoint**: `POST /api/v1/entities/{entity_id}/control`

Execute a control command on a specific entity with optimistic update support.

**Path Parameters**:
- `entity_id` (string): Unique entity identifier

**Request Body**: `ControlCommandSchema`
```json
{
  "command": "set",
  "state": true,
  "brightness": 85,
  "parameters": {
    "transition_duration": 2000,
    "color_temperature": 2700
  }
}
```

**Available Commands**:
- `set`: Set explicit state values
- `toggle`: Toggle current state
- `brightness_up`: Increase brightness by 10%
- `brightness_down`: Decrease brightness by 10%

**Response**: `OperationResultSchema`
```json
{
  "entity_id": "light_living_room_001",
  "status": "success",
  "error_message": null,
  "error_code": null,
  "execution_time_ms": 145
}
```

**Status Values**:
- `success`: Operation completed successfully
- `failed`: Operation failed (see error_message)
- `timeout`: Operation timed out
- `unauthorized`: Insufficient permissions

**Example Requests**:

1. **Turn on light with brightness**:
```bash
curl -X POST "/api/v1/entities/light_001/control" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "set",
    "state": true,
    "brightness": 75
  }'
```

2. **Toggle light state**:
```bash
curl -X POST "/api/v1/entities/light_001/control" \
  -H "X-API-Key: <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"command": "toggle"}'
```

### Bulk Control Operations

**Endpoint**: `POST /api/v1/entities/bulk-control`

Execute the same control command on multiple entities efficiently with detailed result tracking.

**Request Body**: `BulkControlRequestSchema`
```json
{
  "entity_ids": [
    "light_living_room_001",
    "light_kitchen_001",
    "light_bedroom_001"
  ],
  "command": {
    "command": "set",
    "state": false
  },
  "ignore_errors": true,
  "timeout_seconds": 30
}
```

**Parameters**:
- `entity_ids` (array): List of entity IDs (max: 100)
- `command` (object): Control command to apply to all entities
- `ignore_errors` (boolean): Continue operation if some entities fail (default: true)
- `timeout_seconds` (integer): Operation timeout (default: 30, max: 120)

**Response**: `BulkOperationResultSchema`

HTTP Status:
- `200 OK`: All operations succeeded
- `207 Multi-Status`: Some operations succeeded, some failed
- `400 Bad Request`: All operations failed

```json
{
  "operation_id": "bulk_op_20240115_103045_abc123",
  "total_count": 3,
  "success_count": 2,
  "failed_count": 1,
  "results": [
    {
      "entity_id": "light_living_room_001",
      "status": "success",
      "execution_time_ms": 120
    },
    {
      "entity_id": "light_kitchen_001",
      "status": "success",
      "execution_time_ms": 135
    },
    {
      "entity_id": "light_bedroom_001",
      "status": "failed",
      "error_message": "Device not responding",
      "error_code": "DEVICE_OFFLINE",
      "execution_time_ms": 5000
    }
  ],
  "total_execution_time_ms": 5255
}
```

**Performance Features**:
- Concurrent execution with configurable concurrency limits
- Individual timeout handling per entity
- Detailed execution timing
- Partial success support

**Example Requests**:

1. **Turn off all lights in living room**:
```bash
curl -X POST "/api/v1/entities/bulk-control" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_ids": ["light_lr_001", "light_lr_002", "light_lr_003"],
    "command": {"command": "set", "state": false},
    "ignore_errors": true,
    "timeout_seconds": 20
  }'
```

2. **Dim all lights to 30%**:
```bash
curl -X POST "/api/v1/entities/bulk-control" \
  -H "X-API-Key: <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_ids": ["light_001", "light_002", "light_003"],
    "command": {"command": "set", "brightness": 30},
    "ignore_errors": false
  }'
```

### Schema Export

**Endpoint**: `GET /api/v1/entities/schemas`

Export TypeScript-compatible schemas for frontend validation and type safety.

**Response**:
```json
{
  "Entity": {
    "type": "object",
    "properties": {
      "entity_id": {"type": "string"},
      "name": {"type": "string"},
      "device_type": {"type": "string"},
      "protocol": {"type": "string"},
      "state": {"type": "object"},
      "area": {"type": "string", "nullable": true},
      "last_updated": {"type": "string", "format": "date-time"},
      "available": {"type": "boolean"}
    },
    "required": ["entity_id", "name", "device_type", "protocol", "state", "last_updated", "available"]
  },
  "ControlCommand": {
    "type": "object",
    "properties": {
      "command": {"type": "string", "enum": ["set", "toggle", "brightness_up", "brightness_down"]},
      "state": {"type": "boolean", "nullable": true},
      "brightness": {"type": "number", "minimum": 0, "maximum": 100, "nullable": true},
      "parameters": {"type": "object", "nullable": true}
    },
    "required": ["command"]
  }
}
```

### Health Check

**Endpoint**: `GET /api/v1/entities/health`

Domain-specific health check with configuration and performance information.

**Response**:
```json
{
  "status": "healthy",
  "feature_enabled": true,
  "bulk_operations_enabled": true,
  "max_bulk_size": 100,
  "validation_enabled": true,
  "entity_count": 42,
  "cache_stats": {
    "enabled": true,
    "hit_rate": 0.85,
    "size_mb": 2.3
  },
  "performance": {
    "avg_response_time_ms": 145,
    "p95_response_time_ms": 320
  }
}
```

### Cache Management (Admin Only)

**Endpoint**: `POST /api/v1/entities/cache/invalidate`

Manually invalidate cache entries for the entities domain.

**Query Parameters**:
- `pattern` (string): Cache pattern to invalidate (default: "*")

**Response**:
```json
{
  "success": true,
  "invalidated_count": 15,
  "pattern": "*",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Endpoint**: `GET /api/v1/entities/cache/stats`

Get cache performance statistics.

**Response**:
```json
{
  "domain": "entities",
  "cache_enabled": true,
  "cache_size": 12485,
  "ttl_entries": 8,
  "memory_usage_estimate": 1048576,
  "hit_rate": 0.82,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Error Handling

### Error Response Format

All domain API endpoints return consistent error responses:

```json
{
  "detail": "Human-readable error message",
  "status_code": 400,
  "timestamp": "2024-01-15T10:30:00Z",
  "error_code": "VALIDATION_ERROR",
  "validation_errors": {
    "entity_ids": ["This field is required"],
    "command.brightness": ["Must be between 0 and 100"]
  }
}
```

### Common Error Codes

- `VALIDATION_ERROR`: Request validation failed
- `ENTITY_NOT_FOUND`: Specified entity does not exist
- `DEVICE_OFFLINE`: Entity device is not responding
- `PERMISSION_DENIED`: Insufficient permissions for operation
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `BULK_SIZE_LIMIT`: Too many entities in bulk operation
- `OPERATION_TIMEOUT`: Operation exceeded timeout limit

### HTTP Status Codes

- `200 OK`: Request successful
- `201 Created`: Resource created successfully
- `207 Multi-Status`: Bulk operation with mixed results
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `413 Request Entity Too Large`: Bulk operation too large
- `422 Unprocessable Entity`: Validation errors
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable

## Rate Limiting

### Rate Limit Headers

All responses include rate limiting information:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642248600
X-RateLimit-Type: domain_api
```

### Rate Limits by Operation Type

| Operation Type | Authenticated User | API Key | Anonymous |
|---------------|-------------------|---------|-----------|
| Read (GET) | 100/minute | 200/minute | 20/minute |
| Write (POST/PUT) | 30/minute | 60/minute | 5/minute |
| Bulk Operations | 10/minute | 20/minute | 2/minute |
| Admin Operations | 10/minute | 10/minute | 0/minute |

### Rate Limit Exceeded Response

```json
{
  "detail": "Rate limit exceeded for domain API",
  "rate_limit": "30/minute",
  "retry_after": 60
}
```

## Monitoring and Performance

### Performance Headers

All responses include performance monitoring headers:

```
X-Response-Time: 145.23ms
X-Domain: entities
X-Operation-Type: bulk
X-Cache: HIT
X-Request-ID: req_20240115_103045_xyz789
```

### Metrics Available

- Request count by domain, operation, status
- Response time percentiles (P50, P95, P99)
- Cache hit/miss rates
- Error rates by type
- Bulk operation statistics
- Authentication method distribution

## Frontend Integration

### React Hooks

The domain API includes TypeScript React hooks for seamless frontend integration:

```typescript
import { useEntitiesV2, useControlEntityV2, useBulkControlEntitiesV2 } from '@/hooks/domains/useEntitiesV2';

// Fetch entities with filtering
const { data: entities, isLoading } = useEntitiesV2({
  device_type: 'light',
  area: 'living_room',
  page: 1,
  page_size: 20
});

// Control single entity with optimistic updates
const controlEntity = useControlEntityV2();
const handleToggle = (entityId: string) => {
  controlEntity.mutate({
    entityId,
    command: { command: 'toggle' }
  });
};

// Bulk operations with selection management
const {
  selectedEntityIds,
  executeBulkOperation,
  bulkOperationState
} = useEntitySelection();
```

### Optimistic Updates

The hooks automatically provide optimistic updates for improved UX:

1. **Immediate UI Response**: State changes appear instantly
2. **Automatic Rollback**: Reverts on error
3. **Conflict Resolution**: Handles concurrent updates
4. **Cache Synchronization**: Keeps data consistent

### Error Handling

```typescript
const controlEntity = useControlEntityV2();

// Automatic error handling with toast notifications
controlEntity.mutate(
  { entityId: 'light_001', command: { command: 'toggle' } },
  {
    onError: (error) => {
      toast.error(`Failed to control entity: ${error.message}`);
    },
    onSuccess: (result) => {
      toast.success(`Entity controlled successfully`);
    }
  }
);
```

## Migration from Legacy API

### Compatibility Layer

The domain API provides compatibility helpers for gradual migration:

```typescript
import { withDomainAPIFallback } from '@/api/domains';

// Automatically falls back to legacy API if domain API fails
const entities = await withDomainAPIFallback(
  () => fetchEntitiesV2(params),
  () => fetchEntitiesLegacy(params),
  { preferDomainAPI: true, fallbackToLegacy: true }
);
```

### Migration Checklist

1. **Update API Calls**: Replace legacy endpoints with domain endpoints
2. **Update Types**: Use new TypeScript types from domain schemas
3. **Add Error Handling**: Implement proper error handling for new error format
4. **Enable Optimistic Updates**: Use domain hooks for better UX
5. **Configure Authentication**: Set up API keys for service-to-service calls
6. **Monitor Performance**: Use new monitoring endpoints for observability

### Breaking Changes

- **Response Format**: New structured response format
- **Error Format**: Standardized error responses
- **Authentication**: Enhanced authentication requirements
- **Rate Limiting**: Different rate limits apply
- **Bulk Operations**: New bulk operation format and capabilities

## Best Practices

### Performance Optimization

1. **Use Pagination**: Always paginate large result sets
2. **Implement Caching**: Leverage built-in caching for read operations
3. **Batch Operations**: Use bulk endpoints for multiple entity operations
4. **Monitor Metrics**: Watch performance metrics and alerts

### Security Guidelines

1. **Use API Keys**: Implement API key authentication for service calls
2. **Principle of Least Privilege**: Grant minimal required permissions
3. **Monitor Access**: Review audit logs regularly
4. **Rotate Keys**: Regularly rotate API keys

### Error Handling

1. **Handle Partial Success**: Properly handle bulk operation results
2. **Implement Retries**: Add retry logic for transient failures
3. **User Feedback**: Provide clear error messages to users
4. **Logging**: Log errors for debugging and monitoring

### Development Workflow

1. **Use TypeScript**: Leverage generated types for type safety
2. **Test Coverage**: Write comprehensive tests for API integrations
3. **Documentation**: Document API usage and error handling
4. **Monitoring**: Set up alerts for API errors and performance issues

## Examples

### Complete React Component Example

```typescript
import React from 'react';
import { useEntitiesV2, useEntitySelection } from '@/hooks/domains/useEntitiesV2';
import { BulkOperationsModalV2 } from '@/components/bulk-operations';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function EntityDashboard() {
  const { data: entityCollection, isLoading, error } = useEntitiesV2({
    device_type: 'light',
    page: 1,
    page_size: 20
  });

  const {
    selectedEntityIds,
    selectEntity,
    deselectEntity,
    executeBulkOperation,
    bulkOperationState
  } = useEntitySelection();

  const [showBulkModal, setShowBulkModal] = React.useState(false);

  if (isLoading) return <div>Loading entities...</div>;
  if (error) return <div>Error: {error.message}</div>;

  const entities = entityCollection?.entities || [];

  const handleBulkTurnOff = async () => {
    try {
      await executeBulkOperation({
        command: { command: 'set', state: false }
      });
    } catch (error) {
      console.error('Bulk operation failed:', error);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Entity Dashboard</h1>
        <div className="space-x-2">
          <Button
            onClick={() => setShowBulkModal(true)}
            disabled={selectedEntityIds.length === 0}
          >
            Bulk Operations ({selectedEntityIds.length})
          </Button>
          <Button
            onClick={handleBulkTurnOff}
            disabled={selectedEntityIds.length === 0 || bulkOperationState.isLoading}
          >
            Turn Off Selected
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {entities.map((entity) => (
          <Card
            key={entity.entity_id}
            className={`cursor-pointer transition-colors ${
              selectedEntityIds.includes(entity.entity_id)
                ? 'ring-2 ring-blue-500'
                : ''
            }`}
            onClick={() => {
              if (selectedEntityIds.includes(entity.entity_id)) {
                deselectEntity(entity.entity_id);
              } else {
                selectEntity(entity.entity_id);
              }
            }}
          >
            <CardHeader>
              <CardTitle className="text-lg">{entity.name}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div>Status: {entity.state.state}</div>
                <div>Brightness: {entity.state.brightness}%</div>
                <div>Area: {entity.area}</div>
                <div>Available: {entity.available ? 'Yes' : 'No'}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <BulkOperationsModalV2
        open={showBulkModal}
        onOpenChange={setShowBulkModal}
        initialSelection={selectedEntityIds}
        entities={entities.reduce((acc, entity) => {
          acc[entity.entity_id] = entity;
          return acc;
        }, {})}
      />
    </div>
  );
}
```

This comprehensive documentation provides developers with everything they need to effectively use the Domain API v1, including detailed endpoint documentation, examples, best practices, and migration guidance.
