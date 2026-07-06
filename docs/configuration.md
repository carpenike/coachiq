# Configuration Management

This document describes the configuration management approach used in CoachIQ. The
canonical schema lives in `backend/core/config.py` as Pydantic Settings classes; this
page covers the structure and the main sections. For worked examples and deployment
recipes, see the [Configuration Guide](configuration-guide.md).

## Environment Variable Patterns

CoachIQ uses a consistent pattern for environment variables to support hierarchical
configuration:

- **Top-level settings**: `COACHIQ_SETTING` (e.g., `COACHIQ_APP_NAME`)
- **Nested settings**: `COACHIQ_SECTION__SETTING` (e.g., `COACHIQ_SERVER__HOST`)

The double underscore (`__`) separates the section name from the setting name. Setting
names map directly to the Pydantic field names in `backend/core/config.py`.

## Configuration Loading Order

Configuration values are loaded in the following order (later values win):

1. Default values specified in the Settings classes
2. Values from a `.env` file (if present)
3. Environment variables

## Top-Level Settings

These settings apply to the entire application (prefix `COACHIQ_`):

- `COACHIQ_APP_NAME`: Application name (default: `CoachIQ`)
- `COACHIQ_APP_VERSION`: Application version
- `COACHIQ_APP_DESCRIPTION`: Application description
- `COACHIQ_APP_TITLE`: API title for documentation
- `COACHIQ_ENVIRONMENT`: Application environment (`development`, `testing`, `staging`, `production`)
- `COACHIQ_DEBUG`: Enable debug mode
- `COACHIQ_TESTING`: Enable testing mode
- `COACHIQ_STATIC_DIR`: Static files directory
- `COACHIQ_RVC_SPEC_PATH`: Path to RV-C spec JSON file
- `COACHIQ_RVC_COACH_MAPPING_PATH`: Path to RV-C coach mapping YAML file
- `COACHIQ_GITHUB_UPDATE_REPO`: GitHub repository for update checks (`owner/repo`)
- `COACHIQ_CONTROLLER_SOURCE_ADDR`: Controller source address (default: `0xF9`)
- `COACHIQ_J1939_ENABLED` / `COACHIQ_FIREFLY_ENABLED`: Protocol enablement toggles

## Configuration Sections

Each section is a nested settings class with its own env-var prefix:

| Section | Env prefix | Purpose |
| ------- | ---------- | ------- |
| Server | `COACHIQ_SERVER__` | Uvicorn bind address, workers, TLS files |
| Security | `COACHIQ_SECURITY__` | Secret key, rate limiting, TLS termination |
| Logging | `COACHIQ_LOGGING__` | Level, format, optional file logging |
| CAN | `COACHIQ_CAN__` | CAN interfaces, bustype, bitrate, interface mappings |
| CAN recorder | `COACHIQ_CAN_RECORDER__` | CAN recording storage path |
| RV-C | `COACHIQ_RVC__` | Spec/coach-mapping file overrides, coach model |
| J1939 | `COACHIQ_J1939__` | J1939 protocol support (Cummins/Allison/chassis) |
| Firefly | `COACHIQ_FIREFLY__` | Firefly RV systems support |
| Victron | `COACHIQ_VICTRON__` | Victron Cerbo GX power system over MQTT |
| Trip log | `COACHIQ_TRIP_LOG__` | GPS trip log (breadcrumbs) via gpsd |
| Time sync | `COACHIQ_TIME_SYNC__` | RV-C time master and GPS DGN broadcasting |
| Spartan K2 | `COACHIQ_SPARTAN_K2__` | Spartan K2 chassis support |
| Multi-network | `COACHIQ_MULTI_NETWORK__` | Multi-network CAN management |
| Persistence | `COACHIQ_PERSISTENCE__` | Data directory, backups (persistence is mandatory) |
| Features | `COACHIQ_FEATURES__` | Feature flags |
| Notifications | `COACHIQ_NOTIFICATIONS__` | Apprise-based notifications (SMTP, Slack, Discord, Pushover, webhook subsections) |
| Auth | `COACHIQ_AUTH__` | Authentication, JWT, OIDC, MFA |
| MCP | `COACHIQ_MCP__` | Embedded MCP OAuth authorization server |
| Router sidecar | `COACHIQ_ROUTER_SIDECAR__` | RouterOS sidecar listener, GPS/Starlink/Nighthawk polling |
| API domains | `COACHIQ_API_DOMAINS__` | Domain API command validation settings |

