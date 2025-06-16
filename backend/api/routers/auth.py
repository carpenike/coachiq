"""
Authentication API Router

This module provides authentication endpoints for the CoachIQ system including:
- Login with username/password (single-user mode)
- Magic link authentication (multi-user mode)
- User profile endpoints
- Token validation and refresh

The router adapts to the configured authentication mode automatically.
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from backend.core.dependencies import get_auth_manager, get_notification_manager
from backend.middleware.rate_limiting import (
    admin_api_rate_limit,
    auth_rate_limit,
    check_auth_rate_limit,
    magic_link_rate_limit,
)
from backend.services.auth_manager import (
    AccountLockedError,
    AuthenticationError,
    AuthManager,
    AuthMode,
    InvalidTokenError,
)
from backend.services.user_invitation_service import (
    UserInvitationRequest,
    UserInvitationResponse,
    UserInvitationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# Pydantic models for request/response
class Token(BaseModel):
    """JWT token response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPair(BaseModel):
    """Access and refresh token pair response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class LoginStepResponse(BaseModel):
    """Login step response - either tokens or MFA challenge."""

    success: bool
    mfa_required: bool = False
    user_id: str | None = None
    # If MFA not required, include tokens
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    refresh_expires_in: int | None = None


class RefreshTokenRequest(BaseModel):
    """Refresh token request model."""

    refresh_token: str


class TokenData(BaseModel):
    """JWT token payload data."""

    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    role: str | None = None
    mode: str | None = None


class UserInfo(BaseModel):
    """User information response model."""

    user_id: str
    username: str | None = None
    email: str | None = None
    role: str = "user"
    mode: str
    authenticated: bool = True


class MagicLinkRequest(BaseModel):
    """Magic link request model."""

    email: EmailStr
    redirect_url: str | None = None


class MagicLinkResponse(BaseModel):
    """Magic link response model."""

    message: str
    email: str
    expires_in_minutes: int


class AuthStatus(BaseModel):
    """Authentication status response model."""

    enabled: bool
    mode: str
    jwt_available: bool
    magic_links_enabled: bool
    oauth_enabled: bool


class AdminCredentials(BaseModel):
    """Auto-generated admin credentials response model."""

    username: str
    password: str
    created_at: str
    warning: str


class MFAVerificationRequest(BaseModel):
    """MFA verification request model."""

    totp_code: str


class MFASetupResponse(BaseModel):
    """MFA setup response model."""

    secret: str
    qr_code: str
    provisioning_uri: str
    backup_codes: list[str]
    issuer: str


class BackupCodesResponse(BaseModel):
    """Backup codes response model."""

    backup_codes: list[str]
    warning: str


class MFAStatus(BaseModel):
    """MFA status response model."""

    user_id: str
    mfa_enabled: bool
    setup_initiated: bool
    created_at: str | None = None
    last_used: str | None = None
    backup_codes_remaining: int
    backup_codes_total: int
    available: bool


class MFASecretResponse(BaseModel):
    """MFA secret setup response model."""

    secret: str
    qr_code: str
    provisioning_uri: str
    backup_codes: list[str]
    issuer: str


# Dependency functions
async def get_user_invitation_service(
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
    notification_manager: Annotated[Any, Depends(get_notification_manager)],
) -> UserInvitationService:
    """
    Get user invitation service instance.

    Args:
        auth_manager: Authentication manager instance
        notification_manager: Notification manager instance

    Returns:
        UserInvitationService: User invitation service instance
    """
    return UserInvitationService(auth_manager, notification_manager)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> UserInfo:
    """
    Get current authenticated user from JWT token.

    Args:
        token: JWT token from Authorization header
        auth_manager: Authentication manager instance

    Returns:
        UserInfo: Current user information

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # In no-auth mode, return default admin user
    if auth_manager.auth_mode == AuthMode.NONE:
        return UserInfo(
            user_id="admin",
            username="admin",
            email="admin@localhost",
            role="admin",
            mode="none",
            authenticated=True,
        )

    if not token:
        raise credentials_exception

    try:
        payload = auth_manager.validate_token(token)
        user_id = payload.get("sub")
        username = payload.get("username", "")
        email = payload.get("email", "")
        role = payload.get("role", "user")
        mode = payload.get("mode", auth_manager.auth_mode.value)

        if not user_id:
            raise credentials_exception

        return UserInfo(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            mode=mode,
            authenticated=True,
        )

    except InvalidTokenError:
        raise credentials_exception from None


