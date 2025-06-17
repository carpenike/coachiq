# Persistence Architecture Modernization Plan

## Overview

This document outlines the plan to modernize our persistence architecture by transforming coach configuration files from runtime filesystem dependencies into bundled seed data imported to SQLite, while keeping rvc.json as a bundled runtime resource.

## Goals

1. **Eliminate filesystem dependencies** for reference data in production
2. **Simplify configuration management** by removing separate override layers
3. **Improve security** by reducing filesystem access requirements
4. **Enable safe runtime modifications** through database-backed storage
5. **Maintain development flexibility** while improving production robustness

## Current State

- Coach mapping YAML files stored in `/config/` directory
- Configuration loader checks multiple paths with fallback
- Separate override system adds complexity
- Files are read from filesystem on each startup
- No safe mechanism for user modifications

## Target State

- All reference data bundled with application
- Coach configurations imported to SQLite on first use
- Database as single source of truth at runtime
- Web UI for configuration management
- No production filesystem dependencies

## Implementation Phases

### Phase 1: Bundle All Reference Data ✅ Status: Not Started

**Goal**: Move all reference files into application bundle

#### Tasks:
- [ ] Update build process to include all coach YAML files as bundled resources
- [ ] Ensure `rvc.json` is included as bundled resource
- [ ] Update `ConfigurationLoader` to prioritize `importlib.resources`
- [ ] Add development mode flag for filesystem loading
- [ ] Remove production references to `/var/lib/coachiq/reference/`

#### Code Changes:
```python
# backend/services/configuration_loader.py
class ConfigurationLoader:
    def __init__(self, development_mode: bool = False):
        self.development_mode = development_mode

    def load_resource(self, filename: str) -> dict:
        if self.development_mode:
            # Try filesystem first for development
            return self._load_from_filesystem(filename)
        # Always use bundled resources in production
        return self._load_from_bundle(filename)
```

### Phase 2: Smart Database Import System ✅ Status: Not Started

**Goal**: Implement database import mechanism for coach configurations

#### Tasks:
- [ ] Create database schema for coach mappings
- [ ] Implement import logic in `CoachMappingService`
- [ ] Add version tracking for imported configurations
- [ ] Create audit trail for modifications
- [ ] Implement change detection for updates

#### Database Schema:
```sql
-- Coach configuration storage
CREATE TABLE coach_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coach_model TEXT NOT NULL,
    component_path TEXT NOT NULL,
    mapping_data TEXT NOT NULL,    -- JSON data
    source TEXT NOT NULL,          -- 'factory'|'import'|'user'
    source_version TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_by TEXT,
    UNIQUE(coach_model, component_path, is_active)
);

-- Audit trail
CREATE TABLE coach_mapping_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mapping_id INTEGER NOT NULL,
    previous_data TEXT,
    change_reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT,
    FOREIGN KEY (mapping_id) REFERENCES coach_mappings(id)
);

-- Import tracking
CREATE TABLE coach_import_status (
    coach_model TEXT PRIMARY KEY,
    yaml_hash TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    imported_version TEXT NOT NULL
);
```

#### Import Service:
```python
# backend/services/coach_import_service.py
class CoachImportService:
    async def import_coach_model(self, model_name: str, user_id: Optional[str] = None):
        """Import coach configuration from bundled YAML to database"""
        # Implementation details in code
        pass

    async def check_for_updates(self, model_name: str) -> bool:
        """Check if bundled version differs from imported version"""
        pass

    async def get_update_preview(self, model_name: str) -> dict:
        """Show what would change if update is applied"""
        pass
```

### Phase 3: Enhanced Coach Mapping Service ✅ Status: Not Started

**Goal**: Update service to use database as primary source

#### Tasks:
- [ ] Refactor `CoachMappingService` to query database
- [ ] Implement caching layer for performance
- [ ] Add methods for runtime modifications
- [ ] Remove filesystem loading logic
- [ ] Add migration support for updates

