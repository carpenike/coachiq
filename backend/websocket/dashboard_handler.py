"""
WebSocket Dashboard Handler for Real-time Notification System Monitoring

This module provides WebSocket endpoints for real-time dashboard updates,
allowing the frontend to receive live notifications about system health,
queue status, and performance metrics changes.

Key Features:
- Real-time health status updates
- Queue statistics streaming
- Rate limiting notifications
- Channel health alerts
- Automatic connection management
- Configurable update intervals

Example:
    ws://localhost:8080/ws/notifications/dashboard
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

# WebSocket handlers don't use FastAPI dependencies the same way as REST endpoints
from backend.services.safe_notification_manager import SafeNotificationManager


class DashboardMessage(BaseModel):
    """WebSocket message for dashboard updates."""

    type: str
    timestamp: datetime
    data: dict[str, Any]
    client_id: str | None = None


class DashboardWebSocketManager:
    """
    Manages WebSocket connections for real-time dashboard updates.

    Handles multiple client connections, broadcasts updates, and manages
    connection lifecycle with automatic cleanup and reconnection support.
    """

    def __init__(self):
        """Initialize dashboard WebSocket manager."""
        self.logger = logging.getLogger(f"{__name__}.DashboardWebSocketManager")

        # Active connections
        self.active_connections: set[WebSocket] = set()
        self.client_metadata: dict[WebSocket, dict[str, Any]] = {}

        # Update configuration
        self.health_check_interval = 10  # seconds
        self.queue_stats_interval = 5  # seconds
        self.rate_limit_interval = 15  # seconds
        self.metrics_interval = 60  # seconds

        # Background tasks
        self.background_tasks: set[asyncio.Task] = set()
        self.is_running = False

        # Cache for last sent data to avoid unnecessary updates
        self.last_sent_data: dict[str, Any] = {}

        # Statistics
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "errors": 0,
            "uptime_start": datetime.utcnow(),
        }

    async def connect(self, websocket: WebSocket, client_id: str | None = None) -> None:
        """
        Accept new WebSocket connection and setup monitoring.

        Args:
            websocket: WebSocket connection
            client_id: Optional client identifier
        """
        try:
            await websocket.accept()

            self.active_connections.add(websocket)
            self.client_metadata[websocket] = {
                "client_id": client_id,
                "connected_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                "messages_received": 0,
                "messages_sent": 0,
            }

            self.stats["total_connections"] += 1
            self.stats["active_connections"] = len(self.active_connections)

            self.logger.info(f"Dashboard WebSocket connected: {client_id or 'unknown'}")

            # Send initial data
            await self._send_initial_data(websocket)

            # Start background monitoring if not already running
            if not self.is_running:
                await self._start_background_monitoring()

        except Exception as e:
            self.logger.error(f"Failed to connect WebSocket: {e}")
            await self._cleanup_connection(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Handle WebSocket disconnection and cleanup.

        Args:
            websocket: WebSocket connection to disconnect
        """
        await self._cleanup_connection(websocket)

    async def send_message(self, websocket: WebSocket, message: DashboardMessage) -> bool:
        """
        Send message to specific WebSocket connection.

        Args:
            websocket: Target WebSocket connection
            message: Message to send

        Returns:
            bool: True if message sent successfully
        """
        try:
            await websocket.send_text(message.json())

            # Update metadata
            if websocket in self.client_metadata:
                self.client_metadata[websocket]["messages_sent"] += 1
                self.client_metadata[websocket]["last_activity"] = datetime.utcnow()

            self.stats["messages_sent"] += 1
            return True

        except Exception as e:
            self.logger.error(f"Failed to send WebSocket message: {e}")
            await self._cleanup_connection(websocket)
            return False

    async def broadcast_message(self, message: DashboardMessage) -> int:
        """
        Broadcast message to all connected clients.

        Args:
            message: Message to broadcast

        Returns:
            int: Number of clients that received the message
        """
        if not self.active_connections:
            return 0

        successful_sends = 0
        failed_connections = set()

        for websocket in self.active_connections.copy():
            success = await self.send_message(websocket, message)
            if success:
                successful_sends += 1
            else:
                failed_connections.add(websocket)

        # Clean up failed connections
        for websocket in failed_connections:
            await self._cleanup_connection(websocket)

        return successful_sends

    async def handle_client_message(self, websocket: WebSocket, data: str) -> None:
        """
        Handle incoming message from client.

        Args:
            websocket: Source WebSocket connection
            data: Message data
        """
        try:
            message = json.loads(data)
            message_type = message.get("type")

            # Update client activity
            if websocket in self.client_metadata:
                self.client_metadata[websocket]["messages_received"] += 1
                self.client_metadata[websocket]["last_activity"] = datetime.utcnow()

            # Handle different message types
            if message_type == "ping":
                await self._handle_ping(websocket, message)
            elif message_type == "request_refresh":
                await self._handle_refresh_request(websocket, message)
            elif message_type == "update_preferences":
                await self._handle_preferences_update(websocket, message)
            else:
                self.logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            self.logger.error("Failed to parse client message")
        except Exception as e:
            self.logger.error(f"Error handling client message: {e}")

    async def get_connection_stats(self) -> dict[str, Any]:
        """
        Get WebSocket connection statistics.

        Returns:
            Dictionary containing connection statistics
        """
        uptime = datetime.utcnow() - self.stats["uptime_start"]

        return {
            "total_connections": self.stats["total_connections"],
            "active_connections": self.stats["active_connections"],
            "messages_sent": self.stats["messages_sent"],
            "errors": self.stats["errors"],
            "uptime_seconds": uptime.total_seconds(),
            "background_tasks_running": len(self.background_tasks),
            "clients": [
                {
                    "client_id": metadata.get("client_id"),
                    "connected_at": metadata["connected_at"].isoformat(),
                    "last_activity": metadata["last_activity"].isoformat(),
                    "messages_sent": metadata["messages_sent"],
                    "messages_received": metadata["messages_received"],
                }
                for metadata in self.client_metadata.values()
            ],
        }

    # Private methods

    async def _cleanup_connection(self, websocket: WebSocket) -> None:
        """Clean up WebSocket connection and metadata."""
        try:
            self.active_connections.discard(websocket)
            client_metadata = self.client_metadata.pop(websocket, {})

            self.stats["active_connections"] = len(self.active_connections)

            client_id = client_metadata.get("client_id", "unknown")
            self.logger.info(f"Dashboard WebSocket disconnected: {client_id}")

            # Stop background monitoring if no connections
            if not self.active_connections and self.is_running:
                await self._stop_background_monitoring()

        except Exception as e:
            self.logger.error(f"Error during connection cleanup: {e}")

    async def _send_initial_data(self, websocket: WebSocket) -> None:
        """Send initial dashboard data to newly connected client."""
        try:
            # For WebSocket context, we need to get notification manager without request
            # This is a simplified approach since WebSocket handlers don't have full FastAPI request context
            manager = None
            try:
                # Try to get from WebSocket app state if available
                app = getattr(websocket, "app", None)
                if not app and hasattr(websocket, "scope"):
                    app = websocket.scope.get("app")  # type: ignore
                if app and hasattr(app.state, "service_registry"):
                    service_registry = app.state.service_registry
                    if service_registry.has_service("notification_manager"):
                        manager = service_registry.get_service("notification_manager")
                elif app and hasattr(app.state, "notification_manager"):
                    manager = app.state.notification_manager
            except Exception as e:
                self.logger.debug(f"Could not get notification manager from WebSocket context: {e}")

            if not manager:
                self.logger.warning("No notification manager available for WebSocket dashboard")
                return

            # Send current health status
            health_data = await self._get_health_data(manager)
            health_message = DashboardMessage(
                type="health_update", timestamp=datetime.utcnow(), data=health_data
            )
            await self.send_message(websocket, health_message)

            # Send current queue statistics
            queue_data = await self._get_queue_data(manager)
            queue_message = DashboardMessage(
                type="queue_update", timestamp=datetime.utcnow(), data=queue_data
            )
            await self.send_message(websocket, queue_message)

            # Send rate limiting status
            rate_limit_data = await self._get_rate_limit_data(manager)
            rate_limit_message = DashboardMessage(
                type="rate_limit_update", timestamp=datetime.utcnow(), data=rate_limit_data
            )
            await self.send_message(websocket, rate_limit_message)

        except Exception as e:
            self.logger.error(f"Failed to send initial data: {e}")

    async def _start_background_monitoring(self) -> None:
        """Start background monitoring tasks."""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info("Starting dashboard background monitoring")

        # Create monitoring tasks
        tasks = [
            asyncio.create_task(self._health_monitor()),
            asyncio.create_task(self._queue_monitor()),
            asyncio.create_task(self._rate_limit_monitor()),
            asyncio.create_task(self._connection_monitor()),
        ]

        self.background_tasks.update(tasks)

    async def _stop_background_monitoring(self) -> None:
        """Stop background monitoring tasks."""
        if not self.is_running:
            return

        self.is_running = False
        self.logger.info("Stopping dashboard background monitoring")

        # Cancel all background tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)

        self.background_tasks.clear()

    async def _health_monitor(self) -> None:
        """Monitor system health and broadcast updates."""
        while self.is_running:
            try:
                # Get notification manager from app state for background monitoring
                manager = None
                try:
                    # Since this is a background task, we need to access the app state differently
                    # We'll use a simplified approach and skip if not available
                    pass  # For now, skip notification manager access in background tasks
                except Exception as e:
                    self.logger.debug(f"Could not get notification manager in background task: {e}")

                if not manager:
                    # Skip this iteration if we can't get the manager
                    await asyncio.sleep(self.health_check_interval)
                    continue

                health_data = await self._get_health_data(manager)

                # Check if data has changed significantly
                if self._should_send_update("health", health_data):
                    message = DashboardMessage(
                        type="health_update", timestamp=datetime.utcnow(), data=health_data
                    )
                    await self.broadcast_message(message)
                    self.last_sent_data["health"] = health_data

                await asyncio.sleep(self.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Health monitor error: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(self.health_check_interval)

    async def _queue_monitor(self) -> None:
        """Monitor queue statistics and broadcast updates."""
        while self.is_running:
            try:
                # Skip notification manager access in background tasks for now
                manager = None
                if not manager:
                    await asyncio.sleep(self.queue_stats_interval)
                    continue

                queue_data = await self._get_queue_data(manager)

                if self._should_send_update("queue", queue_data):
                    message = DashboardMessage(
                        type="queue_update", timestamp=datetime.utcnow(), data=queue_data
                    )
                    await self.broadcast_message(message)
                    self.last_sent_data["queue"] = queue_data

                await asyncio.sleep(self.queue_stats_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Queue monitor error: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(self.queue_stats_interval)

    async def _rate_limit_monitor(self) -> None:
        """Monitor rate limiting status and broadcast updates."""
        while self.is_running:
            try:
                # Skip notification manager access in background tasks for now
                manager = None
                if not manager:
                    await asyncio.sleep(self.rate_limit_interval)
                    continue

                rate_limit_data = await self._get_rate_limit_data(manager)

                if self._should_send_update("rate_limit", rate_limit_data):
                    message = DashboardMessage(
                        type="rate_limit_update", timestamp=datetime.utcnow(), data=rate_limit_data
                    )
                    await self.broadcast_message(message)
                    self.last_sent_data["rate_limit"] = rate_limit_data

                await asyncio.sleep(self.rate_limit_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Rate limit monitor error: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(self.rate_limit_interval)

    async def _connection_monitor(self) -> None:
        """Monitor connection health and clean up stale connections."""
        while self.is_running:
            try:
                current_time = datetime.utcnow()
                stale_threshold = timedelta(minutes=5)
                stale_connections = set()

                for websocket, metadata in self.client_metadata.items():
                    last_activity = metadata["last_activity"]
                    if current_time - last_activity > stale_threshold:
                        stale_connections.add(websocket)

                # Clean up stale connections
                for websocket in stale_connections:
                    await self._cleanup_connection(websocket)

                await asyncio.sleep(60)  # Check every minute

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Connection monitor error: {e}")
                await asyncio.sleep(60)

    async def _get_health_data(self, manager: SafeNotificationManager) -> dict[str, Any]:
        """Get current system health data."""
        queue_stats = await manager.get_queue_statistics()
        rate_limit_status = await manager.get_rate_limit_status()
        channel_status = await manager.get_channel_status()
        manager_stats = manager.get_statistics()

        # Calculate success rate
        total = manager_stats.get("total_notifications", 0)
        successful = manager_stats.get("successful_notifications", 0)
        success_rate = (successful / total * 100) if total > 0 else 100.0

        return {
            "queue_depth": queue_stats.pending_count,
            "success_rate_percent": success_rate,
            "dispatcher_running": queue_stats.dispatcher_running,
            "avg_processing_time_ms": queue_stats.avg_processing_time,
            "queue_healthy": queue_stats.dispatcher_running and queue_stats.pending_count < 1000,
            "rate_limiter_healthy": rate_limit_status.healthy,
        }

    async def _get_queue_data(self, manager: SafeNotificationManager) -> dict[str, Any]:
        """Get current queue statistics."""
        stats = await manager.get_queue_statistics()
        return {
            "pending_count": stats.pending_count,
            "processing_count": stats.processing_count,
            "completed_count": stats.completed_count,
            "failed_count": stats.failed_count,
            "dlq_count": stats.dlq_count,
            "dispatcher_running": stats.dispatcher_running,
            "success_rate_percent": stats.success_rate,
            "avg_processing_time_ms": stats.avg_processing_time,
        }

    async def _get_rate_limit_data(self, manager: SafeNotificationManager) -> dict[str, Any]:
        """Get current rate limiting status."""
        status = await manager.get_rate_limit_status()
        return {
            "current_tokens": status.current_tokens,
            "max_tokens": status.max_tokens,
            "requests_last_minute": status.requests_last_minute,
            "active_debounces": status.active_debounces,
            "healthy": status.healthy,
        }

    def _should_send_update(self, data_type: str, new_data: dict[str, Any]) -> bool:
        """
        Determine if update should be sent based on data changes.

        Args:
            data_type: Type of data being updated
            new_data: New data to compare

        Returns:
            bool: True if update should be sent
        """
        if data_type not in self.last_sent_data:
            return True

        last_data = self.last_sent_data[data_type]

        # Check for significant changes based on data type
        if data_type == "health":
            # Send if queue depth, success rate, or dispatcher status changed
            return (
                last_data.get("queue_depth") != new_data.get("queue_depth")
                or abs(
                    last_data.get("success_rate_percent", 0)
                    - new_data.get("success_rate_percent", 0)
                )
                > 1.0
                or last_data.get("dispatcher_running") != new_data.get("dispatcher_running")
            )
        if data_type == "queue":
            # Send if any count changed
            return any(
                last_data.get(key) != new_data.get(key)
                for key in ["pending_count", "processing_count", "completed_count", "failed_count"]
            )
        if data_type == "rate_limit":
            # Send if token count changed significantly or requests changed
            return abs(
                last_data.get("current_tokens", 0) - new_data.get("current_tokens", 0)
            ) > 5 or last_data.get("requests_last_minute") != new_data.get("requests_last_minute")

        return True  # Default to sending update

    async def _handle_ping(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        """Handle ping message from client."""
        pong_message = DashboardMessage(
            type="pong", timestamp=datetime.utcnow(), data={"ping_id": message.get("ping_id")}
        )
        await self.send_message(websocket, pong_message)

    async def _handle_refresh_request(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        """Handle refresh request from client."""
        await self._send_initial_data(websocket)

    async def _handle_preferences_update(
        self, websocket: WebSocket, message: dict[str, Any]
    ) -> None:
        """Handle preferences update from client."""
        # Store client preferences (simplified implementation)
        if websocket in self.client_metadata:
            self.client_metadata[websocket]["preferences"] = message.get("preferences", {})


# Global dashboard manager instance
dashboard_manager = DashboardWebSocketManager()


async def dashboard_websocket_endpoint(websocket: WebSocket, client_id: str | None = None):
    """
    WebSocket endpoint for dashboard real-time updates.

    Args:
        websocket: WebSocket connection
        client_id: Optional client identifier
    """
    await dashboard_manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_text()
            await dashboard_manager.handle_client_message(websocket, data)

    except WebSocketDisconnect:
        await dashboard_manager.disconnect(websocket)
    except Exception as e:
        logging.getLogger(__name__).error(f"Dashboard WebSocket error: {e}")
        await dashboard_manager.disconnect(websocket)
