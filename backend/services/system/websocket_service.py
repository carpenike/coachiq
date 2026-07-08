"""
WebSocket Service - Clean Service Implementation

Service for managing WebSocket connections without Feature inheritance.
Uses repository injection pattern for all dependencies.
"""

import asyncio
import contextlib
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from backend.repositories import CANTrackingRepository, SystemStateRepository

logger = logging.getLogger(__name__)


def _get_websocket_auth_handler():
    """Import the WebSocket auth handler lazily to avoid DI alias import cycles."""
    from backend.websocket.auth_handler import get_websocket_auth_handler

    return get_websocket_auth_handler()


class WebSocketService:
    """
    Service that manages WebSocket connections and broadcasting.

    This is a clean service implementation without Feature inheritance,
    using repository injection for all dependencies.
    """

    def __init__(
        self,
        can_tracking_repository: CANTrackingRepository | None = None,
        system_state_repository: SystemStateRepository | None = None,
        can_bus_recorder: Any | None = None,
        can_protocol_analyzer: Any | None = None,
        can_message_filter: Any | None = None,
    ):
        """
        Initialize the WebSocket service with repository dependencies.

        Args:
            can_tracking_repository: Repository for CAN tracking operations
            system_state_repository: Repository for system state operations
            can_bus_recorder: Optional CAN bus recorder for initial status
            can_protocol_analyzer: Optional CAN protocol analyzer for initial statistics
            can_message_filter: Optional CAN message filter for initial status
        """
        # Store repository references
        self._can_tracking_repository = can_tracking_repository
        self._system_state_repository = system_state_repository
        self._can_bus_recorder = can_bus_recorder
        self._can_protocol_analyzer = can_protocol_analyzer
        self._can_message_filter = can_message_filter

        # WebSocket client sets (page-scoped CAN diagnostic streams only; the
        # main app data stream is SSE via EventBroker, and live logs are SSE
        # at /api/logs/stream)
        self.can_sniffer_clients: set[WebSocket] = set()  # CAN sniffer stream
        self.can_recorder_clients: set[WebSocket] = set()  # CAN recorder status
        self.can_analyzer_clients: set[WebSocket] = set()  # CAN analyzer updates
        self.can_filter_clients: set[WebSocket] = set()  # CAN filter updates

        # For background task management
        self.background_tasks: set[asyncio.Task] = set()
        self._running = False

        logger.info("WebSocketService initialized with repositories")

    async def start(self) -> None:
        """Start the WebSocket service and its background tasks."""
        if self._running:
            return

        logger.info("Starting WebSocket service")

        # Set up broadcast function in repository
        if self._system_state_repository:
            self._system_state_repository.set_broadcast_function(
                "can_sniffer_group", self.broadcast_can_sniffer_group
            )

        # Start token expiry check task
        self.background_tasks.add(asyncio.create_task(self._check_token_expiry_task()))

        self._running = True
        logger.info("WebSocket service started successfully")

    async def stop(self) -> None:
        """Stop the WebSocket service and clean up resources."""
        if not self._running:
            return

        logger.info("Stopping WebSocket service")
        self._running = False

        # Cancel any background tasks
        for task in self.background_tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.background_tasks.clear()

        # Close all WebSocket connections
        for client_set in [
            self.can_sniffer_clients,
            self.can_recorder_clients,
            self.can_analyzer_clients,
            self.can_filter_clients,
        ]:
            for client in list(client_set):
                with contextlib.suppress(Exception):
                    await client.close()
            client_set.clear()

        logger.info("WebSocket service stopped")

    def get_health_status(self) -> dict[str, Any]:
        """
        Get service health status.

        Returns:
            Health status information
        """
        return {
            "service": "WebSocketService",
            "healthy": self._running,
            "running": self._running,
            "total_connections": self.total_connections,
            "connections": {
                "can_sniffer": len(self.can_sniffer_clients),
                "can_recorder": len(self.can_recorder_clients),
                "can_analyzer": len(self.can_analyzer_clients),
                "can_filter": len(self.can_filter_clients),
            },
        }

    @property
    def total_connections(self) -> int:
        """Return the total number of active WebSocket connections across all client sets."""
        return (
            len(self.can_sniffer_clients)
            + len(self.can_recorder_clients)
            + len(self.can_analyzer_clients)
            + len(self.can_filter_clients)
        )

    # ── Broadcasting Functions ──────────────────────────────────────────────────

    async def broadcast_json_to_clients(
        self, clients: set[WebSocket], data: dict[str, Any]
    ) -> None:
        """
        Broadcast JSON data to a specific set of WebSocket clients.

        Args:
            clients: Set of WebSocket clients to broadcast to
            data: The data to broadcast as JSON
        """
        to_remove = set()
        for client in clients:
            try:
                await client.send_json(data)
            except Exception:
                to_remove.add(client)
        for client in to_remove:
            clients.discard(client)

    async def broadcast_can_sniffer_group(self, group: dict[str, Any]) -> None:
        """
        Broadcast a CAN sniffer group to all connected CAN sniffer clients.

        Args:
            group: The CAN sniffer group to broadcast
        """
        await self.broadcast_json_to_clients(self.can_sniffer_clients, group)

    async def broadcast_can_sniffer_entry(self, entry: dict[str, Any]) -> None:
        """
        Broadcast a single live CAN sniffer entry to all connected sniffer clients.

        Mirrors ``broadcast_to_data_clients`` (dead-socket cleanup, exception
        guards) so a broken client can never break the RX path. The entry is
        sent as a bare frame; the sniffer page (useCANScanWebSocket) consumes
        the raw JSON directly as a CANMessage.

        Args:
            entry: The CAN sniffer entry to broadcast
        """
        await self.broadcast_json_to_clients(self.can_sniffer_clients, entry)

    async def broadcast_can_recorder_update(self, update_type: str, data: dict[str, Any]) -> None:
        """
        Broadcast CAN recorder updates to all connected clients.

        Args:
            update_type: Type of update (e.g., 'status', 'recording_started')
            data: The update data to broadcast
        """
        message = {"type": update_type, "payload": data, "timestamp": time.time()}
        await self.broadcast_json_to_clients(self.can_recorder_clients, message)

    async def broadcast_can_analyzer_update(self, update_type: str, data: dict[str, Any]) -> None:
        """
        Broadcast CAN analyzer updates to all connected clients.

        Args:
            update_type: Type of update (e.g., 'statistics', 'messages', 'protocol_detected')
            data: The update data to broadcast
        """
        message = {"type": update_type, "payload": data, "timestamp": time.time()}
        await self.broadcast_json_to_clients(self.can_analyzer_clients, message)

    async def broadcast_can_filter_update(self, update_type: str, data: dict[str, Any]) -> None:
        """
        Broadcast CAN filter updates to all connected clients.

        Args:
            update_type: Type of update (e.g., 'status', 'captured_messages', 'rule_triggered')
            data: The update data to broadcast
        """
        message = {"type": update_type, "payload": data, "timestamp": time.time()}
        await self.broadcast_json_to_clients(self.can_filter_clients, message)

    async def _check_token_expiry_task(self) -> None:
        """Periodically check for expired tokens and close connections."""
        auth_handler = _get_websocket_auth_handler()
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Check all authenticated connections
                for connection_id, user_info in list(
                    auth_handler.authenticated_connections.items()
                ):
                    # Find the websocket by connection_id
                    for ws in list(
                        self.can_sniffer_clients
                        | self.can_recorder_clients
                        | self.can_analyzer_clients
                        | self.can_filter_clients
                    ):
                        if f"{ws.client.host}:{ws.client.port}" == connection_id:
                            await auth_handler.check_token_expiry(ws, user_info)
                            break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in token expiry check: %s", e)

    # ── WebSocket Endpoints ─────────────────────────────────────────────────────

    async def handle_can_sniffer_connection(self, websocket: WebSocket) -> None:
        """
        Handle a new CAN sniffer WebSocket connection.

        Args:
            websocket: The WebSocket connection
        """
        # Authenticate the connection
        auth_handler = _get_websocket_auth_handler()
        user_info = await auth_handler.authenticate_connection(websocket, require_auth=True)

        if not user_info:
            return  # Connection already closed by auth handler

        # Check permission to view CAN data
        if not await auth_handler.require_permission(websocket, user_info, "view_status"):
            await websocket.close(code=1008)
            return

        self.can_sniffer_clients.add(websocket)
        logger.info(
            "CAN sniffer WebSocket client connected: %s:%s (user: %s)",
            websocket.client.host,
            websocket.client.port,
            user_info.get("username", "unknown"),
        )
        try:
            # Get initial CAN sniffer data from repository
            if self._can_tracking_repository:
                for group in self._can_tracking_repository.get_can_sniffer_grouped():
                    await websocket.send_json(group)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info(
                "CAN sniffer WebSocket client disconnected: %s:%s",
                websocket.client.host,
                websocket.client.port,
            )
        except Exception as e:
            logger.error(
                "CAN sniffer WebSocket error for client %s:%s: %s",
                websocket.client.host,
                websocket.client.port,
                e,
            )
        finally:
            self.can_sniffer_clients.discard(websocket)
            auth_handler.remove_connection(websocket)

    async def handle_can_recorder_connection(self, websocket: WebSocket) -> None:
        """
        Handle a new CAN recorder WebSocket connection.

        Args:
            websocket: The WebSocket connection
        """
        # Authenticate the connection
        auth_handler = _get_websocket_auth_handler()
        user_info = await auth_handler.authenticate_connection(websocket, require_auth=True)

        if not user_info:
            return  # Connection already closed by auth handler

        # Check permission to view CAN data
        if not await auth_handler.require_permission(websocket, user_info, "view_status"):
            await websocket.close(code=1008)
            return

        self.can_recorder_clients.add(websocket)
        logger.info(
            "CAN recorder WebSocket client connected: %s:%s (user: %s)",
            websocket.client.host,
            websocket.client.port,
            user_info.get("username", "unknown"),
        )
        try:
            # Send initial recorder status if available. Shape matches
            # broadcast_can_recorder_update("recorder_status", ...) so the
            # frontend hook handles the snapshot and live updates identically.
            if self._can_bus_recorder is not None:
                initial_status = self._can_bus_recorder.get_status()
                if initial_status:
                    await websocket.send_json(
                        {
                            "type": "recorder_status",
                            "payload": {"status": initial_status},
                            "timestamp": time.time(),
                        }
                    )

            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info(
                "CAN recorder WebSocket client disconnected: %s:%s",
                websocket.client.host,
                websocket.client.port,
            )
        except Exception as e:
            logger.error(
                "CAN recorder WebSocket error for client %s:%s: %s",
                websocket.client.host,
                websocket.client.port,
                e,
            )
        finally:
            self.can_recorder_clients.discard(websocket)
            auth_handler.remove_connection(websocket)

    async def handle_can_analyzer_connection(self, websocket: WebSocket) -> None:
        """
        Handle a new CAN analyzer WebSocket connection.

        Args:
            websocket: The WebSocket connection
        """
        # Authenticate the connection
        auth_handler = _get_websocket_auth_handler()
        user_info = await auth_handler.authenticate_connection(websocket, require_auth=True)

        if not user_info:
            return  # Connection already closed by auth handler

        # Check permission to view CAN data
        if not await auth_handler.require_permission(websocket, user_info, "view_status"):
            await websocket.close(code=1008)
            return

        self.can_analyzer_clients.add(websocket)
        logger.info(
            "CAN analyzer WebSocket client connected: %s:%s (user: %s)",
            websocket.client.host,
            websocket.client.port,
            user_info.get("username", "unknown"),
        )
        try:
            # Send initial analyzer stats if available. Shape matches
            # broadcast_can_analyzer_update("analyzer_statistics", ...) so the
            # frontend hook handles snapshot and live updates identically.
            if self._can_protocol_analyzer is not None:
                initial_stats = self._can_protocol_analyzer.get_statistics()
                if initial_stats:
                    await websocket.send_json(
                        {
                            "type": "analyzer_statistics",
                            "payload": {"statistics": initial_stats},
                            "timestamp": time.time(),
                        }
                    )

            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info(
                "CAN analyzer WebSocket client disconnected: %s:%s",
                websocket.client.host,
                websocket.client.port,
            )
        except Exception as e:
            logger.error(
                "CAN analyzer WebSocket error for client %s:%s: %s",
                websocket.client.host,
                websocket.client.port,
                e,
            )
        finally:
            self.can_analyzer_clients.discard(websocket)
            auth_handler.remove_connection(websocket)

    async def handle_can_filter_connection(self, websocket: WebSocket) -> None:
        """
        Handle a new CAN filter WebSocket connection.

        Args:
            websocket: The WebSocket connection
        """
        # Authenticate the connection
        auth_handler = _get_websocket_auth_handler()
        user_info = await auth_handler.authenticate_connection(websocket, require_auth=True)

        if not user_info:
            return  # Connection already closed by auth handler

        # Check permission to view CAN data
        if not await auth_handler.require_permission(websocket, user_info, "view_status"):
            await websocket.close(code=1008)
            return

        self.can_filter_clients.add(websocket)
        logger.info(
            "CAN filter WebSocket client connected: %s:%s (user: %s)",
            websocket.client.host,
            websocket.client.port,
            user_info.get("username", "unknown"),
        )
        try:
            # Send initial filter status if available. Shape matches
            # broadcast_can_filter_update("filter_status", ...) so the frontend
            # hook handles snapshot and live updates identically.
            if self._can_message_filter is not None:
                initial_status = self._can_message_filter.get_status()
                if initial_status:
                    await websocket.send_json(
                        {
                            "type": "filter_status",
                            "payload": {"status": initial_status},
                            "timestamp": time.time(),
                        }
                    )

            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info(
                "CAN filter WebSocket client disconnected: %s:%s",
                websocket.client.host,
                websocket.client.port,
            )
        except Exception as e:
            logger.error(
                "CAN filter WebSocket error for client %s:%s: %s",
                websocket.client.host,
                websocket.client.port,
                e,
            )
        finally:
            self.can_filter_clients.discard(websocket)
            auth_handler.remove_connection(websocket)


def create_websocket_service() -> WebSocketService:
    """
    Factory function for creating WebSocketService with dependencies.

    This would be registered with composition root and automatically
    get the repositories injected.
    """
    # In real usage, this would get the repositories from composition root
    # For now, we'll document the pattern
    msg = (
        "This factory should be registered with composition root "
        "to get automatic dependency injection of repositories"
    )
    raise NotImplementedError(msg)
