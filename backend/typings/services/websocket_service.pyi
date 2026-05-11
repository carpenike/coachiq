"""
Type stubs for WebSocketService
"""

import asyncio
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

from backend.repositories import CANTrackingRepository, SystemStateRepository

class WebSocketService:
    """
    Service that manages WebSocket connections and broadcasting.
    
    This is a clean service implementation without Feature inheritance,
    using repository injection for all dependencies.
    """

    _can_tracking_repository: CANTrackingRepository | None
    _system_state_repository: SystemStateRepository | None
    _service_registry: Any | None
    data_clients: set[WebSocket]
    log_clients: set[WebSocket]
    can_sniffer_clients: set[WebSocket]
    network_map_clients: set[WebSocket]
    features_clients: set[WebSocket]
    can_recorder_clients: set[WebSocket]
    can_analyzer_clients: set[WebSocket]
    can_filter_clients: set[WebSocket]
    background_tasks: set[asyncio.Task]
    _running: bool

    def __init__(
        self,
        can_tracking_repository: CANTrackingRepository | None = None,
        system_state_repository: SystemStateRepository | None = None,
        service_registry: Any | None = None,
    ) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def health_check(self) -> dict[str, Any]: ...

    async def handle_data_stream(self, websocket: WebSocket) -> None: ...

    async def handle_log_stream(self, websocket: WebSocket) -> None: ...

    async def handle_can_sniffer_stream(self, websocket: WebSocket) -> None: ...

    async def handle_network_map_stream(self, websocket: WebSocket) -> None: ...

    async def handle_features_stream(self, websocket: WebSocket) -> None: ...

    async def handle_can_recorder_stream(self, websocket: WebSocket) -> None: ...

    async def handle_can_analyzer_stream(self, websocket: WebSocket) -> None: ...

    async def handle_can_filter_stream(self, websocket: WebSocket) -> None: ...

    async def broadcast_to_data_stream(self, message: dict[str, Any]) -> None: ...

    async def broadcast_to_log_stream(self, message: dict[str, Any]) -> None: ...

    async def broadcast_can_sniffer_group(self, message: dict[str, Any]) -> None: ...

    async def broadcast_network_map_update(self, message: dict[str, Any]) -> None: ...

    async def broadcast_features_update(self, message: dict[str, Any]) -> None: ...

    async def broadcast_can_recorder_status(self, message: dict[str, Any]) -> None: ...

    async def broadcast_can_analyzer_update(self, message: dict[str, Any]) -> None: ...

    async def broadcast_can_filter_update(self, message: dict[str, Any]) -> None: ...

    async def _check_token_expiry_task(self) -> None: ...

    async def _send_message_to_client(self, websocket: WebSocket, message: str) -> bool: ...

    def get_connection_stats(self) -> dict[str, int]: ...
