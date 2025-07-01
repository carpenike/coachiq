"""
WebSocket manager for CoachIQ.

This module provides a facade over the WebSocketService V2.
"""

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    WebSocket manager that delegates to the modern WebSocketService.

    This is a clean facade with no Feature inheritance or legacy patterns.
    It exists to provide a familiar interface while using the modern service.
    """

    def __init__(
        self,
        websocket_service: Any,
        **kwargs,  # Ignore all legacy parameters
    ):
        """Initialize with the modern WebSocket service."""
        self._service = websocket_service

        # Direct delegation - expose service attributes
        self.data_clients = self._service.data_clients
        self.log_clients = self._service.log_clients
        self.can_sniffer_clients = self._service.can_sniffer_clients
        self.network_map_clients = self._service.network_map_clients
        self.features_clients = self._service.features_clients
        self.background_tasks = self._service.background_tasks

    async def startup(self) -> None:
        """Start the WebSocket service."""
        await self._service.start()

    async def shutdown(self) -> None:
        """Stop the WebSocket service."""
        await self._service.stop()

    @property
    def health(self) -> str:
        """Get health status."""
        status = self._service.get_status()
        return "healthy" if status.value == "healthy" else "degraded"

    @property
    def total_connections(self) -> int:
        """Get total number of connections."""
        health = self._service.get_health_status()
        return health["clients"]["total"]

    # Broadcasting methods - direct delegation

    async def broadcast_to_data_clients(self, data: dict[str, Any]) -> None:
        """Broadcast to data clients."""
        await self._service.broadcast_to_data_clients(data)

    async def broadcast_json_to_clients(
        self, clients: set[WebSocket], data: dict[str, Any]
    ) -> None:
        """Broadcast JSON to specific clients."""
        # This is a legacy method - we'll implement it for compatibility
        import json

        message = json.dumps(data)
        disconnected = []

        for client in clients.copy():
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)

        for client in disconnected:
            clients.discard(client)

    async def broadcast_text_to_log_clients(self, text: str) -> None:
        """Broadcast text to log clients."""
        # Convert text to log entry format
        log_entry = {
            "message": text,
            "timestamp": time.perf_counter(),
        }
        await self._service.broadcast_log_message(log_entry)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast data to all data clients."""
        await self._service.broadcast_to_data_clients(data)

    async def broadcast_entity_update(
        self, entity_instance_id: str, entity_data: dict[str, Any]
    ) -> None:
        """Broadcast entity update."""
        await self._service.broadcast_entity_update(entity_instance_id, entity_data)

    async def broadcast_entity_batch_update(self, entities: list[dict[str, Any]]) -> None:
        """Broadcast batch entity update."""
        await self._service.broadcast_entity_batch_update(entities)

    async def broadcast_can_sniffer_group(self, data: dict[str, Any]) -> None:
        """Broadcast CAN sniffer data."""
        await self._service.broadcast_can_message(data)

    async def broadcast_network_map_update(self, update: dict[str, Any]) -> None:
        """Broadcast network map update."""
        await self._service.broadcast_network_map_update(update)

    async def broadcast_features_status(self, status: dict[str, Any]) -> None:
        """Broadcast features status."""
        await self._service.broadcast_features_status(status)

    # Connection management - direct delegation

    async def connect_client(self, websocket: WebSocket, client_type: str) -> None:
        """Connect a client based on type."""
        if client_type == "data":
            await self._service.connect_data_client(websocket)
        elif client_type == "log":
            await self._service.connect_log_client(websocket)
        elif client_type == "can_sniffer":
            await self._service.connect_can_sniffer_client(websocket)
        elif client_type == "network_map":
            await self._service.connect_network_map_client(websocket)
        elif client_type == "features":
            await self._service.connect_features_client(websocket)
        else:
            logger.warning(f"Unknown client type: {client_type}")
            await websocket.close()

    async def disconnect_client(self, websocket: WebSocket, client_type: str) -> None:
        """Disconnect a client based on type."""
        if client_type == "data":
            await self._service.disconnect_data_client(websocket)
        elif client_type == "log":
            await self._service.disconnect_log_client(websocket)
        elif client_type == "can_sniffer":
            await self._service.disconnect_can_sniffer_client(websocket)
        elif client_type == "network_map":
            await self._service.disconnect_network_map_client(websocket)
        elif client_type == "features":
            await self._service.disconnect_features_client(websocket)


class WebSocketLogHandler(logging.Handler):
    """
    Logging handler that broadcasts log entries via WebSocket.
    """

    def __init__(self, websocket_manager: WebSocketManager):
        """Initialize with WebSocket manager."""
        super().__init__()
        self.websocket_manager = websocket_manager

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record via WebSocket."""
        try:
            log_entry = {
                "timestamp": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
                "filename": record.filename,
                "lineno": record.lineno,
                "funcName": record.funcName,
            }

            # Use asyncio to broadcast in the event loop
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(
                    self.websocket_manager._service.broadcast_log_message(log_entry)
                )
        except Exception:
            self.handleError(record)


# Global instance for backward compatibility (will be removed)
websocket_manager: WebSocketManager | None = None


def get_websocket_manager() -> WebSocketManager:
    """
    Get the global WebSocket manager instance.

    DEPRECATED: Use dependency injection instead.
    """
    if websocket_manager is None:
        raise RuntimeError("WebSocket manager not initialized")
    return websocket_manager


def initialize_websocket_manager(
    config: dict[str, Any] | None = None,
    **kwargs,
) -> WebSocketManager:
    """
    Initialize the WebSocket manager.

    This now creates a facade over the modern WebSocketService from ServiceRegistry.
    """
    global websocket_manager

    # Get the modern service from ServiceRegistry
    from backend.core.dependencies import get_service_registry

    try:
        service_registry = get_service_registry()
        websocket_service = service_registry.get_service("websocket_service")

        if not websocket_service:
            raise RuntimeError("WebSocketService not available in ServiceRegistry")

        websocket_manager = WebSocketManager(websocket_service=websocket_service)
        logger.info("WebSocket manager initialized with modern WebSocketService")
        return websocket_manager
    except Exception as e:
        raise RuntimeError(f"Failed to initialize WebSocket manager: {e}") from e