#### Updated Service:
```python
# backend/services/coach_mapping_service.py
class EnhancedCoachMappingService:
    def __init__(self, persistence_service: PersistenceService):
        self._persistence = persistence_service
        self._cache = {}

    async def get_mapping(self, coach_model: str, component_path: str):
        # Check cache first
        # Query database
        # Cache result
        pass

    async def update_mapping(self, coach_model: str, component_path: str,
                           new_data: dict, user_id: str, reason: str):
        # Update database with audit trail
        # Invalidate cache
        # Notify observers
        pass
```

### Phase 4: Web UI for Configuration Management ✅ Status: Not Started

**Goal**: Provide user-friendly interface for coach configuration

#### Tasks:
- [ ] Create coach configuration page in settings
- [ ] List available bundled coach models
- [ ] Show import status and version info
- [ ] Enable viewing/editing current configuration
- [ ] Add import/export functionality
- [ ] Implement update notifications

#### UI Components:
```typescript
// frontend/src/pages/coach-configuration.tsx
- CoachModelSelector
- ImportStatusIndicator
- ConfigurationEditor
- UpdateAvailableNotification
- ExportImportButtons
```

### Phase 5: Migration and Cleanup ✅ Status: Not Started

**Goal**: Migrate existing deployments and remove legacy code

#### Tasks:
- [ ] Create migration script for existing installations
- [ ] Update deployment scripts to remove reference directory
- [ ] Remove legacy override configuration code
- [ ] Update documentation
- [ ] Create rollback procedure

#### Migration Script:
```python
# scripts/migrate_coach_configs.py
async def migrate_existing_installation():
    """One-time migration for existing deployments"""
    # Check for existing YAML files
    # Import to database if not already present
    # Preserve any user modifications
    # Mark migration complete
    pass
```

## Testing Strategy

### Unit Tests:
- [ ] Test bundled resource loading
- [ ] Test database import logic
- [ ] Test version comparison
- [ ] Test update detection
- [ ] Test audit trail

### Integration Tests:
- [ ] Test full import flow
- [ ] Test configuration updates
- [ ] Test cache invalidation
- [ ] Test UI interactions
- [ ] Test migration script

### Performance Tests:
- [ ] Measure import time for large configs
- [ ] Verify caching effectiveness
- [ ] Test concurrent access patterns
- [ ] Validate startup time impact

## Rollback Plan

If issues arise during deployment:

1. **Revert code changes** to previous version
2. **Keep database tables** (no data loss)
3. **Re-enable filesystem loading** temporarily
4. **Export database configs** to YAML if needed
5. **Document issues** for resolution

## Success Metrics

- [ ] Zero filesystem dependencies for reference data in production
- [ ] All coach configs successfully imported to database
- [ ] No increase in startup time (< 100ms impact)
- [ ] User modifications preserved through updates
- [ ] Clean audit trail for all changes

## Timeline Estimate

- **Phase 1**: 1-2 days (bundling setup)
- **Phase 2**: 3-4 days (database import system)
- **Phase 3**: 2-3 days (service refactoring)
- **Phase 4**: 3-4 days (UI implementation)
- **Phase 5**: 1-2 days (migration and cleanup)

**Total**: 10-15 days of development effort

## Open Questions

1. Should we support importing custom coach YAMLs via UI upload?
2. How many versions of history should we retain?
3. Should we implement automatic backups before imports?
4. Do we need a "factory reset" option for configurations?

## Related Documents

- [PERSISTENCE_MIGRATION_PLAN.md](./PERSISTENCE_MIGRATION_PLAN.md) - Overall persistence strategy
- [Configuration Loading Documentation](./docs/architecture/configuration-loading.md) - Current implementation details
- [8-Layer Configuration Hierarchy](./PERSISTENCE_MIGRATION_PLAN.md#configuration-hierarchy) - Configuration precedence rules