### Server Settings

Prefix `COACHIQ_SERVER__`. Key settings:

- `COACHIQ_SERVER__HOST`: Bind address (default: `127.0.0.1`; use `0.0.0.0` only on controlled networks)
- `COACHIQ_SERVER__PORT`: Server port (default: `8000`)
- `COACHIQ_SERVER__RELOAD`: Enable auto-reload in development
- `COACHIQ_SERVER__WORKERS`: Number of worker processes
- `COACHIQ_SERVER__ACCESS_LOG`: Enable access logging
- `COACHIQ_SERVER__DEBUG`: Enable server debug mode
- `COACHIQ_SERVER__ROOT_PATH`: Root path for the application

### CAN Settings

Prefix `COACHIQ_CAN__`. Key settings:

- `COACHIQ_CAN__INTERFACES`: CAN interface names, comma-separated (default: `can0`)
- `COACHIQ_CAN__INTERFACE_MAPPINGS`: Logical-to-physical interface mapping, e.g. `'{"house": "can0", "chassis": "can1"}'` (JSON) or `house:can0,chassis:can1`
- `COACHIQ_CAN__BUSTYPE`: python-can bus type (default: `socketcan`)
- `COACHIQ_CAN__BITRATE`: CAN bus bitrate (default: `500000`)
- `COACHIQ_CAN__TIMEOUT`: CAN timeout in seconds
- `COACHIQ_CAN__BUFFER_SIZE`: Message buffer size
- `COACHIQ_CAN__AUTO_RECONNECT`: Auto-reconnect on CAN failure
- `COACHIQ_CAN__FILTERS`: CAN message filters (comma-separated)

### Victron Settings

Prefix `COACHIQ_VICTRON__`. Integrates a Victron Cerbo GX (Venus OS) power system over
MQTT:

- `COACHIQ_VICTRON__ENABLED`: Enable the Victron MQTT integration (default: `false`)
- `COACHIQ_VICTRON__HOST`: Cerbo GX hostname or IP address
- `COACHIQ_VICTRON__PORT`: MQTT broker port (default: `1883`)
- `COACHIQ_VICTRON__USERNAME` / `COACHIQ_VICTRON__PASSWORD`: MQTT credentials (usually unset)
- `COACHIQ_VICTRON__PORTAL_ID`: VRM portal id (auto-discovered when unset)
- `COACHIQ_VICTRON__KEEPALIVE_INTERVAL_SECONDS`: Venus OS keepalive publish interval (default: `30`)
- `COACHIQ_VICTRON__BROADCAST_INTERVAL_SECONDS`: Minimum interval between entity state broadcasts (default: `1`)

### Trip Log Settings

Prefix `COACHIQ_TRIP_LOG__`. Records GPS breadcrumbs from gpsd, segmented into trips
(surfaced on the `/location` page, exportable as GPX):

- `COACHIQ_TRIP_LOG__ENABLED`: Enable GPS trip logging (default: `false`)
- `COACHIQ_TRIP_LOG__GPSD_HOST` / `COACHIQ_TRIP_LOG__GPSD_PORT`: gpsd endpoint (default: `127.0.0.1:2947`)
- `COACHIQ_TRIP_LOG__MIN_DISTANCE_M`: Minimum distance between breadcrumbs (default: `50`)
- `COACHIQ_TRIP_LOG__MIN_INTERVAL_SECONDS`: Minimum time between breadcrumbs while moving (default: `15`)
- `COACHIQ_TRIP_LOG__STATIONARY_SPEED_MPS`: Speed below which the RV is considered stationary (default: `1.0`)
- `COACHIQ_TRIP_LOG__TRIP_GAP_MINUTES`: Stationary time that closes the current trip (default: `20`)
- `COACHIQ_TRIP_LOG__RETENTION_DAYS`: Days of breadcrumbs to keep; `0` keeps everything (default: `0`)

