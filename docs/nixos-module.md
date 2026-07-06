# NixOS Module Reference

This document is the option reference for the CoachIQ NixOS module
(`nixosModules.default` in the flake, defined in `nix/module.nix`). The module runs
CoachIQ as a hardened systemd service configured under `services.coachiq`.

The module uses a hybrid options pattern (see
[ADR-0009](adr/ADR-0009-nix-module-hybrid-options.md)): only load-bearing deployment
knobs are first-class typed options; every other non-secret setting passes through the
freeform `settings` attrset as `COACHIQ_*` environment variables, validated at runtime
by the backend's Pydantic schema in `backend/core/config.py`.

## Basic Usage

```nix
# In your flake-based NixOS configuration
{
  imports = [
    inputs.coachiq.nixosModules.default
  ];

  services.coachiq = {
    enable = true;
    settings = {
      COACHIQ_CAN__INTERFACES = "can0,can1";
    };
  };
}
```

## First-Class Options

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `enable` | boolean | `false` | Enable the CoachIQ RV-C network server |
| `package` | package | `self.packages.<system>.coachiq` | The CoachIQ package to run |
| `host` | string | `"127.0.0.1"` | Interface to bind. The default assumes a reverse proxy on the same host; use `"0.0.0.0"` only on controlled networks |
| `port` | port | `8000` | TCP port to bind on `host` |
| `dataDir` | string | `"/var/lib/coachiq"` | Base directory for persistent data (maps to `COACHIQ_PERSISTENCE__DATA_DIR`; persistence is mandatory) |
| `environmentFile` | null or path | `null` | Optional root-readable systemd `EnvironmentFile` carrying secrets |
| `openFirewall` | boolean | `false` | Open `port` in the host firewall (default false: expected topology is a local reverse proxy) |
| `logLevel` | enum `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` | `"INFO"` | CoachIQ logging level |
| `tlsTerminationIsExternal` | boolean | `false` | Set when Caddy or another trusted reverse proxy terminates TLS (sets `COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL=true`) |

### RouterOS Sidecar Options

The plain-HTTP RouterOS sidecar listener is intended only for the RV LAN and is not
mounted under the main authenticated CoachIQ API.

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `routerSidecar.enable` | boolean | `false` | Enable the RouterOS sidecar listener |
| `routerSidecar.host` | string | `"0.0.0.0"` | Sidecar bind host. Use only on controlled LANs |
| `routerSidecar.port` | port | `8100` | Sidecar TCP port |
| `routerSidecar.openFirewall` | boolean | `false` | Open the sidecar port, restricted to `lanInterfaces` |
| `routerSidecar.lanInterfaces` | list of strings | `[ ]` | Firewall interfaces on which to open the sidecar port (e.g. `[ "br-lan" "wlan0" ]`). Required when `routerSidecar.openFirewall` is set, so the port stays LAN-only |

## Freeform `settings`

| Option | Type | Default |
| ------ | ---- | ------- |
| `settings` | attrset of string/int/bool | `{ }` |

`settings` holds non-secret `COACHIQ_*` environment variables passed verbatim to the
service. Keys must be full environment variable names (the module asserts the
`COACHIQ_` prefix) using the current Pydantic field names from
`backend/core/config.py`.

Encoding rules:

- **Booleans and integers** may use native Nix values (`true`, `8000`)
- **Floats** must be quoted strings (`"0.25"`) — the option type intentionally accepts
  only string/int/bool
- **Lists and dicts** should be JSON strings (`builtins.toJSON [...]`) unless the
  specific Pydantic field parser is known to accept comma-separated strings (e.g.
  `COACHIQ_CAN__INTERFACES = "can0,can1"`)

Notes:

- Values in `settings` end up in the world-readable Nix store. **Never put secrets
  here** — the module rejects `COACHIQ_SECURITY__SECRET_KEY`,
  `COACHIQ_AUTH__SECRET_KEY`, and their `_FILE` variants at eval time; supply those
  through `environmentFile` instead.
