"""
Type stubs for EntityService
"""

from typing import Any, Dict, List, Optional

from backend.models.entity import (
    ControlCommand,
    ControlEntityResponse,
    CreateEntityMappingRequest,
    CreateEntityMappingResponse,
)
from backend.models.unmapped import UnknownPGNEntry, UnmappedEntryModel
from backend.repositories import DiagnosticsRepository, EntityStateRepository, RVCConfigRepository
from backend.websocket.handlers import WebSocketManager

class EntityService:
    """
    Service for managing RV-C entities using repository pattern.
    
    This service provides business logic for entity operations using repositories
    directly, eliminating AppState dependency.
    """

    websocket_manager: WebSocketManager
    _entity_state_repo: EntityStateRepository
    _rvc_config_repo: RVCConfigRepository
    _diagnostics_repo: DiagnosticsRepository

    def __init__(
        self,
        websocket_manager: WebSocketManager,
        entity_state_repository: EntityStateRepository,
        rvc_config_repository: RVCConfigRepository,
        diagnostics_repository: DiagnosticsRepository,
    ) -> None: ...

    async def list_entities(
        self,
        device_type: str | None = None,
        area: str | None = None,
        protocol: str | None = None,
    ) -> dict[str, dict[str, Any]]: ...

    async def list_entity_ids(self) -> list[str]: ...

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None: ...

    async def control_entity(
        self, entity_id: str, command: ControlCommand
    ) -> ControlEntityResponse: ...

    async def delete_entity(self, entity_id: str) -> dict[str, str]: ...

    async def clear_all_entities(self) -> dict[str, str]: ...

    async def list_unknowns(self) -> list[UnknownPGNEntry]: ...

    async def get_unknown(self, unknown_id: str) -> UnmappedEntryModel | None: ...

    async def map_unknown(
        self, request: CreateEntityMappingRequest
    ) -> CreateEntityMappingResponse: ...

    async def delete_unknown(self, unknown_id: str) -> dict[str, str]: ...

    async def reset_entity_statistics(self, entity_id: str) -> dict[str, Any]: ...

    async def reset_all_statistics(self) -> dict[str, str]: ...

    async def get_entity_statistics(self, entity_id: str) -> dict[str, Any]: ...

    async def get_all_statistics(self) -> dict[str, dict[str, Any]]: ...

    async def export_configuration(self) -> dict[str, Any]: ...

    async def import_configuration(self, config: dict[str, Any]) -> dict[str, Any]: ...
