"""
Security WebSocket Handler

Provides real-time security event broadcasting to connected clients.
Simple implementation for small user base with basic security dashboard needs.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from backend.models.security_events import SecurityEvent
from backend.services.security_event_manager import SecurityEventManager

logger = logging.getLogger(__name__)


class SecurityWebSocketHandler:
    """
    Handles WebSocket connections for security monitoring dashboard.

    Provides real-time updates for:
    - Security event stream
    - Aggregated statistics
    - Incident notifications
    - System health status

    ARCHITECTURE NOTE: This handler is designed as an application-scoped singleton.
    It is instantiated once at application startup and persists for the entire
    lifespan. This ensures no security events are missed between startup and the
    first client connection.

    CRITICAL LIMITATION: This implementation relies on in-memory broadcasting and
    is only suitable for single-process deployments. For multi-worker deployments,
    a message broker backend (e.g., Redis Pub/Sub) would be required.
    """

    def __init__(self, event_manager: SecurityEventManager | None = None):
        """Initialize the security WebSocket handler.

        Args:
            event_manager: SecurityEventManager instance for dependency injection
        """
        self.clients: set[WebSocket] = set()
        self.client_contexts: dict[WebSocket, dict[str, Any]] = {}
        self._stats_cache: dict[str, Any] = {}
        self._last_stats_update = 0.0
        self._stats_cache_ttl = 2.0  # 2 second cache for stats

        # Store injected SecurityEventManager
        self._event_manager = event_manager
        self._is_registered = False
        # Lock for thread-safe access to active connections
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        """Initialize the handler and register with SecurityEventManager."""
        try:
            if not self._event_manager:
                raise RuntimeError("SecurityEventManager not provided to SecurityWebSocketHandler")

            await self._event_manager.subscribe(
                self._handle_security_event, name="security_websocket"
            )
            self._is_registered = True
            logger.info("SecurityWebSocketHandler registered with SecurityEventManager")
        except Exception as e:
            logger.error(f"Failed to register SecurityWebSocketHandler: {e}")

    async def shutdown(self) -> None:
        """Cleanup handler and disconnect all clients."""
        if self._is_registered and self._event_manager:
            await self._event_manager.unsubscribe(self._handle_security_event)

        # Disconnect all clients
        for client in list(self.clients):
            await self.disconnect_client(client)

        logger.info("SecurityWebSocketHandler shutdown complete")

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
                "last_ping": time.time(),
            }
            client_count = len(self.clients)

        logger.info(f"Security WebSocket client connected. Total: {client_count}")

        # Send initial data to new client
        await self._send_initial_data(websocket)

    async def disconnect_client(self, websocket: WebSocket) -> None:
        """
        Disconnect and cleanup a WebSocket client.

        Args:
            websocket: WebSocket connection to disconnect
        """
        async with self._lock:
            self.clients.discard(websocket)
            self.client_contexts.pop(websocket, None)
            remaining_clients = len(self.clients)

        try:
            await websocket.close()
        except Exception:
            pass  # Already closed

        logger.info(f"Security WebSocket client disconnected. Remaining: {remaining_clients}")

    async def handle_client_message(self, websocket: WebSocket, message: str) -> None:
        """
        Handle incoming messages from WebSocket clients.

        Args:
            websocket: WebSocket that sent the message
            message: JSON message string
        """
        try:
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "set_view_context":
                await self._handle_set_view_context(websocket, data)
            elif message_type == "ping":
                await self._handle_ping(websocket, data)
            elif message_type == "get_stats":
                await self._handle_get_stats(websocket)
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message from client: {message}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")

    async def _handle_set_view_context(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """Handle view context change from client."""
        view = data.get("payload", {}).get("view", "overview")

        if websocket in self.client_contexts:
            self.client_contexts[websocket]["view_context"] = view

        # Send acknowledgment
        await self._send_to_client(
            websocket, {"type": "ack", "request_id": data.get("request_id"), "status": "success"}
        )

        logger.debug(f"Client view context changed to: {view}")

    async def _handle_ping(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        """Handle ping message from client."""
        if websocket in self.client_contexts:
            self.client_contexts[websocket]["last_ping"] = time.time()

        # Send pong response
        await self._send_to_client(
            websocket,
            {"type": "pong", "request_id": data.get("request_id"), "timestamp": time.time()},
        )

    async def _handle_get_stats(self, websocket: WebSocket) -> None:
        """Handle stats request from client."""
        stats = await self._get_current_stats()
        await self._send_to_client(
            websocket, {"type": "stats_response", "data": stats, "timestamp": time.time()}
        )

    async def _send_initial_data(self, websocket: WebSocket) -> None:
        """Send initial dashboard data to new client."""
        try:
            # Send current statistics
            stats = await self._get_current_stats()
            await self._send_to_client(
                websocket,
                {
                    "type": "initial_data",
                    "data": {
                        "stats": stats,
                        "server_time": time.time(),
                        "connection_id": id(websocket),
                    },
                },
            )

            # Send recent events if available
            if self._event_manager:
                recent_events = self._event_manager.get_recent_events(limit=20)
                if recent_events:
                    await self._send_to_client(
                        websocket,
                        {
                            "type": "recent_events",
                            "data": [event.dict() for event in recent_events],
                            "count": len(recent_events),
                        },
                    )

        except Exception as e:
            logger.error(f"Error sending initial data: {e}")

    async def _handle_security_event(self, event: SecurityEvent) -> None:
        """
        Handle security event from SecurityEventManager.

        Args:
            event: SecurityEvent to broadcast to clients
        """
        if not self.clients:
            return  # No clients to notify

        # Create broadcast message
        message = {"type": "security_event", "data": event.dict(), "timestamp": time.time()}

        # Send to all connected clients
        await self._broadcast_to_all(message)

        # Also trigger stats update for critical events
        if event.severity in ["high", "critical"]:
            stats = await self._get_current_stats()
            stats_message = {"type": "stats_update", "data": stats, "timestamp": time.time()}
            await self._broadcast_to_all(stats_message)

    async def _get_current_stats(self) -> dict[str, Any]:
        """Get current security statistics with caching."""
        current_time = time.time()

        # Use cached stats if recent
        if (current_time - self._last_stats_update) < self._stats_cache_ttl and self._stats_cache:
            return self._stats_cache

        try:
            if self._event_manager:
                # Get stats from SecurityEventManager
                manager_stats = self._event_manager.get_statistics()
                event_stats = self._event_manager.get_event_stats()

                stats = {
                    "manager": manager_stats,
                    "events": event_stats.dict(),
                    "system_health": {
                        "security_monitoring": "healthy",
                        "event_processing": manager_stats.get("performance", {}).get(
                            "delivery_success_rate", 0
                        )
                        > 0.95,
                        "connected_clients": len(self.clients),
                    },
                    "updated_at": current_time,
                }
            else:
                # Fallback stats if manager not available
                stats = {
                    "manager": {"events_published": 0, "events_delivered": 0},
                    "events": {"total_events": 0, "events_last_hour": 0},
                    "system_health": {
                        "security_monitoring": "unknown",
                        "event_processing": False,
                        "connected_clients": len(self.clients),
                    },
                    "updated_at": current_time,
                }

            # Cache the stats
            self._stats_cache = stats
            self._last_stats_update = current_time

            return stats

        except Exception as e:
            logger.error(f"Error getting security stats: {e}")
            return {"error": "Failed to get statistics", "updated_at": current_time}

    async def _send_to_client(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        """
        Send message to specific client.

        Args:
            websocket: Target client WebSocket
            message: Message to send
        """
        try:
            await websocket.send_text(json.dumps(message))
        except WebSocketDisconnect:
            await self.disconnect_client(websocket)
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")
            await self.disconnect_client(websocket)

    async def _broadcast_to_all(self, message: dict[str, Any]) -> None:
        """
        Broadcast message to all connected clients.

        This method is designed for robustness in a safety-critical system:
        1. It copies the list of connections under a lock to prevent race conditions
           while minimizing lock hold time.
        2. It uses asyncio.gather with return_exceptions=True to ensure that one
           failed connection does not stop the broadcast to others.
        3. It logs failures for observability and removes dead connections.

        Args:
            message: Message to broadcast
        """
        # Copy the connection list under lock to minimize lock hold time
        async with self._lock:
            connections_to_send = list(self.clients)

        if not connections_to_send:
            return

        # Prepare send tasks
        tasks = [self._send_to_client(client, message) for client in connections_to_send]

        # Execute tasks concurrently and collect results
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Post-broadcast cleanup and error handling
        for client, result in zip(connections_to_send, results, strict=False):
            if isinstance(result, Exception):
                logger.warning(f"Failed to send message to client: {result}")
                # This connection is likely dead. Remove it safely.
                await self.disconnect_client(client)

    async def send_system_notification(self, notification_type: str, data: dict[str, Any]) -> None:
        """
        Send system notification to all clients.

        Args:
            notification_type: Type of notification (emergency_stop, system_health, etc.)
            data: Notification data
        """
        message = {
            "type": "system_notification",
            "notification_type": notification_type,
            "data": data,
            "timestamp": time.time(),
        }

        await self._broadcast_to_all(message)
        logger.info(f"Sent system notification: {notification_type}")

    def get_client_count(self) -> int:
        """Get number of connected clients."""
        return len(self.clients)

    def get_handler_stats(self) -> dict[str, Any]:
        """Get handler statistics."""
        current_time = time.time()

        return {
            "connected_clients": len(self.clients),
            "is_registered": self._is_registered,
            "stats_cache_age": current_time - self._last_stats_update,
            "clients_by_view": {
                view: sum(
                    1 for ctx in self.client_contexts.values() if ctx.get("view_context") == view
                )
                for view in ["overview", "incident", "forensics"]
            },
        }


# Global instance
_security_websocket_handler: SecurityWebSocketHandler | None = None


def get_security_websocket_handler() -> SecurityWebSocketHandler:
    """Get the global security WebSocket handler instance.

    Note: This is a legacy function for backward compatibility.
    Prefer dependency injection when possible.
    """
    global _security_websocket_handler
    if _security_websocket_handler is None:
        # For backward compatibility, try to get SecurityEventManager globally
        # This will be removed once all callers use dependency injection
        try:
            from backend.services.security_event_manager import get_security_event_manager

            event_manager = get_security_event_manager()
            _security_websocket_handler = SecurityWebSocketHandler(event_manager)
        except RuntimeError:
            # Create without event manager - will fail on startup() if not set later
            _security_websocket_handler = SecurityWebSocketHandler()
    return _security_websocket_handler


async def initialize_security_websocket_handler(
    event_manager: SecurityEventManager | None = None,
) -> SecurityWebSocketHandler:
    """Initialize the global security WebSocket handler.

    Args:
        event_manager: Optional SecurityEventManager for dependency injection
    """
    global _security_websocket_handler

    if event_manager:
        # Use provided event manager (preferred)
        _security_websocket_handler = SecurityWebSocketHandler(event_manager)
    else:
        # Fall back to legacy behavior
        _security_websocket_handler = get_security_websocket_handler()

    await _security_websocket_handler.startup()
    return _security_websocket_handler
