# Configuration File Loading Architecture

This document describes how configuration files are loaded, stored, and managed in the CoachIQ system. The configuration system supports multiple deployment scenarios through a flexible search path mechanism with environment variable overrides.

## Overview

CoachIQ uses a multi-layered configuration system that supports:
- Development environments with local configuration files
- Production deployments with read-only system configurations
- Packaged distributions using bundled resources
- User customizations and overrides
- Environment-specific settings

## Core Configuration Files

### 1. RV-C Protocol Specification (`rvc.json`)

The RV-C protocol specification file contains PGN (Parameter Group Number) definitions, signal mappings, and data types for the RV-C network protocol.

**Loading Mechanism:**
```python
# backend/core/config.py - RVCSettings.get_spec_path()
```

**Search Order:**
1. Environment variable override: `COACHIQ_RVC__SPEC_PATH`
2. Current working directory: `./config/rvc.json`
3. Bundled resources via `importlib.resources`
4. Production location: `/var/lib/coachiq/reference/rvc.json`

**Usage:**
- Loaded by RV-C decoder service
- Provides protocol definitions for message parsing
- Contains PGN-to-signal mappings

### 2. Coach Mapping Files (`*.yml`)

Coach mapping files define device-specific configurations, custom PGN mappings, and coach model-specific settings.

**Loading Mechanism:**
```python
# backend/core/config.py - RVCSettings.get_coach_mapping_path()
```

**Search Order:**
1. Environment variable override: `COACHIQ_RVC__COACH_MAPPING_PATH`
2. Model-specific file based on `COACHIQ_RVC__COACH_MODEL`:
   - Example: `COACHIQ_RVC__COACH_MODEL=2021_Entegra_Aspire_44R`
   - Loads: `config/2021_entegra_aspire_44r.yml`
3. Bundled default mapping
4. Current working directory: `./config/coach_mapping.default.yml`
5. Production location: `/var/lib/coachiq/reference/coach_mapping.default.yml`

**Model Selection:**
- Filename normalization: spaces → underscores, lowercase
- Falls back to default if specific model not found
- Supports both `.yml` and `.yaml` extensions

## Directory Structure

### Development Structure
```
project_root/
├── config/                          # Development configuration files
│   ├── rvc.json                    # RV-C protocol specification
│   ├── coach_mapping.default.yml   # Default coach mapping
│   ├── 2021_entegra_aspire_44r.yml # Model-specific mappings
│   └── models/                     # Additional model configs
└── backend/
    └── config/                     # Bundled resources (for packaging)
```

### Production Structure (`/var/lib/coachiq`)
```
/var/lib/coachiq/
├── reference/                      # Read-only reference data (444 permissions)
│   ├── rvc.json                   # System RV-C specification
│   ├── coach_mapping.default.yml  # System default mapping
│   └── models/                    # System model mappings
├── database/                      # SQLite databases
│   └── coachiq.db                # Main application database
├── backups/                       # Database backups
├── config/                        # User configuration files
├── themes/                        # Custom UI themes
├── dashboards/                    # Custom dashboard configs
├── logs/                          # Persistent application logs
└── user/                          # User-specific data
    ├── user_patches.json          # User customizations
    ├── config-overrides.toml      # User config overrides
    └── coachiq.db                 # User preferences database
```

## Configuration Loading Classes

### 1. RVCSettings (Primary Configuration)

Located in `backend/core/config.py`, this class manages RV-C related configuration paths.

**Key Methods:**
- `get_config_dir()`: Determines configuration directory
- `get_spec_path()`: Returns path to RV-C specification
- `get_coach_mapping_path()`: Returns path to coach mapping
- `_get_bundled_config_dir()`: Locates bundled resources
- `_get_bundled_file()`: Finds specific bundled file

**Environment Variables:**
- `COACHIQ_RVC__CONFIG_DIR`: Override config directory
- `COACHIQ_RVC__SPEC_PATH`: Override RV-C spec path
- `COACHIQ_RVC__COACH_MAPPING_PATH`: Override mapping path
- `COACHIQ_RVC__COACH_MODEL`: Select specific coach model

### 2. ConfigurationLoader (Hierarchical System)

Located in `backend/core/config_loader.py`, implements an 8-layer configuration hierarchy for the persistence migration.

**Configuration Layers (in precedence order):**
1. **Core Protocol Specification** (JSON) - RV-C protocol definitions
2. **Coach Model Base Definition** (YAML) - Coach-specific mappings
3. **User Structural Customizations** (JSON Patch) - User modifications
4. **System Settings** (TOML) - System deployment configuration
5. **User Config Overrides** (TOML) - User configuration overrides
6. **User Model Selection & System State** (SQLite) - Mutable system state
7. **User Preferences** (SQLite) - User cosmetic preferences
8. **Secrets & Runtime Overrides** (Environment Variables) - Runtime config

