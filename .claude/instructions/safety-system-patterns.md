# Safety System Patterns

This file provides comprehensive guidance for developing with the SafetyServiceRegistry and ISO 26262-compliant safety patterns in the RV-C vehicle control system.

## 🚨 Critical Safety Context

This is a **safety-critical RV-C vehicle control system**. Code quality failures can result in dangerous malfunctions affecting:
- Slide rooms (position-critical)
- Awnings (position-critical)
- Leveling jacks (position-critical)
- Vehicle safety interlocks
- Emergency stop systems

**ALL safety-critical code MUST follow these patterns exactly.**

## Safety Architecture Overview

The safety system consists of three main components:

1. **SafetyServiceRegistry** - Extends EnhancedServiceRegistry with safety-specific functionality
2. **SafetyCapable Protocol** - Interface for services participating in safety systems
3. **Safety Classifications** - ISO 26262-inspired safety levels

## SafetyServiceRegistry Usage

### Registering Safety Services

Use `register_safety_service()` instead of `register_service()` for safety-critical services:

```python
from backend.core.safety_registry import SafetyServiceRegistry
from backend.services.feature_models import SafetyClassification

# Initialize safety registry
service_registry = SafetyServiceRegistry()

# Register safety-critical service
service_registry.register_safety_service(
    name="safety_service",
    init_func=_init_safety_service,
    safety_classification=SafetyClassification.CRITICAL,
    dependencies=[
        ServiceDependency("pin_manager", DependencyType.REQUIRED),
        ServiceDependency("security_audit_service", DependencyType.REQUIRED)
    ],
    description="ISO 26262-compliant safety monitoring and emergency stop coordination",
    tags={"iso26262", "emergency-stop", "safety-interlocks"}
)
```

### Safety Classifications

**CRITICAL** - Core safety functions, highest priority emergency stop:
- SafetyService
- Emergency stop coordination
- Safety interlock management

**SAFETY_RELATED** - Safety-supporting functions:
- AuthManager (security for safety access)
- SecurityAuditService (safety audit trails)

**POSITION_CRITICAL** - Physical positioning systems:
- Slide room controls
- Awning controls
- Leveling jack controls

**OPERATIONAL** - Normal operational services:
- Regular entity controls
- Dashboard services
- Monitoring services

**MAINTENANCE** - Non-critical maintenance functions:
- Logging services
- Analytics services

### Emergency Stop Coordination

```python
# Execute coordinated emergency stop
emergency_results = await service_registry.execute_emergency_stop(
    reason="Safety interlock violation: slide room extension blocked",
    triggered_by="safety_service"
)

# Check results
for service_name, success in emergency_results.items():
    if not success:
        logger.critical(f"Emergency stop FAILED for {service_name}")
```

## SafetyCapable Protocol Implementation

### Required Interface

All safety-critical services MUST implement the SafetyCapable protocol:

```python
from backend.core.safety_interfaces import SafetyCapable, SafetyStatus
from backend.services.feature_models import SafetyClassification

class MyVehicleControlService(SafetyCapable):
    @property
    def safety_classification(self) -> SafetyClassification:
        return SafetyClassification.POSITION_CRITICAL

    async def emergency_stop(self, reason: str) -> None:
        """CRITICAL: Implement immediate safe shutdown."""
        logger.critical(f"Emergency stop: {reason}")

        # 1. Stop all physical movement IMMEDIATELY
        await self._stop_all_motors()

        # 2. Engage safety locks/brakes
        await self._engage_safety_locks()

        # 3. Update safety status
        self._set_emergency_stop_active(True)

        # 4. Audit log
        await self._audit_emergency_stop(reason)

    async def get_safety_status(self) -> SafetyStatus:
        """Return current safety status."""
        if self._emergency_stop_active:
            return SafetyStatus.EMERGENCY_STOP
        elif self._has_active_interlocks():
            return SafetyStatus.DEGRADED
        elif self._system_faults_detected():
            return SafetyStatus.UNSAFE
        else:
            return SafetyStatus.SAFE

    async def validate_safety_interlock(self, operation: str) -> bool:
        """Validate operation against safety interlocks."""
        # Check vehicle state
        if not await self._vehicle_in_safe_state():
            return False

        # Check operation-specific interlocks
        if operation == "extend_slide":
            return await self._check_slide_extension_safety()
        elif operation == "extend_awning":
            return await self._check_awning_extension_safety()

        return True
```

