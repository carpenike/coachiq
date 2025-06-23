"""
Network Security API Router

Provides endpoints for managing network security policies including:
- IP whitelist/blacklist management
- Security event monitoring
- Threat detection and response
- DDoS protection configuration
- Geographic access control

Designed for RV deployments with admin-only access to security controls.
"""

import logging
import time
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette import status

from backend.core.dependencies import create_service_dependency

# Create service dependencies
get_authenticated_admin = lambda: None  # Placeholder
get_security_audit_service = create_service_dependency("security_audit_service")
get_network_security_service_dep = create_service_dependency("network_security_service")
from backend.services.network_security_service import NetworkSecurityService, SecurityEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security/network", tags=["network-security"])


# Request/Response Models


class IPBlockRequest(BaseModel):
    """IP block request model."""

    ip_address: str = Field(..., description="IP address to block")
    duration_seconds: int = Field(
        3600, ge=60, le=86400, description="Block duration in seconds (1 min to 24 hours)"
    )
    reason: str = Field(..., description="Reason for blocking")


class IPUnblockRequest(BaseModel):
    """IP unblock request model."""

    ip_address: str = Field(..., description="IP address to unblock")
    reason: str = Field("manual_unblock", description="Reason for unblocking")


class TrustedIPRequest(BaseModel):
    """Trusted IP request model."""

    ip_address: str = Field(..., description="IP address to add/remove from trusted list")


class SecurityEventQuery(BaseModel):
    """Security event query parameters."""

    event_type: str | None = Field(None, description="Filter by event type")
    client_ip: str | None = Field(None, description="Filter by client IP")
    severity: str | None = Field(None, description="Filter by severity level")
    hours: int = Field(24, ge=1, le=168, description="Look back this many hours")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of events to return")


class SecurityEventResponse(BaseModel):
    """Security event response model."""

    events: list[SecurityEvent] = Field(..., description="List of security events")
    total_count: int = Field(..., description="Total number of matching events")
    query_params: SecurityEventQuery = Field(..., description="Query parameters used")


class IPBlockResponse(BaseModel):
    """IP block response model."""

    success: bool = Field(..., description="Whether operation succeeded")
    ip_address: str = Field(..., description="IP address affected")
    action: str = Field(..., description="Action taken")
    message: str = Field(..., description="Response message")
    expires_at: float | None = Field(None, description="Block expiration timestamp")


class SecuritySummaryResponse(BaseModel):
    """Security summary response model."""

    summary: dict[str, Any] = Field(..., description="Security summary data")
    timestamp: float = Field(..., description="Summary generation timestamp")
    system_status: str = Field(..., description="Overall security system status")


# Security Monitoring Endpoints


@router.get("/events", response_model=SecurityEventResponse)
async def get_security_events(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    query: SecurityEventQuery = Depends(),
    admin_user: dict = Depends(get_authenticated_admin),
) -> SecurityEventResponse:
    """
    Get security events (Admin only).

    Returns filtered security events for monitoring and analysis.
    """
    try:
        # Get events based on query parameters
        import time

        cutoff_time = time.time() - (query.hours * 3600)

        # Filter events
        filtered_events = []
        for event in network_security.security_events:
            if event.timestamp < cutoff_time:
                continue

            if query.event_type and event.event_type != query.event_type:
                continue

            if query.client_ip and event.client_ip != query.client_ip:
                continue

            if query.severity and event.severity != query.severity:
                continue

            filtered_events.append(event)

        # Sort by timestamp (newest first) and limit
        filtered_events.sort(key=lambda x: x.timestamp, reverse=True)
        limited_events = filtered_events[: query.limit]

        logger.info(f"Security events retrieved by admin {admin_user['user_id']}")

        return SecurityEventResponse(
            events=limited_events,
            total_count=len(filtered_events),
            query_params=query,
        )

    except Exception as e:
        logger.error(f"Error retrieving security events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving security events",
        ) from e


@router.get("/summary", response_model=SecuritySummaryResponse)
async def get_security_summary(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    admin_user: dict = Depends(get_authenticated_admin),
) -> SecuritySummaryResponse:
    """
    Get network security summary (Admin only).

    Returns comprehensive security monitoring data.
    """
    try:
        summary = network_security.get_security_summary()

        # Determine overall system status
        active_threats = summary["summary"]["active_threats"]
        recent_events = summary["summary"]["recent_events_24h"]

        if active_threats > 0:
            system_status = "threats_detected"
        elif recent_events > 100:  # High activity threshold
            system_status = "high_activity"
        else:
            system_status = "normal"

        import time

        response = SecuritySummaryResponse(
            summary=summary,
            timestamp=time.time(),
            system_status=system_status,
        )

        logger.info(f"Security summary accessed by admin {admin_user['user_id']}")

        return response

    except Exception as e:
        logger.error(f"Error getting security summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving security summary",
        ) from e


