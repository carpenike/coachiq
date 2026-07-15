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
from backend.integrations.can.message_factory import (
    create_ac_load_can_message,
    create_light_can_message,
    create_thermostat_can_message,
)
from backend.integrations.rvc import climate_units
from backend.models.entity import (
    ControlCommand,
    ControlEntityResponse,
    CreateEntityMappingRequest,
    CreateEntityMappingResponse,
)
from backend.models.unmapped import UnknownPGNEntry, UnmappedEntryModel
from backend.repositories import DiagnosticsRepository, RVCConfigRepository
from backend.repositories.entity_repository import EntityRuntimeStateRepository
from backend.services.system.event_broker import EventBroker

logger = logging.getLogger(__name__)


class _AuthorizationError(PermissionError):
    """Raised when a service operation is invoked without sufficient privileges."""


def _require_role(
    user_context: dict[str, Any] | None,
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


@dataclass(frozen=True, slots=True)
class _ClimateCommandDecision:
    """Pure result of resolving a climate ``ControlCommand`` against live state.

    THERMOSTAT_COMMAND_1 carries the zone's complete state in one frame, so
    the decision holds every field the encoder needs — requested changes
    merged over the zone's current raw signals. Built by
    :meth:`EntityService._resolve_climate_command`, consumed by
    :meth:`EntityService._execute_climate_command`.
    """

    operating_mode: int
    fan_mode: int
    schedule_mode: int
    fan_speed_raw: int
    setpoint_heat_raw: int
    setpoint_cool_raw: int
    action: str
    state_label: str


class EntityService:
    """
    Service for managing RV-C entities using repository pattern.

    This service provides business logic for entity operations using repositories
    directly, eliminating AppState dependency.
    """

    def __init__(
        self,
        event_broker: EventBroker,
        entity_state_repository: EntityRuntimeStateRepository,
        rvc_config_repository: RVCConfigRepository,
        diagnostics_repository: DiagnosticsRepository,
    ):
        """
        Initialize the entity service with repository dependencies.

        Args:
            event_broker: SSE event broker for realtime state push
            entity_state_repository: Repository for entity state management
            rvc_config_repository: Repository for RVC configuration data
            diagnostics_repository: Repository for runtime diagnostic data
        """
        self.event_broker = event_broker
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
        # Get all entity states from the async repository wired by the composition root.
        all_states = await self._entity_state_repo.get_all_states()

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
        return list((await self._entity_state_repo.get_all_states()).keys())

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """
        Get a specific entity by ID.

        Args:
            entity_id: The ID of the entity to retrieve

        Returns:
            The entity data or None if not found
        """
        return await self._entity_state_repo.get_entity_state(entity_id)

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
        del entity_id, since, limit
        return []

    async def get_unmapped_entries(self) -> dict[str, UnmappedEntryModel]:
        """
        Get unmapped entries.

        Returns:
            Dictionary of unmapped entries
        """
        # Use diagnostics repository for unmapped entries
        result = {}
        for key, source_entry in self._diagnostics_repo.get_unmapped_entries().items():
            # Fill missing fields with dummy/test values for API contract
            normalized_entry = {
                "pgn_hex": source_entry.get("pgn_hex", "0xFF00"),
                "pgn_name": source_entry.get("pgn_name", "Unknown"),
                "dgn_hex": source_entry.get("dgn_hex", "0xFF00"),
                "dgn_name": source_entry.get("dgn_name", "Unknown"),
                "instance": source_entry.get("instance", "1"),
                "last_data_hex": source_entry.get("last_data_hex", "00"),
                "decoded_signals": source_entry.get("decoded_signals", {}),
                "first_seen_timestamp": source_entry.get("first_seen_timestamp", 0.0),
                "last_seen_timestamp": source_entry.get("last_seen_timestamp", 0.0),
                "count": source_entry.get("count", 1),
                "suggestions": source_entry.get("suggestions", []),
                "spec_entry": source_entry.get("spec_entry", {}),
            }
            result[key] = UnmappedEntryModel(**normalized_entry)
        return result

    async def get_unknown_pgns(self) -> dict[str, UnknownPGNEntry]:
        """
        Get unknown PGN entries.

        Returns:
            Dictionary of unknown PGN entries
        """
        result = {}
        for key, source_entry in self._diagnostics_repo.get_unknown_pgns().items():
            normalized_entry = {
                "arbitration_id_hex": source_entry.get("arbitration_id_hex", "0x1FFFF"),
                "first_seen_timestamp": source_entry.get("first_seen_timestamp", 0.0),
                "last_seen_timestamp": source_entry.get("last_seen_timestamp", 0.0),
                "count": source_entry.get("count", 1),
                "last_data_hex": source_entry.get("last_data_hex", "00"),
            }
            result[key] = UnknownPGNEntry(**normalized_entry)
        return result

    async def get_metadata(self) -> dict[str, Any]:
        """
        Get metadata about available entity attributes.

        Returns:
            Dictionary with lists of available values for each metadata category
        """
        # Aggregate metadata from all entity states
        all_entities = await self._entity_state_repo.get_all_states()
        device_types = set()
        capabilities = set()
        suggested_areas = set()
        groups = set()
        for config in all_entities.values():
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
        all_entities = await self._entity_state_repo.get_all_states()
        protocol_summary = {}

        for entity_id, config in all_entities.items():
            if isinstance(config, dict):
                protocol = config.get("protocol", "rvc")
                if protocol not in protocol_summary:
                    protocol_summary[protocol] = {"count": 0, "device_types": set(), "entities": []}
                protocol_summary[protocol]["count"] += 1
                protocol_summary[protocol]["device_types"].add(config.get("device_type", "unknown"))
                protocol_summary[protocol]["entities"].append(entity_id)

        # Convert sets to lists for JSON serialization
        for protocol_data in protocol_summary.values():
            protocol_data["device_types"] = sorted(protocol_data["device_types"])

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
            existing_entity = await self._entity_state_repo.get_entity_state(request.entity_id)
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
                "suggested_area": request.suggested_area or "Unknown",
                "capabilities": request.capabilities or [],
                "notes": request.notes or "",
                "state": "unknown",
                "raw": {},
                "timestamp": None,
                "value": {},
            }

            await self._entity_state_repo.save_entity_state(request.entity_id, entity_config)

            # Get entity data to return
            entity_data = entity_config

            logger.info("Successfully created entity mapping: %s", request.entity_id)

            await self.event_broker.publish(
                "entity_created",
                {"entity_id": request.entity_id, "data": entity_data},
            )

            return CreateEntityMappingResponse(
                status="success",
                entity_id=request.entity_id,
                message=f"Entity '{request.entity_id}' created successfully",
                entity_data=entity_data,
            )

        except Exception as e:
            logger.error("Failed to create entity mapping for %s: %s", request.entity_id, e)
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

        entity = await self._entity_state_repo.get_entity_state(entity_id)
        if not entity:
            msg = f"Entity '{entity_id}' not found"
            raise ValueError(msg)

        device_type = entity.get("device_type")

        if device_type == "light":
            return await self.control_light(entity_id, command, user_context=user_context)
        if device_type == "climate":
            return await self.control_climate(entity_id, command, user_context=user_context)
        if device_type == "ac_load":
            return await self.control_ac_load(entity_id, command, user_context=user_context)
        msg = (
            f"Control not supported for device type '{device_type}'. "
            "Supported types: light, climate, ac_load"
        )
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

        entity = await self._entity_state_repo.get_entity_state(entity_id)
        if not entity:
            msg = f"Entity '{entity_id}' not found"
            raise ValueError(msg)

        entity_config = entity
        if entity_config.get("device_type") != "light":
            msg = f"Entity '{entity_id}' is not controllable as a light"
            raise ValueError(msg)

        # Snapshot current state into plain values the resolver can reason about.
        current_on, current_brightness_ui = self._read_light_current_state(entity)

        # Look up last-known brightness for restore-on-toggle semantics.
        last_brightness_ui = await self._read_last_known_brightness(entity_id)

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

    async def control_climate(
        self,
        entity_id: str,
        cmd: ControlCommand,
        user_context: dict[str, Any] | None = None,
    ) -> ControlEntityResponse:
        """
        Control a thermostat zone (device_type ``climate``).

        Climate zones only support ``set`` with ``parameters``; recognized
        keys: ``setpoint_f`` (drives heat and cool together, matching how the
        G6 keeps them in lockstep), ``setpoint_heat_f`` / ``setpoint_cool_f``,
        ``mode`` (off/cool/heat/auto/fan_only), ``fan_mode`` (auto/on) and
        ``fan_speed_pct`` (0-100).

        THERMOSTAT_COMMAND_1 carries the full zone state in one frame, so
        unchanged fields are filled from the zone's live RX state rather than
        relying on the Firefly G6 honoring RV-C "no change" sentinels. That
        also means a zone cannot be commanded until its status has been seen
        on the bus at least once.
        """
        _require_role(user_context, operation=f"control_climate({entity_id})")

        entity = await self._entity_state_repo.get_entity_state(entity_id)
        if not entity:
            msg = f"Entity '{entity_id}' not found"
            raise ValueError(msg)
        if entity.get("device_type") != "climate":
            msg = f"Entity '{entity_id}' is not controllable as a climate zone"
            raise ValueError(msg)

        if cmd.command != "set":
            msg = f"Climate zones only support the 'set' command, got '{cmd.command}'"
            raise ValueError(msg)

        current = self._read_climate_current_raw(entity_id, entity)
        decision = self._resolve_climate_command(cmd.parameters or {}, current)

        return await self._execute_climate_command(
            entity_id=entity_id,
            entity=entity,
            decision=decision,
        )

    @staticmethod
    def _read_climate_current_raw(entity_id: str, entity: dict[str, Any]) -> dict[str, int]:
        """Snapshot the zone's live raw thermostat signals for command fill-in."""
        raw = entity.get("raw") or {}
        current: dict[str, int] = {}
        missing: list[str] = []
        for field in (
            "operating_mode",
            "fan_mode",
            "schedule_mode",
            "fan_speed",
            "setpoint_heat",
            "setpoint_cool",
        ):
            value = raw.get(field)
            try:
                current[field] = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                missing.append(field)
        # schedule_mode is the only field we can safely default: the G6
        # broadcasts 0 (disabled) for every zone.
        if "schedule_mode" in missing:
            missing.remove("schedule_mode")
            current["schedule_mode"] = 0
        if missing:
            msg = (
                f"No live thermostat state for '{entity_id}' yet (missing {missing}); "
                "cannot build a full THERMOSTAT_COMMAND_1 frame. Wait for the zone's "
                "status broadcast (every ~5s when the CAN bus is up)."
            )
            raise ValueError(msg)
        return current

    @staticmethod
    def _resolve_climate_command(  # noqa: C901 - flat parameter validation tree
        params: dict[str, Any], current: dict[str, int]
    ) -> "_ClimateCommandDecision":
        """Pure decision tree: merge requested changes over the live zone state."""
        allowed = {
            "setpoint_f",
            "setpoint_heat_f",
            "setpoint_cool_f",
            "mode",
            "fan_mode",
            "fan_speed_pct",
        }
        unknown = set(params) - allowed
        if unknown:
            msg = f"Unknown climate parameters {sorted(unknown)}; allowed: {sorted(allowed)}"
            raise ValueError(msg)
        if not params:
            msg = f"Climate 'set' requires parameters; allowed: {sorted(allowed)}"
            raise ValueError(msg)

        operating_mode = current["operating_mode"]
        fan_mode = current["fan_mode"]
        fan_speed_raw = current["fan_speed"]
        setpoint_heat_raw = current["setpoint_heat"]
        setpoint_cool_raw = current["setpoint_cool"]
        changes: list[str] = []

        if "mode" in params:
            label = str(params["mode"]).lower()
            if label not in climate_units.OPERATING_MODE_RAW:
                msg = (
                    f"Unknown climate mode '{label}'; "
                    f"allowed: {sorted(climate_units.OPERATING_MODE_RAW)}"
                )
                raise ValueError(msg)
            operating_mode = climate_units.OPERATING_MODE_RAW[label]
            changes.append(f"mode {label}")

        if "fan_mode" in params:
            label = str(params["fan_mode"]).lower()
            if label not in climate_units.FAN_MODE_RAW:
                msg = f"Unknown fan_mode '{label}'; allowed: {sorted(climate_units.FAN_MODE_RAW)}"
                raise ValueError(msg)
            fan_mode = climate_units.FAN_MODE_RAW[label]
            changes.append(f"fan {label}")

        if "fan_speed_pct" in params:
            pct = float(params["fan_speed_pct"])
            if not 0 <= pct <= climate_units.FAN_SPEED_MAX_PCT:
                msg = f"fan_speed_pct must be 0-{climate_units.FAN_SPEED_MAX_PCT}, got {pct}"
                raise ValueError(msg)
            fan_speed_raw = round(pct * 2)
            changes.append(f"fan speed {pct:g}%")

        def _setpoint_raw(key: str) -> int:
            fahrenheit = float(params[key])
            if not climate_units.SETPOINT_MIN_F <= fahrenheit <= climate_units.SETPOINT_MAX_F:
                msg = (
                    f"{key} must be {climate_units.SETPOINT_MIN_F:g}-"
                    f"{climate_units.SETPOINT_MAX_F:g} F, got {fahrenheit:g}"
                )
                raise ValueError(msg)
            return climate_units.f_to_raw_temp(fahrenheit)

        if "setpoint_f" in params:
            setpoint_heat_raw = setpoint_cool_raw = _setpoint_raw("setpoint_f")
            changes.append(f"setpoint {float(params['setpoint_f']):g}F")
        if "setpoint_heat_f" in params:
            setpoint_heat_raw = _setpoint_raw("setpoint_heat_f")
            changes.append(f"heat setpoint {float(params['setpoint_heat_f']):g}F")
        if "setpoint_cool_f" in params:
            setpoint_cool_raw = _setpoint_raw("setpoint_cool_f")
            changes.append(f"cool setpoint {float(params['setpoint_cool_f']):g}F")

        return _ClimateCommandDecision(
            operating_mode=operating_mode,
            fan_mode=fan_mode,
            schedule_mode=current["schedule_mode"],
            fan_speed_raw=fan_speed_raw,
            setpoint_heat_raw=setpoint_heat_raw,
            setpoint_cool_raw=setpoint_cool_raw,
            action="; ".join(changes),
            state_label=climate_units.OPERATING_MODE_LABELS.get(operating_mode, "unknown"),
        )

    async def _execute_climate_command(
        self,
        entity_id: str,
        entity: dict[str, Any],
        decision: "_ClimateCommandDecision",
    ) -> ControlEntityResponse:
        """Send THERMOSTAT_COMMAND_1 and apply the optimistic state update."""
        instance = entity.get("instance")
        if instance is None:
            msg = f"Entity {entity_id} missing 'instance' for CAN message creation"
            raise RuntimeError(msg)

        physical_interface = self._resolve_physical_interface(entity)

        # Optimistic update mirrors the RX shaping in can_bus_service so the
        # UI reflects the command immediately; the G6's next status broadcast
        # confirms (or corrects) it.
        raw = dict(entity.get("raw") or {})
        raw.update(
            {
                "operating_mode": decision.operating_mode,
                "fan_mode": decision.fan_mode,
                "schedule_mode": decision.schedule_mode,
                "fan_speed": decision.fan_speed_raw,
                "setpoint_heat": decision.setpoint_heat_raw,
                "setpoint_cool": decision.setpoint_cool_raw,
            }
        )
        raw.update(climate_units.derive_climate_fields(raw))

        entity.update(
            {
                "timestamp": time.time(),
                "state": decision.state_label,
                "raw": raw,
            }
        )
        await self._entity_state_repo.save_entity_state(entity_id, entity)
        persisted_entity = await self._entity_state_repo.get_entity_state(entity_id)
        await self.event_broker.publish(
            "entity_update",
            {"entity_id": entity_id, "entity_data": persisted_entity or entity},
        )

        try:
            can_message = create_thermostat_can_message(
                instance=int(instance),
                operating_mode=decision.operating_mode,
                fan_mode=decision.fan_mode,
                schedule_mode=decision.schedule_mode,
                fan_speed_raw=decision.fan_speed_raw,
                setpoint_heat_raw=decision.setpoint_heat_raw,
                setpoint_cool_raw=decision.setpoint_cool_raw,
            )
            await can_tx_queue.put((can_message, physical_interface))
            logger.debug(
                "Sent THERMOSTAT_COMMAND_1 for %s (instance %s) on %s: %s",
                entity_id,
                instance,
                physical_interface,
                decision.action,
            )
        except Exception as e:
            logger.error("CAN command failed for %s: %s", entity_id, e)
            msg = f"CAN command failed: {e}"
            raise RuntimeError(msg) from e

        return ControlEntityResponse(
            status="success",
            entity_id=entity_id,
            command="set",
            state=decision.state_label,
            brightness=0,
            action=decision.action,
        )

    async def control_ac_load(
        self,
        entity_id: str,
        cmd: ControlCommand,
        user_context: dict[str, Any] | None = None,
    ) -> ControlEntityResponse:
        """
        Control a generic energy-managed AC load (device_type ``ac_load``).

        On the 2021 Aspire 44R these are the Aqua-Hot electric element
        (instance 0xD4) and burner (instance 0xD2). Supports ``set`` (with
        ``state`` on/off) and ``toggle``, emitting AC_LOAD_COMMAND (1FFBE)
        with level 0xC8 (on) / 0x00 (off).

        Turning a load OFF is honored immediately and latches. Turning it ON
        is a *request*: the coach's energy manager grants it only when the
        power budget allows and may shed it (reported as state ``shed``).
        Verified on the wire 2026-07-05; see docs/can-re-findings.md.
        """
        _require_role(user_context, operation=f"control_ac_load({entity_id})")

        entity = await self._entity_state_repo.get_entity_state(entity_id)
        if not entity:
            msg = f"Entity '{entity_id}' not found"
            raise ValueError(msg)
        if entity.get("device_type") != "ac_load":
            msg = f"Entity '{entity_id}' is not controllable as an AC load"
            raise ValueError(msg)

        if cmd.command == "toggle":
            currently_on = str(entity.get("state")) in ("on", "shed")
            target_on = not currently_on
        elif cmd.command == "set":
            if cmd.state not in ("on", "off"):
                msg = f"AC load 'set' requires state on/off, got {cmd.state!r}"
                raise ValueError(msg)
            target_on = cmd.state == "on"
        else:
            msg = f"AC load supports 'set'/'toggle', got '{cmd.command}'"
            raise ValueError(msg)

        instance = entity.get("instance")
        if instance is None:
            msg = f"Entity {entity_id} missing 'instance' for CAN message creation"
            raise RuntimeError(msg)
        physical_interface = self._resolve_physical_interface(entity)

        level = climate_units.AC_LOAD_LEVEL_ON if target_on else climate_units.AC_LOAD_LEVEL_OFF
        action = f"{'on' if target_on else 'off'}"

        # Optimistic update. OFF is reliable; for ON we optimistically show
        # "on" but the AC_LOAD_STATUS echo will correct it to "shed" if the
        # energy manager defers it.
        new_raw = dict(entity.get("raw") or {})
        new_raw["operating_status"] = level
        new_raw.update(climate_units.derive_ac_load_fields(new_raw))
        entity.update(
            {
                "timestamp": time.time(),
                "state": "on" if target_on else "off",
                "raw": new_raw,
            }
        )
        await self._entity_state_repo.save_entity_state(entity_id, entity)
        persisted_entity = await self._entity_state_repo.get_entity_state(entity_id)
        await self.event_broker.publish(
            "entity_update",
            {"entity_id": entity_id, "entity_data": persisted_entity or entity},
        )

        try:
            can_message = create_ac_load_can_message(instance=int(instance), level=level)
            await can_tx_queue.put((can_message, physical_interface))
            logger.info(
                "Sent AC_LOAD_COMMAND for %s (instance %s) on %s: %s",
                entity_id,
                instance,
                physical_interface,
                action,
            )
        except Exception as e:
            logger.error("CAN command failed for %s: %s", entity_id, e)
            msg = f"CAN command failed: {e}"
            raise RuntimeError(msg) from e

        return ControlEntityResponse(
            status="success",
            entity_id=entity_id,
            command=cmd.command,
            state="on" if target_on else "off",
            brightness=0,
            action=action,
        )

    @staticmethod
    def _resolve_physical_interface(entity_config: dict[str, Any]) -> str:
        """Resolve the entity's logical CAN interface (e.g. 'house') to a physical one."""
        logical_interface = entity_config.get("interface", "house")
        can_settings = get_can_settings()
        physical_interface = can_settings.interface_mappings.get(logical_interface)
        if not physical_interface:
            warning_message = (
                "No mapping found for logical interface '%s'; "
                "falling back to first available interface"
            )
            logger.warning(
                warning_message,
                logical_interface,
            )
            physical_interface = (
                can_settings.all_interfaces[0] if can_settings.all_interfaces else "can0"
            )
        return physical_interface

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
        current_brightness_raw = (
            current_raw_values.get("operating_status", 0)
            if isinstance(current_raw_values, dict)
            else current_raw_values
        )
        # RV-C operating_status is 0..200 (half-percent); UI uses 0..100.
        current_brightness_raw_value = (
            current_brightness_raw if isinstance(current_brightness_raw, int | float) else 0
        )
        current_brightness_ui = int((current_brightness_raw_value / 200.0) * 100)
        current_state_value = current_state_data.get("state", "off")
        current_on = str(current_state_value).lower() == "on"
        return current_on, current_brightness_ui

    async def _read_last_known_brightness(self, entity_id: str) -> int:
        """Return the stored last-known brightness, defaulting to 100.

        Defaults to 100 when the repo returns ``None`` / a non-numeric /
        a non-positive value -- preserves the legacy
        ``control_light`` semantics where 'unknown last brightness'
        means 'turn on at full' rather than 'leave off'.
        """
        entity = await self._entity_state_repo.get_entity_state(entity_id)
        last_brightness_ui = entity.get("last_known_brightness") if entity else None
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
            entity["last_known_brightness"] = int(decision.persist_last_known)
            await self._entity_state_repo.save_entity_state(entity_id, entity)
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
        entity = await self._entity_state_repo.get_entity_state(entity_id)
        if not entity:
            msg = (
                f"Control Error: {entity_id} not found in repository for "
                f"action '{action_description}'"
            )
            raise RuntimeError(msg)

        # Extract info needed for CAN message creation from entity state/config
        entity_config = entity
        instance = entity_config.get("instance") if isinstance(entity_config, dict) else None
        if instance is None:
            msg = f"Entity {entity_id} missing 'instance' for CAN message creation"
            raise RuntimeError(msg)

        # Get entity's logical interface and resolve to physical interface
        logical_interface = entity_config.get("interface", "house")
        physical_interface = self._resolve_physical_interface(entity_config)

        target_state = "on" if target_brightness_ui > 0 else "off"
        target_raw_level = int((target_brightness_ui / 100.0) * 200)

        # Create and send CAN message(s). A light may map to several dimmer
        # instances that must all be commanded (e.g. the bedroom ceiling is
        # instances 25 and 26, both driven by one physical button); fan the
        # command out to each. DGN 0x1FEDB = DC_DIMMER_COMMAND_2 (verified).
        try:
            command_instances = entity_config.get("command_instances") or [instance]
            can_interface = physical_interface
            logger.debug(
                "Sending CAN command for %s to instances %s on interface %s (logical: %s)",
                entity_id,
                command_instances,
                can_interface,
                logical_interface,
            )
            for cmd_instance in command_instances:
                can_message = create_light_can_message(
                    pgn=0x1FEDB,  # DC_DIMMER_COMMAND_2
                    instance=int(cmd_instance),
                    brightness_can_level=target_raw_level,
                )
                await can_tx_queue.put((can_message, can_interface))

            # Note: We don't have access to can_tracking_repo here for sniffer entries
            # This could be added as another dependency if needed
            logger.debug("Successfully sent CAN command")

            return ControlEntityResponse(
                status="success",
                entity_id=entity_id,
                command=action_description,
                state=target_state,
                brightness=target_brightness_ui,
                action=action_description,
            )
        except Exception as e:
            logger.error("CAN command failed for %s: %s", entity_id, e)
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
    msg = (
        "This factory should be registered with composition root "
        "to get automatic dependency injection of repositories"
    )
    raise NotImplementedError(msg)
