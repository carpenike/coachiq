# CoachIQ Configuration Guide

## Configuration Precedence

CoachIQ uses a layered configuration system with the following precedence (highest to lowest):

1. **Environment Variables** - Always wins
2. **SQLite Persistence** - User preferences stored in database
3. **Configuration Files** - YAML/JSON files
4. **Backend Defaults** - Hardcoded in application

## Configuration Methods

### 1. Environment Variables

All settings can be configured via environment variables using the `COACHIQ_` prefix:

```bash
# Simple values
export COACHIQ_SERVER__PORT=8000
export COACHIQ_LOGGING__LEVEL=DEBUG

# Nested values use double underscore
export COACHIQ_J1939__ENABLED=true
export COACHIQ_TRIP_LOG__ENABLED=true

# Lists use comma separation
export COACHIQ_CAN__INTERFACES=can0,can1,vcan0

# Complex mappings use JSON
export COACHIQ_CAN__INTERFACE_MAPPINGS='{"house":"can0","chassis":"can1"}'
```

Variable names map to the Pydantic field names in `backend/core/config.py`.

### 2. NixOS Module

For NixOS deployments, use the provided module (`nixosModules.default`, configured
under `services.coachiq`):

```nix
{
  services.coachiq = {
    enable = true;
    port = 8000;
    logLevel = "DEBUG";
    settings = {
      COACHIQ_CAN__INTERFACES = "can0,can1";
      COACHIQ_J1939__ENABLED = true;
    };
  };
}
```

The Nix module provides:

- First-class typed options for the load-bearing deployment knobs
- A freeform `settings` attrset that passes `COACHIQ_*` env vars straight through
- Automatic systemd service generation with hardening
- Secret management via `environmentFile`
- Config validation and health checks

See the [NixOS Integration](nixos-integration.md) and [NixOS Module](nixos-module.md)
docs for details.

### 3. Docker Compose

For Docker deployments:

```yaml
version: '3.8'
services:
  coachiq:
    image: coachiq:latest
    environment:
      COACHIQ_SERVER__PORT: 8000
      COACHIQ_PERSISTENCE__DATA_DIR: /data
    volumes:
      - coachiq-data:/data
    devices:
      - /dev/can0:/dev/can0
```

### 4. Data Directory Structure

All CoachIQ data is stored under a single directory (default: `/var/lib/coachiq/`):

```
/var/lib/coachiq/
├── reference/          # Read-only reference data (managed by Nix)
│   ├── rvc.json       # RV-C protocol specification
│   ├── coach_mapping.default.yml
│   └── *.yml          # Coach-specific mappings
├── databases/         # SQLite databases (user data)
├── backups/           # Automatic backups
├── config/            # User configuration overrides
├── themes/            # Custom UI themes
├── dashboards/        # Custom dashboards
├── logs/              # Application logs
├── recordings/        # CAN recordings
└── reports/           # Generated reports
```

**Directory Permissions:**

- `reference/` - Read-only, owned by root (managed by Nix tmpfiles)
- All other directories - Writable by coachiq user

**For Development:**

- Reference files are loaded from `./config/` in the project root
- Or from the Python package via importlib.resources

**Environment Variables:**

- `COACHIQ_PERSISTENCE__DATA_DIR` - Change base directory (default: `/var/lib/coachiq`)
- `COACHIQ_RVC__CONFIG_DIR` - Override reference data location (rarely needed)

Persistence is mandatory in the current architecture; there is no
enable/disable toggle for it.

## Feature Management

Feature flags are typed Pydantic fields on `FeaturesSettings` in
`backend/core/config.py` (there is no separate feature-flags YAML file). They can be
set at three levels:

1. **Backend defaults** - The `Field(default=...)` values in `FeaturesSettings`
2. **Environment/Nix** - Override via `COACHIQ_FEATURES__*` env vars
3. **Runtime API** - Some features support runtime toggling

Override via environment:

```bash
export COACHIQ_FEATURES__ENABLE_MAINTENANCE_TRACKING=true
export COACHIQ_FEATURES__ENABLE_API_DOCS=false
```

## Integration Settings

### Victron Cerbo GX (MQTT)

CoachIQ can integrate a Victron Cerbo GX (Venus OS) power system over MQTT. When
enabled, CoachIQ connects to the Cerbo's MQTT broker, publishes the keepalive Venus OS
requires, and surfaces batteries, chargers, and inverters as CoachIQ entities. The VRM
portal id is auto-discovered from broker traffic if not set.

| Environment Variable | Default | Description |
| -------------------- | ------- | ----------- |
| `COACHIQ_VICTRON__ENABLED` | `false` | Enable the Victron MQTT integration |
| `COACHIQ_VICTRON__HOST` | `""` | Cerbo GX hostname or IP address |
| `COACHIQ_VICTRON__PORT` | `1883` | MQTT broker port on the Cerbo GX |
| `COACHIQ_VICTRON__USERNAME` | unset | MQTT username (usually unset) |
| `COACHIQ_VICTRON__PASSWORD` | unset | MQTT password (usually unset) |
| `COACHIQ_VICTRON__PORTAL_ID` | unset | VRM portal id; auto-discovered when unset |
| `COACHIQ_VICTRON__KEEPALIVE_INTERVAL_SECONDS` | `30.0` | Venus OS keepalive publish interval (broker stops publishing after 60s without one) |
| `COACHIQ_VICTRON__BROADCAST_INTERVAL_SECONDS` | `1.0` | Minimum interval between entity state broadcasts per entity |