- The first-class options win over `settings`: `COACHIQ_SERVER__HOST`,
  `COACHIQ_SERVER__PORT`, `COACHIQ_PERSISTENCE__DATA_DIR`, `COACHIQ_LOGGING__LEVEL`,
  `COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL`, `COACHIQ_ROUTER_SIDECAR__ENABLED`,
  `COACHIQ_ROUTER_SIDECAR__HOST`, `COACHIQ_ROUTER_SIDECAR__PORT`, and
  `COACHIQ_ENVIRONMENT` (always `production`) are set from the typed options and
  override any same-named `settings` keys.
- `COACHIQ_STATIC_DIR` defaults to the flake's prebuilt frontend package unless you
  override it in `settings`.

## Example Configurations

### Basic Configuration

```nix
services.coachiq = {
  enable = true;
  settings.COACHIQ_CAN__INTERFACES = "can0,can1";
};
```

### Complete Configuration

```nix
services.coachiq = {
  enable = true;

  # Bind behind a local Caddy reverse proxy that terminates TLS
  host = "127.0.0.1";
  port = 8000;
  tlsTerminationIsExternal = true;
  logLevel = "INFO";

  dataDir = "/var/lib/coachiq";

  # Secrets from sops-nix/agenix: a file with lines like
  #   COACHIQ_SECURITY__SECRET_KEY=...
  #   COACHIQ_AUTH__SECRET_KEY=...
  environmentFile = config.age.secrets.coachiq-env.path;

  # RouterOS sidecar on the RV LAN only
  routerSidecar = {
    enable = true;
    openFirewall = true;
    lanInterfaces = [ "br-lan" ];
  };

  settings = {
    # CAN topology
    COACHIQ_CAN__INTERFACES = "can0,can1";
    COACHIQ_CAN__INTERFACE_MAPPINGS = builtins.toJSON {
      house = "can0";
      chassis = "can1";
    };

    # Coach mapping selection
    COACHIQ_RVC__COACH_MODEL = "2021_Entegra_Aspire_44R";

    # Victron Cerbo GX power system over MQTT
    COACHIQ_VICTRON__ENABLED = true;
    COACHIQ_VICTRON__HOST = "192.168.1.20";

    # GPS trip log (breadcrumbs from gpsd, /location page, GPX export)
    COACHIQ_TRIP_LOG__ENABLED = true;
    COACHIQ_TRIP_LOG__RETENTION_DAYS = 365;

    # RV-C time master: broadcast DATE_TIME_STATUS + GPS DGNs
    COACHIQ_TIME_SYNC__ENABLED = true;
    COACHIQ_TIME_SYNC__SET_COMMAND_INTERVAL_SECONDS = "300.0";  # float: quoted
  };
};
```

## What the Module Sets Up

When enabled, the module:

- Creates the `coachiq` system user/group (with `dialout` supplementary group for CAN
  device access) and the `dataDir` subdirectory layout (`databases/`, `backups/`,
  `config/`, `themes/`, `dashboards/`, `logs/`, `reference/`) via systemd tmpfiles
- Copies bundled reference data (RV-C spec, coach mappings) into
  `<dataDir>/reference` when `dataDir` is the default `/var/lib/coachiq`
- Runs `coachiq-validate-config` before start (fail-fast on invalid configuration),
  starts `coachiq-daemon`, and runs a post-start health check
- Applies systemd hardening (`NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`,
  `ProtectHome`, restricted `ReadWritePaths`)
- Opens firewall ports only as configured by `openFirewall` and
  `routerSidecar.openFirewall`/`routerSidecar.lanInterfaces`

## Advanced Configuration

To use a custom package build:

```nix
services.coachiq = {
  enable = true;
  package = inputs.coachiq.packages.${pkgs.system}.coachiq;
  # ...other settings
};
```
