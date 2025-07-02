# CAN Facade Emergency Procedures

## Document Information
- **System**: CoachIQ CAN Facade
- **Version**: 1.0
- **Date**: December 28, 2024
- **Compliance**: ISO 26262 Safety-Critical Systems
- **Classification**: SAFETY_CRITICAL
- **Review Frequency**: Quarterly or after any safety incident

## 🚨 Emergency Contact Information

### Primary Support
- **System Owner**: Check GitHub repository owner
- **Emergency**: Physical emergency stop button on RV control panel
- **Support**: Open issue on GitHub repository

### Community Support
- **Project Issues**: GitHub Issues page
- **Discussions**: GitHub Discussions for questions
- **Documentation**: See project README and docs/

## Emergency Response Flowchart

```
┌─────────────────────┐
│   SAFETY EVENT      │
│    DETECTED         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  ASSESS SEVERITY    │
└──────────┬──────────┘
           │
    ┌──────┴──────┬──────────────┐
    │             │              │
    ▼             ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│CRITICAL│  │  HIGH    │  │ MEDIUM   │
└────┬───┘  └────┬─────┘  └────┬─────┘
     │           │              │
     ▼           ▼              ▼
[EMERGENCY] [IMMEDIATE]    [SCHEDULED]
[  STOP   ] [RESPONSE ]    [RESPONSE ]
```

## Emergency Procedures by Severity

### 🔴 CRITICAL: Immediate Safety Risk

**Indicators**:
- Uncontrolled vehicle movement
- Slide room/awning activation without command
- Total CAN bus failure
- Multiple simultaneous safety violations

**Response Procedure**:
1. **IMMEDIATELY** trigger emergency stop:
   ```bash
   curl -X POST http://localhost:8080/api/can/emergency-stop \
     -H "Content-Type: application/json" \
     -d '{"reason": "Critical safety event - [DESCRIBE]"}'
   ```

2. **NOTIFY** on-call engineer via PagerDuty
3. **DISABLE** physical CAN interfaces if possible
4. **DOCUMENT** all actions in incident log
5. **DO NOT** restart system without safety inspection

### 🟡 HIGH: Potential Safety Risk

**Indicators**:
- SafetyStatus = DEGRADED
- Service health check failures
- Performance degradation >50ms
- Queue overflow warnings

**Response Procedure**:
1. **CHECK** comprehensive health status:
   ```bash
   curl http://localhost:8080/api/can/health/comprehensive
   ```

2. **MONITOR** Prometheus metrics:
   - `coachiq_can_safety_status`
   - `coachiq_can_message_latency_seconds`
   - `coachiq_can_error_frames_total`

3. **PREPARE** for emergency stop if conditions worsen
4. **NOTIFY** engineering team via Slack #can-alerts
5. **REDUCE** system load if possible

### 🟢 MEDIUM: Operational Issue

**Indicators**:
- Individual service warnings
- Intermittent connection issues
- Non-critical performance alerts

**Response Procedure**:
1. **GATHER** diagnostic information
2. **CREATE** support ticket
3. **SCHEDULE** maintenance window
4. **CONTINUE** monitoring

## Emergency Stop Procedures

### Triggering Emergency Stop

#### Via API (Recommended)
```bash
# Basic emergency stop
curl -X POST http://localhost:8080/api/can/emergency-stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "Emergency stop reason here"}'

# With authentication (production)
curl -X POST https://api.production.com/api/can/emergency-stop \
  -H "Authorization: Bearer $EMERGENCY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Production emergency stop"}'
```

#### Via Code (Internal)
```python
# Direct facade access (for internal services)
can_facade = get_can_facade()  # Via ServiceRegistry
await can_facade.emergency_stop("Code-triggered emergency")
```

#### Via Hardware (Physical)
1. Locate emergency stop button on control panel
2. Press and hold for 3 seconds
3. System will enter hardware lockout mode

### Post-Emergency Stop Recovery

**⚠️ WARNING**: System restart after emergency stop requires verification