### SafetyAware Base Class

For simpler safety integration, extend SafetyAware:

```python
from backend.core.safety_interfaces import SafetyAware, SafetyStatus
from backend.services.feature_models import SafetyClassification, SafeStateAction

class MyPositionCriticalService(SafetyAware):
    def __init__(self):
        super().__init__(
            safety_classification=SafetyClassification.POSITION_CRITICAL,
            safe_state_action=SafeStateAction.RETRACT_TO_SAFE
        )

    async def emergency_stop(self, reason: str) -> None:
        """Implement position-specific emergency stop."""
        # Retract to safe position
        await self._retract_to_safe_position()

        # Call base class emergency stop
        self._set_emergency_stop_active(True)

        logger.critical(f"Position-critical emergency stop: {reason}")
```

## Safety Interlock Patterns

### Defining Safety Interlocks

```python
from backend.services.safety_service import SafetyInterlock
from backend.services.feature_models import SafeStateAction

# Slide room safety interlock
slide_interlock = SafetyInterlock(
    name="slide_room_extension",
    feature_name="slide_rooms",
    interlock_conditions=[
        "vehicle_parked",
        "leveling_jacks_deployed",
        "clearance_sensors_clear",
        "awnings_retracted"
    ],
    safe_state_action=SafeStateAction.RETRACT_TO_SAFE
)

# Register with SafetyService
safety_service.register_interlock(slide_interlock)
```

### Safety Validation Patterns

```python
# Before any position-critical operation
async def control_slide_room(self, command: dict) -> dict:
    # 1. Validate safety interlocks
    if not await self.safety_service.validate_interlock("slide_room_extension"):
        return {
            "success": False,
            "error": "Safety interlock violation",
            "safety_status": "unsafe"
        }

    # 2. Check service safety status
    safety_status = await self.get_safety_status()
    if safety_status != SafetyStatus.SAFE:
        return {
            "success": False,
            "error": f"Service not in safe state: {safety_status.value}",
            "safety_status": safety_status.value
        }

    # 3. Proceed with operation
    return await self._execute_slide_control(command)
```

## Dependency Injection Patterns

### Using Safety Services

```python
from typing import Annotated
from fastapi import Depends
from backend.core.dependencies import get_safety_service

@router.post("/emergency-stop")
async def emergency_stop(
    safety_service: Annotated[Any, Depends(get_safety_service)],
    reason: str
) -> dict:
    """Emergency stop endpoint."""
    await safety_service.emergency_stop(reason, triggered_by="api")
    return {"success": True, "message": "Emergency stop executed"}

@router.get("/safety-status")
async def safety_status(
    safety_service: Annotated[Any, Depends(get_safety_service)]
) -> dict:
    """Get comprehensive safety status."""
    return await safety_service.get_safety_status_summary()
```

### Safety Service Access in Services

```python
class MyEntityControlService:
    def __init__(self, safety_service=None):
        self.safety_service = safety_service

    async def control_entity(self, entity_id: str, command: dict) -> dict:
        # Check safety before any control operation
        if self.safety_service:
            if not await self.safety_service.validate_operation(entity_id, command):
                return {"success": False, "error": "Safety validation failed"}

        # Proceed with control
        return await self._execute_control(entity_id, command)
```

## Error Handling and Safety Validation

### Safety Validation Errors

```python
from backend.core.safety_interfaces import SafetyValidationError, SafetyStatus

try:
    await service.validate_safety_interlock("extend_awning")
except SafetyValidationError as e:
    logger.error(f"Safety validation failed: {e}")
    return {
        "success": False,
        "error": str(e),
        "operation": e.operation,
        "safety_status": e.safety_status.value
    }
```

### Emergency Stop Error Handling

