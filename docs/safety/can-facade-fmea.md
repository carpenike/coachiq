# CAN Facade FMEA (Failure Mode and Effects Analysis)

## Document Information
- **System**: CoachIQ CAN Facade
- **Version**: 1.0
- **Date**: December 28, 2024
- **Compliance**: ISO 26262 Safety-Critical Systems
- **Classification**: SAFETY_CRITICAL

## Executive Summary

This FMEA analyzes potential failure modes in the CAN Facade architecture, evaluating their severity, occurrence probability, and detection capability. The CAN Facade is a safety-critical component controlling RV systems including slide rooms, awnings, and leveling jacks.

## Risk Priority Number (RPN) Calculation

**RPN = Severity × Occurrence × Detection**

### Severity (S)
- 10: Catastrophic - Could result in injury or death
- 8: Critical - Major system damage or safety hazard
- 6: Major - System inoperable, potential property damage
- 4: Minor - System degraded but operational
- 2: Minimal - Cosmetic or minor inconvenience

### Occurrence (O)
- 10: Very High - Failure almost inevitable
- 8: High - Repeated failures likely
- 6: Moderate - Occasional failures
- 4: Low - Relatively few failures
- 2: Very Low - Failure unlikely

### Detection (D)
- 10: Absolute Uncertainty - Cannot detect
- 8: Very Remote - Very low chance of detection
- 6: Remote - Low chance of detection
- 4: Moderate - Moderate chance of detection
- 2: Very High - Almost certain detection

## Failure Mode Analysis

### 1. Emergency Stop System Failures

#### 1.1 Emergency Stop Command Not Propagated
- **Failure Mode**: Emergency stop command fails to reach all safety-critical services
- **Cause**: Network partition, service crash, asyncio.gather exception
- **Effect**: Vehicle systems continue operating in unsafe condition
- **Severity**: 10 (Catastrophic)
- **Occurrence**: 2 (Very Low - asyncio.gather with exception handling)
- **Detection**: 2 (Very High - exception logging and metrics)
- **RPN**: 40
- **Current Controls**:
  - Parallel execution with asyncio.gather
  - Individual exception handling
  - Prometheus metrics (CAN_EMERGENCY_STOPS_TOTAL)
  - Critical service logging
- **Recommended Actions**:
  - Add redundant emergency stop channel
  - Implement hardware watchdog timer
  - Add emergency stop acknowledgment protocol

#### 1.2 Emergency Stop State Not Persisted
- **Failure Mode**: System restarts without remembering emergency stop state
- **Cause**: In-memory state only, no persistence
- **Effect**: System could resume unsafe operation after restart
- **Severity**: 8 (Critical)
- **Occurrence**: 4 (Low - requires both emergency stop and restart)
- **Detection**: 4 (Moderate - startup logs show state)
- **RPN**: 128
- **Current Controls**:
  - _emergency_stop_active flag
  - Safety status enum
- **Recommended Actions**:
  - Persist emergency stop state to disk
  - Require manual reset with PIN verification
  - Add startup safety check sequence

### 2. Health Monitoring Failures

#### 2.1 Health Monitor Task Crash
- **Failure Mode**: Health monitoring loop terminates unexpectedly
- **Cause**: Unhandled exception in _monitor_health()
- **Effect**: No automatic degradation detection, metrics stop updating
- **Severity**: 6 (Major)
- **Occurrence**: 4 (Low - exception handling in place)
- **Detection**: 6 (Remote - no direct monitoring of monitor)
- **RPN**: 144
- **Current Controls**:
  - Try/except blocks in health loop
  - 5-second check intervals
  - UNSAFE state on exceptions
- **Recommended Actions**:
  - Add health monitor supervisor task
  - Implement monitor heartbeat metric
  - Add redundant health check mechanism

#### 2.2 False Healthy Status
- **Failure Mode**: Service reports healthy when actually degraded
- **Cause**: Incorrect health check implementation
- **Effect**: System operates with degraded service
- **Severity**: 8 (Critical)
- **Occurrence**: 4 (Low - simple health checks)
- **Detection**: 6 (Remote - depends on failure visibility)
- **RPN**: 192
- **Current Controls**:
  - Individual service health checks
  - Safety status transitions
  - Comprehensive health endpoint
- **Recommended Actions**:
  - Add service self-test routines
  - Implement health check validation
  - Add cross-service health verification

### 3. Service Coordination Failures

#### 3.1 Service Dependency Failure
- **Failure Mode**: Required service unavailable during operation
- **Cause**: Service crash, network issue, resource exhaustion
- **Effect**: CAN operations fail or timeout
- **Severity**: 6 (Major)
- **Occurrence**: 4 (Low - ServiceRegistry manages dependencies)
- **Detection**: 2 (Very High - immediate exceptions)
- **RPN**: 48
- **Current Controls**:
  - ServiceRegistry dependency management
  - Service health checks
  - Exception propagation