### GPS Trip Log

The trip log reads position from the local gpsd (the same daemon the router sidecar
uses) and records distance-sampled breadcrumbs, segmented into trips by stationary
gaps. Trips appear on the `/location` page in the UI and can be exported as GPX.

| Environment Variable | Default | Description |
| -------------------- | ------- | ----------- |
| `COACHIQ_TRIP_LOG__ENABLED` | `false` | Enable GPS trip logging |
| `COACHIQ_TRIP_LOG__GPSD_HOST` | `127.0.0.1` | gpsd host |
| `COACHIQ_TRIP_LOG__GPSD_PORT` | `2947` | gpsd JSON port |
| `COACHIQ_TRIP_LOG__MIN_DISTANCE_M` | `50.0` | Minimum distance between recorded breadcrumbs (meters) |
| `COACHIQ_TRIP_LOG__MIN_INTERVAL_SECONDS` | `15.0` | Minimum time between breadcrumbs while moving (`0` disables) |
| `COACHIQ_TRIP_LOG__STATIONARY_SPEED_MPS` | `1.0` | Below this speed the RV is considered stationary |
| `COACHIQ_TRIP_LOG__TRIP_GAP_MINUTES` | `20.0` | Stationary time that closes the current trip |
| `COACHIQ_TRIP_LOG__RETENTION_DAYS` | `0` | Days of breadcrumbs to keep; `0` keeps everything |

### RV-C Time Sync (Time Master)

When enabled, CoachIQ acts as the coach's RV-C time master: it broadcasts
`DATE_TIME_STATUS` (winning time-master arbitration by source address) and the GPS
DGNs, sourced from the Pi's GPS-disciplined clock and gpsd position. It can also send
periodic `SET_DATE_TIME_COMMAND` nudges to force non-spec-compliant clocks to correct,
and synthesize `COMPASS_BEARING_STATUS` from the GPS course while the coach is moving.

| Environment Variable | Default | Description |
| -------------------- | ------- | ----------- |
| `COACHIQ_TIME_SYNC__ENABLED` | `false` | Enable RV-C time/GPS broadcasting |
| `COACHIQ_TIME_SYNC__INTERFACE` | `house` | Logical CAN interface to transmit on |
| `COACHIQ_TIME_SYNC__BROADCAST_INTERVAL_SECONDS` | `1.0` | `DATE_TIME_STATUS` / GPS broadcast interval |
| `COACHIQ_TIME_SYNC__SEND_GPS` | `true` | Also broadcast `GPS_POSITION`/`GPS_STATUS`/`GPS_TIME_STATUS` |
| `COACHIQ_TIME_SYNC__SET_COMMAND_INTERVAL_SECONDS` | `300.0` | Interval for `SET_DATE_TIME_COMMAND` nudges (`0` disables) |
| `COACHIQ_TIME_SYNC__SEND_COMPASS` | `true` | Synthesize `COMPASS_BEARING_STATUS` from GPS course while moving |
| `COACHIQ_TIME_SYNC__COMPASS_MIN_SPEED_MPS` | `1.5` | Minimum speed for GPS course to update the compass bearing |

## Security Considerations

### Never Put Secrets in:

- Environment variables in scripts
- Nix configuration files
- Git repositories
- Docker images

### Instead Use:

- NixOS secrets management (agenix, sops-nix) via `services.coachiq.environmentFile`
- Docker secrets
- Kubernetes secrets
- HashiCorp Vault
- Environment files with restricted permissions

### Example Secret Management:

```nix
# NixOS with sops-nix or agenix: point environmentFile at a root-readable
# file containing COACHIQ_SECURITY__SECRET_KEY=... / COACHIQ_AUTH__SECRET_KEY=...
services.coachiq.environmentFile = config.age.secrets.coachiq-env.path;
```

```bash
# Docker with secrets
docker secret create coachiq-jwt jwt.key
docker service create \
  --secret coachiq-jwt \
  --env COACHIQ_SECURITY__SECRET_KEY_FILE=/run/secrets/coachiq-jwt \
  coachiq:latest
```

## Validation and Debugging

### Check Current Configuration:

```bash
# Show effective configuration
poetry run python scripts/validate-config.py

# Test configuration without starting service
poetry run python -c "from backend.core.config import get_settings; print(get_settings())"
```

### Common Issues:

1. **Environment variable not taking effect**
   - Check spelling and case (use UPPER_SNAKE_CASE)
   - Ensure double underscore for nesting
   - Verify the variable is exported

2. **Type conversion errors**
   - Booleans: use "true"/"false" (lowercase)
   - Lists: use comma separation
   - Numbers: ensure no quotes in shell

3. **Nix module not applying**
   - Run `nixos-rebuild switch` not just `nixos-rebuild build`
   - Check systemd service: `systemctl status coachiq`
   - View logs: `journalctl -u coachiq -f`

## Migration Guide

See `scripts/migrate-to-nix.sh` for automated migration assistance.

## Reference

- Configuration structure and section overview: [Configuration Management](configuration.md)
- Nix module options: `nix/module.nix` and [NixOS Module](nixos-module.md)
- Backend defaults (source of truth): `backend/core/config.py`
