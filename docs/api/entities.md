# Entity API Reference

!!! warning "API Version Notice"
    This documentation describes the **Domain API v1** which is now the primary API.
    Legacy `/api/entities` endpoints have been removed. Please use `/api/v1/entities` for all entity operations.

Entities represent the devices and systems in your RV, such as lights, tanks, and temperature sensors. The Entity API v1 is the unified surface for **all** entity types — there are no per-device routes (no `/api/lights`); filter by `device_type` instead. It provides guardrail-validated controls and bulk operations. The router lives at `backend/api/domains/entities.py` and is mounted at `/api/v1/entities`.

Real-time entity state changes are pushed over the SSE stream at
`GET /api/events` (`entity_update` / `entity_created` events) — see the
[Realtime API Reference](websocket.md).

## Entity Model (v1)

Each entity in the v1 API has the following structure:

```json
{
  "entity_id": "light_1",
  "name": "Living Room Light",
  "device_type": "light",
  "protocol": "rvc",
  "state": {
    "operating_status": 100,
    "state": "on"
  },
  "area": "living_room",
  "last_updated": "2023-05-18T15:30:45Z",
  "available": true
}
```

### Key Changes from Legacy API:
- `id` → `entity_id`
- `suggested_area` → `area`
- `raw` → `state` (unified state object)
- Added `protocol` field
- Added `available` field for device availability
- Removed `capabilities` (now inferred from device_type)

## List Entities

```
GET /api/v1/entities
```

Returns entities with pagination and filtering.

### Query Parameters

| Parameter   | Type    | Description                                                      |
| ----------- | ------- | ---------------------------------------------------------------- |
| device_type | string  | Optional. Filter by device type (e.g., "light")                  |
| area        | string  | Optional. Filter by area (e.g., "living_room")                   |
| protocol    | string  | Optional. Filter by protocol (e.g., "rvc")                       |
| page        | integer | Optional. Page number for pagination (default: 1)                |
| page_size   | integer | Optional. Number of items per page (default: 50, max: 100)       |

### Example

Get all lights:

```
GET /api/v1/entities?device_type=light
```

Get entities in the bedroom with pagination:

```
GET /api/v1/entities?area=bedroom&page=1&page_size=50
```

### Response

```json
{
  "entities": [
    {
      "entity_id": "light_1",
      "name": "Living Room Light",
      "device_type": "light",
      "protocol": "rvc",
      "state": {
        "operating_status": 100,
        "state": "on"
      },
      "area": "living_room",
      "last_updated": "2023-05-18T15:30:45Z",
      "available": true
    },
    {
      "entity_id": "light_2",
      "name": "Bedroom Light",
      "device_type": "light",
      "protocol": "rvc",
      "state": {
        "operating_status": 0,
        "state": "off"
      },
      "area": "bedroom",
      "last_updated": "2023-05-18T15:25:30Z",
      "available": true
    }
  ],
  "total_count": 2,
  "page": 1,
  "page_size": 50,
  "has_next": false,
  "filters_applied": {
    "device_type": "light",
    "area": null,
    "protocol": null
  }
}
```

## Get Entity by ID

```
GET /api/v1/entities/{entity_id}
```

Returns a specific entity by ID with enhanced metadata.

### Path Parameters

| Parameter | Type   | Description                 |
| --------- | ------ | --------------------------- |
| entity_id | string | The ID of the entity to get |

### Response

```json
{
  "entity_id": "light_1",
  "name": "Living Room Light",
  "device_type": "light",
  "protocol": "rvc",
  "state": {
    "operating_status": 100,
    "state": "on"
  },
  "area": "living_room",
  "last_updated": "2023-05-18T15:30:45Z",
  "available": true
}
```

## Control Entity

```
POST /api/v1/entities/{entity_id}/control
```

Controls an entity with guardrail-validated command/acknowledgment patterns.

### Path Parameters

| Parameter | Type   | Description                     |
| --------- | ------ | ------------------------------- |
| entity_id | string | The ID of the entity to control |

### Request Body

The request body contains a command object with the following structure:

