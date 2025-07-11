"""
PIN Authentication API Router

Provides PIN-based authorization endpoints for safety-critical operations.
Designed for RV deployments with internet connectivity requiring additional
security layers beyond standard authentication.
"""

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.core.dependencies import (
    get_authenticated_admin,
    get_authenticated_user,
    get_pin_manager,
    get_security_audit_service,
)
from backend.services.pin_manager import PINManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pin-auth", tags=["pin-authentication"])

# PIN manager and security audit service are now accessed via standardized dependencies
# This eliminates global service variables and app.state access patterns


# Request/Response Models


class PINValidationRequest(BaseModel):
    """PIN validation request."""

    pin: str = Field(..., description="PIN to validate")
    pin_type: str = Field(..., description="Type of PIN: emergency, override, maintenance")


class PINValidationResponse(BaseModel):
    """PIN validation response."""

    success: bool = Field(..., description="Whether PIN validation succeeded")
    session_id: str | None = Field(None, description="Authorization session ID if successful")
    expires_in_seconds: int | None = Field(None, description="Session expiration time")
    operations_allowed: list[str] | None = Field(
        None, description="Operations allowed with this session"
    )
    message: str = Field(..., description="Status message")


class OperationAuthorizationRequest(BaseModel):
    """Operation authorization request."""

    session_id: str = Field(..., description="PIN session ID")
    operation: str = Field(..., description="Operation to authorize")


class OperationAuthorizationResponse(BaseModel):
    """Operation authorization response."""

    authorized: bool = Field(..., description="Whether operation is authorized")
    message: str = Field(..., description="Authorization status message")
    session_consumed: bool = Field(
        False, description="Whether session was consumed by this operation"
    )


class PINStatusResponse(BaseModel):
    """User PIN status response."""

    user_id: str = Field(..., description="User ID")
    is_locked_out: bool = Field(..., description="Whether user is currently locked out")
    lockout_until: float | None = Field(None, description="Lockout expiration timestamp")
    active_sessions: int = Field(..., description="Number of active PIN sessions")
    can_use_pins: bool = Field(..., description="Whether user can currently use PINs")
    message: str = Field(..., description="Status message")


class PINRotationResponse(BaseModel):
    """PIN rotation response."""

    success: bool = Field(..., description="Whether PIN rotation succeeded")
    new_pins: dict[str, str] = Field(..., description="New PINs by type")
    sessions_revoked: int = Field(..., description="Number of sessions revoked")
    warning: str = Field(..., description="Security warning about PIN display")


class SystemStatusResponse(BaseModel):
    """PIN system status response."""

    pin_types_configured: list[str] = Field(..., description="Available PIN types")
    active_sessions: int = Field(..., description="Number of active sessions")
    locked_users: int = Field(..., description="Number of locked out users")
    total_attempts_today: int = Field(..., description="Total PIN attempts today")
    healthy: bool = Field(..., description="System health status")


# PIN Validation Endpoints


