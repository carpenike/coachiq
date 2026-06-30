"""
Entity Service - Repository Pattern Implementation

Service for managing RV-C entities using clean repository pattern.

Authorization model
-------------------
Mutating methods (``control_entity``, ``control_light``,
``create_entity_mapping``) require an authenticated user context. FastAPI
routers MUST already validate the caller's session and pass the user dict
in via ``user_context``; we re-validate here as defense in depth so a
router that forgets to authenticate cannot accidentally reach hardware
control or configuration mutations.

Roles understood here:
- ``user`` / ``operator`` / ``admin``: may call ``control_entity`` /
  ``control_light``.
- ``admin`` only: may call ``create_entity_mapping`` (configuration op
  that changes which hardware our API can address).
"""

import logging
import time
from dataclasses import dataclass
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


class _AuthorizationError(PermissionError):
    """Raised when a service operation is invoked without sufficient privileges."""


def _require_role(
    user_context: dict | None,
    *,
    allowed_roles: tuple[str, ...] = ("user", "operator", "admin"),
    operation: str,
) -> None:
    """Defense-in-depth role check at the service boundary.

    Routers should already enforce auth via ``Depends(get_authenticated_*)``,
    but services must never trust that. Raises ``_AuthorizationError``
    (a ``PermissionError`` subclass) when the caller is unauthenticated
    or lacks the required role.
    """
    if not user_context:
        msg = f"Authentication required for {operation}"
        raise _AuthorizationError(msg)
    role = user_context.get("role")
    if role not in allowed_roles:
        msg = f"Role {role!r} not permitted for {operation}; requires one of {allowed_roles}"
        raise _AuthorizationError(msg)


