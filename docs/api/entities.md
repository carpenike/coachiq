# Entity API Reference

!!! warning "API Version Notice"
    This documentation describes the **Domain API v1** which is now the primary API.
    Legacy `/api/entities` endpoints have been removed. Please use `/api/v1/entities` for all entity operations.

Entities represent the devices and systems in your RV, such as lights, tanks, and temperature sensors. The Entity API v1 provides enhanced safety-critical controls and bulk operations.

## Entity Model (v2)

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

Returns entities with enhanced pagination, filtering, and safety-critical metadata.

### Query Parameters

| Parameter   | Type    | Description                                                      |
| ----------- | ------- | ---------------------------------------------------------------- |
| device_type | string  | Optional. Filter by device type (e.g., "light")                  |
| area        | string  | Optional. Filter by area (e.g., "living_room")                   |
| page        | integer | Optional. Page number for pagination (default: 1)                |
| page_size   | integer | Optional. Number of items per page (default: 100, max: 1000)     |
| sort_by     | string  | Optional. Sort field (entity_id, name, last_updated)             |
| sort_order  | string  | Optional. Sort order (asc, desc) (default: asc)                  |

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
  "items": [
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
  "total": 2,
  "page": 1,
  "page_size": 100,
  "total_pages": 1
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

Controls an entity with safety-critical command/acknowledgment patterns.

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

```json
{
  "entity_id": "light_1",
  "success": true,
  "command": {
    "command": "set",
    "state": true,
    "brightness": 75
  },
  "acknowledgment": {
    "timestamp": "2023-05-18T15:30:46Z",
    "source": "rvc",
    "confirmed": true
  },
  "new_state": {
    "operating_status": 75,
    "state": "on"
  }
}
```

## Bulk Control Entities

```
POST /api/v1/entities/bulk/control
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
  "options": {
    "continue_on_error": true,
    "timeout": 5.0
  }
}
```

### Response

```json
{
  "success": true,
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "results": [
    {
      "entity_id": "light_1",
      "success": true,
      "acknowledgment": {
        "timestamp": "2023-05-18T15:30:46Z",
        "confirmed": true
      }
    },
    {
      "entity_id": "light_2",
      "success": true,
      "acknowledgment": {
        "timestamp": "2023-05-18T15:30:46Z",
        "confirmed": true
      }
    },
    {
      "entity_id": "light_3",
      "success": false,
      "error": "Entity not available"
    }
  ]
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

### Debug Endpoints

```
GET /api/v1/entities/debug/pending-commands
GET /api/v1/entities/debug/state-sync
```

Provides debug information for pending commands and state synchronization (requires debug mode).
