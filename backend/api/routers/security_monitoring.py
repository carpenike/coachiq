"""
Security Monitoring API endpoints.

Provides access to CAN bus security monitoring, anomaly detection,
access control lists, and security alerts.
"""

import logging
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.core.dependencies import create_service_dependency

logger = logging.getLogger(__name__)

# Create service dependency for security monitoring
get_security_monitoring_service = create_service_dependency("security_monitoring_service")

router = APIRouter(prefix="/api/security", tags=["security"])


class SecurityStatusResponse(BaseModel):
    """Response for security monitoring status."""

    status: str
    uptime_seconds: float
    stats: dict[str, Any]
    alert_summary: dict[str, Any]
    storm_detector: dict[str, Any]
    acl_status: dict[str, Any]
    rate_limiting: dict[str, Any]


class SecurityAlertResponse(BaseModel):
    """Response for security alerts."""

    alert_id: str
    timestamp: float
    anomaly_type: str
    severity: str
    source_address: int
    source_address_hex: str
    pgn: int | None
    pgn_hex: str | None
    description: str
    evidence: dict[str, Any]
    mitigation_action: str | None


class ACLEntryRequest(BaseModel):
    """Request to add/update ACL entry."""

    source_address: int
    allowed_pgns: list[int] | None = None
    denied_pgns: list[int] | None = None
    description: str = ""


class ACLPolicyRequest(BaseModel):
    """Request to set ACL policy."""

    policy: str  # "allow" or "deny"


