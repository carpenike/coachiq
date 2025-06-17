"""
WebSocket setup module for CoachIQ.

This module provides functions to set up and integrate WebSocket functionality with the FastAPI
application, including WebSocket routes, handlers, and the WebSocketManager feature.

Usage Example:
    >>> setup_websocket(app, feature_manager)
"""

import logging
from typing import Any

from fastapi import FastAPI

# app_state global removed - AppState accessed via dependency injection
from backend.services.feature_manager import FeatureManager
from backend.websocket.handlers import (
    WebSocketLogHandler,
    WebSocketManager,
    initialize_websocket_manager,
)
from backend.websocket.routes import setup_websocket_routes

logger = logging.getLogger(__name__)


def setup_websocket(
    app: FastAPI,
    feature_manager: FeatureManager,
    config: dict[str, Any] | None = None,
    app_state: Any | None = None,
) -> WebSocketManager:
    """
    Set up WebSocket functionality for the FastAPI application.

    This function:
      1. Initializes the WebSocketManager feature
      2. Sets up WebSocket routes
      3. Configures the WebSocketLogHandler

    Args:
        app (FastAPI): The FastAPI application instance.
        feature_manager (FeatureManager): The feature manager instance.
        config (dict[str, Any] | None): Optional configuration dictionary.
        app_state (Any | None): Optional app state instance.

    Returns:
        WebSocketManager: The initialized WebSocketManager instance.

    Example:
        >>> ws_manager = setup_websocket(app, feature_manager)
    """
    ws_manager = initialize_websocket_manager(
        app_state=app_state,  # Pass app_state from caller
        feature_manager=feature_manager,
        config=config or {},
    )
    setup_websocket_routes(app, app_state)
    # Initialize and attach WebSocket log handler to capture application and access logs
    ws_handler = WebSocketLogHandler(ws_manager)
    # Attach to root logger so all app logs are streamed
    root_logger = logging.getLogger()
    root_logger.addHandler(ws_handler)
    # Also attach to Uvicorn access logger to capture HTTP access logs
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(ws_handler)
    # Ensure access logs propagate to attached handlers
    access_logger.propagate = True
    logger.info("WebSocket setup complete.")
    return ws_manager


def shutdown_websocket() -> None:
    """
    Clean up WebSocket resources.

    This function should be called when shutting down the application
    to ensure proper cleanup of WebSocket connections and resources.
    """
    logger.info("WebSocket shutdown complete")
