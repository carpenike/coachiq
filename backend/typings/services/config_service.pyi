"""
Type stubs for ConfigService
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import Settings
from backend.repositories import RVCConfigRepository, SystemStateRepository

class ConfigService:
    """
    Service for managing application configuration and coach mappings.
    
    Handles loading, validation, and distribution of configuration data
    throughout the application.
    """

    _rvc_config_repo: RVCConfigRepository
    _system_state_repo: SystemStateRepository
    _settings: Settings
    _running: bool
    _config_cache: dict[str, Any]
    _coach_mapping: dict[str, Any] | None
    _rvc_spec: dict[str, Any] | None

    def __init__(
        self,
        rvc_config_repository: RVCConfigRepository,
        system_state_repository: SystemStateRepository,
        settings: Settings | None = None,
    ) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def load_coach_mapping(self, force_reload: bool = False) -> dict[str, Any]: ...

    async def load_rvc_spec(self, force_reload: bool = False) -> dict[str, Any]: ...

    async def get_coach_mapping(self) -> dict[str, Any] | None: ...

    async def get_rvc_spec(self) -> dict[str, Any] | None: ...

    async def reload_configuration(self) -> dict[str, str]: ...

    async def validate_configuration(self) -> dict[str, Any]: ...

    async def get_configuration_summary(self) -> dict[str, Any]: ...

    async def update_coach_mapping(
        self,
        entity_id: str,
        mapping_data: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def save_coach_mapping(self) -> bool: ...

    async def export_configuration(self) -> dict[str, Any]: ...

    async def import_configuration(
        self,
        config_data: dict[str, Any],
        validate: bool = True,
    ) -> dict[str, Any]: ...

    def get_config_file_path(self, config_type: str) -> Path: ...

    async def health_check(self) -> dict[str, Any]: ...

    def get_settings(self) -> Settings: ...
