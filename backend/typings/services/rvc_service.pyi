"""
Type stubs for RVCService
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from backend.repositories import CANTrackingRepository, RVCConfigRepository

class RVCService:
    """
    Service for RV-C protocol-specific operations using repository pattern.
    
    This service handles:
    - RV-C protocol message translation
    - Instance tracking for multi-instance devices
    - Protocol-specific filters and routing
    
    Uses repositories directly, eliminating AppState dependency.
    """

    _rvc_config_repo: RVCConfigRepository
    _can_tracking_repo: CANTrackingRepository | None
    _running: bool
    _processing_task: asyncio.Task | None
    _instance_mapping: dict[str, dict[int, str]]
    _message_handlers: dict[int, Any]

    def __init__(
        self,
        rvc_config_repository: RVCConfigRepository,
        can_tracking_repository: CANTrackingRepository | None = None,
    ) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def _init_message_handlers(self) -> None: ...

    async def _process_messages(self) -> None: ...

    async def health_check(self) -> dict[str, Any]: ...

    def decode_message(self, can_id: int, data: list[int]) -> dict[str, Any] | None: ...

    def encode_message(self, dgn: int, source: int, data: dict[str, Any]) -> tuple[int, list[int]]: ...

    def register_instance(self, device_type: str, instance: int, entity_id: str) -> None: ...

    def get_instance_mapping(self, device_type: str) -> dict[int, str]: ...

    def clear_instance_mappings(self) -> None: ...

    async def handle_rvc_message(self, msg: dict[str, Any]) -> None: ...

    def get_rvc_statistics(self) -> dict[str, Any]: ...
