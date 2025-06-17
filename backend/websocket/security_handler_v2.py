"""
Security WebSocket Handler V2

Enhanced version using the new service pattern for better dependency management
and lifecycle control.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict

from fastapi import WebSocket, WebSocketDisconnect

from backend.core.service_patterns import WebSocketHandlerBase
from backend.models.security_events import SecurityEvent
from backend.services.security_event_manager import SecurityEventManager

logger = logging.getLogger(__name__)


class SecurityWebSocketHandlerV2(WebSocketHandlerBase):
    """
    Enhanced security WebSocket handler using the new service pattern.

    This handler extends WebSocketHandlerBase to provide structured
    dependency injection and lifecycle management.
    """

    def __init__(self, security_event_manager: SecurityEventManager):
        """
        Initialize with required service dependency.

        Args:
            security_event_manager: The SecurityEventManager instance
        """
        # Pass dependencies to base class
        super().__init__(service_dependencies={
            'security_event_manager': security_event_manager
        })

        # Handler-specific state
        self.client_contexts: Dict[WebSocket, Dict[str, Any]] = {}
        self._stats_cache: Dict[str, Any] = {}
        self._last_stats_update = 0.0
        self._stats_cache_ttl = 2.0  # 2 second cache for stats

    async def _register_listeners(self) -> None:
        """Register with SecurityEventManager to receive events."""
        event_manager = self.services.get('security_event_manager')
        if not event_manager:
            raise RuntimeError("SecurityEventManager not available")

        event_manager.register_listener(
            self._handle_security_event,
            name="security_websocket_v2"
        )
        logger.info("SecurityWebSocketHandlerV2 registered with SecurityEventManager")

    async def _unregister_listeners(self) -> None:
        """Unregister from SecurityEventManager."""
        event_manager = self.services.get('security_event_manager')
        if event_manager:
            event_manager.unregister_listener(self._handle_security_event)

    async def _disconnect_client(self, client: WebSocket) -> None:
        """Disconnect a specific client."""
        try:
            await client.close()
        except Exception:
            pass  # Client may already be disconnected

        # Clean up client context
        self.client_contexts.pop(client, None)

    async def connect_client(self, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket client.

        Args:
            websocket: WebSocket connection to register
        """
        await websocket.accept()

        async with self._lock:
            self.clients.add(websocket)
            self.client_contexts[websocket] = {
                "connected_at": time.time(),
                "view_context": "overview",  # Default view
                "last_ping": time.time()
            }

        logger.info(f"Security WebSocket client connected. Total clients: {len(self.clients)}")

        # Send initial connection acknowledgment
        await self._send_to_client(websocket, {
            "type": "connection",
            "status": "connected",
            "timestamp": time.time()
        })

        # Send current stats
        await self._send_current_stats(websocket)

    async def disconnect_client(self, websocket: WebSocket) -> None:
        """
        Disconnect and unregister a WebSocket client.

        Args:
            websocket: WebSocket connection to disconnect
        """
        async with self._lock:
            self.clients.discard(websocket)
            self.client_contexts.pop(websocket, None)

        await self._disconnect_client(websocket)
        logger.info(f"Security WebSocket client disconnected. Total clients: {len(self.clients)}")

    async def handle_client(self, websocket: WebSocket) -> None:
        """
        Handle a WebSocket client connection lifecycle.

        Args:
            websocket: The WebSocket connection
        """
        await self.connect_client(websocket)

        try:
            while True:
                # Receive and process client messages
                try:
                    data = await websocket.receive_json()
                    await self._process_client_message(websocket, data)
                except json.JSONDecodeError:
                    await self._send_error(websocket, "Invalid JSON")
                except WebSocketDisconnect:
                    break

        except Exception as e:
            logger.error(f"Error handling WebSocket client: {e}")
        finally:
            await self.disconnect_client(websocket)

    async def _process_client_message(self, websocket: WebSocket, data: Dict[str, Any]) -> None:
        """Process a message from a client."""
        msg_type = data.get("type")

        if msg_type == "ping":
            # Update last ping time
            if websocket in self.client_contexts:
                self.client_contexts[websocket]["last_ping"] = time.time()

            # Send pong response
            await self._send_to_client(websocket, {
                "type": "pong",
                "timestamp": time.time()
            })

        elif msg_type == "set_view_context":
            # Update client's view context for filtered events
            view_context = data.get("context", "overview")
            if websocket in self.client_contexts:
                self.client_contexts[websocket]["view_context"] = view_context

            await self._send_to_client(websocket, {
                "type": "view_context_updated",
                "context": view_context
            })

        elif msg_type == "get_stats":
            # Send current statistics
            await self._send_current_stats(websocket)

        else:
            await self._send_error(websocket, f"Unknown message type: {msg_type}")

    async def _handle_security_event(self, event: SecurityEvent) -> None:
        """
        Handle security event from SecurityEventManager.

        This is called by the SecurityEventManager when a new event occurs.
        """
        if not self.clients:
            return  # No clients to notify

        # Prepare event data
        event_data = {
            "type": "security_event",
            "event": {
                "id": event.event_id,
                "timestamp": event.timestamp,
                "severity": event.severity.value if event.severity else None,
                "event_type": event.event_type.value if event.event_type else None,
                "source_component": event.source_component,
                "title": event.title,
                "description": event.description,
                "payload": event.payload,
                "metadata": event.event_metadata
            }
        }

        # Broadcast to all connected clients
        await self._broadcast_to_all(event_data)

        # Update cached stats (they're now stale)
        self._stats_cache.clear()

    async def _send_current_stats(self, websocket: WebSocket) -> None:
        """Send current security statistics to a client."""
        # Check cache
        now = time.time()
        if self._stats_cache and (now - self._last_stats_update) < self._stats_cache_ttl:
            stats = self._stats_cache
        else:
            # Get fresh stats from SecurityEventManager
            event_manager = self.services.get('security_event_manager')
            if event_manager:
                try:
                    stats = await event_manager.get_statistics()
                    self._stats_cache = stats
                    self._last_stats_update = now
                except Exception as e:
                    logger.error(f"Failed to get security stats: {e}")
                    stats = {"error": "Failed to retrieve statistics"}
            else:
                stats = {"error": "SecurityEventManager not available"}

        await self._send_to_client(websocket, {
            "type": "statistics",
            "stats": stats,
            "timestamp": now
        })

    async def _send_to_client(self, websocket: WebSocket, data: Dict[str, Any]) -> None:
        """Send data to a specific client."""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"Failed to send to client: {e}")
            # Client will be disconnected by handle_client

    async def _send_error(self, websocket: WebSocket, error_msg: str) -> None:
        """Send an error message to a client."""
        await self._send_to_client(websocket, {
            "type": "error",
            "error": error_msg,
            "timestamp": time.time()
        })

    async def _broadcast_to_all(self, data: Dict[str, Any]) -> None:
        """Broadcast data to all connected clients."""
        if not self.clients:
            return

        # Send to all clients concurrently
        disconnected_clients = []

        async with self._lock:
            tasks = []
            for client in self.clients:
                tasks.append(self._send_to_client(client, data))

        # Wait for all sends to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Track disconnected clients
        async with self._lock:
            for client, result in zip(list(self.clients), results):
                if isinstance(result, Exception):
                    disconnected_clients.append(client)

        # Clean up disconnected clients
        for client in disconnected_clients:
            await self.disconnect_client(client)
