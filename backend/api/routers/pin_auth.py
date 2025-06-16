"""
PIN Authentication API Router

Provides PIN-based authorization endpoints for safety-critical operations.
Designed for RV deployments with internet connectivity requiring additional
security layers beyond standard authentication.
"""

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.core.dependencies import get_authenticated_admin, get_authenticated_user
from backend.services.pin_manager import PINManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pin", tags=["pin-authentication"])

# Global PIN manager instance (will be initialized in main.py)
_pin_manager: PINManager | None = None


def get_pin_manager(request: Request | None = None) -> PINManager:
    """Get the PIN manager instance."""
    global _pin_manager
    if _pin_manager is None:
        if request and hasattr(request.app.state, "pin_manager"):
            _pin_manager = request.app.state.pin_manager
        else:
            # Fallback for testing
            from backend.services.pin_manager import PINConfig

            _pin_manager = PINManager(PINConfig())

    # Ensure we return a valid PINManager instance
    if _pin_manager is None:
        from backend.services.pin_manager import PINConfig

        _pin_manager = PINManager(PINConfig())

    return _pin_manager


def get_security_audit_service(request: Request):
    """Get security audit service for enhanced logging."""
    if hasattr(request.app.state, "security_audit_service"):
        return request.app.state.security_audit_service
    return None


def set_pin_manager(pin_manager: PINManager) -> None:
    """Set the PIN manager instance (called from main.py)."""
    global _pin_manager
    _pin_manager = pin_manager


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
    user: dict = Depends(get_authenticated_user),
) -> PINValidationResponse:
    """
    Validate a PIN and create authorization session.

    Creates a time-limited session that can be used to authorize
    safety-critical operations. Sessions are single-use for emergency
    operations and multi-use for maintenance operations.
    """
    try:
        pin_manager = get_pin_manager(request)
        user_id = user["user_id"]

        # Get client IP for logging
        client_ip = None
        try:
            if hasattr(request, "client") and request.client and hasattr(request.client, "host"):
                client_ip = request.client.host  # type: ignore
        except AttributeError:
            client_ip = None

        # Enhanced security logging
        security_service = get_security_audit_service(request)

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
            user_status = pin_manager.get_user_status(user_id)
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
        session_info = pin_manager.get_session_info(session_id)
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
    user: dict = Depends(get_authenticated_user),
) -> OperationAuthorizationResponse:
    """
    Authorize an operation using PIN session.

    Consumes a PIN session to authorize a specific safety-critical operation.
    Some sessions are single-use (emergency) while others allow multiple
    operations (maintenance).
    """
    try:
        pin_manager = get_pin_manager(request)
        user_id = user["user_id"]

        # Check if session exists and get info before authorization
        session_info = pin_manager.get_session_info(auth_request.session_id)
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
        session_consumed = pin_manager.get_session_info(auth_request.session_id) is None

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
    request: Request, session_id: str, user: dict = Depends(get_authenticated_user)
) -> dict[str, str]:
    """
    Revoke a specific PIN session.

    Users can revoke their own sessions. Admins can revoke any session.
    """
    try:
        pin_manager = get_pin_manager(request)
        user_id = user["user_id"]
        is_admin = user.get("role") == "admin"

        # Get session info to check ownership
        session_info = pin_manager.get_session_info(session_id)
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
    request: Request, user: dict = Depends(get_authenticated_user)
) -> dict[str, Any]:
    """
    Revoke all PIN sessions for the current user.

    Useful for security cleanup or when leaving the RV.
    """
    try:
        pin_manager = get_pin_manager(request)
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
    request: Request, user: dict = Depends(get_authenticated_user)
) -> PINStatusResponse:
    """
    Get PIN status for the current user.

    Shows lockout status, active sessions, and PIN availability.
    """
    try:
        pin_manager = get_pin_manager(request)
        user_id = user["user_id"]

        status = pin_manager.get_user_status(user_id)

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
    request: Request, admin_user: dict = Depends(get_authenticated_admin)
) -> SystemStatusResponse:
    """
    Get overall PIN system status (Admin only).

    Provides system-wide statistics and health information.
    """
    try:
        pin_manager = get_pin_manager(request)
        status = pin_manager.get_system_status()

        return SystemStatusResponse(**status)

    except Exception as e:
        logger.error(f"PIN system status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PIN system status error"
        ) from e


@router.post("/admin/rotate-pins", response_model=PINRotationResponse)
async def rotate_pins(
    request: Request, admin_user: dict = Depends(get_authenticated_admin)
) -> PINRotationResponse:
    """
    Generate new PINs for all types (Admin only).

    This is a security operation that revokes all existing sessions
    and generates new PINs. Use with caution.
    """
    try:
        pin_manager = get_pin_manager(request)

        # Count active sessions before rotation
        status = pin_manager.get_system_status()
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
    request: Request, user_id: str, admin_user: dict = Depends(get_authenticated_admin)
) -> dict[str, Any]:
    """
    Get PIN status for a specific user (Admin only).

    Provides detailed information about user's PIN authentication status.
    """
    try:
        pin_manager = get_pin_manager(request)
        status = pin_manager.get_user_status(user_id)

        return status

    except Exception as e:
        logger.error(f"User PIN status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User PIN status error"
        ) from e


@router.post("/admin/unlock-user/{user_id}")
async def unlock_user(
    request: Request, user_id: str, admin_user: dict = Depends(get_authenticated_admin)
) -> dict[str, str]:
    """
    Unlock a user from PIN lockout (Admin only).

    Clears PIN attempt failures and removes lockout for the specified user.
    """
    try:
        pin_manager = get_pin_manager(request)

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
