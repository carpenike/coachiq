"""
FastAPI WebSocket routes and endpoints.

WebSockets serve only the page-scoped, high-frequency CAN diagnostic streams
(sniffer/recorder/analyzer/filter). App-wide realtime state (entity updates
etc.) rides the SSE stream at GET /api/events, and live logs ride SSE at
GET /api/logs/stream — see backend/api/routers/events.py and
backend/api/routers/logs.py.
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

    Services are accessed via composition root.
    """
    app.include_router(router)
    logger.info("WebSocket routes configured")


@router.websocket("/ws/can-sniffer")
async def can_sniffer_ws_endpoint(websocket: WebSocket, ws_service: WebSocketManager) -> None:
    """
    WebSocket endpoint for CAN sniffer data.

    Connect to ws://<host>/ws/can-sniffer to receive raw CAN frames.
    """
    await ws_service.handle_can_sniffer_connection(websocket)


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
