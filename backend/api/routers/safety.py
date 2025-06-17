"""
Safety API endpoints for RV-C vehicle control systems.

Provides access to safety monitoring, interlocks, emergency stop,
and audit logging functionality.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.core.dependencies_v2 import (
    get_authenticated_admin,
    get_authenticated_user,
    get_safety_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/safety", tags=["safety"])


class SystemStateUpdate(BaseModel):
    """System state update model."""

    vehicle_speed: float | None = Field(None, description="Vehicle speed in mph")
    parking_brake: bool | None = Field(None, description="Parking brake engaged status")
    leveling_jacks_down: bool | None = Field(None, description="Leveling jacks deployed status")
    engine_running: bool | None = Field(None, description="Engine running status")
    transmission_gear: str | None = Field(None, description="Current transmission gear")
    all_slides_retracted: bool | None = Field(None, description="All slides retracted status")


class EmergencyStopRequest(BaseModel):
    """Emergency stop request model."""

    reason: str = Field(..., description="Reason for emergency stop")


class EmergencyStopResetRequest(BaseModel):
    """Emergency stop reset request model."""

    authorization_code: str = Field("", description="Legacy authorization code for reset")
    pin_session_id: str = Field("", description="PIN session ID for enhanced authorization")


@router.get("/status")
async def get_safety_status(
    safety_service=Depends(get_safety_service),  # noqa: B008
    user: dict = Depends(get_authenticated_user),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Get comprehensive safety system status.

    Returns current state of all safety systems including:
    - Safe state status
    - Emergency stop status
    - Watchdog timer status
    - Safety interlock states
    - System state information
    - Audit log entry count
    """
    try:
        return safety_service.get_safety_status()
    except Exception as e:
        logger.error("Error getting safety status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/update-state")
