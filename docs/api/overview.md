# API Overview

The CoachIQ server provides a RESTful API for interacting with RV-C devices and systems. This page provides an overview of the API structure and common patterns.

## API Base URL

The primary API surface is the Domain API v1, with endpoints under
`/api/v1/{domain}` (see [ADR-0011](../adr/ADR-0011-public-api-v1-naming.md)).
Legacy unversioned routers under `/api/*` still exist for many surfaces; they
are being retired endpoint-by-endpoint as their domain replacements cover the
capability (see [ADR-0003](../adr/ADR-0003-api-v2-only-no-legacy.md)), not
parallel-maintained. New development targets `/api/v1/*`.

### Domain API v1 (Primary)

- **Entities**: `/api/v1/entities` - Entity management and control
- **Diagnostics**: `/api/v1/diagnostics` - System diagnostics and health monitoring
- **Networks**: `/api/v1/networks` - Network interface management
- **System**: `/api/v1/system` - System configuration and status
- **Auth**: `/api/v1/auth` - Domain auth endpoints

### Legacy / specialized APIs

Functionality that has not yet moved to a domain router remains under `/api/*`,
including:

- **CAN Bus**: `/api/can` - Low-level CAN bus operations (plus CAN tools, recorder, analyzer, filter)
- **Configuration**: `/api/config` - System configuration management
- **Authentication**: `/api/auth` - Login, token refresh, magic links, MFA
- **Victron**: `/api/victron` - Victron integration
- **Location**: `/api/location` - Location services
- **Docs**: `/api/docs` - Documentation search

`backend/api/router_config.py` is the source of truth for what is mounted.

## Authentication

The API requires authentication. An `AuthenticationMiddleware` validates a JWT
bearer token (`Authorization: Bearer <token>`) on every request; tokens are
obtained via `/api/auth/login` (with optional MFA and magic-link flows), and a
PIN-based elevation flow exists for sensitive operations. A small set of paths
is excluded from the middleware (health checks, OpenAPI docs, and the
login/refresh endpoints themselves). The SSE stream at `/api/events` uses the
same bearer-token authentication.

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

Domain API v1 endpoints for managing and controlling entities with
command/acknowledgment patterns:

- `GET /api/v1/entities` - List all entities with pagination and filtering
- `GET /api/v1/entities/{entity_id}` - Get details for a specific entity
- `POST /api/v1/entities/{entity_id}/control` - Control an entity with command/acknowledgment
- `POST /api/v1/entities/bulk-control` - Control multiple entities in a single operation
- `GET /api/v1/entities/metadata` - Get available device types and capabilities
- `GET /api/v1/entities/protocol-summary` - Get protocol statistics

See the [Entity API Reference](entities.md) for the full endpoint list.

### CAN Bus API

Endpoints for interacting with the CAN bus directly.

- `GET /api/can/status` - Get status of the CAN bus interface
- `GET /api/can/sniffer` - Get recent CAN messages

### Configuration API

Endpoints for retrieving and modifying system configuration.

- `GET /api/config` - Get current configuration

### Realtime API

Real-time state updates are pushed over a single authenticated Server-Sent
Events stream; diagnostic WebSocket endpoints remain for high-frequency
tooling streams:

- `GET /api/events` - SSE stream of `entity_update`, `entity_created`, and
  `halt_command_emission` events (bearer auth, `Last-Event-ID` gap replay)
- `GET /api/logs/stream` - Admin-only SSE stream of live server logs (log
  viewer); `GET /api/logs/history` serves historical logs
- `WS /ws/can-sniffer`, `/ws/can-recorder`, `/ws/can-analyzer`,
  `/ws/can-filter` - Diagnostic streams for the CAN tools

See the [Realtime API Reference](websocket.md) for details. The old `/api/ws`
entity-data WebSocket has been removed.
