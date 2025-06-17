# Configuration File Loading Summary

## Quick Reference

### RVC Protocol Specification (`rvc.json`)
**Search Order:**
1. `$COACHIQ_RVC__SPEC_PATH` (environment variable)
2. `./config/rvc.json` (development)
3. Bundled resources via Python package
4. `/var/lib/coachiq/reference/rvc.json` (production)

### Coach Mapping Files (`*.yml`)
**Search Order:**
1. `$COACHIQ_RVC__COACH_MAPPING_PATH` (environment variable)
2. Model-specific: `./config/{coach_model}.yml` (if `$COACHIQ_RVC__COACH_MODEL` is set)
3. Bundled resources for default mapping
4. `./config/coach_mapping.default.yml` (development)
5. `/var/lib/coachiq/reference/coach_mapping.default.yml` (production)

### Persistence Directories
**Base Directory:** `/var/lib/coachiq` (or `$COACHIQ_PERSISTENCE__DATA_DIR`)

**Subdirectories:**
- `/database` - SQLite databases
- `/backups` - Database backups
- `/config` - User configuration files
- `/themes` - Custom UI themes
- `/dashboards` - Custom dashboards
- `/logs` - Persistent logs
- `/reference` - Read-only system configs (production)

## Key Environment Variables

```bash
# RVC Configuration
COACHIQ_RVC__SPEC_PATH=/path/to/rvc.json
COACHIQ_RVC__COACH_MAPPING_PATH=/path/to/mapping.yml
COACHIQ_RVC__COACH_MODEL=2021_Entegra_Aspire_44R
COACHIQ_RVC__CONFIG_DIR=/path/to/config

# Persistence
COACHIQ_PERSISTENCE__DATA_DIR=/var/lib/coachiq
COACHIQ_PERSISTENCE__CREATE_DIRS=true

# Hierarchical Config Loader
COACHIQ_CONFIG_SYSTEM_ROOT=/var/lib/coachiq
COACHIQ_CONFIG_USER_ROOT=/var/lib/coachiq/user
COACHIQ_CONFIG_DB_PATH=/var/lib/coachiq/user/coachiq.db
```

## Configuration Loading Classes

1. **`RVCSettings`** (`backend/core/config.py`)
   - Manages RV-C protocol and coach mapping paths
   - Implements bundled resource fallback
   - Provides search path logic

2. **`ConfigurationLoader`** (`backend/core/config_loader.py`)
   - Implements 8-layer hierarchical configuration
   - Handles JSON patches for user customizations
   - Validates permissions and schema versions

3. **`PersistenceService`** (`backend/services/persistence_service.py`)
   - Creates and manages data directories
   - Handles database backups
   - Manages user configuration storage

## File Permissions

- **System configs**: 444 (read-only)
- **User configs**: 644 (read-write by owner)
- **Directories**: 755 (read and traverse)

## Bundled Resource Support

For packaged deployments (Nix, Docker), configuration files are loaded via `importlib.resources`:
- Searches relative to backend package
- No filesystem dependencies
- Works in read-only environments

## Coach Model Selection

Model names are normalized:
- Spaces → underscores
- Uppercase → lowercase
- Extension removed

Example: `"2021 Entegra Aspire 44R"` → `"2021_entegra_aspire_44r.yml"`