async def update_system_state(
    state_update: SystemStateUpdate,
    safety_service=Depends(get_safety_service),  # noqa: B008
    user: dict = Depends(get_authenticated_user),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Update system state information used by safety interlocks.

    This endpoint allows updating vehicle state information that
    safety interlocks use to determine if operations are safe.
    """
    try:
        # Convert model to dict and filter out None values
        updates = {k: v for k, v in state_update.model_dump().items() if v is not None}

        if not updates:
            raise HTTPException(status_code=400, detail="No state updates provided")

        safety_service.update_system_state(updates)

        # Check interlocks after state update
        interlock_results = await safety_service.check_safety_interlocks()

        return {
            "status": "success",
            "updated_fields": list(updates.keys()),
            "interlock_check_results": {
                name: {"satisfied": satisfied, "reason": reason}
                for name, (satisfied, reason) in interlock_results.items()
            },
        }
    except Exception as e:
        logger.error("Error updating system state: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/interlocks")
async def get_interlock_status(
    safety_service=Depends(get_safety_service),  # noqa: B008
    user: dict = Depends(get_authenticated_user),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Get status of all safety interlocks.

    Returns detailed information about each safety interlock including:
    - Engagement status
    - Protected feature
    - Required conditions
    - Engagement time and reason
    """
    try:
        status = safety_service.get_safety_status()
        return {"interlocks": status["interlocks"], "system_state": status["system_state"]}
    except Exception as e:
        logger.error("Error getting interlock status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/interlocks/check")
async def check_interlocks(
    safety_service=Depends(get_safety_service),  # noqa: B008
    user: dict = Depends(get_authenticated_user),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Manually trigger safety interlock checks.

    Forces an immediate check of all safety interlocks and returns
    the results. Interlocks will be engaged/disengaged as needed.
    """
    try:
        results = await safety_service.check_safety_interlocks()
        return {
            "status": "success",
            "results": {
                name: {"satisfied": satisfied, "reason": reason}
                for name, (satisfied, reason) in results.items()
            },
        }
    except Exception as e:
        logger.error("Error checking interlocks: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/emergency-stop")
async def trigger_emergency_stop(
    stop_request: EmergencyStopRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, str]:
    """
    Trigger emergency stop for all position-critical features.

    This will:
    - Stop all position-critical features
    - Engage all safety interlocks
    - Enter system-wide safe state
    - Log the event to audit trail

    WARNING: This is a safety-critical operation that requires
    manual reset with authorization.
    """
    try:
        # Include user information in the emergency stop call for audit trail
        triggered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"
        await safety_service.trigger_emergency_stop(stop_request.reason, triggered_by)

        logger.warning(
            "Emergency stop triggered by admin user %s: %s", triggered_by, stop_request.reason
        )

        return {
            "status": "emergency_stop_activated",
            "reason": stop_request.reason,
            "triggered_by": triggered_by,
            "message": "Emergency stop activated. Manual reset with authorization required.",
        }
    except Exception as e:
        logger.error("Error triggering emergency stop: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/emergency-stop/reset")
async def reset_emergency_stop(
    reset_request: EmergencyStopResetRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, str]:
    """
    Reset emergency stop with authorization.

    Requires valid authorization code. After reset, individual
    features and interlocks must be manually re-enabled.
    """
    try:
        # Include user information in the reset call for audit trail
        reset_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"
        success = await safety_service.reset_emergency_stop(
            reset_request.authorization_code, reset_by, reset_request.pin_session_id
        )

        if not success:
            logger.warning("Invalid authorization code provided by admin user %s", reset_by)
            raise HTTPException(status_code=403, detail="Invalid authorization code")

        logger.warning("Emergency stop reset by admin user %s", reset_by)

        return {
            "status": "success",
            "reset_by": reset_by,
            "message": "Emergency stop reset. Features must be manually re-enabled.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting emergency stop: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/audit-log")
async def get_audit_log(
    max_entries: int = 100,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Get safety audit log entries.

    Returns recent safety-critical events including:
    - Interlock engagements/disengagements
    - Emergency stops
    - Safe state entries
    - System errors

    Args:
        max_entries: Maximum number of entries to return (default: 100)
    """
    try:
        max_audit_entries = 1000
        if max_entries < 1 or max_entries > max_audit_entries:
            raise HTTPException(status_code=400, detail="max_entries must be between 1 and 1000")

        entries = safety_service.get_audit_log(max_entries)
        return {"total_entries": len(entries), "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting audit log: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/health")
async def get_safety_health(
    safety_service=Depends(get_safety_service),  # noqa: B008
    user: dict = Depends(get_authenticated_user),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Get safety service health status.

    Returns information about the safety monitoring system itself:
    - Monitoring task status
    - Watchdog timer health
    - Last check timestamps
    """
    try:
        status = safety_service.get_safety_status()

        # Calculate health based on watchdog status
        watchdog_healthy = status["time_since_last_kick"] < status["watchdog_timeout"]

        return {
            "healthy": watchdog_healthy and not status["in_safe_state"],
            "in_safe_state": status["in_safe_state"],
            "emergency_stop_active": status["emergency_stop_active"],
            "watchdog": {
                "timeout": status["watchdog_timeout"],
                "time_since_last_kick": status["time_since_last_kick"],
                "healthy": watchdog_healthy,
            },
            "monitoring_active": not status["in_safe_state"],
        }
    except Exception as e:
        logger.error("Error getting safety health: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# PIN-Based Safety Endpoints


class PINEmergencyStopRequest(BaseModel):
    """PIN-based emergency stop request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")
    reason: str = Field(..., description="Reason for emergency stop")


class PINEmergencyResetRequest(BaseModel):
    """PIN-based emergency reset request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")


@router.post("/pin/emergency-stop")
async def pin_emergency_stop(
    stop_request: PINEmergencyStopRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Trigger emergency stop using PIN authorization (Admin Only).

    Requires valid PIN session for emergency operations.
    Provides enhanced security for safety-critical operations.
    """
    try:
        triggered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        success = await safety_service.emergency_stop_with_pin(
            pin_session_id=stop_request.pin_session_id,
            reason=stop_request.reason,
            triggered_by=triggered_by,
        )

        if not success:
            logger.warning("PIN emergency stop failed for admin user %s", triggered_by)
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for emergency stop"
            )

        logger.warning(
            "PIN emergency stop triggered by admin user %s: %s", triggered_by, stop_request.reason
        )

        return {
            "status": "emergency_stop_activated",
            "reason": stop_request.reason,
            "triggered_by": triggered_by,
            "authorization_method": "pin_session",
            "message": "PIN-authorized emergency stop activated. Reset requires PIN authorization.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error triggering PIN emergency stop: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pin/emergency-stop/reset")
async def pin_emergency_reset(
    reset_request: PINEmergencyResetRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Reset emergency stop using PIN authorization (Admin Only).

    Requires valid PIN session for reset operations.
    Provides enhanced security for safety-critical operations.
    """
    try:
        reset_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        success = await safety_service.reset_emergency_stop_with_pin(
            pin_session_id=reset_request.pin_session_id, reset_by=reset_by
        )

        if not success:
            logger.warning("PIN emergency reset failed for admin user %s", reset_by)
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for emergency reset"
            )

        logger.warning("PIN emergency stop reset by admin user %s", reset_by)

        return {
            "status": "success",
            "reset_by": reset_by,
            "authorization_method": "pin_session",
            "message": "PIN-authorized emergency stop reset. Features must be manually re-enabled.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting PIN emergency stop: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# PIN-Based Interlock Override Endpoints


class PINInterlockOverrideRequest(BaseModel):
    """PIN-based interlock override request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")
    interlock_name: str = Field(..., description="Name of the interlock to override")
    reason: str = Field(..., description="Reason for overriding the interlock")
    duration_minutes: int = Field(
        default=60,
        ge=1,
        le=480,  # Max 8 hours
        description="Override duration in minutes (1-480)",
    )


class InterlockOverrideClearRequest(BaseModel):
    """Clear interlock override request model."""

    interlock_name: str = Field(..., description="Name of the interlock to clear override")


@router.post("/pin/interlocks/override")
async def pin_override_interlock(
    override_request: PINInterlockOverrideRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Override a safety interlock using PIN authorization (Admin Only).

    Allows temporary override of safety interlocks for maintenance or
    diagnostic operations. Requires valid PIN session with override permissions.
    Override will automatically expire after the specified duration.
    """
    try:
        overridden_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the safety service method to override with PIN authorization
        success = await safety_service.override_interlock_with_pin(
            pin_session_id=override_request.pin_session_id,
            interlock_name=override_request.interlock_name,
            reason=override_request.reason,
            duration_minutes=override_request.duration_minutes,
            overridden_by=overridden_by,
        )

        if not success:
            logger.warning(
                "PIN interlock override failed for admin user %s on %s",
                overridden_by,
                override_request.interlock_name,
            )
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for interlock override"
            )

        logger.warning(
            "Interlock %s overridden by %s for %d minutes: %s",
            override_request.interlock_name,
            overridden_by,
            override_request.duration_minutes,
            override_request.reason,
        )

        return {
            "status": "success",
            "interlock_name": override_request.interlock_name,
            "overridden_by": overridden_by,
            "reason": override_request.reason,
            "duration_minutes": override_request.duration_minutes,
            "authorization_method": "pin_session",
            "message": (
                f"Interlock override activated for {override_request.duration_minutes} minutes"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error overriding interlock with PIN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/interlocks/clear-override")
async def clear_interlock_override(
    clear_request: InterlockOverrideClearRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Clear an active interlock override (Admin Only).

    Immediately removes any active override on the specified interlock,
    returning it to normal operation.
    """
    try:
        cleared_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Clear the override
        success = safety_service.clear_interlock_override(clear_request.interlock_name)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Interlock '{clear_request.interlock_name}' not found or not overridden",
            )

        logger.info(
            "Interlock override cleared for %s by %s", clear_request.interlock_name, cleared_by
        )

        return {
            "status": "success",
            "interlock_name": clear_request.interlock_name,
            "cleared_by": cleared_by,
            "message": "Interlock override cleared successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing interlock override: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/interlocks/overrides")
async def get_active_overrides(
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Get all active interlock overrides (Admin Only).

    Returns information about currently active interlock overrides including
    who authorized them, when they expire, and the reason for override.
    """
    try:
        status = safety_service.get_safety_status()
        active_overrides = status.get("active_overrides", {})

        # Get detailed override information for each interlock
        override_details = []
        for interlock_name, expiry in active_overrides.items():
            interlock = safety_service._interlocks.get(interlock_name)  # noqa: SLF001
            if interlock:
                override_info = interlock.get_override_info()
                if override_info:
                    override_details.append(
                        {
                            "interlock_name": interlock_name,
                            "feature": interlock.feature_name,
                            "overridden_by": override_info["overridden_by"],
                            "reason": override_info["reason"],
                            "expires_at": expiry,
                            "session_id": override_info["session_id"],
                        }
                    )

        return {
            "total_overrides": len(override_details),
            "overrides": override_details,
        }

    except Exception as e:
        logger.error("Error getting active overrides: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# PIN-Based Maintenance Mode Endpoints


class PINMaintenanceModeRequest(BaseModel):
    """PIN-based maintenance mode request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")
    reason: str = Field(..., description="Reason for entering maintenance mode")
    duration_minutes: int = Field(
        default=120,
        ge=15,
        le=480,  # Max 8 hours
        description="Maintenance mode duration in minutes (15-480)",
    )


class PINMaintenanceModeExitRequest(BaseModel):
    """PIN-based maintenance mode exit request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")


@router.post("/pin/maintenance-mode/enter")
async def pin_enter_maintenance_mode(
    mode_request: PINMaintenanceModeRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Enter maintenance mode using PIN authorization (Admin Only).

    In maintenance mode:
    - Safety interlocks can be temporarily overridden
    - Certain safety checks may be relaxed for service operations
    - All actions are fully audited
    - Mode automatically expires after the specified duration

    Requires valid PIN session with maintenance permissions.
    """
    try:
        entered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the safety service method to enter maintenance mode with PIN authorization
        success = await safety_service.enter_maintenance_mode_with_pin(
            pin_session_id=mode_request.pin_session_id,
            reason=mode_request.reason,
            duration_minutes=mode_request.duration_minutes,
            entered_by=entered_by,
        )

        if not success:
            logger.warning(
                "PIN maintenance mode entry failed for admin user %s",
                entered_by,
            )
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for maintenance mode"
            )

        logger.warning(
            "Maintenance mode entered by %s for %d minutes: %s",
            entered_by,
            mode_request.duration_minutes,
            mode_request.reason,
        )

        return {
            "status": "success",
            "operational_mode": "maintenance",
            "entered_by": entered_by,
            "reason": mode_request.reason,
            "duration_minutes": mode_request.duration_minutes,
            "authorization_method": "pin_session",
            "message": (
                f"Maintenance mode activated for {mode_request.duration_minutes} minutes"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error entering maintenance mode with PIN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pin/maintenance-mode/exit")
async def pin_exit_maintenance_mode(
    exit_request: PINMaintenanceModeExitRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Exit maintenance mode using PIN authorization (Admin Only).

    Returns system to normal operational mode:
    - All safety interlocks return to normal operation
    - Any active overrides are cleared
    - Full safety validation resumes

    Requires valid PIN session.
    """
    try:
        exited_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the safety service method to exit maintenance mode with PIN authorization
        success = await safety_service.exit_maintenance_mode_with_pin(
            pin_session_id=exit_request.pin_session_id,
            exited_by=exited_by,
        )

        if not success:
            logger.warning(
                "PIN maintenance mode exit failed for admin user %s",
                exited_by,
            )
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for maintenance mode exit"
            )

        logger.info("Maintenance mode exited by %s", exited_by)

        return {
            "status": "success",
            "operational_mode": "normal",
            "exited_by": exited_by,
            "authorization_method": "pin_session",
            "message": "Maintenance mode deactivated, normal operation resumed",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error exiting maintenance mode with PIN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/operational-mode")
async def get_operational_mode(
    safety_service=Depends(get_safety_service),  # noqa: B008
    user: dict = Depends(get_authenticated_user),  # noqa: B008, ARG001
) -> dict[str, Any]:
    """
    Get current operational mode and session details.

    Returns information about the current operational mode including:
    - Current mode (normal, maintenance, diagnostic)
    - Who activated the mode
    - When it was activated and when it expires
    - Active overrides count
    """
    try:
        status = safety_service.get_safety_status()
        mode = status["operational_mode"]
        mode_session = status.get("mode_session")

        result = {
            "operational_mode": mode,
            "is_normal_mode": mode == "normal",
        }

        if mode_session:
            result.update({
                "session_details": mode_session,
                "active_overrides_count": len(status.get("active_overrides", {})),
            })

        return result

    except Exception as e:
        logger.error("Error getting operational mode: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# PIN-Based Diagnostic Mode Endpoints


class PINDiagnosticModeRequest(BaseModel):
    """PIN-based diagnostic mode request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")
    reason: str = Field(..., description="Reason for entering diagnostic mode")
    duration_minutes: int = Field(
        default=60,
        ge=5,
        le=240,  # Max 4 hours for diagnostics
        description="Diagnostic mode duration in minutes (5-240)",
    )


class PINDiagnosticModeExitRequest(BaseModel):
    """PIN-based diagnostic mode exit request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")


@router.post("/pin/diagnostic-mode/enter")
async def pin_enter_diagnostic_mode(
    mode_request: PINDiagnosticModeRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Enter diagnostic mode using PIN authorization (Admin Only).

    In diagnostic mode:
    - System diagnostics and testing can be performed
    - Test procedures may temporarily modify safety constraints
    - All actions are fully audited
    - Mode automatically expires after the specified duration

    WARNING: Diagnostic mode is intended for troubleshooting only.
    Safety constraints may be modified during diagnostics.

    Requires valid PIN session with diagnostic permissions.
    """
    try:
        entered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the safety service method to enter diagnostic mode with PIN authorization
        success = await safety_service.enter_diagnostic_mode_with_pin(
            pin_session_id=mode_request.pin_session_id,
            reason=mode_request.reason,
            duration_minutes=mode_request.duration_minutes,
            entered_by=entered_by,
        )

        if not success:
            logger.warning(
                "PIN diagnostic mode entry failed for admin user %s",
                entered_by,
            )
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for diagnostic mode"
            )

        logger.warning(
            "Diagnostic mode entered by %s for %d minutes: %s",
            entered_by,
            mode_request.duration_minutes,
            mode_request.reason,
        )

        return {
            "status": "success",
            "operational_mode": "diagnostic",
            "entered_by": entered_by,
            "reason": mode_request.reason,
            "duration_minutes": mode_request.duration_minutes,
            "authorization_method": "pin_session",
            "message": (
                f"Diagnostic mode activated for {mode_request.duration_minutes} minutes"
            ),
            "warning": "Safety constraints may be modified during diagnostics",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error entering diagnostic mode with PIN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pin/diagnostic-mode/exit")
async def pin_exit_diagnostic_mode(
    exit_request: PINDiagnosticModeExitRequest,
    safety_service=Depends(get_safety_service),  # noqa: B008
    admin_user: dict = Depends(get_authenticated_admin),  # noqa: B008
) -> dict[str, Any]:
    """
    Exit diagnostic mode using PIN authorization (Admin Only).

    Returns system to normal operational mode:
    - All safety constraints return to normal operation
    - Any diagnostic overrides are cleared
    - Full safety validation resumes

    Requires valid PIN session.
    """
    try:
        exited_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the safety service method to exit diagnostic mode with PIN authorization
        success = await safety_service.exit_diagnostic_mode_with_pin(
            pin_session_id=exit_request.pin_session_id,
            exited_by=exited_by,
        )

        if not success:
            logger.warning(
                "PIN diagnostic mode exit failed for admin user %s",
                exited_by,
            )
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for diagnostic mode exit"
            )

        logger.info("Diagnostic mode exited by %s", exited_by)

        return {
            "status": "success",
            "operational_mode": "normal",
            "exited_by": exited_by,
            "authorization_method": "pin_session",
            "message": "Diagnostic mode deactivated, normal operation resumed",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error exiting diagnostic mode with PIN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
