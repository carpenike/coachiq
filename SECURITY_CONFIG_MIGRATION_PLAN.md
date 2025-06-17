# Security Configuration Hybrid Architecture Migration Plan

## Overview

This document outlines the migration from the current file-based security configuration (`config/security.yml`) to a hybrid architecture that combines file-based defaults with database-stored runtime overrides for better security, auditability, and reliability in this safety-critical RV-C vehicle control system.

## Current State Analysis

### Existing Implementation
- **File**: `config/security.yml` (84 lines of security policies)
- **Service**: `SecurityConfigService` with 5-minute auto-reload
- **Usage**: PIN policies, rate limiting, authentication, audit, network security
- **Integration**: Used by PIN Manager, Network Security Service, Security Audit Service

### Current Risks
- Race conditions during file updates
- No validation before changes take effect
- Poor audit trail for security incidents
- Requires filesystem write access for updates
- Potential for partial file reads during updates

## Target Architecture

### Hybrid Model Components

1. **Immutable Base Configuration** (`config/security.yml`)
   - Read-only defaults shipped with application
   - Provides secure bootstrap configuration
   - Validated via checksum on startup
   - Never modified at runtime

2. **Runtime Override Storage** (SQLite `security_overrides` table)
   - Dynamic policy adjustments for incident response
   - Transactional updates with audit trail
   - Validated through API endpoints
   - Falls back to defaults if unavailable

3. **Enhanced SecurityConfigService**
   - Loads base config on startup
   - Merges database overrides
   - 5-minute reload only queries database
   - Maintains backward compatibility

## Implementation Plan

### Phase 1: Database Schema and Models

#### 1.1 Create Security Overrides Table
- **File**: New Alembic migration
- **Schema**:
  ```sql
  CREATE TABLE security_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'string',
    created_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    expires_at TIMESTAMP NULL
  );
  ```

#### 1.2 Create Pydantic Models
- **File**: `backend/models/security_overrides.py`
- **Models**: `SecurityOverride`, `SecurityOverrideCreate`, `SecurityOverrideUpdate`

#### 1.3 Database Service
- **File**: `backend/services/security_override_service.py`
- **Methods**: CRUD operations with validation and audit logging

**Estimated Effort**: 1-2 days

### Phase 2: Enhanced SecurityConfigService

#### 2.1 Refactor Configuration Loading
- **File**: `backend/services/security_config_service.py`
- **Changes**:
  - Add checksum validation for base file
  - Implement override merging logic
  - Separate base reload from override reload
  - Add error handling for database unavailability

#### 2.2 Configuration Merge Logic
- **Helper Functions**:
  - `set_nested_value(config, key, value)` - Apply dot-notation overrides
  - `validate_override_key(key)` - Ensure valid configuration paths
  - `type_convert_value(value, type)` - Handle type conversions

#### 2.3 Maintain Backward Compatibility
- Existing API methods continue to work
- No changes to dependent services required

**Estimated Effort**: 2-3 days

### Phase 3: Security Override API

#### 3.1 Create API Router
- **File**: `backend/api/routers/security_overrides.py`
- **Endpoints**:
  - `GET /api/security/overrides` - List active overrides
  - `POST /api/security/overrides` - Create/update override
  - `DELETE /api/security/overrides/{key}` - Remove override
  - `POST /api/security/overrides/validate` - Validate before applying

#### 3.2 Authentication and Authorization
- Require admin-level authentication
- Log all override operations for audit
- Rate limiting for security operations

#### 3.3 Input Validation
- Validate override keys against allowed paths
- Type checking for values
- Security policy validation (e.g., PIN length minimums)

**Estimated Effort**: 2-3 days

### Phase 4: Frontend Integration

#### 4.1 Security Override Management UI
- **File**: `frontend/src/pages/security-overrides.tsx`
- **Features**:
  - View current overrides vs defaults
  - Apply temporary policy changes
  - Audit trail display
  - Override expiration management

#### 4.2 API Client
- **File**: `frontend/src/api/security-overrides.ts`
- **Methods**: CRUD operations for security overrides

#### 4.3 Integration with Existing Security Dashboard
- Add override status to existing security configuration display
- Highlight when policies are overridden

**Estimated Effort**: 3-4 days

### Phase 5: Enhanced Security Features

#### 5.1 Configuration Checksum Validation
- Generate and verify SHA-256 checksum of `config/security.yml`
- Fail-safe behavior if checksum mismatch detected
- Log security events for tamper detection