@router.get("/status", response_model=SecurityStatusResponse)
async def get_security_status(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> SecurityStatusResponse:
    """
    Get overall security monitoring status.

    Returns:
        Comprehensive security status including statistics and alert summary
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        status = await security_service.get_security_status()
        return SecurityStatusResponse(
            status=status["status"],
            uptime_seconds=status["uptime_seconds"],
            stats=status["stats"],
            alert_summary=status["alert_summary"],
            storm_detector=status["storm_detector"],
            acl_status=status["acl_status"],
            rate_limiting=status["rate_limiting"],
        )
    except Exception as e:
        logger.error(f"Error getting security status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts", response_model=list[SecurityAlertResponse])
async def get_security_alerts(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
    since: float | None = Query(None, description="Timestamp to filter from"),
    severity: str | None = Query(None, description="Filter by severity level"),
    anomaly_type: str | None = Query(None, description="Filter by anomaly type"),
    limit: int = Query(100, description="Maximum number of alerts to return"),
) -> list[SecurityAlertResponse]:
    """
    Get security alerts with optional filtering.

    Args:
        since: Timestamp to filter alerts from
        severity: Filter by severity (low, medium, high, critical)
        anomaly_type: Filter by anomaly type
        limit: Maximum number of alerts to return

    Returns:
        List of security alerts matching criteria
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        # Convert string enums to actual enum values if provided
        severity_enum = None
        if severity:
            from backend.integrations.can.anomaly_detector import SeverityLevel

            try:
                severity_enum = SeverityLevel(severity.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

        anomaly_type_enum = None
        if anomaly_type:
            from backend.integrations.can.anomaly_detector import AnomalyType

            try:
                anomaly_type_enum = AnomalyType(anomaly_type.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid anomaly type: {anomaly_type}")

        alerts = await security_service.get_alerts(
            since=since, severity=severity_enum, anomaly_type=anomaly_type_enum, limit=limit
        )

        return [
            SecurityAlertResponse(
                alert_id=alert["alert_id"],
                timestamp=alert["timestamp"],
                anomaly_type=alert["anomaly_type"],
                severity=alert["severity"],
                source_address=alert["source_address"],
                source_address_hex=alert["source_address_hex"],
                pgn=alert["pgn"],
                pgn_hex=alert["pgn_hex"],
                description=alert["description"],
                evidence=alert["evidence"],
                mitigation_action=alert["mitigation_action"],
            )
            for alert in alerts
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting security alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/summary")
async def get_alerts_summary(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, Any]:
    """
    Get summary of recent security alerts.

    Returns:
        Summary statistics for alerts in different time windows
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        import time

        current_time = time.time()

        # Get alerts for different time windows
        last_hour = await security_service.get_alerts(since=current_time - 3600, limit=1000)
        last_24h = await security_service.get_alerts(since=current_time - 86400, limit=1000)

        # Count by severity and type
        def count_alerts(alerts):
            by_severity = {}
            by_type = {}
            for alert in alerts:
                severity = alert["severity"]
                anomaly_type = alert["anomaly_type"]
                by_severity[severity] = by_severity.get(severity, 0) + 1
                by_type[anomaly_type] = by_type.get(anomaly_type, 0) + 1
            return {"by_severity": by_severity, "by_type": by_type}

        return {
            "current_time": current_time,
            "last_hour": {"total": len(last_hour), **count_alerts(last_hour)},
            "last_24h": {"total": len(last_24h), **count_alerts(last_24h)},
        }
    except Exception as e:
        logger.error(f"Error getting alerts summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storm-status")
async def get_storm_status(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, Any]:
    """
    Get broadcast storm detection status.

    Returns:
        Current storm detector status and statistics
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        status = await security_service.get_security_status()
        return status["storm_detector"]
    except Exception as e:
        logger.error(f"Error getting storm status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acl/source")
async def add_source_to_acl(
    entry: ACLEntryRequest,
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, str]:
    """
    Add or update a source in the Access Control List.

    Args:
        entry: ACL entry configuration

    Returns:
        Success message
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        await security_service.add_source_to_acl(
            source_address=entry.source_address,
            allowed_pgns=set(entry.allowed_pgns) if entry.allowed_pgns else None,
            denied_pgns=set(entry.denied_pgns) if entry.denied_pgns else None,
            description=entry.description,
        )

        return {"message": f"Successfully added source 0x{entry.source_address:02X} to ACL"}
    except Exception as e:
        logger.error(f"Error adding source to ACL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/acl/source/{source_address}")
async def remove_source_from_acl(
    source_address: int,
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, str]:
    """
    Remove a source from the Access Control List.

    Args:
        source_address: Source address to remove (decimal)

    Returns:
        Success message
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        removed = await security_service.remove_source_from_acl(source_address)

        if removed:
            return {"message": f"Successfully removed source 0x{source_address:02X} from ACL"}
        raise HTTPException(
            status_code=404, detail=f"Source 0x{source_address:02X} not found in ACL"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing source from ACL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/acl/sources")
async def list_acl_sources(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, Any]:
    """
    List all sources in the Access Control List.

    Returns:
        Dictionary of ACL entries by source address
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        acl_entries = {}
        for source_addr, entry in security_service.source_acl.items():
            acl_entries[f"0x{source_addr:02X}"] = {
                "address": source_addr,
                "allowed_pgns": list(entry.allowed_pgns),
                "denied_pgns": list(entry.denied_pgns),
                "is_whitelisted": entry.is_whitelisted,
                "description": entry.description,
                "added_time": entry.added_time,
            }

        return {
            "sources": acl_entries,
            "default_policy": security_service.default_acl_policy,
            "total_sources": len(acl_entries),
        }
    except Exception as e:
        logger.error(f"Error listing ACL sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acl/policy")
async def set_acl_policy(
    policy_request: ACLPolicyRequest,
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, str]:
    """
    Set the default ACL policy.

    Args:
        policy_request: Policy configuration ("allow" or "deny")

    Returns:
        Success message
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        if policy_request.policy not in ["allow", "deny"]:
            raise HTTPException(status_code=400, detail="Policy must be 'allow' or 'deny'")

        await security_service.set_default_acl_policy(policy_request.policy)

        return {"message": f"Default ACL policy set to: {policy_request.policy}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting ACL policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rate-limiting")
async def get_rate_limiting_status(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, Any]:
    """
    Get rate limiting status and statistics.

    Returns:
        Rate limiting configuration and current token bucket status
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        # Get basic rate limiting info from security status
        status = await security_service.get_security_status()
        rate_limiting_info = status["rate_limiting"]

        # Add detailed bucket information
        bucket_details = {}
        for (source_addr, pgn), bucket in security_service.token_buckets.items():
            key = f"0x{source_addr:02X}_0x{pgn:05X}"
            bucket_details[key] = {
                "source_address": source_addr,
                "source_address_hex": f"0x{source_addr:02X}",
                "pgn": pgn,
                "pgn_hex": f"0x{pgn:05X}",
                **bucket.get_status(),
            }

        return {
            **rate_limiting_info,
            "bucket_details": bucket_details,
            "total_buckets": len(bucket_details),
        }
    except Exception as e:
        logger.error(f"Error getting rate limiting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_security_monitoring(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
) -> dict[str, str]:
    """
    Reset all security monitoring data.

    This clears all alerts, statistics, and tracking data.
    Use with caution as this will lose all security history.

    Returns:
        Confirmation message
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        await security_service.reset_statistics()

        logger.info("Security monitoring data reset")

        return {"message": "Security monitoring data has been reset"}
    except Exception as e:
        logger.error(f"Error resetting security monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test/simulate-attack")
async def simulate_attack_for_testing(
    security_service: Annotated[Any | None, Depends(get_security_monitoring_service)],
    attack_type: str = Query(..., description="Type of attack to simulate"),
    source_address: int = Query(0x42, description="Source address for simulation"),
    duration: int = Query(10, description="Duration in seconds"),
) -> dict[str, Any]:
    """
    Simulate various types of attacks for testing (development/demo only).

    Args:
        attack_type: Type of attack (flood, scan, storm)
        source_address: Source address to use for simulation
        duration: How long to run the simulation

    Returns:
        Simulation results
    """
    if not security_service:
        raise HTTPException(status_code=503, detail="Security monitoring service not available")

    try:
        import asyncio
        import random
        import time

        start_time = time.time()
        messages_sent = 0
        alerts_before = len(security_service.alerts)

        if attack_type == "flood":
            # Message flooding attack
            while time.time() - start_time < duration:
                await security_service.analyze_message(
                    arbitration_id=(0x1FF << 8) | source_address,
                    data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
                    timestamp=time.time(),
                )
                messages_sent += 1
                await asyncio.sleep(0.001)  # 1000 messages/second

        elif attack_type == "scan":
            # PGN scanning attack
            base_time = time.time()
            for i in range(100):  # Scan 100 different PGNs
                pgn = 0x1FF00 + i
                await security_service.analyze_message(
                    arbitration_id=(pgn << 8) | source_address,
                    data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
                    timestamp=base_time + (i * 0.1),
                )
                messages_sent += 1

        elif attack_type == "storm":
            # Broadcast storm simulation
            while time.time() - start_time < duration:
                # Multiple sources sending rapidly
                for src in range(source_address, source_address + 5):
                    await security_service.analyze_message(
                        arbitration_id=(0x1FF << 8) | src,
                        data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
                        timestamp=time.time(),
                    )
                    messages_sent += 1
                await asyncio.sleep(0.001)

        else:
            raise HTTPException(status_code=400, detail="Invalid attack type")

        alerts_after = len(security_service.alerts)

        return {
            "attack_type": attack_type,
            "duration": duration,
            "messages_sent": messages_sent,
            "alerts_generated": alerts_after - alerts_before,
            "message": f"Simulated {attack_type} attack completed",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error simulating attack: {e}")
        raise HTTPException(status_code=500, detail=str(e))
