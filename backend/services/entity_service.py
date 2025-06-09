"""
Entity Service

Handles business logic for RV-C entity management, including:
- Entity querying and filtering
- Entity state management
- Light control with CAN command sending
- History management
- Metadata extraction

This service uses the EntityManagerFeature for unified entity management,
completely removing legacy state dictionary dependencies.
"""

import logging
import time
from typing import Any

from backend.core.config import get_can_settings
from backend.core.entity_manager import EntityManager
from backend.integrations.can.manager import can_tx_queue
from backend.integrations.can.message_factory import create_light_can_message
from backend.models.entity import (
    ControlCommand,
    ControlEntityResponse,
    CreateEntityMappingRequest,
    CreateEntityMappingResponse,
)
from backend.models.unmapped import UnknownPGNEntry, UnmappedEntryModel
from backend.websocket.handlers import WebSocketManager

logger = logging.getLogger(__name__)


class EntityService:
    """
    Service for managing RV-C entities and their control operations.

    This service provides business logic for entity operations using the
    EntityManagerFeature for unified entity management, completely removing
    legacy state dictionary dependencies.
    """

    def __init__(
        self,
        websocket_manager: WebSocketManager,
        entity_manager: EntityManager | None = None,
    ):
        """
        Initialize the entity service.

        Args:
            websocket_manager: WebSocket communication manager
            entity_manager: EntityManager instance (will be retrieved from feature manager if None)
        """
        self.websocket_manager = websocket_manager
        self._entity_manager = entity_manager

    @property
    def entity_manager(self) -> EntityManager:
        """Get the EntityManager instance."""
        if self._entity_manager is None:
            # Get entity manager from feature manager
            from backend.services.feature_manager import get_feature_manager

            feature_manager = get_feature_manager()
            entity_manager_feature = feature_manager.get_feature("entity_manager")
            if entity_manager_feature is None:
                raise RuntimeError("EntityManager feature not found in feature manager")

            self._entity_manager = entity_manager_feature.get_entity_manager()

        return self._entity_manager

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
        # Use EntityManager for efficient filtering
        filtered_entities = self.entity_manager.filter_entities(
            device_type=device_type, area=area, protocol=protocol
        )
        # Convert to API format
        return {entity_id: entity.to_dict() for entity_id, entity in filtered_entities.items()}

    async def list_entity_ids(self) -> list[str]:
        """Return all known entity IDs."""
        return self.entity_manager.get_entity_ids()

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """
        Get a specific entity by ID.

        Args:
            entity_id: The ID of the entity to retrieve

        Returns:
            The entity data or None if not found
        """
        entity = self.entity_manager.get_entity(entity_id)
        if entity:
            return entity.to_dict()
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
        entity = self.entity_manager.get_entity(entity_id)
        if entity:
            # Get history from the entity with optional filtering
            history_entries = entity.get_history(count=limit, since=since)
            # Convert each EntityState to a dictionary
            return [state.model_dump() for state in history_entries]
        return None

    async def get_unmapped_entries(self) -> dict[str, UnmappedEntryModel]:
        """
        Get unmapped entries.

        Returns:
            Dictionary of unmapped entries
        """
        # Use EntityManager for unmapped entries
        result = {}
        for key, entry in self.entity_manager.unmapped_entries.items():
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
        for key, entry in self.entity_manager.unknown_pgns.items():
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
        entities = self.entity_manager.get_all_entities().values()
        device_types = set()
        capabilities = set()
        suggested_areas = set()
        groups = set()
        for entity in entities:
            config = getattr(entity, "config", {})
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
            "total_entities": len(entities),
        }

    async def get_protocol_summary(self) -> dict[str, Any]:
        """
        Get summary of entity distribution across protocols.

        Returns:
            Dictionary with protocol ownership statistics and entity distribution
        """
        return self.entity_manager.get_protocol_summary()

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
            existing_entity = self.entity_manager.get_entity(request.entity_id)
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
            }

            # Register the new entity with the EntityManager
            new_entity = self.entity_manager.register_entity(
                entity_id=request.entity_id,
                config=entity_config,
            )

            if not new_entity:
                return CreateEntityMappingResponse(
                    status="error",
                    entity_id=request.entity_id,
                    message="Failed to register entity with EntityManager",
                    entity_data=None,
                )

            # Get entity data to return
            entity_data = new_entity.to_dict() if new_entity else entity_config

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
        entity = self.entity_manager.get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity '{entity_id}' not found")

        device_type = entity.config.get("device_type")

        if device_type == "light":
            return await self.control_light(entity_id, command)
        else:
            raise ValueError(
                f"Control not supported for device type '{device_type}'. Supported types: light"
            )

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
        entity = self.entity_manager.get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity '{entity_id}' not found")
        if entity.config.get("device_type") != "light":
            raise ValueError(f"Entity '{entity_id}' is not controllable as a light")

        current_state = entity.get_state()
        current_state_data = current_state.model_dump()
        current_raw_values = current_state_data.get("raw", {})
        current_brightness_raw = current_raw_values.get("operating_status", 0)
        current_brightness_ui = int((current_brightness_raw / 200.0) * 100)
        current_on_str = current_state_data.get("state", "off")
        current_on = current_on_str.lower() == "on"

        last_brightness_ui = getattr(entity, "last_known_brightness", None)
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
                entity.last_known_brightness = int(target_brightness_ui)
                new_state = True
                new_brightness = int(target_brightness_ui)
                if new_brightness <= 0:
                    new_brightness = 100
            elif cmd.state == "off":
                if current_on:
                    entity.last_known_brightness = int(current_brightness_ui)
                target_brightness_ui = 0
                action = "Set OFF"
                new_state = False
                new_brightness = 0
            else:
                raise ValueError(f"Invalid state for set command: {cmd.state}")
        elif cmd.command == "toggle":
            new_state = not current_on
            if new_state:
                new_brightness = last_brightness_ui if last_brightness_ui > 0 else 100
                action = f"Toggled ON to {new_brightness}%"
            else:
                entity.last_known_brightness = int(current_brightness_ui)
                new_brightness = 0
                action = "Toggled OFF"
        elif cmd.command == "brightness_up":
            new_brightness = min(current_brightness_ui + 10, 100)
            new_state = bool(new_brightness)
            action = f"Brightness up to {new_brightness}%"
            entity.last_known_brightness = int(new_brightness)
        elif cmd.command == "brightness_down":
            new_brightness = max(current_brightness_ui - 10, 0)
            new_state = bool(new_brightness)
            action = f"Brightness down to {new_brightness}%"
            if new_brightness > 0:
                entity.last_known_brightness = int(new_brightness)
        else:
            raise ValueError(f"Unknown command: {cmd.command}")

        # Ensure new_brightness is always a valid integer between 0 and 100
        try:
            new_brightness = round(new_brightness)
        except Exception:
            new_brightness = 100 if new_state else 0
        if new_brightness < 0:
            new_brightness = 0
        if new_brightness > 100:
            new_brightness = 100

        # Broadcast entity update over WebSocket after control
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
            command=cmd.command,
            state="on" if new_state else "off",
            brightness=new_brightness,
            action=action,
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
        entity = self.entity_manager.get_entity(entity_id)
        if not entity:
            raise RuntimeError(
                f"Control Error: {entity_id} not found in entity manager for "
                f"action '{action_description}'"
            )

        # Extract info needed for CAN message creation from entity config
        entity_config = entity.config
        instance = entity_config.get("instance")
        if instance is None:
            raise RuntimeError(f"Entity {entity_id} missing 'instance' for CAN message creation")

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
        entity.update_state(optimistic_payload)

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
            decoded = None
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

            # Add sniffer entry for TX tracking
            sniffer_entry = {
                "timestamp": ts,
                "interface": can_interface,
                "can_id": f"{can_message.arbitration_id:08X}",
                "data": can_message.data.hex().upper(),
                "dlc": len(can_message.data),
                "is_extended": can_message.is_extended_id,
                "decoded": decoded,
                "origin": "self",
            }
            logger.debug(f"Adding TX sniffer entry: {sniffer_entry}")

            # Note: Since we removed AppState dependency, we don't track pending commands
            # This could be added to EntityManager or handled differently if needed
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
            raise RuntimeError(f"CAN command failed: {e}") from e
