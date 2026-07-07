"""
Victron Service - Cerbo GX (Venus OS) power system integration.

Bridges the Cerbo's local MQTT broker onto CoachIQ entities: registers one
entity per Venus OS service in the catalog (inverter/charger, battery, solar,
system aggregate), accumulates topic updates, and flushes them to the entity
manager / runtime state repository / WebSocket on a fixed cadence so
high-rate power telemetry doesn't flood clients.

Also exposes the Phase-3 control paths: VE.Bus mode and AC input current
limit writes.
"""

import asyncio
import contextlib
import time
from typing import Any

from backend.core.config import VictronSettings
from backend.core.structured_logging import get_logger
from backend.integrations.victron.catalog import (
    DEFS_BY_SERVICE_TYPE,
    VEBUS_MODE_NAMES,
    VictronEntityDef,
)
from backend.integrations.victron.client import VictronMqttClient
from backend.integrations.victron.topics import VictronUpdate
from backend.models.entity_model import EntityConfig

logger = get_logger(__name__, "VictronService")

# Fallback bounds for the AC input current limit when the broker has not
# told us the adjustable range yet (payload carries min/max).
DEFAULT_CURRENT_LIMIT_RANGE = (0.0, 100.0)


class VictronService:
    """Victron power system protocol service (MQTT transport)."""

    def __init__(
        self,
        settings: VictronSettings,
        entity_manager_service: Any,
        entity_state_repository: Any = None,
        event_broker: Any = None,
    ) -> None:
        self._settings = settings
        self._entity_manager_service = entity_manager_service
        self._entity_state_repository = entity_state_repository
        self._event_broker = event_broker

        self._client = VictronMqttClient(
            host=settings.host,
            port=settings.port,
            username=settings.username or None,
            password=settings.password or None,
            portal_id=settings.portal_id or None,
            keepalive_interval=settings.keepalive_interval_seconds,
            on_update=self._handle_update,
            on_connection_change=self._handle_connection_change,
        )

        self._running = False
        self._client_task: asyncio.Task | None = None
        self._flush_task: asyncio.Task | None = None

        # (service_type, instance) -> entity_id, bound as instances appear.
        self._instance_bindings: dict[tuple[str, str], str] = {}
        # entity_id -> accumulated-but-unflushed signal values.
        self._pending: dict[str, dict[str, Any]] = {}
        self._dirty: set[str] = set()
        # entity_id -> adjustable range reported for the input current limit.
        self._current_limit_range: dict[str, tuple[float, float]] = {}

        logger.info(
            "VictronService initialized",
            host=settings.host,
            port=settings.port,
        )

    async def start(self) -> None:
        """Register catalog entities and start the MQTT session."""
        if self._running:
            return

        logger.info("Starting Victron Service")
        entity_manager = self._entity_manager_service.get_entity_manager()
        for entity_def in DEFS_BY_SERVICE_TYPE.values():
            self._register_entity(entity_manager, entity_def, entity_def.key)

        self._client_task = asyncio.create_task(self._client.run())
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._running = True
        logger.info("Victron Service started")

    async def stop(self) -> None:
        """Stop the MQTT session and background tasks."""
        if not self._running:
            return

        logger.info("Stopping Victron Service")
        self._running = False
        await self._client.stop()
        for task in (self._client_task, self._flush_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._client_task = None
        self._flush_task = None
        logger.info("Victron Service stopped")

    # ------------------------------------------------------------------
    # Inbound data path
    # ------------------------------------------------------------------

    async def _handle_update(self, update: VictronUpdate) -> None:
        entity_def = DEFS_BY_SERVICE_TYPE.get(update.service_type)
        if entity_def is None:
            return
        signal = entity_def.paths.get(update.path)
        if signal is None:
            return

        entity_id = self._bind_instance(entity_def, update.instance)
        self._pending.setdefault(entity_id, {})[signal] = update.value
        self._dirty.add(entity_id)

        # Remember the adjustable range the broker reports for the input
        # current limit so control writes can be validated against it.
        if signal == "input_current_limit" and update.maximum is not None:
            self._current_limit_range[entity_id] = (update.minimum or 0.0, update.maximum)

    def _bind_instance(self, entity_def: VictronEntityDef, instance: str) -> str:
        """Map a live device instance onto an entity id.

        The first instance seen for a service type claims the base entity id;
        additional instances (e.g. a second MPPT) get suffixed entities
        registered on the fly.
        """
        binding_key = (entity_def.service_type, instance)
        entity_id = self._instance_bindings.get(binding_key)
        if entity_id is not None:
            return entity_id

        already_bound = any(
            service_type == entity_def.service_type for service_type, _ in self._instance_bindings
        )
        entity_id = f"{entity_def.key}_{instance}" if already_bound else entity_def.key
        self._instance_bindings[binding_key] = entity_id

        if entity_id != entity_def.key:
            entity_manager = self._entity_manager_service.get_entity_manager()
            self._register_entity(entity_manager, entity_def, entity_id)
        logger.info(
            "Bound Victron device",
            service_type=entity_def.service_type,
            instance=instance,
            entity_id=entity_id,
        )
        return entity_id

    def _register_entity(
        self, entity_manager: Any, entity_def: VictronEntityDef, entity_id: str
    ) -> None:
        config = EntityConfig(
            device_type=entity_def.device_type,
            suggested_area=entity_def.suggested_area,
            friendly_name=entity_def.friendly_name,
            capabilities=list(entity_def.capabilities),
            groups=["power"],
            protocol="victron",
            physical_id=f"victron:{entity_id}",
        )
        entity_manager.register_entity(entity_id, config, protocol="victron")

    async def _flush_loop(self) -> None:
        """Flush accumulated updates to entities on a fixed cadence."""
        try:
            while True:
                await asyncio.sleep(self._settings.broadcast_interval_seconds)
                dirty, self._dirty = self._dirty, set()
                for entity_id in dirty:
                    try:
                        await self._flush_entity(entity_id)
                    except Exception:
                        logger.exception("Error flushing Victron entity %s", entity_id)
        except asyncio.CancelledError:
            raise

    async def _flush_entity(self, entity_id: str) -> None:
        entity_manager = self._entity_manager_service.get_entity_manager()
        entity = entity_manager.get_entity(entity_id)
        if entity is None:
            return

        pending = self._pending.get(entity_id, {})
        previous = dict(entity.get_state().value or {})
        merged = {**previous, **pending}
        pending.clear()

        entity_def = self._def_for_entity(entity_id)
        if entity_def and entity_def.derive_fn:
            merged.update(entity_def.derive_fn(merged))
        state_label = entity_def.state_fn(merged) if entity_def else "unknown"
        # MQTT values arrive already decoded, so raw mirrors value; the v2
        # entities API surfaces `raw` as the state dict, and the frontend
        # reads the derived human label from its `status` key.
        signals = {**merged, "status": state_label}
        payload = {
            "entity_id": entity_id,
            "timestamp": time.time(),
            "value": signals,
            "raw": signals,
            "state": state_label,
        }
        # Devices that carry a user-assigned name on the bus (e.g. RuuviTag
        # CustomName) override the generic catalog friendly name.
        custom_name = merged.get("custom_name")
        if isinstance(custom_name, str) and custom_name.strip():
            payload["friendly_name"] = custom_name.strip()
        updated_entity = entity_manager.update_entity_state(entity_id, payload)
        if updated_entity is None:
            return

        if self._entity_state_repository is not None:
            try:
                await self._entity_state_repository.save_entity_state(
                    entity_id, updated_entity.to_dict()
                )
            except Exception as exc:
                logger.debug("Unable to persist Victron entity %s: %s", entity_id, exc)

        if self._event_broker is not None:
            await self._event_broker.publish(
                "entity_update",
                {"entity_id": entity_id, "entity_data": updated_entity.to_dict()},
            )

    def _def_for_entity(self, entity_id: str) -> VictronEntityDef | None:
        for (service_type, _), bound_id in self._instance_bindings.items():
            if bound_id == entity_id:
                return DEFS_BY_SERVICE_TYPE.get(service_type)
        # Entities registered at startup that have not seen data yet.
        for entity_def in DEFS_BY_SERVICE_TYPE.values():
            if entity_def.key == entity_id:
                return entity_def
        return None

    async def _handle_connection_change(self, connected: bool) -> None:
        logger.info("Victron MQTT connection %s", "established" if connected else "lost")

    # ------------------------------------------------------------------
    # Control path (VE.Bus)
    # ------------------------------------------------------------------

    async def set_inverter_mode(self, mode: int | str) -> dict[str, Any]:
        """Set the VE.Bus switch position (charger_only/inverter_only/on/off)."""
        if isinstance(mode, str):
            by_name = {name: code for code, name in VEBUS_MODE_NAMES.items()}
            if mode not in by_name:
                msg = f"Invalid inverter mode {mode!r}; expected one of {sorted(by_name)}"
                raise ValueError(msg)
            mode = by_name[mode]
        if mode not in VEBUS_MODE_NAMES:
            msg = f"Invalid inverter mode {mode}; expected one of {sorted(VEBUS_MODE_NAMES)}"
            raise ValueError(msg)

        instance = self._vebus_instance()
        await self._client.write_value("vebus", instance, "Mode", mode)
        return {"mode": mode, "mode_name": VEBUS_MODE_NAMES[mode]}

    async def set_input_current_limit(self, amps: float) -> dict[str, Any]:
        """Set the VE.Bus AC input current limit in amps."""
        instance = self._vebus_instance()
        entity_id = self._instance_bindings[("vebus", instance)]
        low, high = self._current_limit_range.get(entity_id, DEFAULT_CURRENT_LIMIT_RANGE)
        if not (low <= amps <= high):
            msg = f"Input current limit {amps}A outside adjustable range {low}-{high}A"
            raise ValueError(msg)
        await self._client.write_value("vebus", instance, "Ac/ActiveIn/CurrentLimit", float(amps))
        return {"input_current_limit": float(amps)}

    async def set_generator_manual(self, run: bool) -> dict[str, Any]:
        """Request a manual generator start (True) or stop (False).

        Writes the Cerbo's dbus-generator /ManualStart — the same control the
        VRM 'manual start' button uses. The Cerbo's genset logic performs the
        actual crank/stop sequence and its own stop conditions still apply.
        """
        instance = self._instance_for("generator")
        await self._client.write_value("generator", instance, "ManualStart", 1 if run else 0)
        return {"manual_start": run}

    def _vebus_instance(self) -> str:
        return self._instance_for("vebus")

    def _instance_for(self, service_type: str) -> str:
        for bound_type, instance in self._instance_bindings:
            if bound_type == service_type:
                return instance
        msg = f"No Victron {service_type} device discovered yet; cannot send command"
        raise RuntimeError(msg)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def get_health_status(self) -> dict[str, Any]:
        """Health status for the composition root and diagnostics."""
        return {
            "service": "VictronService",
            "healthy": self._running and self._client.connected,
            "running": self._running,
            "connected": self._client.connected,
            "portal_id": self._client.portal_id,
            "bound_devices": {
                f"{service_type}/{instance}": entity_id
                for (service_type, instance), entity_id in self._instance_bindings.items()
            },
        }