async def get_current_admin_user(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> UserInfo:
    """
    Get current user and verify admin privileges.

    Args:
        current_user: Current authenticated user

    Returns:
        UserInfo: Current admin user information

    Raises:
        HTTPException: If user is not an admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user


# Authentication endpoints
@router.post("/login", response_model=TokenPair)
@auth_rate_limit
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> TokenPair:
    """
    Authenticate user with username and password (single-user mode).

    Args:
        form_data: OAuth2 form data with username and password
        auth_manager: Authentication manager instance

    Returns:
        TokenPair: JWT access token, refresh token and metadata

    Raises:
        HTTPException: If authentication fails or not in single-user mode
    """
    if auth_manager.auth_mode == AuthMode.NONE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication is disabled"
        )

    if auth_manager.auth_mode != AuthMode.SINGLE_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username/password login not available in this mode",
        )

    # Additional rate limiting check with username
    check_auth_rate_limit(request, form_data.username)

    try:
        # Authenticate admin user with refresh token
        tokens = await auth_manager.authenticate_admin_with_refresh(
            form_data.username, form_data.password
        )

        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token, refresh_token = tokens
        logger.info(f"Successful login for user: {form_data.username}")

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=auth_manager.settings.jwt_expire_minutes * 60,
            refresh_expires_in=auth_manager.settings.refresh_token_expire_days * 24 * 60 * 60,
        )

    except AccountLockedError:
        # Let AccountLockedError bubble up to the global exception handler
        # which will return HTTP 423 with proper lockout information
        raise
    except AuthenticationError as e:
        logger.warning(f"Authentication failed for user {form_data.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@router.post("/login-step", response_model=LoginStepResponse)
@auth_rate_limit
async def login_step_with_mfa_check(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> LoginStepResponse:
    """
    First step of login - checks credentials and MFA requirement.

    Args:
        form_data: OAuth2 form data with username and password
        auth_manager: Authentication manager instance

    Returns:
        LoginStepResponse: Either tokens (if no MFA) or MFA challenge

    Raises:
        HTTPException: If authentication fails or not in single-user mode
    """
    if auth_manager.auth_mode == AuthMode.NONE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication is disabled"
        )

    if auth_manager.auth_mode != AuthMode.SINGLE_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username/password login not available in this mode",
        )

    # Additional rate limiting check with username
    check_auth_rate_limit(request, form_data.username)

    try:
        # First verify username and password (without MFA)
        tokens = await auth_manager.authenticate_admin_with_refresh(
            form_data.username, form_data.password
        )

        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token, refresh_token = tokens
        user_id = "admin"  # In single-user mode, user is always admin

        # Check if MFA is required for this user
        if auth_manager.is_mfa_available():
            mfa_status = await auth_manager.get_mfa_status(user_id)
            if mfa_status["mfa_enabled"]:
                # MFA is enabled - return challenge
                logger.info(f"MFA verification required for user: {form_data.username}")
                return LoginStepResponse(
                    success=True,
                    mfa_required=True,
                    user_id=user_id,
                )

        # No MFA required - return tokens
        logger.info(f"Successful login for user: {form_data.username}")
        return LoginStepResponse(
            success=True,
            mfa_required=False,
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=auth_manager.settings.jwt_expire_minutes * 60,
            refresh_expires_in=auth_manager.settings.refresh_token_expire_days * 24 * 60 * 60,
        )

    except AccountLockedError:
        # Let AccountLockedError bubble up to the global exception handler
        # which will return HTTP 423 with proper lockout information
        raise
    except AuthenticationError as e:
        logger.warning(f"Authentication failed for user {form_data.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@router.post("/login-mfa", response_model=TokenPair)
@auth_rate_limit
async def complete_login_with_mfa(
    request: Request,
    mfa_verification: MFAVerificationRequest,
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> TokenPair:
    """
    Complete login after MFA verification.

    Args:
        mfa_verification: MFA verification request with TOTP or backup code
        current_user: Current authenticated user (from step 1)
        auth_manager: Authentication manager instance

    Returns:
        TokenPair: Final JWT access and refresh tokens

    Raises:
        HTTPException: If MFA verification fails
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    try:
        # Verify MFA code
        success = await auth_manager.verify_mfa_code(current_user.user_id, mfa_verification.totp_code)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Generate fresh tokens after successful MFA verification
        access_token = auth_manager.generate_token(
            user_id=current_user.user_id,
            username=current_user.username or "",
            additional_claims={
                "role": current_user.role,
                "mode": "single-user",
                "mfa_verified": True,
            },
        )

        refresh_token = ""
        if auth_manager.settings.enable_refresh_tokens:
            refresh_token = await auth_manager.generate_refresh_token(
                user_id=current_user.user_id,
                username=current_user.username or "",
                additional_claims={
                    "role": current_user.role,
                    "mode": "single-user",
                    "mfa_verified": True,
                },
            )

        logger.info(f"MFA verification successful for user: {current_user.user_id}")

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=auth_manager.settings.jwt_expire_minutes * 60,
            refresh_expires_in=auth_manager.settings.refresh_token_expire_days * 24 * 60 * 60,
        )

    except AuthenticationError as e:
        logger.error(f"MFA verification failed for user {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@router.post("/refresh", response_model=TokenPair)
@auth_rate_limit
async def refresh_access_token(
    request: Request,
    refresh_request: RefreshTokenRequest,
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> TokenPair:
    """
    Refresh access token using a valid refresh token.

    Args:
        request: FastAPI request object
        refresh_request: Refresh token request data
        auth_manager: Authentication manager instance

    Returns:
        TokenPair: New access token and refresh token

    Raises:
        HTTPException: If refresh token is invalid or refresh is disabled
    """
    if not auth_manager.settings.enable_refresh_tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh tokens are disabled",
        )

    try:
        access_token, new_refresh_token = await auth_manager.refresh_access_token(
            refresh_request.refresh_token
        )

        logger.info("Access token refreshed successfully")

        return TokenPair(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=auth_manager.settings.jwt_expire_minutes * 60,
            refresh_expires_in=auth_manager.settings.refresh_token_expire_days * 24 * 60 * 60,
        )

    except InvalidTokenError as e:
        logger.warning(f"Refresh token invalid: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except AuthenticationError as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
        ) from e


@router.post("/revoke", status_code=204)
@auth_rate_limit
async def revoke_refresh_token(
    request: Request,
    refresh_request: RefreshTokenRequest,
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> None:
    """
    Revoke a refresh token.

    Args:
        request: FastAPI request object
        refresh_request: Refresh token to revoke
        auth_manager: Authentication manager instance

    Raises:
        HTTPException: If refresh tokens are disabled
    """
    if not auth_manager.settings.enable_refresh_tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh tokens are disabled",
        )

    try:
        revoked = await auth_manager.revoke_refresh_token(refresh_request.refresh_token)
        if revoked:
            logger.info("Refresh token revoked successfully")
        else:
            logger.warning("Refresh token not found for revocation")
    except Exception as e:
        logger.error(f"Failed to revoke refresh token: {e}")
        # Don't raise an error - revocation should be idempotent


@router.post("/magic-link", response_model=MagicLinkResponse)
@magic_link_rate_limit
async def send_magic_link(
    request: Request,
    magic_request: MagicLinkRequest,
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> MagicLinkResponse:
    """
    Send magic link for passwordless authentication (multi-user mode).

    Args:
        request: Magic link request with email and optional redirect URL
        auth_manager: Authentication manager instance

    Returns:
        MagicLinkResponse: Confirmation message and metadata

    Raises:
        HTTPException: If magic links are not enabled or email sending fails
    """
    if auth_manager.auth_mode == AuthMode.NONE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication is disabled"
        )

    if not auth_manager.settings.enable_magic_links:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Magic links are not enabled",
        )

    try:
        success = await auth_manager.send_magic_link_email(
            email=magic_request.email,
            expires_minutes=auth_manager.settings.magic_link_expire_minutes,
            redirect_url=magic_request.redirect_url,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send magic link email",
            )

        logger.info(f"Magic link sent to: {magic_request.email}")

        return MagicLinkResponse(
            message="Magic link sent successfully",
            email=magic_request.email,
            expires_in_minutes=auth_manager.settings.magic_link_expire_minutes,
        )

    except Exception as e:
        logger.error(f"Failed to send magic link to {magic_request.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send magic link",
        ) from e