```python
async def handle_emergency_condition(self, condition: str):
    """Handle emergency conditions with proper error handling."""
    try:
        # Attempt coordinated emergency stop
        results = await self.service_registry.execute_emergency_stop(
            reason=f"Emergency condition: {condition}",
            triggered_by="safety_monitor"
        )

        # Check for failures
        failed_services = [
            name for name, success in results.items()
            if not success
        ]

        if failed_services:
            # Critical: Some services failed to stop
            logger.critical(f"EMERGENCY STOP PARTIAL FAILURE: {failed_services}")
            # Trigger hardware emergency stops if available
            await self._trigger_hardware_emergency_stops()

    except Exception as e:
        # CRITICAL: Emergency stop system failure
        logger.critical(f"EMERGENCY STOP SYSTEM FAILURE: {e}")
        await self._trigger_failsafe_procedures()
```

## Testing Safety Systems

### Safety Function Testing

```python
import pytest
from backend.core.safety_interfaces import SafetyStatus
from backend.services.feature_models import SafetyClassification

@pytest.mark.asyncio
async def test_emergency_stop_coordination():
    """Test coordinated emergency stop across services."""
    registry = SafetyServiceRegistry()

    # Register test safety service
    registry.register_safety_service(
        "test_service",
        MockSafetyService,
        SafetyClassification.CRITICAL
    )

    # Execute emergency stop
    results = await registry.execute_emergency_stop(
        "test emergency", "test_system"
    )

    # Verify all services stopped
    assert results["test_service"] is True

    # Verify service status
    service = registry.get_service("test_service")
    status = await service.get_safety_status()
    assert status == SafetyStatus.EMERGENCY_STOP

@pytest.mark.asyncio
async def test_safety_interlock_validation():
    """Test safety interlock prevents unsafe operations."""
    safety_service = SafetyService()

    # Create test interlock
    interlock = SafetyInterlock(
        name="test_interlock",
        feature_name="test_feature",
        interlock_conditions=["condition_a", "condition_b"]
    )
    safety_service.register_interlock(interlock)

    # Test with unsafe conditions
    unsafe_state = {"condition_a": False, "condition_b": True}
    is_safe, reason = await interlock.check_conditions(unsafe_state)
    assert not is_safe
    assert "condition_a" in reason
```

### Mock Safety Services

```python
class MockSafetyService(SafetyAware):
    def __init__(self):
        super().__init__(SafetyClassification.CRITICAL)
        self.emergency_stop_called = False

    async def emergency_stop(self, reason: str) -> None:
        self.emergency_stop_called = True
        self._set_emergency_stop_active(True)

    async def get_safety_status(self) -> SafetyStatus:
        return SafetyStatus.EMERGENCY_STOP if self.emergency_stop_called else SafetyStatus.SAFE
```

## Common Patterns and Anti-Patterns

### ✅ Good Safety Patterns

**1. Always validate safety before operations:**
```python
# GOOD: Check safety first
if not await self.validate_safety_interlock("extend_slide"):
    return {"error": "Safety interlock active"}
await self.extend_slide()
```

**2. Use proper safety classifications:**
```python
# GOOD: Classify safety-critical services properly
registry.register_safety_service(
    "slide_control", SlideControlService,
    SafetyClassification.POSITION_CRITICAL
)
```

**3. Implement comprehensive emergency stops:**
```python
# GOOD: Complete emergency stop implementation
async def emergency_stop(self, reason: str) -> None:
    await self.stop_all_motion()          # Stop movement
    await self.engage_safety_locks()      # Engage locks
    await self.audit_emergency_stop()     # Audit trail
    self._set_emergency_stop_active(True) # Update status
```

### ❌ Safety Anti-Patterns

**1. Skipping safety validation:**
```python
# BAD: No safety checks
await self.extend_slide()  # Could cause accident!
```

**2. Ignoring emergency stop results:**
```python
# BAD: Not checking emergency stop success
await registry.execute_emergency_stop("emergency", "system")
# Should check results and handle failures
```

**3. Blocking emergency stop methods:**
```python
# BAD: Slow emergency stop
async def emergency_stop(self, reason: str) -> None:
    await asyncio.sleep(5)  # TOO SLOW for emergency!
    await self.slow_retraction()
```

**4. Improper safety classifications:**
```python
# BAD: Wrong classification for position-critical service
registry.register_safety_service(
    "slide_control", SlideControlService,
    SafetyClassification.MAINTENANCE  # Should be POSITION_CRITICAL!
)
```

## Integration with ServiceRegistry

### Service Registration Order

