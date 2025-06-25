"""
Entity Service - Repository Pattern Implementation

Service for managing RV-C entities using clean repository pattern
with no legacy AppState dependencies.
"""

import logging
import time
from typing import Any

from backend.core.config import get_can_settings
from backend.integrations.can.manager import can_tx_queue
from backend.integrations.can.message_factory import create_light_can_message
from backend.models.entity import (
    ControlCommand,
    ControlEntityResponse,
    CreateEntityMappingRequest,
    CreateEntityMappingResponse,
)
from backend.models.unmapped import UnknownPGNEntry, UnmappedEntryModel
from backend.repositories import DiagnosticsRepository, EntityStateRepository, RVCConfigRepository
from backend.websocket.handlers import WebSocketManager

logger = logging.getLogger(__name__)


class EntityService:
    """
    Service for managing RV-C entities using repository pattern.

    This service provides business logic for entity operations using repositories
    directly, eliminating AppState dependency.
    """

    def __init__(
        self,
        websocket_manager: WebSocketManager,
        entity_state_repository: EntityStateRepository,
        rvc_config_repository: RVCConfigRepository,
        diagnostics_repository: DiagnosticsRepository,
    ):
        """
        Initialize the entity service with repository dependencies.

        Args:
            websocket_manager: WebSocket communication manager
            entity_state_repository: Repository for entity state management
            rvc_config_repository: Repository for RVC configuration data
            diagnostics_repository: Repository for runtime diagnostic data
        """
        self.websocket_manager = websocket_manager
        self._entity_state_repo = entity_state_repository
        self._rvc_config_repo = rvc_config_repository
        self._diagnostics_repo = diagnostics_repository
        logger.info("EntityService initialized with repositories")

    async def list_entities(
        self,
        device_type: str | None = None,
        area: str | None = None,
        protocol: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        List all entities with optional filtering.

        Args:
            device_type: Optional filter by entity device_type
            area: Optional filter by entity suggested_area
            protocol: Optional filter by protocol ownership

        Returns:
            Dictionary of entities matching the filter criteria
        """
        # Get all entity states from repository
        all_states = self._entity_state_repo.get_entity_states()

        # Apply filters
        filtered_entities = {}
        for entity_id, entity_state in all_states.items():
            # Apply device_type filter
            if device_type and entity_state.get("device_type") != device_type:
                continue
            # Apply area filter
            if area and entity_state.get("suggested_area") != area:
                continue
            # Apply protocol filter (default to "rvc" if not specified)
            entity_protocol = entity_state.get("protocol", "rvc")
            if protocol and entity_protocol != protocol:
                continue

            filtered_entities[entity_id] = entity_state

        return filtered_entities

    async def list_entity_ids(self) -> list[str]:
        """Return all known entity IDs."""
        return self._entity_state_repo.get_all_entity_ids()

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """
        Get a specific entity by ID.

        Args:
            entity_id: The ID of the entity to retrieve

        Returns:
            The entity data or None if not found
        """
        entity = self._entity_state_repo.get_entity(entity_id)
        if entity:
            return entity.to_dict() if hasattr(entity, "to_dict") else entity
        return None

    async def get_entity_history(
        self,
        entity_id: str,
        since: float | None = None,
        limit: int | None = 1000,
    ) -> list[dict[str, Any]] | None:
        """
        Get entity history with optional filtering.

        Args:
            entity_id: The ID of the entity
            since: Optional Unix timestamp to filter entries newer than this
            limit: Optional limit on the number of points to return

        Returns:
            List of entity history entries or None if entity not found
        """
        # Use the repository's get_entity_history method
        history = self._entity_state_repo.get_entity_history(entity_id, count=limit)
        if history is not None:
            return history
        return None

    async def get_unmapped_entries(self) -> dict[str, UnmappedEntryModel]:
        """
        Get unmapped entries.

        Returns:
            Dictionary of unmapped entries
        """
        # Use diagnostics repository for unmapped entries
        result = {}
        for key, entry in self._diagnostics_repo.get_unmapped_entries().items():
            # Fill missing fields with dummy/test values for API contract
            entry = {
                "pgn_hex": entry.get("pgn_hex", "0xFF00"),
                "pgn_name": entry.get("pgn_name", "Unknown"),
                "dgn_hex": entry.get("dgn_hex", "0xFF00"),
                "dgn_name": entry.get("dgn_name", "Unknown"),
                "instance": entry.get("instance", "1"),
                "last_data_hex": entry.get("last_data_hex", "00"),
                "decoded_signals": entry.get("decoded_signals", {}),
                "first_seen_timestamp": entry.get("first_seen_timestamp", 0.0),
                "last_seen_timestamp": entry.get("last_seen_timestamp", 0.0),
                "count": entry.get("count", 1),
                "suggestions": entry.get("suggestions", []),
                "spec_entry": entry.get("spec_entry", {}),
            }
            result[key] = UnmappedEntryModel(**entry)
        return result

    async def get_unknown_pgns(self) -> dict[str, UnknownPGNEntry]:
        """
        Get unknown PGN entries.

        Returns:
            Dictionary of unknown PGN entries
        """
        result = {}
        for key, entry in self._diagnostics_repo.get_unknown_pgns().items():
            entry = {
                "arbitration_id_hex": entry.get("arbitration_id_hex", "0x1FFFF"),
                "first_seen_timestamp": entry.get("first_seen_timestamp", 0.0),
                "last_seen_timestamp": entry.get("last_seen_timestamp", 0.0),
                "count": entry.get("count", 1),
                "last_data_hex": entry.get("last_data_hex", "00"),
            }
            result[key] = UnknownPGNEntry(**entry)
        return result

    async def get_metadata(self) -> dict:
        """
        Get metadata about available entity attributes.

        Returns:
            Dictionary with lists of available values for each metadata category
        """
        # Aggregate metadata from all entities
        all_entities = self._entity_state_repo.get_all_entities()
        device_types = set()
        capabilities = set()
        suggested_areas = set()
        groups = set()
        for entity in all_entities.values():
            # Get entity config
            config = entity.config if hasattr(entity, "config") else entity
            if isinstance(config, dict):
                if config.get("device_type"):
                    device_types.add(config["device_type"])
                if config.get("capabilities"):
                    capabilities.update(config["capabilities"])
                if config.get("suggested_area"):
                    suggested_areas.add(config["suggested_area"])
                if config.get("groups"):
                    groups.update(config["groups"])
        return {
            "device_types": sorted(device_types),
            "capabilities": sorted(capabilities),
            "suggested_areas": sorted(suggested_areas),
            "groups": sorted(groups),
            "total_entities": len(all_entities),
        }

    async def get_protocol_summary(self) -> dict[str, Any]:
        """
        Get summary of entity distribution across protocols.

        Returns:
            Dictionary with protocol ownership statistics and entity distribution
        """
        all_entities = self._entity_state_repo.get_all_entities()
        protocol_summary = {}

        for entity_id, entity in all_entities.items():
            # Get entity config
            config = entity.config if hasattr(entity, "config") else entity
            if isinstance(config, dict):
                protocol = config.get("protocol", "rvc")
                if protocol not in protocol_summary:
                    protocol_summary[protocol] = {"count": 0, "device_types": set(), "entities": []}
                protocol_summary[protocol]["count"] += 1
                protocol_summary[protocol]["device_types"].add(config.get("device_type", "unknown"))
                protocol_summary[protocol]["entities"].append(entity_id)

        # Convert sets to lists for JSON serialization
        for protocol_data in protocol_summary.values():
            protocol_data["device_types"] = sorted(list(protocol_data["device_types"]))

        return protocol_summary

    async def create_entity_mapping(
        self, request: CreateEntityMappingRequest
    ) -> CreateEntityMappingResponse:
        """
        Create a new entity mapping from an unmapped entry.

        Args:
            request: CreateEntityMappingRequest with entity configuration details

        Returns:
            CreateEntityMappingResponse: Response with status and entity information

        Raises:
            ValueError: If entity_id already exists or invalid configuration
            RuntimeError: If entity registration fails
        """
        try:
            # Check if entity already exists
            existing_entity = self._entity_state_repo.get_entity(request.entity_id)
            if existing_entity:
                return CreateEntityMappingResponse(
                    status="error",
                    entity_id=request.entity_id,
                    message=f"Entity '{request.entity_id}' already exists",
                    entity_data=None,
                )

            # Create entity configuration
            entity_config = {
                "entity_id": request.entity_id,
                "friendly_name": request.friendly_name,
                "device_type": request.device_type,
                "suggested_area": request.suggested_area,
                "capabilities": request.capabilities or [],
                "notes": request.notes or "",
                "state": "unknown",
                "raw": {},
                "timestamp": None,
                "value": {},
            }

            # Create EntityConfig object and register with repository
            from backend.models.entity_model import EntityConfig as EntityConfigModel

            entity_config_obj = EntityConfigModel(
                device_type=request.device_type,
                suggested_area=request.suggested_area,
                friendly_name=request.friendly_name,
                capabilities=request.capabilities or [],
                groups=[],
            )

            # Register the entity with the repository's entity manager
            self._entity_state_repo.entity_manager.register_entity(
                request.entity_id, entity_config_obj
            )

            # Get entity data to return
            entity_data = entity_config

            logger.info(f"Successfully created entity mapping: {request.entity_id}")

            # Broadcast the new entity via WebSocket
            broadcast_data = {
                "type": "entity_created",
                "entity_id": request.entity_id,
                "data": entity_data,
            }
            await self.websocket_manager.broadcast_to_data_clients(broadcast_data)

            return CreateEntityMappingResponse(
                status="success",
                entity_id=request.entity_id,
                message=f"Entity '{request.entity_id}' created successfully",
                entity_data=entity_data,
            )

        except Exception as e:
            logger.error(f"Failed to create entity mapping for {request.entity_id}: {e}")
            return CreateEntityMappingResponse(
                status="error",
                entity_id=request.entity_id,
                message=f"Failed to create entity: {e!s}",
                entity_data=None,
            )

    async def control_entity(
        self, entity_id: str, command: ControlCommand
    ) -> ControlEntityResponse:
        """
        Control an entity by routing to the appropriate device-specific control method.

        Args:
            entity_id: The ID of the entity to control
            command: Control command with action details

        Returns:
            ControlEntityResponse: Response with status and action description

        Raises:
            ValueError: If entity not found or device type not supported
            RuntimeError: If control command fails
        """
        entity = self._entity_state_repo.get_entity(entity_id)
        if not entity:
            msg = f"Entity '{entity_id}' not found"
            raise ValueError(msg)

        device_type = (
            entity.config.get("device_type")
            if hasattr(entity, "config")
            else entity.get("device_type")
        )

        if device_type == "light":
            return await self.control_light(entity_id, command)
        msg = f"Control not supported for device type '{device_type}'. Supported types: light"
        raise ValueError(msg)

    async def control_light(self, entity_id: str, cmd: ControlCommand) -> ControlEntityResponse:
        """
        Control a light entity.

        Args:
            entity_id: The ID of the light entity to control
            cmd: Control command with action details

        Returns:
            ControlEntityResponse: Response with status and action description

        Raises:
            ValueError: If entity not found or command invalid
            RuntimeError: If CAN command fails to send
        """
        entity = self._entity_state_repo.get_entity(entity_id)
        if not entity:
            msg = f"Entity '{entity_id}' not found"
            raise ValueError(msg)

        entity_config = entity.config if hasattr(entity, "config") else entity
        if entity_config.get("device_type") != "light":
            msg = f"Entity '{entity_id}' is not controllable as a light"
            raise ValueError(msg)

        # Get current state
        current_state = entity.get_state() if hasattr(entity, "get_state") else entity
        if hasattr(current_state, "model_dump"):
            current_state_data = current_state.model_dump()
        else:
            current_state_data = (
                current_state if isinstance(current_state, dict) else {"raw": {}, "state": "off"}
            )

        current_raw_values = current_state_data.get("raw", {})
        current_brightness_raw = current_raw_values.get("operating_status", 0)
        current_brightness_ui = int((current_brightness_raw / 200.0) * 100)
        current_on_str = current_state_data.get("state", "off")
        current_on = current_on_str.lower() == "on"

        # Get last known brightness from repository
        last_brightness_ui = self._entity_state_repo.get_last_known_brightness(entity_id)
        if (
            last_brightness_ui is None
            or not isinstance(last_brightness_ui, int | float)
            or last_brightness_ui <= 0
        ):
            last_brightness_ui = 100
        last_brightness_ui = int(last_brightness_ui)

        target_brightness_ui = cmd.brightness if cmd.brightness is not None else last_brightness_ui
        action = ""
        new_state = current_on
        new_brightness = current_brightness_ui

        # If 'set' command is sent with brightness but no state, treat as 'on'
        if cmd.command == "set" and cmd.state is None and cmd.brightness is not None:
            cmd.state = "on"

        if cmd.command == "set":
            if cmd.state == "on":
                if cmd.brightness is None:
                    target_brightness_ui = last_brightness_ui
                else:
                    target_brightness_ui = cmd.brightness
                action = f"Set ON to {target_brightness_ui}%"
                # Update last known brightness
                self._entity_state_repo.set_last_known_brightness(
                    entity_id, int(target_brightness_ui)
                )
                new_state = True
                new_brightness = int(target_brightness_ui)
                if new_brightness <= 0:
                    new_brightness = 100
            elif cmd.state == "off":
                if current_on:
                    # Update last known brightness in entity state
                    entity["last_known_brightness"] = int(current_brightness_ui)
                    await self._entity_state_repo.save_entity_state(entity_id, entity)
                target_brightness_ui = 0
                action = "Set OFF"
                new_state = False
                new_brightness = 0
            else:
                msg = f"Invalid state for set command: {cmd.state}"
                raise ValueError(msg)
        elif cmd.command == "toggle":
            new_state = not current_on
            if new_state:
                new_brightness = last_brightness_ui if last_brightness_ui > 0 else 100
                action = f"Toggled ON to {new_brightness}%"
            else:
                # Update last known brightness
                self._entity_state_repo.set_last_known_brightness(
                    entity_id, int(current_brightness_ui)
                )
                new_brightness = 0
                action = "Toggled OFF"
        elif cmd.command == "brightness_up":
            new_brightness = min(current_brightness_ui + 10, 100)
            new_state = bool(new_brightness)
            action = f"Brightness up to {new_brightness}%"
            self._entity_state_repo.set_last_known_brightness(entity_id, int(new_brightness))
        elif cmd.command == "brightness_down":
            new_brightness = max(current_brightness_ui - 10, 0)
            new_state = bool(new_brightness)
            action = f"Brightness down to {new_brightness}%"
            if new_brightness > 0:
                self._entity_state_repo.set_last_known_brightness(entity_id, int(new_brightness))
        else:
            msg = f"Unknown command: {cmd.command}"
            raise ValueError(msg)

        # Ensure new_brightness is always a valid integer between 0 and 100
        try:
            new_brightness = round(new_brightness)
        except Exception:
            new_brightness = 100 if new_state else 0
        new_brightness = max(new_brightness, 0)
        new_brightness = min(new_brightness, 100)

        # Execute the command
        return await self._execute_light_command(
            entity_id=entity_id,
            target_brightness_ui=new_brightness,
            action_description=action,
        )

    async def _execute_light_command(
        self,
        entity_id: str,
        target_brightness_ui: int,
        action_description: str,
    ) -> ControlEntityResponse:
        """
        Execute a light control command by sending CAN messages.

        Args:
            entity_id: The entity ID
            target_brightness_ui: Target brightness (0-100)
            action_description: Description of the action being taken

        Returns:
            Control response with status and details
        """
        # Get entity information for CAN message creation
        entity = self._entity_state_repo.get_entity(entity_id)
        if not entity:
            msg = (
                f"Control Error: {entity_id} not found in repository for "
                f"action '{action_description}'"
            )
            raise RuntimeError(msg)

        # Extract info needed for CAN message creation from entity config
        entity_config = entity.config if hasattr(entity, "config") else entity
        instance = entity_config.get("instance") if isinstance(entity_config, dict) else None
        if instance is None:
            msg = f"Entity {entity_id} missing 'instance' for CAN message creation"
            raise RuntimeError(msg)

        # Get entity's logical interface and resolve to physical interface
        logical_interface = entity_config.get(
            "interface", "house"
        )  # Default to "house" if not specified
        can_settings = get_can_settings()

        # Resolve logical interface to physical interface using interface mappings
        physical_interface = can_settings.interface_mappings.get(logical_interface)
        if not physical_interface:
            logger.warning(
                f"No mapping found for logical interface '{logical_interface}', falling back to first available interface"
            )
            physical_interface = (
                can_settings.all_interfaces[0] if can_settings.all_interfaces else "can0"
            )

        # Create optimistic update payload
        ts = time.time()
        optimistic_state_str = "on" if target_brightness_ui > 0 else "off"
        optimistic_raw_val = int((target_brightness_ui / 100.0) * 200)

        optimistic_payload = {
            "entity_id": entity_id,
            "timestamp": ts,
            "state": optimistic_state_str,
            "raw": optimistic_raw_val,
            "brightness_pct": target_brightness_ui,
            "suggested_area": entity_config.get("suggested_area", "unknown"),
            "device_type": entity_config.get("device_type", "unknown"),
            "capabilities": entity_config.get("capabilities", []),
            "friendly_name": entity_config.get("friendly_name", entity_id),
            "groups": entity_config.get("groups", []),
        }

        # Update entity state optimistically
        self._entity_state_repo.update_entity_state_and_history(entity_id, optimistic_payload)

        # Broadcast update via WebSocket (correct structure)
        await self.websocket_manager.broadcast_to_data_clients(
            {
                "type": "entity_update",
                "data": {
                    "entity_id": entity_id,
                    "entity_data": entity.to_dict(),
                },
            }
        )

        # Create and send CAN message
        try:
            can_message = create_light_can_message(
                pgn=0x1F0D0,  # Standard PGN for DML_COMMAND_2 light commands
                instance=instance,
                brightness_can_level=optimistic_raw_val,
            )

            # Use the resolved physical interface for this entity
            can_interface = physical_interface
            logger.debug(
                f"Sending CAN message for {entity_id} on interface {can_interface} (logical: {logical_interface})"
            )

            await can_tx_queue.put((can_message, can_interface))

            # Note: We don't have access to can_tracking_repo here for sniffer entries
            # This could be added as another dependency if needed
            logger.debug("Successfully sent CAN command")

            # Broadcast the state update via WebSocket (correct structure)
            await self.websocket_manager.broadcast_to_data_clients(
                {
                    "type": "entity_update",
                    "data": {
                        "entity_id": entity_id,
                        "entity_data": entity.to_dict(),
                    },
                }
            )

            return ControlEntityResponse(
                status="success",
                entity_id=entity_id,
                command=action_description,
                state=optimistic_state_str,
                brightness=target_brightness_ui,
                action=action_description,
            )
        except Exception as e:
            logger.error(f"CAN command failed for {entity_id}: {e}")
            msg = f"CAN command failed: {e}"
            raise RuntimeError(msg) from e


def create_entity_service() -> EntityService:
    """
    Factory function for creating EntityService with dependencies.

    This would be registered with ServiceRegistry and automatically
    get the repositories injected.
    """
    # In real usage, this would get the repositories from ServiceRegistry
    # For now, we'll document the pattern
    raise NotImplementedError(
        "This factory should be registered with ServiceRegistry "
        "to get automatic dependency injection of repositories"
    )