@router.get("/magic", response_model=Token)
async def verify_magic_link(
    token: str, auth_manager: Annotated[AuthManager, Depends(get_auth_manager)]
) -> Token:
    """
    Verify magic link token and return access token.

    Args:
        token: Magic link token from URL parameter
        auth_manager: Authentication manager instance

    Returns:
        Token: JWT access token for authenticated user

    Raises:
        HTTPException: If magic link token is invalid or expired
    """
    if auth_manager.auth_mode == AuthMode.NONE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication is disabled"
        )

    try:
        user_info = await auth_manager.validate_magic_link(token)

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired magic link",
            )

        # Generate new access token for the user
        access_token = auth_manager.generate_token(
            user_id=user_info["user_id"],
            username=user_info["email"],
            additional_claims={
                "email": user_info["email"],
                "role": "user",  # Default role for magic link users
                "mode": "multi-user",
            },
        )

        logger.info(f"Successful magic link authentication for: {user_info['email']}")

        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=auth_manager.settings.jwt_expire_minutes * 60,
        )

    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic link",
        ) from None
    except Exception as e:
        logger.error(f"Magic link verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Magic link verification failed",
        ) from e


@router.get("/me", response_model=UserInfo)
async def get_user_profile(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> UserInfo:
    """
    Get current user profile information.

    Args:
        current_user: Current authenticated user

    Returns:
        UserInfo: Current user profile data
    """
    return current_user


@router.get("/status", response_model=AuthStatus)
async def get_auth_status(
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> AuthStatus:
    """
    Get authentication system status and configuration.

    Args:
        auth_manager: Authentication manager instance

    Returns:
        AuthStatus: Authentication system status
    """
    return AuthStatus(
        enabled=auth_manager.settings.enabled,
        mode=auth_manager.auth_mode.value,
        jwt_available=bool(auth_manager.settings.secret_key),
        magic_links_enabled=auth_manager.settings.enable_magic_links,
        oauth_enabled=auth_manager.settings.enable_oauth,
    )


@router.post("/logout")
async def logout(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, str]:
    """
    Logout current user and revoke all refresh tokens.

    Args:
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        dict[str, str]: Logout confirmation message
    """
    logger.info(f"User logout: {current_user.user_id}")

    # Revoke all refresh tokens for the user if refresh tokens are enabled
    if auth_manager.settings.enable_refresh_tokens:
        revoked_count = await auth_manager.revoke_all_user_refresh_tokens(current_user.user_id)
        if revoked_count > 0:
            logger.info(f"Revoked {revoked_count} refresh tokens for user {current_user.user_id}")

    return {
        "message": "Logged out successfully",
        "detail": "All tokens have been revoked",
    }


# User invitation endpoints
@router.post("/invitation/send", response_model=UserInvitationResponse)
async def send_user_invitation(
    request: UserInvitationRequest,
    current_admin: Annotated[UserInfo, Depends(get_current_admin_user)],
    invitation_service: Annotated[UserInvitationService, Depends(get_user_invitation_service)],
) -> UserInvitationResponse:
    """
    Send a user invitation (admin only).

    Args:
        request: Invitation request details
        current_admin: Current admin user
        invitation_service: User invitation service instance

    Returns:
        UserInvitationResponse: Created invitation details

    Raises:
        HTTPException: If invitation creation fails
    """
    try:
        invitation = await invitation_service.create_invitation(
            email=request.email,
            invited_by_admin=current_admin.user_id,
            role=request.role or "user",
            message=request.message,
        )

        logger.info(f"Admin {current_admin.user_id} sent invitation to {request.email}")
        return invitation

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to create invitation for {request.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation",
        ) from e


@router.get("/invitation/accept", response_model=Token)
async def accept_user_invitation(
    token: str,
    invitation_service: Annotated[UserInvitationService, Depends(get_user_invitation_service)],
) -> Token:
    """
    Accept a user invitation and get authentication token.

    Args:
        token: Invitation token from URL parameter
        invitation_service: User invitation service instance

    Returns:
        Token: JWT access token for the new user

    Raises:
        HTTPException: If invitation token is invalid or expired
    """
    try:
        magic_token = await invitation_service.accept_invitation(token)

        if not magic_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired invitation",
            )

        # Validate the magic token and get user info
        from backend.core.dependencies import get_auth_manager

        auth_manager = get_auth_manager()
        user_info = await auth_manager.validate_magic_link(magic_token)

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to authenticate after invitation acceptance",
            )

        # Generate final access token
        access_token = auth_manager.generate_token(
            user_id=user_info["user_id"],
            username=user_info["email"],
            additional_claims={
                "email": user_info["email"],
                "role": "user",  # Default role for invited users
                "mode": "multi-user",
            },
        )

        logger.info(f"User invitation accepted and authenticated: {user_info['email']}")

        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=auth_manager.settings.jwt_expire_minutes * 60,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to accept invitation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation",
        ) from e


