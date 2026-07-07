"""
Victron Power System API

Status and control endpoints for the Victron Cerbo GX integration.
Control writes go to the Cerbo over MQTT (VE.Bus mode and AC input current
limit) and require admin privileges; entity telemetry itself is served by
the regular entities API and WebSocket stream.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette import status

from backend.core.dependencies import create_optional_service_dependency
from backend.middleware.auth import get_admin_user

logger = logging.getLogger(__name__)

get_optional_victron_service = create_optional_service_dependency("victron_service")

router = APIRouter(
    prefix="/api/victron",
    tags=["victron"],
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Admin privileges required"},
        503: {"description": "Victron integration disabled or unavailable"},
    },
)


class InverterModeRequest(BaseModel):
    """Request to change the VE.Bus switch position."""

    mode: int | str = Field(
        ...,
        description="Target mode: charger_only (1), inverter_only (2), on (3), or off (4)",
    )


class InputCurrentLimitRequest(BaseModel):
    """Request to change the AC input current limit."""

    amps: float = Field(..., description="Input current limit in amps", ge=0)


class GeneratorManualRequest(BaseModel):
    """Request a manual generator start or stop."""

    run: bool = Field(..., description="True starts the generator, False stops it")


def _require_victron_service(service: Any) -> Any:
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Victron integration is not enabled (set COACHIQ_VICTRON__ENABLED=true)",
        )
    return service


@router.get(
    "/status",
    summary="Victron integration status",
    description="Connection health and discovered devices for the Cerbo GX integration",
)
async def get_victron_status(
    victron_service: Annotated[Any, Depends(get_optional_victron_service)],
) -> dict[str, Any]:
    """Return Victron service health and device bindings."""
    service = _require_victron_service(victron_service)
    return service.get_health_status()


@router.post(
    "/inverter/mode",
    summary="Set inverter/charger mode",
    description="Set the VE.Bus switch position (charger_only/inverter_only/on/off)",
    dependencies=[Depends(get_admin_user)],
)
async def set_inverter_mode(
    request: InverterModeRequest,
    victron_service: Annotated[Any, Depends(get_optional_victron_service)],
) -> dict[str, Any]:
    """Command the Quattro system mode over MQTT."""
    service = _require_victron_service(victron_service)
    try:
        result = await service.set_inverter_mode(request.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    logger.info("Victron inverter mode set: %s", result)
    return {"success": True, **result}


@router.post(
    "/generator/manual",
    summary="Manual generator start/stop",
    description=(
        "Request a manual generator run via the Cerbo's genset controller "
        "(equivalent to VRM's manual start; the Cerbo performs the crank/stop "
        "sequence and its own stop conditions still apply)"
    ),
    dependencies=[Depends(get_admin_user)],
)
async def set_generator_manual(
    request: GeneratorManualRequest,
    victron_service: Annotated[Any, Depends(get_optional_victron_service)],
) -> dict[str, Any]:
    """Command a manual generator start or stop over MQTT."""
    service = _require_victron_service(victron_service)
    try:
        result = await service.set_generator_manual(request.run)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    logger.info("Victron generator manual request: %s", result)
    return {"success": True, **result}


@router.post(
    "/inverter/input-current-limit",
    summary="Set AC input current limit",
    description=(
        "Set the VE.Bus AC input current limit in amps "
        "(validated against the adjustable range the Cerbo reports)"
    ),
    dependencies=[Depends(get_admin_user)],
)
async def set_input_current_limit(
    request: InputCurrentLimitRequest,
    victron_service: Annotated[Any, Depends(get_optional_victron_service)],
) -> dict[str, Any]:
    """Command the shore/generator input current limit over MQTT."""
    service = _require_victron_service(victron_service)
    try:
        result = await service.set_input_current_limit(request.amps)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    logger.info("Victron input current limit set: %s", result)
    return {"success": True, **result}