- **Recommended Actions**:
  - Add service restart capability
  - Implement circuit breaker pattern
  - Add fallback operation modes

#### 3.2 Message Send During Emergency Stop
- **Failure Mode**: CAN messages sent while in emergency stop state
- **Cause**: Race condition, safety interlock bypass
- **Effect**: Unsafe vehicle system activation
- **Severity**: 10 (Catastrophic)
- **Occurrence**: 2 (Very Low - safety interlock in place)
- **Detection**: 2 (Very High - logged and returns error)
- **RPN**: 40
- **Current Controls**:
  - validate_safety_interlock() check
  - Emergency stop flag check
  - Error response on blocked operations
- **Recommended Actions**:
  - Add hardware-level CAN bus disable
  - Implement two-stage safety check
  - Add safety violation alerting

### 4. Performance Degradation

#### 4.1 Message Processing Latency Exceeds Threshold
- **Failure Mode**: CAN message processing takes >50ms
- **Cause**: CPU overload, queue backup, lock contention
- **Effect**: Delayed vehicle control response
- **Severity**: 8 (Critical - safety timing violation)
- **Occurrence**: 4 (Low - performance monitoring in place)
- **Detection**: 2 (Very High - PerformanceMonitor alerts)
- **RPN**: 64
- **Current Controls**:
  - PerformanceMonitor decorators
  - 50ms alert threshold for send_message
  - 20ms threshold for emergency_stop
- **Recommended Actions**:
  - Add adaptive load shedding
  - Implement priority message queuing
  - Add real-time scheduling hints

#### 4.2 Queue Overflow
- **Failure Mode**: CAN message queue exceeds capacity
- **Cause**: High message rate, slow processing
- **Effect**: Messages dropped, control commands lost
- **Severity**: 8 (Critical)
- **Occurrence**: 4 (Low - queue monitoring in place)
- **Detection**: 2 (Very High - queue metrics)
- **RPN**: 64
- **Current Controls**:
  - Queue depth monitoring
  - Prometheus metrics
  - Queue status endpoint
- **Recommended Actions**:
  - Implement queue overflow handling
  - Add message priority system
  - Add backpressure mechanism

### 5. State Management Failures

#### 5.1 Safety Status Incorrect Transition
- **Failure Mode**: Safety status transitions to wrong state
- **Cause**: Logic error, race condition
- **Effect**: System operates in incorrect safety mode
- **Severity**: 8 (Critical)
- **Occurrence**: 2 (Very Low - simple state machine)
- **Detection**: 4 (Moderate - status endpoints)
- **RPN**: 64
- **Current Controls**:
  - SafetyStatus enum
  - _set_safety_status() method
  - Status logging
- **Recommended Actions**:
  - Add state transition validation
  - Implement state audit trail
  - Add invalid transition alerting

### 6. Integration Failures

#### 6.1 Mixed Sync/Async Health Status Calls
- **Failure Mode**: Comprehensive health check fails
- **Cause**: Some services return sync, others async results
- **Effect**: Health monitoring endpoint errors
- **Severity**: 4 (Minor - monitoring only)
- **Occurrence**: 10 (Very High - was occurring)
- **Detection**: 2 (Very High - immediate exception)
- **RPN**: 80
- **Current Controls**:
  - asyncio.iscoroutine() check
  - Exception handling
  - ✅ FIXED in latest update
- **Status**: RESOLVED

## Risk Mitigation Summary

### High Priority Actions (RPN > 100)
1. **Persist Emergency Stop State** (RPN: 128)
   - Implement persistent storage for emergency stop flag
   - Add startup safety verification sequence

2. **Health Monitor Supervision** (RPN: 144)
   - Add supervisor task for health monitor
   - Implement monitor heartbeat metric

3. **Service Health Validation** (RPN: 192)
   - Implement comprehensive service self-tests
   - Add cross-service health verification

### Medium Priority Actions (RPN 50-100)
1. **Performance Management** (RPN: 64)
   - Implement adaptive load shedding
   - Add priority message queuing

2. **Queue Management** (RPN: 64)
   - Add queue overflow handling
   - Implement backpressure mechanism

### Low Priority Actions (RPN < 50)
1. **Emergency Stop Redundancy** (RPN: 40)
   - Add hardware-level safety mechanisms
   - Implement acknowledgment protocol

## Compliance Notes

This FMEA follows ISO 26262 guidelines for automotive safety-critical systems adapted for RV applications. All identified failure modes with catastrophic severity (S=10) have been designed with multiple mitigation layers to achieve low occurrence and high detection ratings.

## Review and Updates

This FMEA should be reviewed:
- After any architectural changes to the CAN Facade
- Following any safety-related incidents
- During annual safety audits
- When new failure modes are identified

**Last Updated**: December 28, 2024
**Next Review**: June 2025