# Admin endpoints
@router.get("/admin/users", dependencies=[Depends(get_current_admin_user)])
async def list_users() -> dict[str, Any]:
    """
    List all users (admin only).

    Returns:
        dict[str, Any]: List of users (placeholder for future implementation)

    Note:
        This endpoint is a placeholder for future multi-user functionality
        when database-backed user management is implemented.
    """
    return {"message": "User management not yet implemented", "users": [], "total": 0}


@router.get("/admin/invitations", dependencies=[Depends(get_current_admin_user)])
async def list_invitations(
    invitation_service: Annotated[UserInvitationService, Depends(get_user_invitation_service)],
    include_expired: bool = False,
    include_used: bool = False,
) -> dict[str, Any]:
    """
    List user invitations (admin only).

    Args:
        include_expired: Include expired invitations
        include_used: Include used invitations
        invitation_service: User invitation service instance

    Returns:
        dict[str, Any]: List of invitations and statistics
    """
    invitations = await invitation_service.list_invitations(include_expired, include_used)
    stats = await invitation_service.get_invitation_stats()

    return {
        "invitations": [inv.model_dump() for inv in invitations],
        "total": len(invitations),
        "stats": stats,
    }


@router.delete("/admin/invitations/{invitation_id}", dependencies=[Depends(get_current_admin_user)])
async def revoke_invitation(
    invitation_id: str,
    invitation_service: Annotated[UserInvitationService, Depends(get_user_invitation_service)],
) -> dict[str, str]:
    """
    Revoke a user invitation (admin only).

    Args:
        invitation_id: ID of invitation to revoke
        invitation_service: User invitation service instance

    Returns:
        dict[str, str]: Revocation confirmation

    Raises:
        HTTPException: If invitation not found
    """
    success = await invitation_service.revoke_invitation(invitation_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    return {"message": "Invitation revoked successfully"}


@router.get("/admin/credentials", response_model=AdminCredentials)
@admin_api_rate_limit
async def get_admin_credentials(
    request: Request,
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> AdminCredentials:
    """
    Get auto-generated admin credentials (one-time display only).

    This endpoint returns auto-generated admin credentials only once for security.
    After calling this endpoint, the credentials are cleared from memory.

    Args:
        auth_manager: Authentication manager instance

    Returns:
        AdminCredentials: Auto-generated admin credentials

    Raises:
        HTTPException: If no credentials available or not in single-user mode
    """
    if auth_manager.auth_mode != AuthMode.SINGLE_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin credentials only available in single-user mode",
        )

    credentials = await auth_manager.get_generated_credentials()

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No auto-generated credentials available or already retrieved",
        )

    logger.info("Auto-generated admin credentials retrieved via API")

    return AdminCredentials(**credentials)


