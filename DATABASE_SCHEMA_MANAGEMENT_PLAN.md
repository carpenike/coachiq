# Database Schema Management Implementation Plan

## Overview

This document outlines the implementation plan for a robust database schema management system for the CoachIQ RV-C control system. The plan prioritizes safety, user control, and data integrity while providing appropriate automation for development environments.

## Current State

- Database schema validation occurs at startup
- Mismatches are logged as warnings only
- No automatic migration execution
- Manual migration requires: `poetry run alembic upgrade head`
- System continues operation with outdated schema (risky for new features)

## Design Principles

1. **Safety First**: No automatic migrations in production without explicit consent
2. **Data Integrity**: Always backup before migrations
3. **User Control**: Clear communication and explicit actions required
4. **Graceful Degradation**: System remains operational with outdated schema when safe
5. **Developer Convenience**: Optional automation for development environments

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                   CoreServices                          │
│  ┌─────────────────┐  ┌──────────────────────────┐    │
│  │ DatabaseManager  │  │ DatabaseUpdateService      │    │
│  │                 │  │                            │    │
│  │ - Connections   │  │ - Schema Validation       │    │
│  │ - Queries       │  │ - Migration Execution     │    │
│  │ - Transactions  │  │ - Backup/Restore         │    │
│  └─────────────────┘  │ - Safety Checks          │    │
│                       │ - Progress Reporting      │    │
│                       └──────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### DatabaseUpdateService Responsibilities

1. **Schema Version Management**
   - Check current vs target schema version
   - Determine migration requirements
   - Track migration history

2. **Migration Execution**
   - Pre-migration safety validation
   - Backup creation
   - Migration orchestration
   - Post-migration verification
   - Rollback coordination

3. **System Integration**
   - Coordinate with SafetyService for state validation
   - WebSocket notifications for progress
   - API endpoints for UI integration

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)

#### 1.1 DatabaseUpdateService Creation

```python
# backend/services/database_update_service.py

class DatabaseUpdateService(Feature):
    """
    Manages database schema updates with safety checks and backups.

    This service ensures database migrations are performed safely with
    proper system state validation and rollback capabilities.
    """

    def __init__(self):
        super().__init__(
            name="database_update_service",
            enabled=True,
            core=True
        )
        self._migration_in_progress = False
        self._backup_manager = BackupManager()
        self._migration_coordinator = MigrationCoordinator()
```

#### 1.2 Configuration Updates

```python
# backend/core/config.py additions

class DatabaseSettings(BaseSettings):
    """Database configuration with migration settings."""

    # Existing settings...

    # Migration settings
    auto_migrate: bool = Field(
        default=False,
        description="Enable automatic migrations (DEVELOPMENT ONLY)"
    )

    backup_before_migrate: bool = Field(
        default=True,
        description="Create backup before migrations"
    )

    migration_timeout_seconds: int = Field(
        default=300,
        description="Maximum time for migration execution"
    )

    require_explicit_consent: bool = Field(
        default=True,
        description="Require user confirmation for migrations"
    )

    backup_retention_days: int = Field(
        default=7,
        description="How long to keep migration backups"
    )
```

#### 1.3 Safety Integration

```python
class MigrationSafetyValidator:
    """Validates system state before allowing migrations."""

    async def validate_safe_for_migration(self) -> tuple[bool, list[str]]:
        """
        Check if system is in safe state for migration.

        Returns:
            Tuple of (is_safe, reasons_if_not)
        """
        reasons = []

        # Check active operations
        if await self._has_active_entity_controls():
            reasons.append("Active entity control operations in progress")

        # Check safety interlocks
        if not await self._all_interlocks_satisfied():
            reasons.append("Safety interlocks not satisfied")

        # Check system state
        if not await self._system_in_parked_state():
            reasons.append("System not in parked state")

        # Check WebSocket connections
        if await self._has_active_control_connections():
            reasons.append("Active control connections present")

        return len(reasons) == 0, reasons
```

### Phase 2: API and Core Features (Week 3-4)

#### 2.1 API Endpoints

```python
# backend/api/routers/database_management.py

@router.get("/api/database/status")
async def get_database_status() -> DatabaseStatusResponse:
    """Get current database schema status."""
    return {
        "current_version": current_version,
        "target_version": target_version,
        "needs_update": current_version != target_version,
        "pending_migrations": pending_migrations,
        "last_migration": last_migration_info,
        "backup_available": latest_backup_info
    }

@router.post("/api/database/update")
async def update_database(
    request: DatabaseUpdateRequest,
    background_tasks: BackgroundTasks
) -> DatabaseUpdateResponse:
    """
    Initiate database migration with safety checks.

    Requires explicit confirmation and passes safety validation.
    """
    # Validate safety
    # Create backup
    # Execute migration
    # Return job ID for progress tracking

@router.get("/api/database/update/{job_id}/progress")
async def get_update_progress(job_id: str) -> UpdateProgressResponse:
    """Get real-time migration progress."""

@router.post("/api/database/backup")
async def create_backup() -> BackupResponse:
    """Create manual database backup."""

@router.post("/api/database/restore/{backup_id}")
async def restore_backup(backup_id: str) -> RestoreResponse:
    """Restore database from backup."""
```

#### 2.2 WebSocket Integration

