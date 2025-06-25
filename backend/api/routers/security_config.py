"""
Security Configuration API Router

Provides endpoints for managing security configurations including:
- PIN policies
- Rate limiting policies
- Authentication requirements
- Audit policies
- Network security policies

Designed for RV deployments with admin-only access.
"""

import logging
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette import status

from backend.core.dependencies import (
    get_authenticated_admin,
    get_security_audit_service,
    get_security_config_service,
)
from backend.services.security_config_service import (
    AuditPolicy,
    AuthenticationPolicy,
    NetworkSecurityPolicy,
    PINSecurityPolicy,
    RateLimitingPolicy,
    SecurityConfigService,
    SecurityConfiguration,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security/config", tags=["security-configuration"])


# Request/Response Models


class SecurityModeUpdateRequest(BaseModel):
    """Security mode update request."""

    mode: str = Field(..., description="Security mode to apply")
    reason: str = Field("", description="Reason for mode change")


class SecurityModeUpdateResponse(BaseModel):
    """Security mode update response."""

    success: bool = Field(..., description="Whether mode update succeeded")
    previous_mode: str = Field(..., description="Previous security mode")
    new_mode: str = Field(..., description="New security mode")
    updated_by: str = Field(..., description="Who updated the mode")
    message: str = Field(..., description="Update status message")


class PolicyUpdateRequest(BaseModel):
    """Policy update request."""

    policy_type: str = Field(..., description="Type of policy to update")
    policy_data: dict[str, Any] = Field(..., description="Policy configuration data")
    reason: str = Field("", description="Reason for policy change")


class ValidationResponse(BaseModel):
    """Configuration validation response."""

    valid: bool = Field(..., description="Whether configuration is valid")
    issues: list[str] = Field(..., description="Configuration issues found")
    recommendations: list[str] = Field(..., description="Configuration recommendations")
    last_validated: str = Field(..., description="Last validation timestamp")
    config_version: str = Field(..., description="Configuration version")
    security_mode: str = Field(..., description="Current security mode")


# Configuration Endpoints


@router.get("/", response_model=dict[str, Any])
async def get_security_config(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Get complete security configuration (Admin only).

    Returns the full security configuration including all policies
    and current settings.
    """
    try:
        config = await config_service.get_config()

        # Log access to security configuration
        if security_audit:
            await security_audit.log_security_event(
                event_type="configuration_accessed",
                severity="medium",
                user_id=admin_user["user_id"],
                endpoint="/api/security/config",
                details={
                    "config_version": config.config_version,
                    "security_mode": config.security_mode,
                },
            )

        logger.info(f"Security configuration accessed by admin {admin_user['user_id']}")

        return config.model_dump()

    except Exception as e:
        logger.error(f"Error getting security configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving security configuration",
        ) from e


@router.get("/summary", response_model=dict[str, Any])
async def get_security_summary(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Get security configuration summary (Admin only).

    Returns a condensed view of security settings and validation status.
    """
    try:
        summary = await config_service.get_security_summary()

        logger.info(f"Security summary accessed by admin {admin_user['user_id']}")

        return summary

    except Exception as e:
        logger.error(f"Error getting security summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving security summary",
        ) from e


@router.put("/", response_model=dict[str, Any])
async def update_security_config(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    config: SecurityConfiguration,
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Update complete security configuration (Admin only).

    Replaces the entire security configuration with the provided data.
    Use with caution as this affects all security policies.
    """
    try:
        admin_id = admin_user["user_id"]

        # Save the new configuration
        success = await config_service.save_config(config, admin_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save security configuration",
            )

        # Enhanced security audit for configuration changes
        if security_audit:
            await security_audit.log_security_event(
                event_type="configuration_changed",
                severity="high",
                user_id=admin_id,
                endpoint="/api/security/config",
                details={
                    "config_version": config.config_version,
                    "security_mode": config.security_mode,
                    "change_type": "full_config_update",
                },
            )

        # Validate the new configuration
        validation = config_service.validate_configuration()

        logger.warning(f"Security configuration updated by admin {admin_id}")

        return {
            "success": True,
            "message": "Security configuration updated successfully",
            "config_version": config.config_version,
            "updated_by": admin_id,
            "validation": validation,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating security configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating security configuration",
        ) from e


@router.post("/mode", response_model=SecurityModeUpdateResponse)
async def update_security_mode(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    mode_request: SecurityModeUpdateRequest,
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> SecurityModeUpdateResponse:
    """
    Update security mode (Admin only).

    Changes the overall security mode which affects multiple policies.
    Available modes: minimal, standard, strict, paranoid.
    """
    try:
        admin_id = admin_user["user_id"]

        # Get current mode
        current_config = await config_service.get_config()
        previous_mode = current_config.security_mode

        # Update security mode
        success = await config_service.update_security_mode(mode_request.mode, admin_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update security mode",
            )

        # Enhanced security audit for mode changes
        if security_audit:
            await security_audit.log_security_event(
                event_type="security_mode_changed",
                severity="critical",
                user_id=admin_id,
                endpoint="/api/security/config/mode",
                details={
                    "previous_mode": previous_mode,
                    "new_mode": mode_request.mode,
                    "reason": mode_request.reason,
                },
            )

        logger.critical(
            f"Security mode changed from {previous_mode} to {mode_request.mode} by admin {admin_id}"
        )

        return SecurityModeUpdateResponse(
            success=True,
            previous_mode=previous_mode,
            new_mode=mode_request.mode,
            updated_by=admin_id,
            message=f"Security mode updated to {mode_request.mode}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating security mode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating security mode"
        ) from e


@router.post("/policies/{policy_type}")
async def update_policy(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    policy_type: str,
    policy_request: PolicyUpdateRequest,
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Update a specific security policy (Admin only).

    Updates individual policies without affecting the entire configuration.
    Supported policy types: pin, rate_limiting, authentication, audit, network.
    """
    try:
        admin_id = admin_user["user_id"]

        # Get current configuration
        config = await config_service.get_config()

        # Update specific policy based on type
        if policy_type == "pin":
            config.pin_policy = PINSecurityPolicy(**policy_request.policy_data)
        elif policy_type == "rate_limiting":
            config.rate_limiting = RateLimitingPolicy(**policy_request.policy_data)
        elif policy_type == "authentication":
            config.authentication = AuthenticationPolicy(**policy_request.policy_data)
        elif policy_type == "audit":
            config.audit = AuditPolicy(**policy_request.policy_data)
        elif policy_type == "network":
            config.network = NetworkSecurityPolicy(**policy_request.policy_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown policy type: {policy_type}",
            )

        # Save updated configuration
        success = await config_service.save_config(config, admin_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save {policy_type} policy",
            )

        # Enhanced security audit for policy changes
        if security_audit:
            await security_audit.log_security_event(
                event_type="policy_updated",
                severity="high",
                user_id=admin_id,
                endpoint=f"/api/security/config/policies/{policy_type}",
                details={
                    "policy_type": policy_type,
                    "reason": policy_request.reason,
                    "config_version": config.config_version,
                },
            )

        # Validate the updated configuration
        validation = await config_service.validate_configuration()

        logger.warning(f"Security policy {policy_type} updated by admin {admin_id}")

        return {
            "success": True,
            "message": f"{policy_type} policy updated successfully",
            "policy_type": policy_type,
            "updated_by": admin_id,
            "validation": validation,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating {policy_type} policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating {policy_type} policy",
        ) from e


@router.get("/validate", response_model=ValidationResponse)
async def validate_config(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> ValidationResponse:
    """
    Validate current security configuration (Admin only).

    Checks the current configuration for issues and provides recommendations.
    """
    try:
        validation = await config_service.validate_configuration()

        logger.info(f"Security configuration validated by admin {admin_user['user_id']}")

        # Get current config for additional info
        config = await config_service.get_config()

        return ValidationResponse(
            valid=validation.get("valid", False),
            issues=validation.get("issues", []),
            recommendations=validation.get("recommendations", []),
            last_validated=validation.get("last_validated", ""),
            config_version=config.config_version,
            security_mode=config.security_mode,
        )

    except Exception as e:
        logger.error(f"Error validating security configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating security configuration",
        ) from e


@router.post("/reload")
async def reload_config(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Reload security configuration from disk (Admin only).

    Forces a reload of the configuration file, useful after manual edits.
    """
    try:
        admin_id = admin_user["user_id"]

        # Force reload from disk
        config = await config_service.get_config(force_reload=True)

        # Enhanced security audit for config reload
        if security_audit:
            await security_audit.log_security_event(
                event_type="configuration_reloaded",
                severity="medium",
                user_id=admin_id,
                endpoint="/api/security/config/reload",
                details={
                    "config_version": config.config_version,
                    "security_mode": config.security_mode,
                },
            )

        logger.info(f"Security configuration reloaded by admin {admin_id}")

        return {
            "success": True,
            "message": "Security configuration reloaded successfully",
            "config_version": config.config_version,
            "security_mode": config.security_mode,
            "reloaded_by": admin_id,
        }

    except Exception as e:
        logger.error(f"Error reloading security configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error reloading security configuration",
        ) from e


# Policy-Specific Endpoints


@router.get("/policies/pin")
async def get_pin_policy(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """Get PIN security policy configuration (Admin only)."""
    try:
        pin_config = await config_service.get_pin_config()

        return {"pin_policy": pin_config}

    except Exception as e:
        logger.error(f"Error getting PIN policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving PIN policy"
        ) from e


@router.get("/policies/rate-limiting")
async def get_rate_limiting_policy(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """Get rate limiting policy configuration (Admin only)."""
    try:
        rate_config = await config_service.get_rate_limit_config()

        return {"rate_limiting_policy": rate_config}

    except Exception as e:
        logger.error(f"Error getting rate limiting policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving rate limiting policy",
        ) from e


@router.get("/policies/authentication")
async def get_authentication_policy(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """Get authentication policy configuration (Admin only)."""
    try:
        auth_config = await config_service.get_auth_config()

        return {"authentication_policy": auth_config}

    except Exception as e:
        logger.error(f"Error getting authentication policy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving authentication policy",
        ) from e


@router.get("/caddy/rate-limits")
async def get_caddy_rate_limits(
    config_service: Annotated[SecurityConfigService, Depends(get_security_config_service)],
    admin_user: Annotated[dict, Depends(get_authenticated_admin)],
) -> dict[str, Any]:
    """
    Get Caddy-compatible rate limit configuration (Admin only).

    Returns the IP-based rate limits that should be configured in Caddy.
    This is separate from the user-aware rate limits handled in FastAPI.
    """
    try:
        caddy_limits = await config_service.get_caddy_rate_limits()
        return {
            "caddy_rate_limits": caddy_limits,
            "usage": "Configure these limits in your Caddyfile for edge-layer IP-based protection",
        }

    except Exception as e:
        logger.error(f"Error getting Caddy rate limits: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving Caddy rate limit configuration",
        ) from e