@router.get("/admin/stats", dependencies=[Depends(get_current_admin_user)])
async def get_auth_stats(
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
    invitation_service: Annotated[UserInvitationService, Depends(get_user_invitation_service)],
) -> dict[str, Any]:
    """
    Get detailed authentication statistics (admin only).

    Args:
        auth_manager: Authentication manager instance
        invitation_service: User invitation service instance

    Returns:
        dict[str, Any]: Detailed authentication statistics
    """
    auth_stats = await auth_manager.get_stats()
    invitation_stats = await invitation_service.get_invitation_stats()

    return {
        "authentication": auth_stats,
        "invitations": invitation_stats,
        "endpoints": {
            "login_enabled": auth_manager.auth_mode == AuthMode.SINGLE_USER,
            "magic_links_enabled": auth_manager.settings.enable_magic_links,
            "oauth_enabled": auth_manager.settings.enable_oauth,
            "invitations_enabled": auth_manager.auth_mode == AuthMode.MULTI_USER,
        },
    }


# Account lockout management endpoints


class LockoutStatus(BaseModel):
    """Account lockout status response model."""

    username: str
    is_locked: bool
    lockout_until: str | None = None
    failed_attempts: int
    escalation_level: int
    last_attempt: str | None = None
    consecutive_successful_logins: int
    lockout_enabled: bool
    max_failed_attempts: int
    lockout_duration_minutes: int


class UnlockAccountRequest(BaseModel):
    """Account unlock request model."""

    username: str


@router.get(
    "/lockout/status/{username}",
    response_model=LockoutStatus,
    dependencies=[Depends(get_current_admin_user)],
)
async def get_user_lockout_status(
    username: str,
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> LockoutStatus:
    """
    Get lockout status for a specific user (admin only).

    Args:
        username: Username to check lockout status for
        auth_manager: Authentication manager instance

    Returns:
        LockoutStatus: Detailed lockout status for the user
    """
    if not auth_manager.settings.enable_account_lockout:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account lockout is disabled",
        )

    status_data = await auth_manager.get_lockout_status(username)
    return LockoutStatus(**status_data)


