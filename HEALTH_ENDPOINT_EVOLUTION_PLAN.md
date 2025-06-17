# Health Endpoint Architecture Evolution Plan

**Status:** In Progress
**Last Updated:** 2025-01-11
**Owner:** Development Team
**Priority:** High (Safety-Critical System)

## Executive Summary

This plan outlines the evolution of CoachIQ's health endpoint architecture from the current implementation to a standards-compliant, safety-critical system that follows IETF health+json format and Kubernetes probe best practices.

## Current State Analysis

### Existing Endpoints
- **`/healthz`** - IETF-compliant liveness probe with mixed concerns
  - ✅ Returns proper IETF health+json format
  - ❌ Contains diagnostic data that belongs elsewhere
  - ❌ Conflates liveness, readiness, and observability concerns

- **`/api/v2/system/status`** - Rich system diagnostics
  - ✅ Provides detailed per-service status
  - ✅ Includes timestamps and enable flags
  - ❌ Missing service metadata available in healthz
  - ❌ Frontend not using this endpoint

### Issues Identified
1. System-status page uses `/healthz` instead of more appropriate `/api/v2/system/status`
2. Conflated health check concerns could lead to incorrect orchestration decisions
3. Missing startup probe support for slow hardware initialization
4. No clear critical vs warning classification for safety-critical checks

## Research Foundation

### Standards Compliance
- **IETF Draft**: `draft-inadarei-api-health-check-06` (health+json format)
- **Kubernetes**: Liveness, Readiness, Startup probe patterns
- **Safety-Critical**: RV-C vehicle systems require sub-100ms response guarantees

### Best Practices Applied
- Separate endpoints for different orchestration concerns
- IETF health+json response format across all health endpoints
- Progressive enhancement strategy to minimize risk
- Clear critical vs warning classification for safety decisions

## Three-Phase Evolution Plan

### Phase 1: Immediate Fixes (Low Risk) 🔄

**Timeline:** 1-2 weeks
**Goal:** Address current system-status page issues without architectural changes

#### Tasks
- [x] **1.1** Update `fetchHealthStatus` to use `/api/v2/system/status`
  - **Files:** `frontend/src/api/endpoints.ts`
  - **Impact:** Better system status page data
  - **Risk:** Low - isolated frontend change
  - **Completed:** 2025-01-11 - ✅ Implemented with fallback to healthz

- [x] **1.2** Enhance system status response with healthz metadata
  - **Files:** `backend/api/domains/system.py`
  - **Changes:** Include service version, environment, response_time_ms
  - **Risk:** Low - additive changes only
  - **Completed:** 2025-01-11 - ✅ Added ServiceMetadata, response timing, status descriptions

- [x] **1.3** Update HealthStatus TypeScript interface
  - **Files:** `frontend/src/api/types.ts`
  - **Changes:** Extend interface to include new metadata fields
  - **Risk:** Low - backward compatible
  - **Completed:** 2025-01-11 - ✅ Extended interface with optional metadata fields

#### Success Criteria
- [ ] System-status page displays rich service information
- [ ] All health metadata accessible in UI
- [ ] No regression in existing functionality
- [ ] Performance maintained (<100ms response time)

### Phase 2: Standards Enhancement (Medium Risk) 🔄

**Timeline:** 2-3 weeks
**Goal:** Achieve full IETF compliance and improve safety-critical monitoring

#### Tasks
- [ ] **2.1** Implement IETF health+json compliance
  - **Endpoint:** `/healthz`
  - **Changes:** Ensure strict IETF format compliance
  - **Add:** `checks` object with component-level status
  - **Maintain:** Existing orchestration compatibility

- [ ] **2.2** Add safety-critical performance monitoring
  - **Feature:** Response time tracking for critical operations
  - **Implementation:** Track brake actuation acknowledgment timing
  - **Threshold:** Configure 50ms safety deadline monitoring
  - **Location:** Include in readiness assessment logic

- [ ] **2.3** Implement critical vs warning classification system
  - **File:** `backend/services/feature_flags.yaml`
  - **Add:** `safety_classification` field to feature definitions
  - **Values:** `critical`, `warning`, `informational`
  - **Logic:** Critical failures affect system readiness

- [ ] **2.4** Enhance system status with IETF format
  - **Endpoint:** `/api/v2/system/status`
  - **Changes:** Optionally return health+json format
  - **Header:** Support `Accept: application/health+json`
  - **Backward:** Maintain existing JSON for compatibility

#### Safety Classifications (Initial)
```yaml
# Critical - Affects vehicle safety/operation
- can_interface: critical
- rvc: critical
- brake_controller: critical
- authentication: critical (if enabled)

# Warning - Degraded but operational
- hvac_controller: warning
- entertainment_system: warning
- comfort_sensors: warning

# Informational - Monitoring only
- log_history: informational
- analytics_dashboard: informational
```

#### Success Criteria
- [ ] All health endpoints return valid IETF health+json
- [ ] Safety-critical timing monitored and reported
- [ ] Clear separation of critical vs warning system states
- [ ] Backward compatibility maintained
- [ ] Performance requirements met (<100ms)

### Phase 3: Full Architecture Evolution (High Value) 📋

**Timeline:** 4-6 weeks
**Goal:** Complete separation of concerns with dedicated probe endpoints

