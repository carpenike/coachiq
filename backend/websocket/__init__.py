"""
WebSocket package for CoachIQ.

This package exposes the main WebSocket API surface for real-time communication, including
WebSocket handlers, log handler, entity integration, and route setup utilities.
"""

from backend.websocket.handlers import (
    WebSocketLogHandler,
    WebSocketManager,
    initialize_websocket_manager,
)
from backend.websocket.routes import router, setup_websocket_routes
from backend.websocket.setup import setup_websocket, shutdown_websocket

__all__ = [
    "WebSocketLogHandler",
    "WebSocketManager",
    "initialize_websocket_manager",
    "router",
    "setup_websocket",
    "setup_websocket_routes",
    "shutdown_websocket",
]