@router.get("/lockout/status", dependencies=[Depends(get_current_admin_user)])
async def get_all_lockout_status(
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> list[LockoutStatus]:
    """
    Get lockout status for all tracked users (admin only).

    Args:
        auth_manager: Authentication manager instance

    Returns:
        list[LockoutStatus]: List of lockout status for all users
    """
    if not auth_manager.settings.enable_account_lockout:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account lockout is disabled",
        )

    all_status = await auth_manager.get_all_lockout_status()
    return [LockoutStatus(**status_data) for status_data in all_status]


@router.post("/lockout/unlock", dependencies=[Depends(get_current_admin_user)])
async def unlock_user_account(
    unlock_request: UnlockAccountRequest,
    current_admin: Annotated[UserInfo, Depends(get_current_admin_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, str]:
    """
    Manually unlock a user account (admin only).

    Args:
        unlock_request: Account unlock request
        current_admin: Current admin user
        auth_manager: Authentication manager instance

    Returns:
        dict[str, str]: Unlock confirmation message

    Raises:
        HTTPException: If lockout is disabled or account not locked
    """
    if not auth_manager.settings.enable_account_lockout:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account lockout is disabled",
        )

    was_unlocked = await auth_manager.unlock_account(unlock_request.username, current_admin.user_id)

    if was_unlocked:
        logger.info(
            f"Admin {current_admin.user_id} unlocked account for user {unlock_request.username}"
        )
        return {
            "message": f"Account unlocked successfully for user {unlock_request.username}",
            "unlocked_by": current_admin.user_id,
        }
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No active lockout found for user {unlock_request.username}",
    )


# Multi-Factor Authentication (MFA) endpoints


@router.post("/mfa/setup")
async def setup_mfa(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> MFASecretResponse:
    """
    Set up MFA for the current user.

    Args:
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        MFASecretResponse: MFA setup information including QR code

    Raises:
        HTTPException: If MFA is not available or already enabled
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available - missing dependencies or disabled",
        )

    # Check if MFA is already enabled
    mfa_status = await auth_manager.get_mfa_status(current_user.user_id)
    if mfa_status["mfa_enabled"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user",
        )

    try:
        mfa_data = await auth_manager.generate_mfa_secret(current_user.user_id)
        logger.info(f"MFA setup initiated for user {current_user.user_id}")

        return MFASecretResponse(**mfa_data)
    except AuthenticationError as e:
        logger.error(f"Failed to set up MFA for user {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set up MFA: {e}",
        ) from e


@router.post("/mfa/verify-setup")
async def verify_mfa_setup(
    verification_request: MFAVerificationRequest,
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, str]:
    """
    Verify MFA setup by validating a TOTP code.

    Args:
        verification_request: MFA verification request with TOTP code
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        dict[str, str]: Verification confirmation message

    Raises:
        HTTPException: If verification fails or MFA not available
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    try:
        success = await auth_manager.verify_mfa_setup(
            current_user.user_id, verification_request.totp_code
        )

        if success:
            logger.info(f"MFA successfully enabled for user {current_user.user_id}")
            return {
                "message": "MFA has been successfully enabled for your account",
                "status": "enabled",
            }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code. Please check your authenticator app and try again.",
        )
    except AuthenticationError as e:
        logger.error(f"MFA verification failed for user {current_user.user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/mfa/verify")
async def verify_mfa_code(
    verification_request: MFAVerificationRequest,
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, str]:
    """
    Verify an MFA code for authentication.

    Args:
        verification_request: MFA verification request with TOTP or backup code
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        dict[str, str]: Verification confirmation message

    Raises:
        HTTPException: If verification fails or MFA not available
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    try:
        success = await auth_manager.verify_mfa_code(current_user.user_id, verification_request.totp_code)

        if success:
            logger.info(f"MFA code verified for user {current_user.user_id}")
            return {"message": "MFA code verified successfully", "status": "verified"}
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code. Please check your authenticator app or backup codes and try again.",
        )
    except AuthenticationError as e:
        logger.error(f"MFA verification failed for user {current_user.user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/mfa/status")
async def get_mfa_status(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> MFAStatus:
    """
    Get MFA status for the current user.

    Args:
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        MFAStatus: Current MFA status

    Raises:
        HTTPException: If MFA is not available
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    mfa_status = await auth_manager.get_mfa_status(current_user.user_id)
    return MFAStatus(**mfa_status)


