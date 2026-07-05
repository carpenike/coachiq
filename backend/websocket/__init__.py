"""
WebSocket package for CoachIQ.

Exposes the WebSocket routes for the page-scoped diagnostic streams
(logs, CAN sniffer/recorder/analyzer/filter). App-wide realtime state
rides SSE (backend/api/routers/events.py), not a WebSocket.
"""

from backend.websocket.routes import router, setup_websocket_routes

__all__ = [
    "router",
    "setup_websocket_routes",
]