**Key Features:**
- Deep merge functionality for hierarchical overrides
- JSON Patch support for user customizations
- Permission validation (444 for system files)
- Schema version validation
- Error recovery with configuration issue flagging

### 3. PersistenceService

Located in `backend/services/persistence_service.py`, manages persistent storage directories.

**Managed Directories:**
- Database storage: `/var/lib/coachiq/database`
- Backup storage: `/var/lib/coachiq/backups`
- User configs: `/var/lib/coachiq/config`
- Custom themes: `/var/lib/coachiq/themes`
- Dashboards: `/var/lib/coachiq/dashboards`
- Persistent logs: `/var/lib/coachiq/logs`

**Configuration:**
- Base directory: `COACHIQ_PERSISTENCE__DATA_DIR` (default: `/var/lib/coachiq`)
- Auto-creation: `COACHIQ_PERSISTENCE__CREATE_DIRS` (default: true)
- Backup settings: retention, size limits

## Bundled Resource Handling

For packaged deployments (e.g., Nix, Docker), CoachIQ uses Python's `importlib.resources` to access bundled configuration files.

**Search Strategy:**
```python
# Try multiple paths relative to backend package
candidates = [
    backend_path.parent / "config" / filename,  # ../config/
    backend_path / "config" / filename,         # backend/config/
]

# Also try direct package resource access
config_resource = resources.files("config")
```

**Benefits:**
- Works in packaged environments
- No filesystem dependencies
- Supports read-only deployments
- Compatible with Nix builds

## Environment Variable Patterns

All configuration paths can be overridden using environment variables following the pattern:
`COACHIQ_{SECTION}__{SETTING}`

**Examples:**
```bash
# Override RV-C specification path
COACHIQ_RVC__SPEC_PATH=/custom/path/rvc.json

# Select specific coach model
COACHIQ_RVC__COACH_MODEL=2021_Entegra_Aspire_44R

# Override persistence base directory
COACHIQ_PERSISTENCE__DATA_DIR=/data/coachiq

# Override hierarchical config paths (ConfigurationLoader)
COACHIQ_CONFIG_SYSTEM_ROOT=/etc/coachiq
COACHIQ_CONFIG_USER_ROOT=/home/user/.coachiq
COACHIQ_CONFIG_DB_PATH=/var/lib/coachiq/user.db
```

## Security Considerations

### File Permissions
- System configuration files: 444 (read-only)
- User configuration files: 644 (read-write by owner)
- Directories: 755 (executable for traversal)

### Validation
- Permission checks on startup with warnings
- Schema version validation for compatibility
- JSON/YAML syntax validation with error recovery
- Path traversal protection

## Usage Examples

### 1. Loading RV-C Configuration
```python
from backend.core.config import get_rvc_settings
from backend.integrations.rvc.config_loader import load_rvc_spec, load_device_mapping

# Get configuration paths
rvc_settings = get_rvc_settings()
spec_path = rvc_settings.get_spec_path()
mapping_path = rvc_settings.get_coach_mapping_path()

# Load configuration files
rvc_spec = load_rvc_spec(str(spec_path))
device_mapping = load_device_mapping(str(mapping_path))
```

### 2. Using Hierarchical Configuration
```python
from backend.core.config_loader import create_configuration_loader

# Create loader with custom paths
loader = create_configuration_loader(
    system_root=Path("/etc/coachiq"),
    user_root=Path("/home/user/.coachiq")
)

# Load merged configuration
config = loader.load()
```

### 3. Accessing Persistence Directories
```python
from backend.services.persistence_service import PersistenceService

persistence = PersistenceService()
await persistence.initialize()

# Get database path
db_path = await persistence.get_database_path("coachiq")

# Save user configuration
await persistence.save_user_config("preferences", {"theme": "dark"})
```

## Best Practices

1. **Development**:
   - Keep configuration files in `config/` directory
   - Use `.env` files for environment variables
   - Test with different coach models

2. **Production**:
   - Deploy system configs to `/var/lib/coachiq/reference/` with 444 permissions
   - Use environment variables for deployment-specific settings
   - Enable persistence for state management

3. **Testing**:
   - Mock configuration paths in tests
   - Test with missing configuration files
   - Verify permission handling

4. **Packaging**:
   - Include configuration files as package resources
   - Use bundled resource loading
   - Test in read-only environments

## Troubleshooting

### Configuration Not Found
1. Check environment variables for overrides
2. Verify file exists in search paths
3. Check file permissions (readable)
4. Review logs for search path details

### Permission Errors
1. System files should be 444 (read-only)
2. User files should be 644 (read-write by owner)
3. Directories need execute permission (755)
4. Check parent directory permissions

### Model-Specific Loading Issues
1. Verify model name format (underscores, lowercase)
2. Check file extension (.yml or .yaml)
3. Confirm file exists in config directory
4. Review fallback to default mapping

### Bundled Resource Issues
1. Verify package structure includes config files
2. Check importlib.resources compatibility
3. Test resource access in packaged environment
4. Review bundled path search order