@router.get("/mfa/backup-codes")
async def get_backup_codes(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> BackupCodesResponse:
    """
    Get backup codes for the current user (one-time display).

    Args:
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        BackupCodesResponse: Backup codes with warning

    Raises:
        HTTPException: If MFA not available or not enabled
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    backup_codes = await auth_manager.get_backup_codes(current_user.user_id)

    if backup_codes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MFA is not set up for this user",
        )

    logger.info(f"Backup codes retrieved for user {current_user.user_id}")
    return BackupCodesResponse(
        backup_codes=backup_codes,
        warning="Save these backup codes immediately! They will not be displayed again."
    )


@router.post("/mfa/regenerate-backup-codes")
async def regenerate_backup_codes(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> BackupCodesResponse:
    """
    Regenerate backup codes for the current user.

    Args:
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        BackupCodesResponse: New backup codes with warning

    Raises:
        HTTPException: If MFA not available or not enabled
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    new_backup_codes = await auth_manager.regenerate_backup_codes(current_user.user_id)

    if new_backup_codes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MFA is not set up for this user",
        )

    logger.info(f"Backup codes regenerated for user {current_user.user_id}")
    return BackupCodesResponse(
        backup_codes=new_backup_codes,
        warning="Save these backup codes immediately! They will not be displayed again."
    )


@router.delete("/mfa/disable")
async def disable_mfa(
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, str]:
    """
    Disable MFA for the current user.

    Args:
        current_user: Current authenticated user
        auth_manager: Authentication manager instance

    Returns:
        dict[str, str]: Disable confirmation message

    Raises:
        HTTPException: If MFA not available or not enabled
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    was_disabled = await auth_manager.disable_mfa(current_user.user_id, current_user.user_id)

    if was_disabled:
        logger.info(f"MFA disabled for user {current_user.user_id}")
        return {
            "message": "MFA has been successfully disabled for your account",
            "status": "disabled",
        }
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="MFA is not enabled for this user",
    )


# Admin MFA management endpoints


@router.get("/admin/mfa/status", dependencies=[Depends(get_current_admin_user)])
async def get_all_mfa_status(
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> list[MFAStatus]:
    """
    Get MFA status for all users (admin only).

    Args:
        auth_manager: Authentication manager instance

    Returns:
        list[MFAStatus]: MFA status for all users

    Raises:
        HTTPException: If MFA is not available
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    all_status = await auth_manager.get_all_mfa_status()
    return [MFAStatus(**status_data) for status_data in all_status]


class AdminMFADisableRequest(BaseModel):
    """Admin MFA disable request model."""

    user_id: str


@router.post("/admin/mfa/disable", dependencies=[Depends(get_current_admin_user)])
async def admin_disable_mfa(
    disable_request: AdminMFADisableRequest,
    current_admin: Annotated[UserInfo, Depends(get_current_admin_user)],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, str]:
    """
    Disable MFA for a specific user (admin only).

    Args:
        disable_request: MFA disable request
        current_admin: Current admin user
        auth_manager: Authentication manager instance

    Returns:
        dict[str, str]: Disable confirmation message

    Raises:
        HTTPException: If MFA not available or not enabled for user
    """
    if not auth_manager.is_mfa_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA is not available",
        )

    was_disabled = await auth_manager.disable_mfa(disable_request.user_id, current_admin.user_id)

    if was_disabled:
        logger.info(
            f"Admin {current_admin.user_id} disabled MFA for user {disable_request.user_id}"
        )
        return {
            "message": f"MFA has been successfully disabled for user {disable_request.user_id}",
            "disabled_by": current_admin.user_id,
        }
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"MFA is not enabled for user {disable_request.user_id}",
    )


# Secure Authentication Endpoints with HttpOnly Cookies