# IP Management Endpoints


@router.post("/block-ip", response_model=IPBlockResponse)
async def block_ip(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    block_request: IPBlockRequest,
    admin_user: dict = Depends(get_authenticated_admin),
) -> IPBlockResponse:
    """
    Block an IP address (Admin only).

    Blocks an IP address for the specified duration with audit logging.
    """
    try:
        admin_id = admin_user["user_id"]

        # Block the IP
        success = await network_security.block_ip(
            block_request.ip_address,
            block_request.duration_seconds,
            f"Manual block by admin {admin_id}: {block_request.reason}",
            auto_block=False,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to block IP address",
            )

        # Enhanced security audit
        if security_audit:
            await security_audit.log_security_event(
                event_type="ip_manual_block",
                severity="high",
                user_id=admin_id,
                endpoint="/api/security/network/block-ip",
                details={
                    "blocked_ip": block_request.ip_address,
                    "duration_seconds": block_request.duration_seconds,
                    "reason": block_request.reason,
                },
            )

        import time

        expires_at = time.time() + block_request.duration_seconds

        logger.warning(f"IP {block_request.ip_address} manually blocked by admin {admin_id}")

        return IPBlockResponse(
            success=True,
            ip_address=block_request.ip_address,
            action="blocked",
            message=f"IP blocked for {block_request.duration_seconds} seconds",
            expires_at=expires_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error blocking IP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error blocking IP address",
        ) from e


@router.post("/unblock-ip", response_model=IPBlockResponse)
async def unblock_ip(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    unblock_request: IPUnblockRequest,
    admin_user: dict = Depends(get_authenticated_admin),
) -> IPBlockResponse:
    """
    Unblock an IP address (Admin only).

    Removes an IP address from the block list with audit logging.
    """
    try:
        admin_id = admin_user["user_id"]

        # Unblock the IP
        success = await network_security.unblock_ip(
            unblock_request.ip_address,
            f"Manual unblock by admin {admin_id}: {unblock_request.reason}",
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="IP address not found in block list",
            )

        # Enhanced security audit
        if security_audit:
            await security_audit.log_security_event(
                event_type="ip_manual_unblock",
                severity="medium",
                user_id=admin_id,
                endpoint="/api/security/network/unblock-ip",
                details={
                    "unblocked_ip": unblock_request.ip_address,
                    "reason": unblock_request.reason,
                },
            )

        logger.info(f"IP {unblock_request.ip_address} manually unblocked by admin {admin_id}")

        return IPBlockResponse(
            success=True,
            ip_address=unblock_request.ip_address,
            action="unblocked",
            message="IP address unblocked successfully",
            expires_at=None,  # No expiration for unblocked IPs
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unblocking IP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error unblocking IP address",
        ) from e


@router.get("/blocked-ips")
async def get_blocked_ips(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    admin_user: dict = Depends(get_authenticated_admin),
) -> dict[str, Any]:
    """
    Get list of blocked IP addresses (Admin only).

    Returns all currently blocked IP addresses with block details.
    """
    try:
        import time

        now = time.time()

        # Get active blocks
        active_blocks = []
        for ip, block_entry in network_security.blocked_ips.items():
            if block_entry.blocked_until > now:
                active_blocks.append(
                    {
                        "ip_address": ip,
                        "reason": block_entry.reason,
                        "blocked_until": block_entry.blocked_until,
                        "expires_in_seconds": int(block_entry.blocked_until - now),
                        "block_count": block_entry.block_count,
                        "first_blocked": block_entry.first_blocked,
                    }
                )

        # Sort by expiration time
        active_blocks.sort(key=lambda x: x["blocked_until"])

        logger.info(f"Blocked IPs list accessed by admin {admin_user['user_id']}")

        return {
            "blocked_ips": active_blocks,
            "total_count": len(active_blocks),
            "timestamp": now,
        }

    except Exception as e:
        logger.error(f"Error getting blocked IPs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving blocked IP addresses",
        ) from e


# Trusted IP Management