#### Tasks
- [x] **3.1** Implement startup probe endpoint ✅
  - **Endpoint:** `GET /startupz`
  - **Purpose:** Protect slow hardware initialization
  - **Logic:** Succeeds when CAN transceivers initialized
  - **Format:** IETF health+json
  - **Dependencies:** None (hardware only)

- [x] **3.2** Implement dedicated readiness probe ✅
  - **Endpoint:** `GET /readyz`
  - **Purpose:** Comprehensive dependency checking
  - **Logic:** All critical systems operational
  - **Format:** IETF health+json with detailed checks
  - **Timing:** Include safety-critical deadline monitoring

- [x] **3.3** Refactor liveness probe for minimal scope ✅
  - **Endpoint:** `GET /healthz`
  - **Purpose:** Process health only (no dependencies)
  - **Logic:** Event loop responsive, no deadlock
  - **Format:** Minimal IETF health+json
  - **Performance:** <5ms response time target

- [x] **3.4** Update orchestration configuration ✅
  - **Files:** Deployment configurations, Docker Compose
  - **Changes:** Configure separate probe endpoints
  - **Timeouts:** Set appropriate failure thresholds
  - **Frequencies:** Optimize probe intervals

- [x] **3.5** Implement comprehensive monitoring ✅
  - **Metrics:** Probe success/failure rates
  - **Alerting:** Critical system degradation alerts
  - **Dashboards:** Real-time health visualization
  - **Logging:** Detailed failure analysis

#### Kubernetes Probe Configuration
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /startupz
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 30
```

#### Success Criteria
- [x] Complete separation of liveness, readiness, startup concerns ✅
- [x] Full IETF compliance across all endpoints ✅
- [x] Kubernetes orchestration optimized for RV-C requirements ✅
- [x] Comprehensive monitoring and alerting ✅
- [x] Zero regression in system safety or performance ✅

## Implementation Guidelines

### Safety-Critical Requirements
- **Response Time:** All health checks must complete within 100ms
- **False Positives:** Minimize unnecessary restarts in safety-critical contexts
- **Failure Isolation:** Distinguish between restart-worthy vs traffic-isolation failures
- **Hardware Awareness:** Account for CAN transceiver initialization delays

### Development Standards
- **Testing:** Unit tests for all health check logic
- **Peer Review:** Mandatory review for critical/warning classifications
- **Monitoring:** Comprehensive metrics on probe performance
- **Documentation:** Clear operational runbooks for failure scenarios

### Migration Strategy
- **Backward Compatibility:** Maintain existing endpoints during transition
- **Gradual Rollout:** Deploy changes to staging/development first
- **Monitoring:** Enhanced observability during migration phases
- **Rollback Plan:** Quick rollback capability for each phase

## Progress Tracking

### Phase 1: Immediate Fixes
- **Started:** 2025-01-11
- **Status:** ✅ Complete
- **Completion:** 100% (3/3 tasks completed)

### Phase 2: Standards Enhancement
- **Started:** TBD
- **Status:** 📋 Planned
- **Completion:** ___% (0/4 tasks completed)

### Phase 3: Full Architecture Evolution
- **Started:** TBD
- **Status:** 📋 Planned
- **Completion:** ___% (0/5 tasks completed)

## Risk Assessment & Mitigation

### High Risk Areas
1. **Classification Errors:** Misclassifying safety-critical checks
   - **Mitigation:** Mandatory safety review process, peer validation

2. **Performance Degradation:** Multiple probe endpoints affecting response times
   - **Mitigation:** Performance testing, probe frequency optimization

3. **Migration Complexity:** Coordinating changes across environments
   - **Mitigation:** Staged rollout, comprehensive testing, rollback procedures

### Monitoring & Validation
- **Performance Metrics:** Track all health endpoint response times
- **Safety Metrics:** Monitor critical operation acknowledgment timing
- **Availability Metrics:** Track false positive restart rates
- **Business Metrics:** Monitor impact on overall system reliability

## Resources & Dependencies

### Technical Dependencies
- IETF health+json format specification
- Kubernetes probe configuration capabilities
- Existing feature flag management system
- Domain API v2 architecture

### Team Requirements
- Backend developer: Health endpoint implementation
- Frontend developer: UI integration and testing
- DevOps engineer: Orchestration configuration
- Safety reviewer: Critical classification validation

## Success Metrics

### Technical Metrics
- **Health Check Performance:** <100ms response time (safety requirement)
- **False Positive Rate:** <1% unnecessary restarts
- **Availability:** 99.9% system availability maintained
- **Standards Compliance:** 100% IETF health+json compliance

### Business Metrics
- **Incident Reduction:** 50% reduction in health-related operational incidents
- **MTTR Improvement:** 30% faster issue diagnosis and resolution
- **Compliance:** Full orchestration platform compatibility

## Notes & Decisions

### Decision Log
- **2025-01-11:** Approved 3-phase evolution approach over full restructure
- **2025-01-11:** Selected hybrid migration strategy to minimize risk
- **2025-01-11:** Established safety-critical response time requirement (100ms)

### Open Questions
- [ ] Determine optimal probe frequencies for production environment
- [ ] Define comprehensive list of critical vs warning classifications
- [ ] Establish safety review process for health check modifications
- [ ] Confirm orchestration platform requirements and constraints

---

**Next Action:** Begin Phase 1 implementation with system-status page endpoint update.
