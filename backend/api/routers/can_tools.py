"""
CAN Tools API Router

Advanced CAN bus utilities for testing, diagnostics, and analysis.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator

from backend.core.dependencies import get_feature_manager
from backend.integrations.can.message_injector import (
    CANMessageInjector,
    InjectionMode,
    InjectionRequest,
    SafetyLevel,
)
from backend.services.feature_manager import FeatureManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/can-tools", tags=["CAN Tools"])


# Pydantic models for API
class MessageInjectionRequest(BaseModel):
    """Request to inject CAN messages."""

    can_id: int = Field(..., description="CAN identifier (11 or 29 bit)")
    data: str = Field(..., description="Message data as hex string (e.g., '0102030405060708')")
    interface: str = Field(default="can0", description="CAN interface to use")
    mode: InjectionMode = Field(default=InjectionMode.SINGLE, description="Injection mode")
    count: int = Field(default=1, ge=1, le=1000, description="Number of messages for burst mode")
    interval: float = Field(default=1.0, ge=0.01, description="Interval for periodic mode (seconds)")
    duration: float = Field(default=0.0, ge=0, description="Duration for periodic mode (0=infinite)")
    priority: int = Field(default=6, ge=0, le=7, description="J1939 priority")
    source_address: int = Field(default=0xFE, ge=0, le=255, description="Source address")
    destination_address: int = Field(default=0xFF, ge=0, le=255, description="Destination address")
    description: str = Field(default="", description="Description of injection")
    reason: str = Field(default="", description="Reason for injection")

    @validator("data")
    def validate_hex_data(cls, v):
        """Validate and convert hex string to bytes."""
        try:
            # Remove spaces and validate hex
            hex_str = v.replace(" ", "").upper()
            if len(hex_str) % 2 != 0:
                raise ValueError("Hex string must have even length")

            # Convert to bytes
            data = bytes.fromhex(hex_str)
            if len(data) > 8:
                raise ValueError("Data too long (max 8 bytes)")

            return hex_str
        except ValueError as e:
            raise ValueError(f"Invalid hex data: {e}")

    class Config:
        json_schema_extra = {
            "example": {
                "can_id": 0x18FEEE00,
                "data": "0102030405060708",
                "interface": "can0",
                "mode": "single",
                "description": "Test engine temperature sensor",
                "reason": "Diagnostic testing",
            }
        }


class MessageInjectionResponse(BaseModel):
    """Response from message injection."""

    success: bool
    messages_sent: int
    messages_failed: int
    duration: float
    success_rate: float
    warnings: list[str]
    error: str | None = None


class J1939MessageRequest(BaseModel):
    """Request to create J1939 message."""

    pgn: int = Field(..., description="Parameter Group Number")
    data: str = Field(..., description="Message data as hex string")
    priority: int = Field(default=6, ge=0, le=7, description="Message priority")
    source_address: int = Field(default=0xFE, ge=0, le=255, description="Source address")
    destination_address: int = Field(default=0xFF, ge=0, le=255, description="Destination address")
    interface: str = Field(default="can0", description="CAN interface to use")
    mode: InjectionMode = Field(default=InjectionMode.SINGLE, description="Injection mode")

    @validator("data")
    def validate_hex_data(cls, v):
        """Validate and convert hex string to bytes."""
        try:
            hex_str = v.replace(" ", "").upper()
            if len(hex_str) % 2 != 0:
                raise ValueError("Hex string must have even length")

            data = bytes.fromhex(hex_str)
            if len(data) > 8:
                raise ValueError("Data too long (max 8 bytes)")

            return hex_str
        except ValueError as e:
            raise ValueError(f"Invalid hex data: {e}")


class InjectorStatusResponse(BaseModel):
    """CAN message injector status."""

    enabled: bool
    safety_level: str
    statistics: dict[str, Any]
    active_injections: int
    active_interfaces: list[str]


class SafetyConfigRequest(BaseModel):
    """Request to update safety configuration."""

    safety_level: SafetyLevel = Field(..., description="New safety level")


# Dependency to get message injector
async def get_message_injector(
    feature_manager: FeatureManager = Depends(get_feature_manager),
) -> CANMessageInjector:
    """Get CAN message injector feature."""
    injector = feature_manager.get_feature("can_message_injector")

    if not injector:
        # Create injector if it doesn't exist
        injector = CANMessageInjector(
            enabled=True,
            safety_level=SafetyLevel.MODERATE,
        )
        feature_manager.register_feature(injector)
        await injector.startup()

    if not isinstance(injector, CANMessageInjector):
        raise HTTPException(
            status_code=500,
            detail="CAN message injector not properly configured"
        )

    if not injector.enabled:
        raise HTTPException(
            status_code=503,
            detail="CAN message injector is disabled"
        )

    return injector


@router.get("/status", response_model=InjectorStatusResponse)
async def get_injector_status(
    injector: CANMessageInjector = Depends(get_message_injector),
) -> InjectorStatusResponse:
    """Get CAN message injector status and statistics."""
    stats = injector.get_statistics()

    return InjectorStatusResponse(
        enabled=injector.enabled,
        safety_level=injector.safety_level.value,
        statistics={
            "total_injected": stats.get("total_injected", 0),
            "total_failed": stats.get("total_failed", 0),
            "dangerous_blocked": stats.get("dangerous_blocked", 0),
            "rate_limited": stats.get("rate_limited", 0),
        },
        active_injections=stats.get("active_injections", 0),
        active_interfaces=stats.get("active_interfaces", []),
    )


@router.post("/inject", response_model=MessageInjectionResponse)
async def inject_message(
    request: MessageInjectionRequest,
    injector: CANMessageInjector = Depends(get_message_injector),
) -> MessageInjectionResponse:
    """
    Inject CAN message(s) for testing and diagnostics.

    Safety levels:
    - STRICT: Blocks dangerous messages
    - MODERATE: Warns on dangerous messages (default)
    - PERMISSIVE: Allows all messages (use with caution)
    """
    try:
        # Convert hex string to bytes
        data = bytes.fromhex(request.data)

        # Create injection request
        injection_req = InjectionRequest(
            can_id=request.can_id,
            data=data,
            interface=request.interface,
            mode=request.mode,
            count=request.count,
            interval=request.interval,
            duration=request.duration,
            priority=request.priority,
            source_address=request.source_address,
            destination_address=request.destination_address,
            description=request.description,
            reason=request.reason,
            user="api",  # TODO: Get from auth context
        )

        # Perform injection
        result = await injector.inject(injection_req)

        return MessageInjectionResponse(
            success=result.success,
            messages_sent=result.messages_sent,
            messages_failed=result.messages_failed,
            duration=result.duration,
            success_rate=result.success_rate,
            warnings=result.warnings,
            error=result.error,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Message injection failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Injection failed: {e}")


@router.post("/inject/j1939", response_model=MessageInjectionResponse)
async def inject_j1939_message(
    request: J1939MessageRequest,
    injector: CANMessageInjector = Depends(get_message_injector),
) -> MessageInjectionResponse:
    """
    Inject J1939 message with automatic CAN ID generation.

    This endpoint simplifies J1939 message injection by automatically
    constructing the proper 29-bit CAN identifier from PGN and addresses.
    """
    try:
        # Convert hex string to bytes
        data = bytes.fromhex(request.data)

        # Generate J1939 CAN ID
        can_id = injector.create_j1939_message(
            pgn=request.pgn,
            data=data,
            priority=request.priority,
            source_address=request.source_address,
            destination_address=request.destination_address,
        )

        # Create injection request
        injection_req = InjectionRequest(
            can_id=can_id,
            data=data,
            interface=request.interface,
            mode=request.mode,
            priority=request.priority,
            source_address=request.source_address,
            destination_address=request.destination_address,
            description=f"J1939 PGN 0x{request.pgn:04X}",
            reason="J1939 message injection",
            user="api",
        )

        # Perform injection
        result = await injector.inject(injection_req)

        return MessageInjectionResponse(
            success=result.success,
            messages_sent=result.messages_sent,
            messages_failed=result.messages_failed,
            duration=result.duration,
            success_rate=result.success_rate,
            warnings=result.warnings,
            error=result.error,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("J1939 message injection failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Injection failed: {e}")


@router.delete("/inject/stop")
async def stop_injection(
    pattern: str | None = Query(None, description="Pattern to match injections"),
    injector: CANMessageInjector = Depends(get_message_injector),
) -> dict[str, Any]:
    """Stop active periodic message injections."""
    stopped = await injector.stop_injection(pattern)

    return {
        "success": True,
        "stopped_count": stopped,
        "message": f"Stopped {stopped} injection(s)",
    }


@router.put("/safety", response_model=dict[str, str])
async def update_safety_config(
    request: SafetyConfigRequest,
    injector: CANMessageInjector = Depends(get_message_injector),
) -> dict[str, str]:
    """Update safety configuration for message injection."""
    old_level = injector.safety_level
    injector.safety_level = request.safety_level

    logger.warning(
        "Safety level changed from %s to %s",
        old_level.value, request.safety_level.value
    )

    return {
        "success": "true",
        "old_level": old_level.value,
        "new_level": request.safety_level.value,
        "message": f"Safety level updated to {request.safety_level.value}",
    }


@router.get("/pgn-info/{pgn}")
async def get_pgn_info(
    pgn: int,
    injector: CANMessageInjector = Depends(get_message_injector),
) -> dict[str, Any]:
    """Get information about a specific PGN."""
    # Check if dangerous
    # Import the DANGEROUS_PGNS from the message_injector module
    from backend.integrations.can.message_injector import DANGEROUS_PGNS
    is_dangerous = pgn in DANGEROUS_PGNS

    # Get name
    name = injector._get_pgn_name(pgn) if hasattr(injector, "_get_pgn_name") else f"PGN 0x{pgn:04X}"

    return {
        "pgn": pgn,
        "hex": f"0x{pgn:04X}",
        "name": name,
        "is_dangerous": is_dangerous,
        "pdu_format": (pgn >> 8) & 0xFF,
        "pdu_specific": pgn & 0xFF,
        "is_pdu1": (pgn >> 8) & 0xFF < 240,
    }


# Example templates for common messages
@router.get("/templates")
async def get_message_templates() -> list[dict[str, Any]]:
    """Get example message templates for testing."""
    return [
        {
            "name": "Engine Temperature",
            "pgn": 0xFEEE,
            "can_id": 0x18FEEE00,
            "data": "FF8C960000FFFFFF",
            "description": "Engine coolant temperature 150°C",
        },
        {
            "name": "Vehicle Speed",
            "pgn": 0xFEF1,
            "can_id": 0x18FEF100,
            "data": "00C8000000000000",
            "description": "Vehicle speed 50 km/h",
        },
        {
            "name": "Fuel Level",
            "pgn": 0xFEFC,
            "can_id": 0x18FEFC00,
            "data": "80FFFFFFFFFFFF",
            "description": "Fuel level 50%",
        },
        {
            "name": "Turn Signals",
            "pgn": 0xFEF0,
            "can_id": 0x18FEF000,
            "data": "0300000000000000",
            "description": "Left turn signal on",
        },
    ]