| Field      | Type    | Description                                                                 |
| ---------- | ------- | --------------------------------------------------------------------------- |
| command    | string  | The command to execute: "set", "toggle", "brightness_up", "brightness_down" |
| state      | boolean | Optional. The desired state: true (on) or false (off) (used with "set" command) |
| brightness | integer | Optional. The desired brightness: 0-100 (used with "set" command)           |
| parameters | object  | Optional. Additional command-specific parameters                             |

### Command Examples

Turn a light on:

```json
{
  "command": "set",
  "state": true
}
```

Turn a light off:

```json
{
  "command": "set",
  "state": false
}
```

Set brightness to 75%:

```json
{
  "command": "set",
  "state": true,
  "brightness": 75
}
```

Toggle a light:

```json
{
  "command": "toggle"
}
```

Increase brightness by 10%:

```json
{
  "command": "brightness_up"
}
```

Decrease brightness by 10%:

```json
{
  "command": "brightness_down"
}
```

### Response

The response is an operation result with acknowledgment tracking:

```json
{
  "operation_id": "op-4f2a1c",
  "entity_id": "light_1",
  "status": "success",
  "acknowledged": true,
  "acknowledgment_time_ms": 42.0,
  "error_message": null,
  "error_code": null,
  "execution_time_ms": 55.3,
  "safety_validation": {}
}
```

`status` is one of `success`, `failed`, `timeout`, `unauthorized`, or
`safety_abort`.

## Bulk Control Entities

```
POST /api/v1/entities/bulk-control
```

Control multiple entities in a single operation with partial success handling.

### Request Body

```json
{
  "entity_ids": ["light_1", "light_2", "light_3"],
  "command": {
    "command": "set",
    "state": false
  },
  "ignore_errors": true,
  "timeout_seconds": 5.0
}
```

### Response

```json
{
  "operation_id": "bulk-9d31ab",
  "total_count": 3,
  "success_count": 2,
  "failed_count": 1,
  "timeout_count": 0,
  "safety_abort_count": 0,
  "results": [
    {
      "entity_id": "light_1",
      "operation_id": "op-1",
      "status": "success",
      "acknowledged": true
    },
    {
      "entity_id": "light_2",
      "operation_id": "op-2",
      "status": "success",
      "acknowledged": true
    },
    {
      "entity_id": "light_3",
      "operation_id": "op-3",
      "status": "failed",
      "error_message": "Entity not available"
    }
  ],
  "total_execution_time_ms": 120.5,
  "safety_summary": {}
}
```

## Additional Endpoints

### Get Entity Metadata

```
GET /api/v1/entities/metadata
```

Returns metadata about available device types, areas, and capabilities.

### Get Protocol Summary

```
GET /api/v1/entities/protocol-summary
```

Returns a summary of entities grouped by protocol with statistics.

### Get Entity History

```
GET /api/v1/entities/{entity_id}/history?limit=100&since=<unix-timestamp>
```

Returns the entity's state-change history.

### Coach Configuration

```
GET /api/v1/entities/config/coach
```

Returns coach mapping metadata: areas hierarchy, lighting scenes, and lighting groups.

### Guardrail / Command Halt (Admin)

```
GET  /api/v1/entities/guardrail-status
POST /api/v1/entities/command-halt
POST /api/v1/entities/command-halt/clear
POST /api/v1/entities/reconcile-state
```

Guardrail status, emergency halt of all entity command emission (admin only),
clearing the halt (admin only), and reconciling application state with the
RV-C bus. A halt is broadcast to clients as a `halt_command_emission` SSE
event.

### Entity Mappings

```
POST /api/v1/entities/mappings
```

Creates a new entity mapping from an unmapped DGN/instance pair (broadcast to
clients as an `entity_created` SSE event).

### Debug Endpoints

```
GET /api/v1/entities/health
GET /api/v1/entities/schemas
GET /api/v1/entities/debug/system-info
GET /api/v1/entities/debug/unmapped
GET /api/v1/entities/debug/unknown-pgns
GET /api/v1/entities/debug/missing-dgns
```

Provide health/schema information and debug views of unmapped entries, unknown
PGNs, and missing DGNs.