@router.post("/validate", response_model=PINValidationResponse)
async def validate_pin(
    request: Request,
    pin_request: PINValidationRequest,
    user: Annotated[dict, Depends(get_authenticated_user)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
    security_service: Annotated[Any, Depends(get_security_audit_service)],
) -> PINValidationResponse:
    """
    Validate a PIN and create authorization session.

    Creates a time-limited session that can be used to authorize
    safety-critical operations. Sessions are single-use for emergency
    operations and multi-use for maintenance operations.
    """
    try:
        user_id = user["user_id"]

        # Get client IP for logging
        client_ip = None
        try:
            if hasattr(request, "client") and request.client and hasattr(request.client, "host"):
                client_ip = request.client.host  # type: ignore
        except AttributeError:
            client_ip = None

        # Validate PIN
        session_id = await pin_manager.validate_pin(
            user_id=user_id,
            pin=pin_request.pin,
            pin_type=pin_request.pin_type,
            ip_address=client_ip,
        )

        if not session_id:
            # Enhanced security audit for failed PIN validation
            if security_service:
                await security_service.log_security_event(
                    event_type="pin_validation_failure",
                    severity="medium",
                    user_id=user_id,
                    source_ip=client_ip,
                    endpoint="/api/pin/validate",
                    details={
                        "pin_type": pin_request.pin_type,
                        "failure_reason": "invalid_pin",
                    },
                )

            # Check if user is locked out for better error message
            user_status = await pin_manager.get_user_status(user_id)
            if user_status["is_locked_out"]:
                lockout_minutes = int((user_status["lockout_until"] - time.time()) / 60)

                # Log lockout event
                if security_service:
                    await security_service.log_security_event(
                        event_type="pin_lockout",
                        severity="high",
                        user_id=user_id,
                        source_ip=client_ip,
                        endpoint="/api/pin/validate",
                        details={
                            "lockout_minutes_remaining": lockout_minutes,
                            "pin_type": pin_request.pin_type,
                        },
                    )

                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Account locked due to failed PIN attempts. Try again in {lockout_minutes} minutes.",
                )

            logger.warning(f"PIN validation failed for user {user_id}, type {pin_request.pin_type}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN or PIN type"
            )

        # Enhanced security audit for successful PIN validation
        if security_service:
            await security_service.log_security_event(
                event_type="pin_validation_success",
                severity="medium",
                user_id=user_id,
                source_ip=client_ip,
                endpoint="/api/pin/validate",
                details={
                    "pin_type": pin_request.pin_type,
                    "session_id": session_id,
                },
            )

        # Get session info for response
        session_info = await pin_manager.get_session_info(session_id)
        if not session_info:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session created but not found",
            )
        expires_in = int(session_info["expires_at"] - time.time())

        logger.info(f"PIN session created for user {user_id}, type {pin_request.pin_type}")

        return PINValidationResponse(
            success=True,
            session_id=session_id,
            expires_in_seconds=expires_in,
            operations_allowed=session_info["operations_allowed"],
            message=f"PIN validation successful. Session expires in {expires_in} seconds.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PIN validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN validation service error"
        ) from e