@router.post("/trusted-ips/add")
async def add_trusted_ip(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    trusted_request: TrustedIPRequest,
    admin_user: dict = Depends(get_authenticated_admin),
) -> dict[str, Any]:
    """
    Add IP to trusted list (Admin only).

    Adds an IP address to the trusted list, preventing it from being blocked.
    """
    try:
        admin_id = admin_user["user_id"]

        success = await network_security.add_trusted_ip(trusted_request.ip_address)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add IP to trusted list",
            )

        # Enhanced security audit
        if security_audit:
            await security_audit.log_security_event(
                event_type="trusted_ip_added",
                severity="medium",
                user_id=admin_id,
                endpoint="/api/security/network/trusted-ips/add",
                details={"trusted_ip": trusted_request.ip_address},
            )

        logger.info(f"IP {trusted_request.ip_address} added to trusted list by admin {admin_id}")

        return {
            "success": True,
            "ip_address": trusted_request.ip_address,
            "action": "added_to_trusted",
            "message": "IP address added to trusted list",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding trusted IP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error adding IP to trusted list",
        ) from e


@router.post("/trusted-ips/remove")
async def remove_trusted_ip(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    trusted_request: TrustedIPRequest,
    admin_user: dict = Depends(get_authenticated_admin),
) -> dict[str, Any]:
    """
    Remove IP from trusted list (Admin only).

    Removes an IP address from the trusted list.
    """
    try:
        admin_id = admin_user["user_id"]

        success = await network_security.remove_trusted_ip(trusted_request.ip_address)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="IP address not found in trusted list",
            )

        # Enhanced security audit
        if security_audit:
            await security_audit.log_security_event(
                event_type="trusted_ip_removed",
                severity="medium",
                user_id=admin_id,
                endpoint="/api/security/network/trusted-ips/remove",
                details={"untrusted_ip": trusted_request.ip_address},
            )

        logger.info(
            f"IP {trusted_request.ip_address} removed from trusted list by admin {admin_id}"
        )

        return {
            "success": True,
            "ip_address": trusted_request.ip_address,
            "action": "removed_from_trusted",
            "message": "IP address removed from trusted list",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing trusted IP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error removing IP from trusted list",
        ) from e


@router.get("/trusted-ips")
async def get_trusted_ips(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    admin_user: dict = Depends(get_authenticated_admin),
) -> dict[str, Any]:
    """
    Get list of trusted IP addresses (Admin only).

    Returns all IP addresses in the trusted list.
    """
    try:
        trusted_ips = list(network_security.trusted_ips)
        trusted_ips.sort()  # Sort for consistent output

        logger.info(f"Trusted IPs list accessed by admin {admin_user['user_id']}")

        return {
            "trusted_ips": trusted_ips,
            "total_count": len(trusted_ips),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Error getting trusted IPs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving trusted IP addresses",
        ) from e


# System Management


@router.post("/cleanup")
async def cleanup_expired_blocks(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    security_audit: Annotated[Any, Depends(get_security_audit_service)],
    admin_user: dict = Depends(get_authenticated_admin),
) -> dict[str, Any]:
    """
    Clean up expired IP blocks (Admin only).

    Removes expired IP blocks from the system.
    """
    try:
        admin_id = admin_user["user_id"]

        removed_count = await network_security.cleanup_expired_blocks()

        # Enhanced security audit
        if security_audit:
            await security_audit.log_security_event(
                event_type="security_cleanup",
                severity="low",
                user_id=admin_id,
                endpoint="/api/security/network/cleanup",
                details={"removed_blocks": removed_count},
            )

        logger.info(
            f"Security cleanup performed by admin {admin_id}: {removed_count} blocks removed"
        )

        return {
            "success": True,
            "removed_blocks": removed_count,
            "message": f"Cleanup completed: {removed_count} expired blocks removed",
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Error during security cleanup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during security cleanup",
        ) from e


@router.get("/stats")
async def get_security_stats(
    network_security: Annotated[NetworkSecurityService, Depends(get_network_security_service_dep)],
    admin_user: dict = Depends(get_authenticated_admin),
) -> dict[str, Any]:
    """
    Get network security statistics (Admin only).

    Returns detailed security statistics for monitoring.
    """
    try:
        # Get comprehensive stats
        summary = network_security.get_security_summary()

        # Note: Middleware stats are not directly accessible through dependency injection
        # They would need to be exposed through a service if needed
        middleware_stats = {}

        logger.info(f"Security stats accessed by admin {admin_user['user_id']}")

        return {
            "service_stats": summary,
            "middleware_stats": middleware_stats,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Error getting security stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving security statistics",
        ) from e
