# API Overview

The CoachIQ server provides a RESTful API for interacting with RV-C devices and systems. This page provides an overview of the API structure and common patterns.

## API Base URL

The primary API uses Domain API v1 with endpoints under `/api/v1/{domain}`. Legacy endpoints under `/api` have been deprecated and removed.

### Domain API v1 (Primary)

- **Entities**: `/api/v1/entities` - Entity management with safety-critical patterns
- **Diagnostics**: `/api/v1/diagnostics` - System diagnostics and health monitoring
- **Networks**: `/api/v1/networks` - Network interface management
- **System**: `/api/v1/system` - System configuration and status

### Specialized APIs

Some specialized functionality remains under `/api`:
- **CAN Bus**: `/api/can` - Low-level CAN bus operations
- **Configuration**: `/api/config` - System configuration management
- **Authentication**: `/api/auth` - Authentication and authorization

## Authentication

Currently, the API doesn't require authentication. This may change in future versions.

## Response Format

Most API endpoints return JSON responses with the following general structure:

```json
{
  "key1": "value1",
  "key2": "value2",
  ...
}
```

List endpoints typically return an array of objects:

```json
[
  { "id": "light_1", ... },
  { "id": "light_2", ... },
  ...
]
```

## Error Handling

The API uses standard HTTP status codes to indicate the success or failure of requests:

- `200 OK`: The request was successful
- `400 Bad Request`: The request was invalid or cannot be served
- `404 Not Found`: The requested resource was not found
- `500 Internal Server Error`: An error occurred on the server

Error responses include a JSON body with details about the error:

```json
{
  "detail": "Error message"
}
```

## API Categories

The API is organized into the following categories:

### Entity API v1

Domain API v1 endpoints for managing and controlling entities with safety-critical patterns:

- `GET /api/v1/entities` - List all entities with pagination and advanced filtering
- `GET /api/v1/entities/{entity_id}` - Get details for a specific entity
- `POST /api/v1/entities/{entity_id}/control` - Control an entity with command/acknowledgment
- `POST /api/v1/entities/bulk/control` - Control multiple entities in a single operation
- `GET /api/v1/entities/metadata` - Get available device types and capabilities
- `GET /api/v1/entities/protocol-summary` - Get protocol statistics

### CAN Bus API

Endpoints for interacting with the CAN bus directly.

- `GET /api/can/status` - Get status of the CAN bus interface
- `GET /api/can/sniffer` - Get recent CAN messages

### Configuration API

Endpoints for retrieving and modifying system configuration.

- `GET /api/config` - Get current configuration

### WebSocket API

The server also provides WebSocket endpoints for real-time updates.

- `WS /api/ws` - WebSocket connection for entity state updates