```python
# 1. Initialize SafetyServiceRegistry
service_registry = SafetyServiceRegistry()

# 2. Register CRITICAL services first
service_registry.register_safety_service(
    "safety_service", SafetyService,
    SafetyClassification.CRITICAL
)

# 3. Register SAFETY_RELATED services
service_registry.register_safety_service(
    "auth_manager", AuthManager,
    SafetyClassification.SAFETY_RELATED
)

# 4. Register POSITION_CRITICAL services
service_registry.register_safety_service(
    "slide_control", SlideControlService,
    SafetyClassification.POSITION_CRITICAL
)

# 5. Register other services
service_registry.register_service("analytics", AnalyticsService)
```

### Service Startup Dependencies

```python
# Safety services have implicit startup order by classification
dependencies = [
    # CRITICAL services start first
    ServiceDependency("safety_service", DependencyType.REQUIRED),
    # Then SAFETY_RELATED
    ServiceDependency("auth_manager", DependencyType.REQUIRED),
    # Then POSITION_CRITICAL
    ServiceDependency("slide_control", DependencyType.OPTIONAL)
]
```

## Monitoring and Observability

### Safety Status Monitoring

```python
# Get comprehensive safety status
safety_summary = await registry.get_safety_status_summary()

# Example response:
{
    "critical_services": {
        "safety_service": "safe",
        "auth_manager": "safe"
    },
    "position_critical_services": {
        "slide_control": "degraded",
        "awning_control": "safe"
    },
    "overall_safety_status": "degraded",
    "summary": {
        "total_safety_services": 4,
        "critical_count": 0,
        "degraded_count": 1,
        "unsafe_count": 0,
        "emergency_stop_count": 0
    }
}
```

### Safety Metrics and Alerting

```python
# Monitor safety status changes
@registry.on_safety_status_change
async def handle_safety_status_change(service_name: str, old_status: SafetyStatus, new_status: SafetyStatus):
    if new_status in [SafetyStatus.UNSAFE, SafetyStatus.EMERGENCY_STOP]:
        # Alert operations team
        await alert_service.send_critical_alert(
            f"Safety status degraded: {service_name} -> {new_status.value}"
        )

        # Consider automatic emergency stop
        if new_status == SafetyStatus.UNSAFE:
            await registry.execute_emergency_stop(
                f"Automatic emergency stop: {service_name} unsafe",
                "safety_monitor"
            )
```

## Development Workflow

### Adding New Safety-Critical Services

1. **Design Phase:**
   - Identify safety classification
   - Define emergency stop procedures
   - Identify safety interlocks
   - Plan failure modes

2. **Implementation:**
   - Implement SafetyCapable protocol or extend SafetyAware
   - Add comprehensive emergency_stop method
   - Implement safety status reporting
   - Add safety interlock validation

3. **Registration:**
   - Register with appropriate safety classification
   - Define service dependencies properly
   - Add comprehensive health checks

4. **Testing:**
   - Test emergency stop procedures
   - Validate safety interlocks
   - Test failure scenarios
   - Verify integration with safety system

5. **Documentation:**
   - Document safety procedures
   - Update safety manuals
   - Train operators on new safety features

### Safety Code Review Checklist

- [ ] Service implements SafetyCapable protocol correctly
- [ ] Emergency stop method is immediate and comprehensive
- [ ] Safety classification is appropriate
- [ ] Safety interlocks are properly validated
- [ ] Error handling doesn't compromise safety
- [ ] Tests cover emergency scenarios
- [ ] Documentation includes safety procedures
- [ ] Performance doesn't block emergency operations

## Commands and Tools

Use these commands for safety system validation:

```bash
# Check safety patterns in code
/check-safety-patterns

# Verify service health including safety status
/check-service-health

# Check memory safety for real-time operations
/check-memory-safety

# Run comprehensive development health check
/dev-health-check
```

## Summary

The SafetyServiceRegistry and safety interfaces provide ISO 26262-inspired safety patterns for RV-C vehicle control. Key principles:

1. **Safety First**: Always validate safety before operations
2. **Fail Safe**: Emergency stops must be immediate and comprehensive
3. **Classify Properly**: Use correct safety classifications
4. **Monitor Continuously**: Track safety status across all services
5. **Test Thoroughly**: Verify emergency procedures work correctly

**Remember: This is safety-critical vehicle control software. When in doubt, fail safe.**