1. **VERIFY** root cause is resolved
2. **INSPECT** physical systems:
   - Slide rooms in safe position
   - Awnings fully retracted
   - Leveling jacks secured

3. **CHECK** system logs:
   ```bash
   # Check emergency stop logs
   grep "EMERGENCY STOP" /var/log/coachiq/can.log

   # Check safety violations
   grep "Safety interlock" /var/log/coachiq/can.log
   ```

4. **CLEAR** emergency state:
   ```python
   # Manual reset required - no API endpoint for safety
   # Must be done by authorized personnel only
   ```

5. **RESTART** services in order:
   ```bash
   # Stop all services
   systemctl stop coachiq

   # Clear message queues
   rm -f /var/lib/coachiq/can_queue/*

   # Start services
   systemctl start coachiq

   # Verify health
   curl http://localhost:8080/api/can/health
   ```

6. **TEST** basic operations before full activation

## Diagnostic Commands

### Quick Health Check
```bash
# Basic health
curl -s http://localhost:8080/api/can/health | jq .

# Comprehensive health
curl -s http://localhost:8080/api/can/health/comprehensive | jq .

# Interface status
curl -s http://localhost:8080/api/can/status | jq .
```

### Performance Monitoring
```bash
# Check message latency
curl -s http://localhost:9090/api/v1/query?query=coachiq_can_message_latency_seconds

# Check queue depth
curl -s http://localhost:9090/api/v1/query?query=coachiq_can_message_queue_depth

# Check error rate
curl -s http://localhost:9090/api/v1/query?query=rate(coachiq_can_error_frames_total[5m])
```

### Log Analysis
```bash
# Recent errors
tail -f /var/log/coachiq/can.log | grep ERROR

# Safety events
grep -i "safety\|emergency" /var/log/coachiq/can.log

# Performance issues
grep "threshold exceeded" /var/log/coachiq/can.log
```

## Common Emergency Scenarios

### Scenario 1: Slide Room Runaway
**Symptoms**: Slide room continues moving despite stop command
**Response**:
1. IMMEDIATE emergency stop
2. Disconnect slide room controller power
3. Engage manual override locks
4. Document CAN message log for analysis

### Scenario 2: CAN Bus Storm
**Symptoms**: Message rate >10,000 msg/sec, system unresponsive
**Response**:
1. Emergency stop all CAN services
2. Disconnect suspicious devices
3. Enable message filtering
4. Restart with reduced device set

### Scenario 3: Multi-Service Failure
**Symptoms**: Multiple services report unhealthy
**Response**:
1. Check system resources (CPU, memory)
2. Review recent deployments
3. Failover to backup system if available
4. Initiate emergency stop if safety risk

### Scenario 4: Authentication Failure
**Symptoms**: Cannot trigger emergency stop via API
**Response**:
1. Use hardware emergency stop
2. Access system console directly
3. Use break-glass credentials
4. Document security incident

## Testing Emergency Procedures

### Monthly Drills
1. **Emergency Stop Test**
   - Trigger via API
   - Verify all services stop
   - Test recovery procedure

2. **Failover Test**
   - Simulate service failure
   - Verify degradation handling
   - Test alert notifications

3. **Performance Degradation**
   - Inject artificial latency
   - Verify threshold alerts
   - Test load shedding

### Quarterly Reviews
1. Update emergency contacts
2. Review recent incidents
3. Update procedures based on lessons learned
4. Train new team members

## Appendix: Safety Boundaries

### Never Override These Safeties
- Emergency stop state persistence
- Safety interlock on message sending
- Watchdog timer thresholds
- Authentication on emergency endpoints

### Acceptable Emergency Overrides
- Queue size limits (with approval)
- Performance thresholds (temporarily)
- Non-critical service health checks

## Document History

- **v1.0** (2024-12-28): Initial emergency procedures
- **Next Review**: March 2025

---
**Remember**: Safety is not optional. When in doubt, trigger emergency stop.