@dataclass(frozen=True, slots=True)
class _LightCommandDecision:
    """Pure result of resolving a light ``ControlCommand`` against state.

    Built by :meth:`EntityService._resolve_light_command` and consumed by
    :meth:`EntityService._apply_light_command_side_effects` +
    :meth:`EntityService._execute_light_command`. Splitting the decision
    out as plain data lets the brightness/state branching logic be
    unit-tested in isolation without mocking the entity repo or the CAN
    bus; see the light control resolver tests.

    Attributes:
        new_state: Target ON/OFF state (True = on).
        new_brightness: Target brightness, clamped to 0..100.
        action: Human-readable action string surfaced in the response
            (e.g. ``"Set ON to 75%"``, ``"Toggled OFF"``).
        persist_last_known: If non-None, the orchestrator should call
            ``set_last_known_brightness(entity_id, value)``. Used by
            ``set on``, ``toggle off``, ``brightness_up``, and the
            >0 branch of ``brightness_down``.
        persist_state_payload_brightness: If True, the orchestrator
            should write the *current* brightness into
            ``entity['last_known_brightness']`` and persist via
            ``save_entity_state``. Used only by the legacy
            ``set off`` branch when the light was previously on.
            (See :meth:`EntityService._apply_light_command_side_effects`
            for why this dual persistence path exists.)
    """

    new_state: bool
    new_brightness: int
    action: str
    persist_last_known: int | None = None
    persist_state_payload_brightness: bool = False

    @staticmethod
    def _clamp_brightness(value: float, *, fallback_on_state: bool) -> int:
        """Clamp brightness to 0..100, with a sane fallback on TypeError."""
        try:
            rounded = round(value)
        except Exception:
            rounded = 100 if fallback_on_state else 0
        return max(0, min(100, int(rounded)))

    @classmethod
    def from_set(
        cls,
        cmd: "ControlCommand",
        current_on: bool,
        last_brightness_ui: int,
    ) -> "_LightCommandDecision":
        """Resolve ``command='set'`` (state required: 'on' or 'off')."""
        if cmd.state == "on":
            target = int(cmd.brightness) if cmd.brightness is not None else last_brightness_ui
            new_brightness = cls._clamp_brightness(target, fallback_on_state=True)
            # Defensive: legacy code remapped 0 -> 100 here so 'on at 0%'
            # didn't silently turn the light off.
            if new_brightness <= 0:
                new_brightness = 100
            return cls(
                new_state=True,
                new_brightness=new_brightness,
                action=f"Set ON to {target}%",
                persist_last_known=new_brightness,
            )
        if cmd.state == "off":
            return cls(
                new_state=False,
                new_brightness=0,
                action="Set OFF",
                # Only persist the previous brightness if the light was
                # actually ON -- matches pre-refactor branch.
                persist_state_payload_brightness=current_on,
            )
        msg = f"Invalid state for set command: {cmd.state}"
        raise ValueError(msg)

    @classmethod
    def from_toggle(
        cls,
        current_on: bool,
        current_brightness_ui: int,
        last_brightness_ui: int,
    ) -> "_LightCommandDecision":
        """Resolve ``command='toggle'``."""
        new_state = not current_on
        if new_state:
            new_brightness = last_brightness_ui if last_brightness_ui > 0 else 100
            return cls(
                new_state=True,
                new_brightness=cls._clamp_brightness(new_brightness, fallback_on_state=True),
                action=f"Toggled ON to {new_brightness}%",
            )
        return cls(
            new_state=False,
            new_brightness=0,
            action="Toggled OFF",
            persist_last_known=int(current_brightness_ui),
        )

    @classmethod
    def from_brightness_step(
        cls,
        current_brightness_ui: int,
        delta: int,
    ) -> "_LightCommandDecision":
        """Resolve ``command='brightness_up'`` (delta=+10) or ``'brightness_down'`` (delta=-10).

        Persists the new brightness only when it ends up > 0; that way
        ``brightness_down`` clear to 0 doesn't overwrite the stored
        last-known brightness with 0 (matching pre-refactor semantics
        for both directions: ``brightness_up`` always persists,
        ``brightness_down`` persists only above 0).
        """
        new_brightness = max(0, min(100, current_brightness_ui + delta))
        new_state = bool(new_brightness)
        direction = "up" if delta >= 0 else "down"
        # Match pre-refactor persistence: up always persists; down only
        # persists when result > 0.
        persist = new_brightness if (delta > 0 or new_brightness > 0) else None
        return cls(
            new_state=new_state,
            new_brightness=new_brightness,
            action=f"Brightness {direction} to {new_brightness}%",
            persist_last_known=persist,
        )


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
        self,
        request: CreateEntityMappingRequest,
        user_context: dict[str, Any] | None = None,
    ) -> CreateEntityMappingResponse:
        """
        Create a new entity mapping from an unmapped entry.

        Admin-only: configuration ops that change which hardware our API
        can address must require the strongest available role.

        Args:
            request: CreateEntityMappingRequest with entity configuration details
            user_context: Authenticated user dict (router must populate)

        Returns:
            CreateEntityMappingResponse: Response with status and entity information
        """
        try:
            _require_role(
                user_context,
                allowed_roles=("admin",),
                operation=f"create_entity_mapping({request.entity_id})",
            )
        except _AuthorizationError as e:
            logger.warning("Authorization denied for create_entity_mapping: %s", e)
            return CreateEntityMappingResponse(
                status="error",
                entity_id=request.entity_id,
                message=str(e),
                entity_data=None,
            )

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
        self,
        entity_id: str,
        command: ControlCommand,
        user_context: dict[str, Any] | None = None,
    ) -> ControlEntityResponse:
        """
        Control an entity by routing to the appropriate device-specific control method.

        Requires an authenticated user (``user`` / ``operator`` / ``admin``).

        Args:
            entity_id: The ID of the entity to control
            command: Control command with action details
            user_context: Authenticated user dict (router must populate)

        Returns:
            ControlEntityResponse: Response with status and action description

        Raises:
            ValueError: If entity not found or device type not supported
            PermissionError: If user_context is missing or lacks required role
            RuntimeError: If control command fails
        """
        _require_role(user_context, operation=f"control_entity({entity_id})")

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
            return await self.control_light(entity_id, command, user_context=user_context)
        msg = f"Control not supported for device type '{device_type}'. Supported types: light"
        raise ValueError(msg)

    async def control_light(
        self,
        entity_id: str,
        cmd: ControlCommand,
        user_context: dict[str, Any] | None = None,
    ) -> ControlEntityResponse:
        """
        Control a light entity.

        Requires an authenticated user (``user`` / ``operator`` / ``admin``).

        This is the orchestration entry point. The brightness/state decision
        tree lives in the pure helper :meth:`_resolve_light_command`; the
        side effects (last-known-brightness persistence) live in
        :meth:`_apply_light_command_side_effects`. Splitting it this way
        keeps each step under the ruff complexity caps and makes the
        decision tree unit-testable in isolation (see
        the light control resolver tests).

        Args:
            entity_id: The ID of the light entity to control
            cmd: Control command with action details
            user_context: Authenticated user dict (router must populate)

        Returns:
            ControlEntityResponse: Response with status and action description

        Raises:
            ValueError: If entity not found or command invalid
            PermissionError: If user_context is missing or lacks required role
            RuntimeError: If CAN command fails to send
        """
        _require_role(user_context, operation=f"control_light({entity_id})")

        entity = self._entity_state_repo.get_entity(entity_id)
        if not entity:
            msg = f"Entity '{entity_id}' not found"
            raise ValueError(msg)

        entity_config = entity.config if hasattr(entity, "config") else entity
        if entity_config.get("device_type") != "light":
            msg = f"Entity '{entity_id}' is not controllable as a light"
            raise ValueError(msg)

        # Snapshot current state into plain values the resolver can reason about.
        current_on, current_brightness_ui = self._read_light_current_state(entity)

        # Look up last-known brightness for restore-on-toggle semantics.
        last_brightness_ui = self._read_last_known_brightness(entity_id)

        # Pure decision tree: figure out what should happen, no I/O.
        decision = self._resolve_light_command(
            cmd=cmd,
            current_on=current_on,
            current_brightness_ui=current_brightness_ui,
            last_brightness_ui=last_brightness_ui,
        )

        # Apply the resolver's persistence intents (last-known-brightness
        # writes), then dispatch the CAN command.
        await self._apply_light_command_side_effects(
            entity_id=entity_id,
            entity=entity,
            current_brightness_ui=current_brightness_ui,
            decision=decision,
        )

        return await self._execute_light_command(
            entity_id=entity_id,
            target_brightness_ui=decision.new_brightness,
            action_description=decision.action,
        )

    @staticmethod
    def _read_light_current_state(entity: Any) -> tuple[bool, int]:
        """Return ``(current_on, current_brightness_ui)`` from an entity.

        Tolerates both real ``Entity`` instances and the dict-shaped
        legacy form some callers still pass.
        """
        current_state = entity.get_state() if hasattr(entity, "get_state") else entity
        if hasattr(current_state, "model_dump"):
            current_state_data = current_state.model_dump()
        elif isinstance(current_state, dict):
            current_state_data = current_state
        else:
            current_state_data = {"raw": {}, "state": "off"}

        current_raw_values = current_state_data.get("raw", {})
        current_brightness_raw = current_raw_values.get("operating_status", 0)
        # RV-C operating_status is 0..200 (half-percent); UI uses 0..100.
        current_brightness_ui = int((current_brightness_raw / 200.0) * 100)
        current_on = current_state_data.get("state", "off").lower() == "on"
        return current_on, current_brightness_ui

    def _read_last_known_brightness(self, entity_id: str) -> int:
        """Return the stored last-known brightness, defaulting to 100.

        Defaults to 100 when the repo returns ``None`` / a non-numeric /
        a non-positive value -- preserves the legacy
        ``control_light`` semantics where 'unknown last brightness'
        means 'turn on at full' rather than 'leave off'.
        """
        last_brightness_ui = self._entity_state_repo.get_last_known_brightness(entity_id)
        if (
            last_brightness_ui is None
            or not isinstance(last_brightness_ui, int | float)
            or last_brightness_ui <= 0
        ):
            return 100
        return int(last_brightness_ui)

    @staticmethod
    def _resolve_light_command(
        cmd: ControlCommand,
        current_on: bool,
        current_brightness_ui: int,
        last_brightness_ui: int,
    ) -> "_LightCommandDecision":
        """Pure decision tree: map ``(cmd, current_state, last_state)`` to an action.

        Returns a :class:`_LightCommandDecision` describing the new
        state, the action label, and a per-branch persistence intent
        the orchestrator should apply. No I/O; safe to unit-test.

        IMPORTANT: this function MUTATES ``cmd.state`` in place to
        normalize the legacy 'set with brightness but no state' case
        (treat as state='on'). That mutation is preserved verbatim
        from the pre-#112 implementation to avoid changing observable
        behavior in this refactor.

        Raises:
            ValueError: if the command is unknown or a 'set' has an
                unrecognized ``state`` value.
        """
        # Normalize 'set' with brightness but no state -> implicit on.
        if cmd.command == "set" and cmd.state is None and cmd.brightness is not None:
            cmd.state = "on"

        if cmd.command == "set":
            return _LightCommandDecision.from_set(cmd, current_on, last_brightness_ui)
        if cmd.command == "toggle":
            return _LightCommandDecision.from_toggle(
                current_on, current_brightness_ui, last_brightness_ui
            )
        if cmd.command == "brightness_up":
            return _LightCommandDecision.from_brightness_step(current_brightness_ui, delta=10)
        if cmd.command == "brightness_down":
            return _LightCommandDecision.from_brightness_step(current_brightness_ui, delta=-10)

        msg = f"Unknown command: {cmd.command}"
        raise ValueError(msg)

    async def _apply_light_command_side_effects(
        self,
        entity_id: str,
        entity: Any,
        current_brightness_ui: int,
        decision: "_LightCommandDecision",
    ) -> None:
        """Persist any side effects requested by the resolver.

        Two distinct persistence paths exist (preserved from the
        pre-refactor code):

        - ``set_last_known_brightness`` -- the repository's dedicated
          last-known-brightness column; called for ``set on``,
          ``toggle off``, ``brightness_up``, and ``brightness_down``.
        - ``entity['last_known_brightness'] + save_entity_state`` --
          the entity-state-payload form; called only for ``set off``
          when the light was on. This dual path predates this PR; if
          the divergence ever causes a real bug, that's a separate
          cleanup.
        """
        if decision.persist_last_known is not None:
            self._entity_state_repo.set_last_known_brightness(
                entity_id, int(decision.persist_last_known)
            )
        if decision.persist_state_payload_brightness:
            # Preserve legacy 'set off' branch: stash current brightness
            # in the entity dict, then save the whole entity.
            entity["last_known_brightness"] = int(current_brightness_ui)
            await self._entity_state_repo.save_entity_state(entity_id, entity)

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

    This would be registered with composition root and automatically
    get the repositories injected.
    """
    # In real usage, this would get the repositories from composition root
    # For now, we'll document the pattern
    raise NotImplementedError(
        "This factory should be registered with composition root "
        "to get automatic dependency injection of repositories"
    )
