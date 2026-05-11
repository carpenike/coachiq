"""
Type stubs for CANBusService
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import Settings
from backend.core.safety_interfaces import (
    SafeStateAction,
    SafetyAware,
    SafetyClassification,
    SafetyStatus,
)
from backend.integrations.rvc import BAMHandler
from backend.repositories.can_tracking_repository import CANTrackingRepository
from backend.repositories.system_state_repository import SystemStateRepository

class CANBusService(SafetyAware):
    """
    Service that manages CAN bus integration.
    
    This is a clean service implementation without Feature inheritance,
    using repository injection for all dependencies.
    """

    _can_tracking_repository: CANTrackingRepository
    _system_state_repository: SystemStateRepository
    settings: Settings
    _running: bool
    config: dict[str, Any]
    _listeners: list[Any]
    _task: asyncio.Task | None
    _simulation_task: asyncio.Task | None
    _deduplicator: Any | None
    decoder_map: dict[int, dict]
    device_lookup: dict[tuple[str, str], dict]
    status_lookup: dict[tuple[str, str], dict]
    pgn_hex_to_name_map: dict[str, str]
    raw_device_mapping: dict
    entity_id_lookup: dict[str, dict]
    bam_handler: BAMHandler | None
    pattern_engine: Any | None
    anomaly_detector: Any | None

    def __init__(
        self,
        can_tracking_repository: CANTrackingRepository,
        system_state_repository: SystemStateRepository,
        can_anomaly_detector: Any | None = None,
    ) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def enter_safe_state(self) -> None: ...

    def get_safety_status(self) -> SafetyStatus: ...

    def is_running(self) -> bool: ...

    async def health_check(self) -> dict[str, Any]: ...

    async def get_interfaces(self) -> list[str]: ...

    async def get_statistics(self) -> dict[str, Any]: ...

    async def send_message(self, can_id: int, data: list[int]) -> bool: ...

    async def process_message(self, msg: Any) -> None: ...

    def decode_rvc_message(self, msg: Any) -> dict[str, Any] | None: ...

    async def load_rvc_decoder_data(self, rvc_spec: dict[str, Any]) -> None: ...

    async def run_simulation(self) -> None: ...

    async def monitor_interfaces(self) -> None: ...