```python
# backend/websocket/database_update_handler.py

class DatabaseUpdateHandler:
    """WebSocket handler for database update notifications."""

    async def notify_update_available(self, version_info: dict):
        """Notify connected clients about available updates."""

    async def send_progress_update(self, progress: MigrationProgress):
        """Send real-time migration progress."""

    async def notify_update_complete(self, result: MigrationResult):
        """Notify clients of migration completion."""
```

### Phase 3: UI Integration (Week 5-6)

#### 3.1 React Components

```typescript
// frontend/src/components/database-update/DatabaseUpdateWidget.tsx

export function DatabaseUpdateWidget() {
    const { status, checkForUpdates } = useDatabaseStatus();
    const { startUpdate, progress } = useDatabaseUpdate();

    // Show update available banner
    // Display progress during migration
    // Show success/failure results
}
```

#### 3.2 Safety UI

```typescript
// frontend/src/components/database-update/UpdateSafetyCheck.tsx

export function UpdateSafetyCheck({ onConfirm }: Props) {
    const safetyStatus = useSystemSafetyStatus();

    // Display safety check results
    // Show blocking conditions
    // Require explicit confirmation
}
```

### Phase 4: Advanced Features (Week 7-8)

#### 4.1 Migration Simulation

```python
class MigrationSimulator:
    """Test migrations without applying changes."""

    async def dry_run(self, target_version: str) -> SimulationResult:
        """
        Simulate migration to identify potential issues.

        - Validates migration scripts
        - Estimates duration
        - Checks disk space requirements
        - Identifies potential conflicts
        """
```

#### 4.2 Automatic Backup Cleanup

```python
class BackupManager:
    """Manages migration backup lifecycle."""

    async def cleanup_old_backups(self):
        """Remove backups older than retention period."""

    async def validate_backup_integrity(self, backup_id: str) -> bool:
        """Verify backup can be restored successfully."""
```

## Error Handling Strategy

### Migration Failure Scenarios

1. **Pre-Migration Failure**
   - Safety check fails → Abort, no changes
   - Backup fails → Abort, notify user
   - Disk space insufficient → Abort, request cleanup

2. **During Migration Failure**
   - Schema change fails → Automatic rollback
   - Data migration fails → Restore from backup
   - Timeout exceeded → Kill migration, restore backup

3. **Post-Migration Failure**
   - Verification fails → Restore from backup
   - Application startup fails → Provide recovery mode

### Recovery Procedures

```python
class MigrationRecovery:
    """Handles migration failure recovery."""

    async def recover_from_failure(self, failure_context: FailureContext):
        """
        Coordinate recovery from migration failure.

        1. Stop all services
        2. Restore from backup
        3. Verify restoration
        4. Restart services in safe mode
        5. Notify user with instructions
        """
```

## Testing Strategy

### Unit Tests
- Migration safety validator
- Backup/restore operations
- Version comparison logic
- Progress tracking

### Integration Tests
- Full migration flow
- Failure recovery
- Concurrent access handling
- WebSocket notifications

### System Tests
- Performance on Raspberry Pi
- Large database handling
- Power failure simulation
- Network interruption handling

## Deployment Considerations

### Environment-Specific Behavior

```python
# Production (default)
AUTO_MIGRATE = False
REQUIRE_EXPLICIT_CONSENT = True
BACKUP_BEFORE_MIGRATE = True

# Development
AUTO_MIGRATE = True  # Optional
REQUIRE_EXPLICIT_CONSENT = False
BACKUP_BEFORE_MIGRATE = True  # Still recommended

# Testing
AUTO_MIGRATE = True
REQUIRE_EXPLICIT_CONSENT = False
BACKUP_BEFORE_MIGRATE = False  # Speed up tests
```

### Resource Requirements

- **Disk Space**: 2x database size for backup
- **Memory**: ~50MB additional during migration
- **CPU**: Minimal impact (I/O bound)
- **Time**: 1-30 seconds typical migration

## Success Criteria

1. **Safety**: Zero data loss incidents
2. **Reliability**: 99.9% successful migrations
3. **Performance**: < 30 second migration time
4. **Usability**: Clear user communication
5. **Recovery**: 100% recoverable failures

## Timeline

- **Weeks 1-2**: Core infrastructure
- **Weeks 3-4**: API and integration
- **Weeks 5-6**: UI implementation
- **Weeks 7-8**: Advanced features
- **Week 9**: Testing and refinement
- **Week 10**: Documentation and deployment

## Future Enhancements

1. **Remote Update Management**
   - Push notifications for updates
   - Scheduled maintenance windows
   - Fleet-wide update coordination

2. **Advanced Backup Features**
   - Incremental backups
   - Cloud backup integration
   - Point-in-time recovery

3. **Schema Version Compatibility**
   - Support multiple schema versions
   - Gradual migration strategies
   - Zero-downtime updates

## Open Questions

1. Should we support downgrades or only forward migrations?
2. How do we handle migrations that require user data input?
3. Should backup location be configurable (USB, network)?
4. Do we need migration approval from multiple users?
5. How do we coordinate updates across multiple devices?

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLite Backup API](https://www.sqlite.org/backup.html)
- [Zero-Downtime Migrations](https://stripe.com/blog/online-migrations)
- [Safety-Critical Software Standards](https://www.iso.org/standard/68383.html)