@router.post("/authorize", response_model=OperationAuthorizationResponse)
async def authorize_operation(
    request: Request,
    auth_request: OperationAuthorizationRequest,
    user: Annotated[dict, Depends(get_authenticated_user)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> OperationAuthorizationResponse:
    """
    Authorize an operation using PIN session.

    Consumes a PIN session to authorize a specific safety-critical operation.
    Some sessions are single-use (emergency) while others allow multiple
    operations (maintenance).
    """
    try:
        user_id = user["user_id"]

        # Check if session exists and get info before authorization
        session_info = await pin_manager.get_session_info(auth_request.session_id)
        if not session_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="PIN session not found or expired"
            )

        # Authorize operation
        authorized = await pin_manager.authorize_operation(
            session_id=auth_request.session_id, operation=auth_request.operation, user_id=user_id
        )

        if not authorized:
            logger.warning(
                f"Operation authorization failed for user {user_id}, operation {auth_request.operation}"
            )
            return OperationAuthorizationResponse(
                authorized=False,
                message="Operation not authorized. Check session validity and operation permissions.",
                session_consumed=False,
            )

        # Check if session was consumed
        session_consumed = (await pin_manager.get_session_info(auth_request.session_id)) is None

        logger.info(f"Operation {auth_request.operation} authorized for user {user_id}")

        return OperationAuthorizationResponse(
            authorized=True,
            message=f"Operation '{auth_request.operation}' authorized successfully.",
            session_consumed=session_consumed,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Operation authorization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authorization service error"
        ) from e


# Session Management Endpoints


@router.delete("/sessions/{session_id}")
async def revoke_session(
    request: Request,
    session_id: str,
    user: Annotated[dict, Depends(get_authenticated_user)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> dict[str, str]:
    """
    Revoke a specific PIN session.

    Users can revoke their own sessions. Admins can revoke any session.
    """
    try:
        user_id = user["user_id"]
        is_admin = user.get("role") == "admin"

        # Get session info to check ownership
        session_info = await pin_manager.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        # Check if user can revoke this session
        if not is_admin and session_info["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Cannot revoke another user's session"
            )

        # Revoke session
        revoked = await pin_manager.revoke_session(session_id)
        if not revoked:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        logger.info(f"PIN session {session_id} revoked by user {user_id}")

        return {"message": "Session revoked successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session revocation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session revocation error"
        ) from e


@router.delete("/sessions")
async def revoke_all_user_sessions(
    request: Request,
    user: Annotated[dict, Depends(get_authenticated_user)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> dict[str, Any]:
    """
    Revoke all PIN sessions for the current user.

    Useful for security cleanup or when leaving the RV.
    """
    try:
        user_id = user["user_id"]

        revoked_count = await pin_manager.revoke_all_user_sessions(user_id)

        logger.info(f"Revoked {revoked_count} PIN sessions for user {user_id}")

        return {
            "message": f"Revoked {revoked_count} PIN sessions",
            "sessions_revoked": revoked_count,
        }

    except Exception as e:
        logger.error(f"Session revocation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session revocation error"
        ) from e


# Status and Information Endpoints


@router.get("/status", response_model=PINStatusResponse)
async def get_pin_status(
    request: Request,
    user: Annotated[dict, Depends(get_authenticated_user)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> PINStatusResponse:
    """
    Get PIN status for the current user.

    Shows lockout status, active sessions, and PIN availability.
    """
    try:
        user_id = user["user_id"]

        status = await pin_manager.get_user_status(user_id)

        # Create friendly message
        if status["is_locked_out"]:
            lockout_minutes = int((status["lockout_until"] - time.time()) / 60)
            message = (
                f"Account locked for {lockout_minutes} more minutes due to failed PIN attempts"
            )
        elif status["active_sessions"]:
            message = f"You have {len(status['active_sessions'])} active PIN sessions"
        else:
            message = "PIN authentication available"

        return PINStatusResponse(
            user_id=user_id,
            is_locked_out=status["is_locked_out"],
            lockout_until=status.get("lockout_until"),
            active_sessions=len(status["active_sessions"]),
            can_use_pins=status["can_use_pins"],
            message=message,
        )

    except Exception as e:
        logger.error(f"PIN status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN status service error"
        ) from e


# Admin Endpoints


@router.get("/admin/system-status", response_model=SystemStatusResponse)
async def get_system_status(
    request: Request,
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> SystemStatusResponse:
    """
    Get overall PIN system status (Admin only).

    Provides system-wide statistics and health information.
    """
    try:
        status = await pin_manager.get_system_status()

        return SystemStatusResponse(**status)

    except Exception as e:
        logger.error(f"PIN system status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN system status error"
        ) from e


@router.post("/admin/rotate-pins", response_model=PINRotationResponse)
async def rotate_pins(
    request: Request,
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> PINRotationResponse:
    """
    Generate new PINs for all types (Admin only).

    This is a security operation that revokes all existing sessions
    and generates new PINs. Use with caution.
    """
    try:
        # Count active sessions before rotation
        status = await pin_manager.get_system_status()
        sessions_before = status["active_sessions"]

        # Generate new PINs
        new_pins = await pin_manager.generate_new_pins()

        admin_id = admin_user["user_id"]
        logger.warning(f"PIN rotation performed by admin {admin_id}")

        return PINRotationResponse(
            success=True,
            new_pins=new_pins,
            sessions_revoked=sessions_before,
            warning="Save these PINs immediately! They will not be displayed again.",
        )

    except Exception as e:
        logger.error(f"PIN rotation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN rotation error"
        ) from e


@router.get("/admin/user-status/{user_id}")
async def get_user_pin_status(
    request: Request,
    user_id: str,
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> dict[str, Any]:
    """
    Get PIN status for a specific user (Admin only).

    Provides detailed information about user's PIN authentication status.
    """
    try:
        status = await pin_manager.get_user_status(user_id)

        return status

    except Exception as e:
        logger.error(f"User PIN status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User PIN status error"
        ) from e


@router.post("/admin/unlock-user/{user_id}")
async def unlock_user(
    request: Request,
    user_id: str,
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> dict[str, str]:
    """
    Unlock a user from PIN lockout (Admin only).

    Clears PIN attempt failures and removes lockout for the specified user.
    """
    try:
        # Clear failed attempts and lockout
        if user_id in pin_manager._failed_attempts:
            del pin_manager._failed_attempts[user_id]

        if user_id in pin_manager._lockouts:
            del pin_manager._lockouts[user_id]

        admin_id = admin_user["user_id"]
        logger.info(f"User {user_id} unlocked by admin {admin_id}")

        return {"message": f"User {user_id} has been unlocked"}

    except Exception as e:
        logger.error(f"User unlock error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User unlock error"
        ) from e


# Additional endpoints for frontend compatibility


@router.get("/security-status", response_model=SystemStatusResponse)
async def get_security_status_compat(
    request: Request,
    user: Annotated[dict, Depends(get_authenticated_user)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> SystemStatusResponse:
    """
    Get security status (compatibility endpoint for frontend).

    Maps to the system status endpoint for consistency.
    """
    try:
        status = await pin_manager.get_system_status()

        # Handle error case where database is unavailable
        if "error" in status:
            return SystemStatusResponse(
                pin_types_configured=[],
                active_sessions=0,
                locked_users=0,
                total_attempts_today=0,
                healthy=False,
            )

        return SystemStatusResponse(**status)

    except Exception as e:
        logger.error(f"Security status error: {e}")
        # Return a default response instead of 500 error for compatibility
        return SystemStatusResponse(
            pin_types_configured=[],
            active_sessions=0,
            locked_users=0,
            total_attempts_today=0,
            healthy=False,
        )


class PINInfo(BaseModel):
    """PIN information model."""

    pin_type: str = Field(..., description="Type of PIN")
    description: str = Field(..., description="PIN description")
    is_active: bool = Field(..., description="Whether PIN is active")
    use_count: int = Field(..., description="Number of times PIN has been used")
    lockout_after_failures: int = Field(..., description="Number of failures before lockout")
    lockout_duration_minutes: int = Field(..., description="Lockout duration in minutes")


class PINListResponse(BaseModel):
    """Response model for PIN list."""

    pins: list[PINInfo]


@router.get("/pins", response_model=PINListResponse)
async def get_user_pins(
    request: Request,
    user: Annotated[dict, Depends(get_authenticated_user)],
    pin_manager: Annotated[PINManager, Depends(get_pin_manager)],
) -> PINListResponse:
    """
    Get configured PINs for the current user.

    Returns information about available PIN types without revealing actual PINs.
    """
    try:
        user_id = user["user_id"]

        # Get available PIN types for this user
        pin_types_configured = []

        # Check which PIN types exist for the user
        # Note: We don't expose actual PINs, just their configuration
        if hasattr(pin_manager, "_pins") and user_id in pin_manager._pins:
            pin_types_configured = list(pin_manager._pins[user_id].keys())

        # Build PIN info for each configured type
        pins = []
        for pin_type in pin_types_configured:
            pin_info = PINInfo(
                pin_type=pin_type,
                description=f"{pin_type.capitalize()} PIN",
                is_active=True,
                use_count=0,
                lockout_after_failures=pin_manager._max_attempts,
                lockout_duration_minutes=pin_manager._lockout_duration,
            )
            pins.append(pin_info)

        return PINListResponse(pins=pins)

    except Exception as e:
        logger.error(f"Get user PINs error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve PIN information",
        ) from e