### Time Sync Settings

Prefix `COACHIQ_TIME_SYNC__`. Makes CoachIQ the RV-C time master: it broadcasts
`DATE_TIME_STATUS` and the GPS DGNs from the Pi's clock and gpsd position, and can
synthesize `COMPASS_BEARING_STATUS` from GPS course:

- `COACHIQ_TIME_SYNC__ENABLED`: Enable RV-C time/GPS broadcasting (default: `false`)
- `COACHIQ_TIME_SYNC__INTERFACE`: Logical CAN interface to transmit on (default: `house`)
- `COACHIQ_TIME_SYNC__BROADCAST_INTERVAL_SECONDS`: Broadcast interval (default: `1.0`)
- `COACHIQ_TIME_SYNC__SEND_GPS`: Also broadcast `GPS_POSITION`/`GPS_STATUS`/`GPS_TIME_STATUS` (default: `true`)
- `COACHIQ_TIME_SYNC__SET_COMMAND_INTERVAL_SECONDS`: Interval for periodic `SET_DATE_TIME_COMMAND` nudges; `0` disables (default: `300`)
- `COACHIQ_TIME_SYNC__SEND_COMPASS`: Synthesize `COMPASS_BEARING_STATUS` from GPS course (default: `true`)
- `COACHIQ_TIME_SYNC__COMPASS_MIN_SPEED_MPS`: Minimum speed for GPS course to update the bearing (default: `1.5`)

### Feature Flags

Prefix `COACHIQ_FEATURES__`. Examples:

- `COACHIQ_FEATURES__ENABLE_MAINTENANCE_TRACKING`: Enable maintenance tracking
- `COACHIQ_FEATURES__ENABLE_NOTIFICATIONS`: Enable notifications
- `COACHIQ_FEATURES__ENABLE_VECTOR_SEARCH`: Enable vector search feature
- `COACHIQ_FEATURES__ENABLE_API_DOCS`: Enable API documentation
- `COACHIQ_FEATURES__ENABLE_METRICS`: Enable metrics collection

See `FeaturesSettings` in `backend/core/config.py` for the complete list.

## Using Settings in Code

Settings are accessed through the `get_settings()` function, which returns a cached
instance of the `Settings` class:

```python
from backend.core.config import get_settings

settings = get_settings()
app_name = settings.app_name
server_host = settings.server.host
```

For specific sections, convenience functions are available (e.g.
`get_server_settings()`, `get_can_settings()`, `get_features_settings()`):

```python
from backend.core.config import get_server_settings, get_can_settings

server_settings = get_server_settings()
can_settings = get_can_settings()
```

## Environment-Specific Configuration

Different environments can be configured by setting the `COACHIQ_ENVIRONMENT`
variable: `development` (default), `testing`, `staging`, or `production`.

```python
from backend.core.config import get_settings

settings = get_settings()
if settings.is_development():
    ...  # Development-specific code
elif settings.is_production():
    ...  # Production-specific code
```

## Tips for Working with Configuration

1. Use environment variables for all configuration that changes between environments
2. Use `.env` files for local development, but never commit them to version control
3. Use the provided settings classes rather than accessing environment variables directly
4. Verify variable names against `backend/core/config.py` — field names are the source of truth
5. For sensitive information, use secret files (`*_FILE` variants) or a secret manager in production; on NixOS use `services.coachiq.environmentFile` (see [NixOS Module](nixos-module.md))