@router.post("/secure/login", response_model=dict)
@auth_rate_limit
async def secure_login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, Any]:
    """
    Secure login with HttpOnly cookie token storage.

    Args:
        form_data: Login form data (username and password)
        auth_manager: Authentication manager instance

    Returns:
        Login success response with secure cookies set

    Raises:
        HTTPException: If authentication fails
    """
    from backend.services.secure_token_service import SecureTokenService

    try:
        # Authenticate user using existing auth manager
        if auth_manager.auth_mode == AuthMode.NONE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authentication is disabled"
            )

        if auth_manager.auth_mode != AuthMode.SINGLE_USER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Secure login only available in single-user mode"
            )

        # Validate credentials
        user_info = await auth_manager.authenticate_admin(
            form_data.username,
            form_data.password
        )

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Create secure token service
        token_service = SecureTokenService(auth_manager)

        # Issue token pair
        token_pair = await token_service.issue_token_pair(
            user_id=user_info["user_id"],
            username=user_info["username"],
            additional_claims={
                "mode": "single-user",
                "admin": True,
                "secure_auth": True
            }
        )

        # Create response
        response_data = {
            "message": "Login successful",
            "user": {
                "user_id": user_info["user_id"],
                "username": user_info["username"],
                "admin": True
            },
            "token_type": token_pair.token_type,
            "expires_in": token_pair.access_token_expires_in,
            "secure_cookies": True
        }

        from fastapi import Response
        response = Response(
            content=json.dumps(response_data),
            media_type="application/json"
        )

        # Set secure cookies
        token_service.set_secure_cookies(response, token_pair)

        logger.info(f"Secure login successful for user: {user_info['username']}")
        return response

    except AccountLockedError as e:
        logger.warning(f"Login attempt for locked account: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=str(e)
        ) from e
    except AuthenticationError as e:
        logger.warning(f"Authentication failed for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        ) from e


@router.post("/secure/refresh")
async def secure_refresh(
    request: Request,
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, Any]:
    """
    Refresh access token using HttpOnly refresh token cookie.

    Args:
        request: HTTP request with refresh token cookie
        auth_manager: Authentication manager instance

    Returns:
        Refresh success response with new tokens

    Raises:
        HTTPException: If refresh token is invalid
    """
    from backend.services.secure_token_service import SecureTokenService

    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        # Create token service
        token_service = SecureTokenService(auth_manager)

        # Refresh the access token
        refresh_result = await token_service.refresh_access_token(refresh_token)

        # Create response
        response_data = {
            "message": "Token refreshed successfully",
            "token_type": "Bearer",
            "expires_in": refresh_result.access_token_expires_in,
            "refresh_rotated": refresh_result.refresh_rotated
        }

        from fastapi import Response
        response = Response(
            content=json.dumps(response_data),
            media_type="application/json"
        )

        # Set new access token in header
        response.headers["X-Access-Token"] = refresh_result.access_token
        response.headers["X-Token-Type"] = "Bearer"
        response.headers["X-Expires-In"] = str(refresh_result.access_token_expires_in)

        # Update refresh token cookie if rotated
        if refresh_result.refresh_rotated and refresh_result.new_refresh_token:
            token_service.set_refresh_cookie(response, refresh_result.new_refresh_token)

        logger.info("Token refresh successful")
        return response

    except InvalidTokenError as e:
        logger.warning(f"Invalid refresh token provided: {e}")
        # Clear invalid refresh token cookie
        from fastapi import Response
        error_response = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )

        # Would need to create custom response to clear cookie
        raise error_response


@router.post("/secure/logout")
async def secure_logout(
    request: Request,
    auth_manager: Annotated[AuthManager, Depends(get_auth_manager)],
) -> dict[str, str]:
    """
    Secure logout with cookie cleanup and token revocation.

    Args:
        request: HTTP request
        auth_manager: Authentication manager instance

    Returns:
        Logout confirmation message
    """
    from backend.services.secure_token_service import SecureTokenService

    # Get refresh token for revocation
    refresh_token = request.cookies.get("refresh_token")

    # Get user info from access token if available
    auth_header = request.headers.get("Authorization")
    user_id = None

    if auth_header:
        token_service = SecureTokenService(auth_manager)
        access_token = token_service.extract_access_token(auth_header)
        if access_token:
            try:
                token_payload = auth_manager.validate_token(access_token)
                user_id = token_payload.get("sub")
            except InvalidTokenError:
                pass  # Token invalid, continue with logout

    # Revoke tokens if we have user info
    if user_id:
        try:
            token_service = SecureTokenService(auth_manager)
            await token_service.revoke_all_tokens(user_id)
            logger.info(f"Revoked all tokens for user: {user_id}")
        except Exception as e:
            logger.warning(f"Failed to revoke tokens during logout: {e}")

    # Create response with cleared cookies
    response_data = {
        "message": "Logged out successfully",
        "secure_cookies_cleared": True
    }

    from fastapi import Response
    response = Response(
        content=json.dumps(response_data),
        media_type="application/json"
    )

    # Clear authentication cookies
    if refresh_token:
        token_service = SecureTokenService(auth_manager)
        token_service.clear_auth_cookies(response)

    logger.info("Secure logout completed")
    return response
