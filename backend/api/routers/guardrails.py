"""Guardrail API endpoints for command-emission control.

Provides access to guardrail monitoring, command preconditions, command halt,
and audit logging. Firefly owns physical interlocks; these endpoints control
CoachIQ's API command-emission behavior.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.core.dependencies import (
    get_authenticated_admin,
    get_authenticated_user,
    get_command_guardrail_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guardrails", tags=["guardrails"])


class SystemStateUpdate(BaseModel):
    """System state update model."""

    vehicle_speed: float | None = Field(None, description="Vehicle speed in mph")
    parking_brake: bool | None = Field(None, description="Parking brake engaged status")
    leveling_jacks_down: bool | None = Field(None, description="Leveling jacks deployed status")
    engine_running: bool | None = Field(None, description="Engine running status")
    transmission_gear: str | None = Field(None, description="Current transmission gear")
    all_slides_retracted: bool | None = Field(None, description="All slides retracted status")


class CommandHaltRequest(BaseModel):
    """Command halt request model."""

    reason: str = Field(..., description="Reason for command halt")


class ClearCommandHaltRequest(BaseModel):
    """Command halt clear request model."""

    authorization_code: str = Field("", description="Legacy authorization code for clear")
    pin_session_id: str = Field("", description="PIN session ID for enhanced authorization")


@router.get("/status")
async def get_guardrail_status(
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    user: Annotated[dict, Depends(get_authenticated_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """
    Get comprehensive guardrail status.

    Returns current state of guardrail checks including:
    - Command halt state
    - Watchdog timer status
    - Command preconditions
    - Operator-supplied state information
    - Audit log entry count
    """
    try:
        return command_guardrail_service.get_guardrail_status()
    except Exception as e:
        logger.error("Error getting guardrails status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/update-state")
async def update_system_state(
    state_update: SystemStateUpdate,
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    user: Annotated[dict, Depends(get_authenticated_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """
    Update operator-supplied state information used by command preconditions.

    This endpoint accepts operator-supplied context; it is not the vehicle
    safety source of truth.
    """
    try:
        # Convert model to dict and filter out None values
        updates = {k: v for k, v in state_update.model_dump().items() if v is not None}

        if not updates:
            raise HTTPException(status_code=400, detail="No state updates provided")

        command_guardrail_service.update_system_state(updates)

        # Check interlocks after state update
        interlock_results = await command_guardrail_service.check_command_preconditions()

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
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    user: Annotated[dict, Depends(get_authenticated_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """
    Get status of all command preconditions.

    Returns detailed information about each command precondition including:
    - Engagement status
    - Protected feature
    - Required conditions
    - Engagement time and reason
    """
    try:
        status = command_guardrail_service.get_guardrail_status()
        return {"interlocks": status["interlocks"], "system_state": status["system_state"]}
    except Exception as e:
        logger.error("Error getting interlock status: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/interlocks/check")
async def check_interlocks(
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    user: Annotated[dict, Depends(get_authenticated_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """
    Manually trigger command precondition checks.

    Forces an immediate check of all command preconditions and returns
    the results. Interlocks will be engaged/disengaged as needed.
    """
    try:
        results = await command_guardrail_service.check_command_preconditions()
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


@router.post("/command-halt")
async def halt_command_emission(
    stop_request: CommandHaltRequest,
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, str]:
    """
    Trigger command halt for all position-critical features.

    This will:
    - Stop all position-critical features
    - Engage all command preconditions
    - Enter system-wide command halt state
    - Log the event to audit trail

    WARNING: This is a guardrail-critical operation that requires
    manual clearing with authorization.
    """
    try:
        # Include user information in the command halt call for audit trail
        triggered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"
        await command_guardrail_service.halt_command_emission(stop_request.reason, triggered_by)

        logger.warning(
            "Command halt triggered by admin user %s: %s", triggered_by, stop_request.reason
        )

        return {
            "status": "halt_command_emission_activated",
            "reason": stop_request.reason,
            "triggered_by": triggered_by,
            "message": "Command halt activated. Manual clearing with authorization required.",
        }
    except Exception as e:
        logger.error("Error triggering command halt: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/command-halt/clear")
async def clear_command_halt(
    clear_request: ClearCommandHaltRequest,
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, str]:
    """
    Clear command halt with authorization.

    Requires valid authorization code. After clearing, individual
    features and command preconditions must be manually re-enabled.
    """
    try:
        # Include user information in the clear call for audit trail
        cleared_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"
        success = await command_guardrail_service.clear_command_halt(
            clear_request.authorization_code, cleared_by, clear_request.pin_session_id
        )

        if not success:
            logger.warning("Invalid authorization code provided by admin user %s", cleared_by)
            raise HTTPException(status_code=403, detail="Invalid authorization code")

        logger.warning("Command halt cleared by admin user %s", cleared_by)

        return {
            "status": "success",
            "cleared_by": cleared_by,
            "message": "Command halt cleared. Features must be manually re-enabled.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing command halt: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/audit-log")
async def get_audit_log(
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],  # noqa: ARG001
    max_entries: int = 100,
) -> dict[str, Any]:
    """
    Get guardrails audit log entries.

    Returns recent guardrail-critical events including:
    - Interlock engagements/disengagements
    - Command halts
    - Command halt state entries
    - System errors

    Args:
        max_entries: Maximum number of entries to return (default: 100)
    """
    try:
        max_audit_entries = 1000
        if max_entries < 1 or max_entries > max_audit_entries:
            raise HTTPException(status_code=400, detail="max_entries must be between 1 and 1000")

        entries = command_guardrail_service.get_audit_log(max_entries)
        return {"total_entries": len(entries), "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting audit log: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/health")
async def get_guardrail_health(
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    user: Annotated[dict, Depends(get_authenticated_user)],  # noqa: ARG001
) -> dict[str, Any]:
    """
    Get guardrails service health status.

    Returns information about the guardrails monitoring system itself:
    - Monitoring task status
    - Watchdog timer health
    - Last check timestamps
    """
    try:
        status = command_guardrail_service.get_guardrail_status()

        # Calculate health based on watchdog status
        watchdog_healthy = status["time_since_last_kick"] < status["watchdog_timeout"]

        return {
            "healthy": watchdog_healthy and not status["in_command_halt_state"],
            "in_command_halt_state": status["in_command_halt_state"],
            "command_halt_active": status["command_halt_active"],
            "watchdog": {
                "timeout": status["watchdog_timeout"],
                "time_since_last_kick": status["time_since_last_kick"],
                "healthy": watchdog_healthy,
            },
            "monitoring_active": not status["in_command_halt_state"],
        }
    except Exception as e:
        logger.error("Error getting guardrails health: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# PIN-Based Guardrail Endpoints


class PINCommandHaltRequest(BaseModel):
    """PIN-based command halt request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")
    reason: str = Field(..., description="Reason for command halt")