#### 5.2 Override Expiration and Cleanup
- Automatic expiration of temporary policy changes
- Scheduled cleanup job for expired overrides
- Notification system for expiring policies

#### 5.3 Configuration Audit Trail
- Comprehensive logging of all configuration changes
- Integration with security event system
- Export capabilities for compliance reporting

**Estimated Effort**: 2-3 days

### Phase 6: Testing and Documentation

#### 6.1 Comprehensive Testing
- Unit tests for override merging logic
- Integration tests for API endpoints
- Security tests for validation and authorization
- Performance tests for configuration loading

#### 6.2 Documentation Updates
- API documentation for override endpoints
- Operational procedures for incident response
- Migration guide for existing configurations

#### 6.3 Deployment Testing
- Test upgrade path on staging environment
- Validate fallback behavior
- Performance impact assessment

**Estimated Effort**: 2-3 days

## Migration Strategy

### Deployment Approach
1. **Backward Compatible**: All changes maintain existing API compatibility
2. **Gradual Rollout**: Override system deployed but not initially used
3. **Validation Period**: Monitor system behavior with hybrid architecture
4. **Operator Training**: Document new incident response procedures

### Rollback Plan
- Database migration includes down migration
- SecurityConfigService falls back to file-only mode if database unavailable
- No changes to `config/security.yml` structure during migration

### Risk Mitigation
- Extensive testing in staging environment
- Checksum validation prevents configuration tampering
- Audit logging tracks all configuration changes
- Automatic fallback to secure defaults

## Success Criteria

### Functional Requirements
- [ ] System boots reliably with secure defaults even if database unavailable
- [ ] Runtime policy changes take effect within 5 minutes
- [ ] All configuration changes are audited and logged
- [ ] API validation prevents invalid configurations
- [ ] Override expiration prevents policy drift

### Performance Requirements
- [ ] Configuration loading time < 100ms during normal operation
- [ ] Override reload time < 50ms
- [ ] No impact on system boot time
- [ ] Database queries optimized for frequent access

### Security Requirements
- [ ] Base configuration tamper detection
- [ ] Authenticated and authorized override operations
- [ ] Audit trail for all security policy changes
- [ ] Automatic cleanup of expired overrides
- [ ] Rate limiting on configuration changes

## Timeline

**Total Estimated Duration**: 12-18 days

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Database Schema | 1-2 days | None |
| Phase 2: SecurityConfigService | 2-3 days | Phase 1 |
| Phase 3: API Endpoints | 2-3 days | Phase 1, 2 |
| Phase 4: Frontend Integration | 3-4 days | Phase 3 |
| Phase 5: Enhanced Security | 2-3 days | Phase 2, 3 |
| Phase 6: Testing & Documentation | 2-3 days | All phases |

## Configuration Examples

### Base Configuration (config/security.yml)
```yaml
# Immutable defaults - never modified at runtime
pin_policy:
  min_length: 6
  session_timeout_minutes: 30
  max_failed_attempts: 3

rate_limiting:
  max_requests_per_minute: 100
  burst_limit: 10
```

### Runtime Overrides (security_overrides table)
```sql
-- Temporary policy for security incident
INSERT INTO security_overrides
VALUES (1, 'rate_limiting.max_requests_per_minute', '50', 'int', 'admin', NOW(), 'admin', NOW(), 'Security incident - rate limiting', NOW() + INTERVAL '2 hours');

-- Enhanced PIN policy during maintenance
INSERT INTO security_overrides
VALUES (2, 'pin_policy.session_timeout_minutes', '15', 'int', 'admin', NOW(), 'admin', NOW(), 'Maintenance window - shorter sessions', NULL);
```

### Merged Runtime Configuration
```python
# Result of base config + overrides
{
    "pin_policy": {
        "min_length": 6,  # from base
        "session_timeout_minutes": 15,  # overridden
        "max_failed_attempts": 3  # from base
    },
    "rate_limiting": {
        "max_requests_per_minute": 50,  # overridden
        "burst_limit": 10  # from base
    }
}
```

## Next Steps

1. **Review and Approval**: Technical review of this plan with team
2. **Environment Setup**: Prepare staging environment for testing
3. **Phase 1 Implementation**: Begin with database schema and models
4. **Incremental Development**: Implement phases sequentially with testing
5. **Documentation**: Maintain operational procedures throughout development

## Notes

- This migration maintains full backward compatibility
- The hybrid approach provides both reliability and flexibility
- Implementation can be paused/resumed at any phase boundary
- All security-critical validations remain in place throughout migration
