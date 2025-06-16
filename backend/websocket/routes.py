"""
FastAPI WebSocket routes and endpoints.

This module defines FastAPI WebSocket routes and endpoints that integrate with
WebSocketManager for handling client connections and data streaming.
"""

import logging
from typing import Any

from fastapi import APIRouter, WebSocket
from fastapi.exceptions import HTTPException

from backend.core.state import AppState
from backend.services.feature_manager import get_feature_manager
from backend.websocket.handlers import WebSocketManager
from backend.websocket.security_handler import get_security_websocket_handler

logger = logging.getLogger(__name__)

# Create an APIRouter for WebSocket endpoints
router = APIRouter()


def setup_websocket_routes(app: Any, app_state: AppState) -> None:
    """
    Set up WebSocket routes for the FastAPI application.

    Args:
        app: The FastAPI application instance.
        app_state: The application state instance.

    Example:
        >>> setup_websocket_routes(app, app_state)
    """
    app.include_router(router)
    logger.info("Setting up WebSocket routes")
    # The WebSocketManager should already be initialized in app startup


def get_websocket_manager_from_feature() -> WebSocketManager:
    """
    Get WebSocket manager instance from feature manager.

    Returns:
        WebSocketManager: The WebSocketManager instance

    Raises:
        HTTPException: If WebSocketManager feature is not found
    """
    feature_manager = get_feature_manager()
    ws_manager = feature_manager.get_feature("websocket")
    if not ws_manager:
        logger.error("WebSocketManager feature not found")
        raise HTTPException(status_code=500, detail="WebSocket service unavailable")
    return ws_manager


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time entity data updates.

    Args:
        websocket (WebSocket): The WebSocket connection.

    Example:
        Connect to ws://<host>/ws for real-time updates.
    """
    ws_manager = get_websocket_manager_from_feature()
    await ws_manager.handle_data_connection(websocket)


@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for log streaming.

    Args:
        websocket (WebSocket): The WebSocket connection.

    Example:
        Connect to ws://<host>/ws/logs to receive log messages.
    """
    # On client connect, delegate to WebSocketLogHandler via the manager
    ws_manager = get_websocket_manager_from_feature()
    await ws_manager.handle_log_connection(websocket)


@router.websocket("/ws/can-sniffer")
async def can_sniffer_ws_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for CAN sniffer data.

    Args:
        websocket (WebSocket): The WebSocket connection.

    Example:
        Connect to ws://<host>/ws/can-sniffer to receive raw CAN frames.
    """
    ws_manager = get_websocket_manager_from_feature()
    await ws_manager.handle_can_sniffer_connection(websocket)


@router.websocket("/ws/network-map")
async def network_map_ws_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for network map updates.

    Args:
        websocket (WebSocket): The WebSocket connection.

    Example:
        Connect to ws://<host>/ws/network-map to receive network topology updates.
    """
    ws_manager = get_websocket_manager_from_feature()
    await ws_manager.handle_network_map_connection(websocket)


@router.websocket("/ws/features")
async def features_ws_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for feature status updates.

    Args:
        websocket (WebSocket): The WebSocket connection.

    Example:
        Connect to ws://<host>/ws/features to receive feature status changes.
    """
    ws_manager = get_websocket_manager_from_feature()
    await ws_manager.handle_features_status_connection(websocket)


@router.websocket("/ws/security")
async def security_ws_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for security monitoring dashboard.

    Args:
        websocket (WebSocket): The WebSocket connection.

    Example:
        Connect to ws://<host>/ws/security to receive real-time security events.
    """
    security_handler = get_security_websocket_handler()
    await security_handler.connect_client(websocket)

    try:
        while True:
            # Listen for client messages
            message = await websocket.receive_text()
            await security_handler.handle_client_message(websocket, message)

    except Exception as e:
        logger.error(f"Security WebSocket error: {e}")
    finally:
        await security_handler.disconnect_client(websocket)