class PINClearCommandHaltRequest(BaseModel):
    """PIN-based command halt clear request model."""

    pin_session_id: str = Field(..., description="PIN session ID for authorization")


@router.post("/pin/command-halt")
async def pin_halt_command_emission(
    stop_request: PINCommandHaltRequest,
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Trigger command halt using PIN authorization (Admin Only).

    Requires valid PIN session for command-halt operations.
    Provides enhanced security for guardrail-critical operations.
    """
    try:
        triggered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        success = await command_guardrail_service.halt_command_emission_with_pin(
            pin_session_id=stop_request.pin_session_id,
            reason=stop_request.reason,
            triggered_by=triggered_by,
        )

        if not success:
            logger.warning("PIN command halt failed for admin user %s", triggered_by)
            raise HTTPException(status_code=401, detail="PIN authorization failed for command halt")

        logger.warning(
            "PIN command halt triggered by admin user %s: %s", triggered_by, stop_request.reason
        )

        return {
            "status": "halt_command_emission_activated",
            "reason": stop_request.reason,
            "triggered_by": triggered_by,
            "authorization_method": "pin_session",
            "message": (
                "PIN-authorized command halt activated. Clearing requires PIN authorization."
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error triggering PIN command halt: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pin/command-halt/clear")
async def pin_clear_command_halt(
    clear_request: PINClearCommandHaltRequest,
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Clear command halt using PIN authorization (Admin Only).

    Requires valid PIN session for command-halt clear operations.
    Provides enhanced security for guardrail-critical operations.
    """
    try:
        cleared_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        success = await command_guardrail_service.clear_command_halt_with_pin(
            pin_session_id=clear_request.pin_session_id, reset_by=cleared_by
        )

        if not success:
            logger.warning("PIN command halt clear failed for admin user %s", cleared_by)
            raise HTTPException(
                status_code=401, detail="PIN authorization failed for command halt clear"
            )

        logger.warning("PIN command halt cleared by admin user %s", cleared_by)

        return {
            "status": "success",
            "cleared_by": cleared_by,
            "authorization_method": "pin_session",
            "message": "PIN-authorized command halt cleared. Features must be manually re-enabled.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing PIN command halt: %s", e)
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
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Override a command precondition using PIN authorization (Admin Only).

    Allows temporary override of command preconditions for maintenance or
    diagnostic operations. Requires valid PIN session with override permissions.
    Override will automatically expire after the specified duration.
    """
    try:
        overridden_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the guardrails service method to override with PIN authorization
        success = await command_guardrail_service.override_interlock_with_pin(
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
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Clear an active interlock override (Admin Only).

    Immediately removes any active override on the specified interlock,
    returning it to normal operation.
    """
    try:
        cleared_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Clear the override
        success = command_guardrail_service.clear_interlock_override(clear_request.interlock_name)

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
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],  # noqa: ARG001
) -> dict[str, Any]:
    """
    Get all active interlock overrides (Admin Only).

    Returns information about currently active interlock overrides including
    who authorized them, when they expire, and the reason for override.
    """
    try:
        status = command_guardrail_service.get_guardrail_status()
        active_overrides = status.get("active_overrides", {})

        # Get detailed override information for each interlock
        override_details = []
        for interlock_name, expiry in active_overrides.items():
            interlock = command_guardrail_service._interlocks.get(interlock_name)  # noqa: SLF001
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
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Enter maintenance mode using PIN authorization (Admin Only).

    In maintenance mode:
    - Guardrail interlocks can be temporarily overridden
    - Certain guardrails checks may be relaxed for service operations
    - All actions are fully audited
    - Mode automatically expires after the specified duration

    Requires valid PIN session with maintenance permissions.
    """
    try:
        entered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the guardrails service method to enter maintenance mode with PIN authorization
        success = await command_guardrail_service.enter_maintenance_mode_with_pin(
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
            "message": (f"Maintenance mode activated for {mode_request.duration_minutes} minutes"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error entering maintenance mode with PIN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pin/maintenance-mode/exit")
async def pin_exit_maintenance_mode(
    exit_request: PINMaintenanceModeExitRequest,
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Exit maintenance mode using PIN authorization (Admin Only).

    Returns system to normal operational mode:
    - All command preconditions return to normal operation
    - Any active overrides are cleared
    - Full guardrails validation resumes

    Requires valid PIN session.
    """
    try:
        exited_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the guardrails service method to exit maintenance mode with PIN authorization
        success = await command_guardrail_service.exit_maintenance_mode_with_pin(
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
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    user: Annotated[dict, Depends(get_authenticated_user)],  # noqa: ARG001
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
        status = command_guardrail_service.get_guardrail_status()
        mode = status["operational_mode"]
        mode_session = status.get("mode_session")

        result = {
            "operational_mode": mode,
            "is_normal_mode": mode == "normal",
        }

        if mode_session:
            result.update(
                {
                    "session_details": mode_session,
                    "active_overrides_count": len(status.get("active_overrides", {})),
                }
            )

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
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Enter diagnostic mode using PIN authorization (Admin Only).

    In diagnostic mode:
    - System diagnostics and testing can be performed
    - Test procedures may temporarily modify guardrails constraints
    - All actions are fully audited
    - Mode automatically expires after the specified duration

    WARNING: Diagnostic mode is intended for troubleshooting only.
    Guardrail constraints may be modified during diagnostics.

    Requires valid PIN session with diagnostic permissions.
    """
    try:
        entered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the guardrails service method to enter diagnostic mode with PIN authorization
        success = await command_guardrail_service.enter_diagnostic_mode_with_pin(
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
            "message": (f"Diagnostic mode activated for {mode_request.duration_minutes} minutes"),
            "warning": "Guardrail constraints may be modified during diagnostics",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error entering diagnostic mode with PIN: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pin/diagnostic-mode/exit")
async def pin_exit_diagnostic_mode(
    exit_request: PINDiagnosticModeExitRequest,
    command_guardrail_service: Annotated[Any, Depends(get_command_guardrail_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Exit diagnostic mode using PIN authorization (Admin Only).

    Returns system to normal operational mode:
    - All guardrails constraints return to normal operation
    - Any diagnostic overrides are cleared
    - Full guardrails validation resumes

    Requires valid PIN session.
    """
    try:
        exited_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"

        # Use the guardrails service method to exit diagnostic mode with PIN authorization
        success = await command_guardrail_service.exit_diagnostic_mode_with_pin(
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
