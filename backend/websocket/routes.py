"""
FastAPI WebSocket routes and endpoints.

This module defines WebSocket routes using dependency injection for service access.
WebSocket endpoints use the same DI pattern as regular HTTP endpoints.
"""

import logging
from typing import Any

from fastapi import APIRouter, WebSocket

from backend.core.dependencies import WebSocketManager

logger = logging.getLogger(__name__)

# Create an APIRouter for WebSocket endpoints
router = APIRouter()


def setup_websocket_routes(app: Any) -> None:
    """
    Set up WebSocket routes for the FastAPI application.

    Services are accessed via ServiceRegistry.
    """
    app.include_router(router)
    logger.info("WebSocket routes configured")


# Helper function removed - using dependency injection instead


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for real-time entity data updates.

    Connect to ws://<host>/ws for real-time updates.
    """
    await ws_service.handle_data_connection(websocket)


@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for log streaming.

    Connect to ws://<host>/ws/logs to receive log messages.
    """
    await ws_service.handle_log_connection(websocket)


@router.websocket("/ws/can-sniffer")
async def can_sniffer_ws_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for CAN sniffer data.

    Connect to ws://<host>/ws/can-sniffer to receive raw CAN frames.
    """
    await ws_service.handle_can_sniffer_connection(websocket)


@router.websocket("/ws/network-map")
async def network_map_ws_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for network map updates.

    Connect to ws://<host>/ws/network-map to receive network topology updates.
    """
    await ws_service.handle_network_map_connection(websocket)


@router.websocket("/ws/features")
async def features_ws_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for feature status updates.

    Connect to ws://<host>/ws/features to receive feature status changes.
    """
    await ws_service.handle_features_status_connection(websocket)


@router.websocket("/ws/can-recorder")
async def can_recorder_ws_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for CAN recorder status updates.

    Connect to ws://<host>/ws/can-recorder to receive real-time recorder status.
    """
    await ws_service.handle_can_recorder_connection(websocket)


@router.websocket("/ws/can-analyzer")
async def can_analyzer_ws_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for CAN analyzer updates.

    Connect to ws://<host>/ws/can-analyzer to receive statistics and messages.
    """
    await ws_service.handle_can_analyzer_connection(websocket)


@router.websocket("/ws/can-filter")
async def can_filter_ws_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for CAN filter updates.

    Connect to ws://<host>/ws/can-filter to receive filter status and captured messages.
    """
    await ws_service.handle_can_filter_connection(websocket)


@router.websocket("/ws/security")
async def security_ws_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for security monitoring dashboard.

    Connect to ws://<host>/ws/security to receive real-time security events.
    """
    # For now, close immediately - SecurityWebSocketHandler needs migration
    logger.warning("Security WebSocket endpoint not yet migrated to ServiceRegistry")
    await websocket.close(code=1011)  # Internal error
