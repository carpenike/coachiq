# Minimal NixOS Configuration Examples

This document shows exactly what happens with different minimal configurations.

## Example 1: Absolute Bare Minimum

### Nix Configuration
```nix
# /etc/nixos/configuration.nix
{
  coachiq.enable = true;
}
```

### Environment Variables Set
```bash
COACHIQ_ENVIRONMENT=production
```

### What Happens
- Service starts on `0.0.0.0:8000` (backend default)
- No persistence (backend default: disabled)
- Virtual CAN interface `virtual0` (backend default)
- Basic features enabled as per `feature_flags.yaml`
- Logging at INFO level
- No authentication required

### systemd Service Created
```ini
[Unit]
Description=CoachIQ RV-C HTTP/WebSocket API
After=network.target

[Service]
Type=simple
User=coachiq
Group=coachiq
SupplementaryGroups=dialout
Environment="COACHIQ_ENVIRONMENT=production"
ExecStart=/nix/store/.../bin/coachiq-daemon
Restart=always
RestartSec=5
```

## Example 2: Basic Production Setup

### Nix Configuration
```nix
{
  coachiq = {
    enable = true;
    settings = {
      server.host = "127.0.0.1";  # Localhost only
      persistence.enabled = true;   # Enable database
      canbus.channels = [ "can0" ]; # Real CAN interface
    };
  };
}
```

### Environment Variables Set
```bash
COACHIQ_ENVIRONMENT=production
COACHIQ_SERVER__HOST=127.0.0.1
COACHIQ_PERSISTENCE__ENABLED=true
COACHIQ_CAN__INTERFACES=can0
```

### What Changes
- Binds to localhost only (security improvement)
- SQLite database at `/var/lib/coachiq/database/coachiq.db`
- Uses real CAN interface `can0`
- Everything else uses backend defaults

## Example 3: Investigating Defaults

### Check Backend Defaults Without Any Environment
```bash
# Start a Python shell in the project
cd /path/to/coachiq
poetry shell

# Check all defaults
python -c "
from backend.core.config import get_settings
import json
settings = get_settings()
print(json.dumps(settings.model_dump(), indent=2))
"
```

### Sample Output (Key Defaults)
```json
{
  "environment": "development",
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "workers": 1,
    "reload": false,
    "debug": false
  },
  "logging": {
    "level": "INFO",
    "log_file": null
  },
  "persistence": {
    "enabled": false,
    "data_dir": "/var/lib/coachiq"
  },
  "canbus": {
    "bustype": "virtual",
    "channels": ["virtual0"]
  },
  "features": {
    "enable_vector_search": true,
    "enable_api_docs": true,
    "enable_metrics": true,
    "enable_maintenance_tracking": false,
    "enable_notifications": false
  }
}
```

## Key Insights

### 1. Backend Defaults Rule
The backend (`backend/core/config.py`) is the single source of truth:
- Server defaults to `0.0.0.0:8000`
- Most features start disabled
- Virtual CAN for safety
- No persistence by default

### 2. NixOS Module Philosophy
- Only set environment variables when needed
- Null options mean "use backend default"
- Minimize configuration surface area
- Type-safe at build time

### 3. Common Patterns

**Development Setup:**
```nix
coachiq = {
  enable = true;
  settings = {
    server.debug = true;
    logging.level = "DEBUG";
  };
};
# Sets: COACHIQ_SERVER__DEBUG=true, COACHIQ_LOGGING__LEVEL=DEBUG
```

**Secure Production:**
```nix
coachiq = {
  enable = true;
  settings = {
    server.host = "127.0.0.1";
    security.secretKeyFile = "/run/secrets/jwt";
    persistence.enabled = true;
  };
};
# Sets: COACHIQ_SERVER__HOST=127.0.0.1, COACHIQ_SECURITY__SECRET_KEY_FILE=/run/secrets/jwt, COACHIQ_PERSISTENCE__ENABLED=true
```

## Debugging Tips

### See Exact Environment
```bash
# What NixOS will set
nixos-option coachiq.settings

# What's actually set in systemd
systemctl show coachiq -p Environment

# Compare with backend defaults
curl http://localhost:8000/api/admin/config
```

### Test Different Configs
```bash
# Test with no environment
env -i poetry run python -c "from backend.core.config import get_settings; print(get_settings().server.host)"
# Output: 0.0.0.0

# Test with override
COACHIQ_SERVER__HOST=192.168.1.1 poetry run python -c "from backend.core.config import get_settings; print(get_settings().server.host)"
# Output: 192.168.1.1
```

## Summary

The bare minimum `coachiq.enable = true;` gives you:
- A running service with systemd management
- Backend defaults for everything
- Only `COACHIQ_ENVIRONMENT=production` set
- Suitable for testing or development
- Add settings only as needed for your use case
