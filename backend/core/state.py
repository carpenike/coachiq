"""
AppState module: Maintains in-memory state, history, and configuration lookups for all entities.

This module defines the AppState class, which is responsible for managing the shared application state
across all entities, including their latest values, historical data, and configuration-derived lookups.
It is a core feature of the backend, supporting initialization, updates, and access patterns for entity state.
"""

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.models.entity_model import EntityConfig

from backend.core.entity_manager import EntityManager
from backend.services.feature_base import Feature
from backend.repositories import (
    EntityStateRepository,
    RVCConfigRepository,
    CANTrackingRepository,
    DiagnosticsRepository,
)

logger = logging.getLogger(__name__)


class AppState(Feature):
    """
    Core feature that manages application state.

    Maintains the in-memory state of all entities, their historical data, and configuration-derived lookups.
    Provides methods to initialize, update, and access this shared state.
    """

    def __init__(
        self,
        name: str = "app_state",
        enabled: bool = True,
        core: bool = True,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        controller_source_addr: int = 0xF9,
        friendly_name: str | None = None,
        safety_classification=None,
        log_state_transitions: bool = True,
        **kwargs
    ) -> None:
        """
        Initialize the AppState feature.
        """
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            config=config or {},
            dependencies=dependencies or [],
            friendly_name=friendly_name,
            safety_classification=safety_classification,
            log_state_transitions=log_state_transitions,
        )
        self.controller_source_addr: int = controller_source_addr

        # Initialize internal repositories (Phase 2R.1)
        # Try to get from ServiceRegistry first (Phase 2R.2), fallback to creating new
        self._init_repositories()

        # Legacy attributes maintained as properties for backward compatibility
        self.max_history_length: int = 1000
        self.history_duration: int = 24 * 3600  # 24 hours in seconds
        self.config_data: dict[str, Any] = config or {}
        self.background_tasks: set[Any] = set()

        # These will be delegated to repositories via properties
        self._broadcast_can_sniffer_group = None

    def _init_repositories(self) -> None:
        """
        Initialize repositories, preferring ServiceRegistry instances if available.

        This supports Phase 2R.2 where repositories can be accessed independently
        through ServiceRegistry while maintaining backward compatibility.
        """
        # Try to get from ServiceRegistry first
        try:
            import backend.main
            if hasattr(backend.main, 'app') and hasattr(backend.main.app.state, 'service_registry'):
                service_registry = backend.main.app.state.service_registry

                # Try to get repositories from ServiceRegistry
                if service_registry.has_service("entity_state_repository"):
                    self._entity_state_repo = service_registry.get_service("entity_state_repository")
                    # Share the entity manager
                    self.entity_manager = self._entity_state_repo.entity_manager
                    logger.info("Using EntityStateRepository from ServiceRegistry")
                else:
                    # Create new with backward compatibility
                    self.entity_manager = EntityManager()
                    self._entity_state_repo = EntityStateRepository(self.entity_manager)

                if service_registry.has_service("rvc_config_repository"):
                    self._rvc_config_repo = service_registry.get_service("rvc_config_repository")
                    logger.info("Using RVCConfigRepository from ServiceRegistry")
                else:
                    self._rvc_config_repo = RVCConfigRepository()

                if service_registry.has_service("can_tracking_repository"):
                    self._can_tracking_repo = service_registry.get_service("can_tracking_repository")
                    logger.info("Using CANTrackingRepository from ServiceRegistry")
                else:
                    self._can_tracking_repo = CANTrackingRepository()

                if service_registry.has_service("diagnostics_repository"):
                    self._diagnostics_repo = service_registry.get_service("diagnostics_repository")
                    logger.info("Using DiagnosticsRepository from ServiceRegistry")
                else:
                    self._diagnostics_repo = DiagnosticsRepository()

            else:
                # No ServiceRegistry available, create new instances
                self.entity_manager = EntityManager()
                self._entity_state_repo = EntityStateRepository(self.entity_manager)
                self._rvc_config_repo = RVCConfigRepository()
                self._can_tracking_repo = CANTrackingRepository()
                self._diagnostics_repo = DiagnosticsRepository()

        except Exception as e:
            logger.warning(f"Failed to get repositories from ServiceRegistry: {e}")
            # Fallback to creating new instances
            self.entity_manager = EntityManager()
            self._entity_state_repo = EntityStateRepository(self.entity_manager)
            self._rvc_config_repo = RVCConfigRepository()
            self._can_tracking_repo = CANTrackingRepository()
            self._diagnostics_repo = DiagnosticsRepository()

    # Backward compatibility properties that delegate to repositories
    @property
    def unmapped_entries(self) -> dict[str, Any]:
        """Legacy property - delegates to diagnostics repository."""
        return self._diagnostics_repo.get_unmapped_entries()

    @unmapped_entries.setter
    def unmapped_entries(self, value: dict[str, Any]) -> None:
        """Legacy setter - not recommended for new code."""
        logger.warning("Direct assignment to unmapped_entries is deprecated")
        self._diagnostics_repo.clear_unmapped_entries()
        for k, v in value.items():
            self._diagnostics_repo.add_unmapped_entry(k, v)

    @property
    def unknown_pgns(self) -> dict[str, Any]:
        """Legacy property - delegates to diagnostics repository."""
        return self._diagnostics_repo.get_unknown_pgns()

    @unknown_pgns.setter
    def unknown_pgns(self, value: dict[str, Any]) -> None:
        """Legacy setter - not recommended for new code."""
        logger.warning("Direct assignment to unknown_pgns is deprecated")
        self._diagnostics_repo.clear_unknown_pgns()
        for k, v in value.items():
            self._diagnostics_repo.add_unknown_pgn(k, v)

    @property
    def raw_device_mapping(self) -> dict[tuple[str, str], Any]:
        """Legacy property - delegates to RVC config repository."""
        return self._rvc_config_repo.get_raw_device_mapping()

    @property
    def pgn_hex_to_name_map(self) -> dict[str, str]:
        """Legacy property - returns from RVC config repository."""
        if self._rvc_config_repo.is_loaded() and self._rvc_config_repo._config:
            return self._rvc_config_repo._config.pgn_hex_to_name_map
        return {}

    @property
    def coach_info(self) -> Any:
        """Legacy property - delegates to RVC config repository."""
        return self._rvc_config_repo.get_coach_info()

    @property
    def known_command_status_pairs(self) -> dict[Any, Any]:
        """Legacy property - returns from RVC config repository."""
        if self._rvc_config_repo.is_loaded() and self._rvc_config_repo._config:
            return self._rvc_config_repo._config.known_command_status_pairs
        return {}

    @property
    def pending_commands(self) -> list[Any]:
        """Legacy property - returns from CAN tracking repository."""
        return self._can_tracking_repo._pending_commands

    @property
    def observed_source_addresses(self) -> set[Any]:
        """Legacy property - returns from CAN tracking repository."""
        return self._can_tracking_repo._observed_source_addresses

    @property
    def can_sniffer_grouped(self) -> list[Any]:
        """Legacy property - returns from CAN tracking repository."""
        return self._can_tracking_repo.get_can_sniffer_grouped()

    @property
    def last_seen_by_source_addr(self) -> dict[Any, Any]:
        """Legacy property - returns from CAN tracking repository."""
        return self._can_tracking_repo._last_seen_by_source_addr

    @property
    def can_command_sniffer_log(self) -> list[Any]:
        """Legacy property - returns from CAN tracking repository."""
        return self._can_tracking_repo.get_can_sniffer_log()

    def __repr__(self) -> str:
        return (
            f"<AppState(entities={len(self.entity_manager.get_entity_ids())}, "
            f"light_entities={len(self.entity_manager.get_light_entity_ids())}, "
            f"unmapped_entries={len(self.unmapped_entries)}, "
            f"unknown_pgns={len(self.unknown_pgns)})>"
        )

    async def startup(self, rvc_config_provider=None) -> None:
        """
        Initialize the state feature on startup.

        Args:
            rvc_config_provider: Optional RVCConfigProvider instance (for ServiceRegistry integration)
        """
        # Global assignment removed - AppState is managed by FeatureManager
        # and accessed via app.state.app_state or dependency injection
        logger.info("Starting AppState feature")

        # Load entities from coach mapping file, similar to legacy system
        try:
            logger.info("Loading entity configuration from coach mapping files...")

            # Use shared config provider if available (ServiceRegistry integration)
            if rvc_config_provider is not None:
                logger.info("Using shared RVCConfigProvider (ServiceRegistry mode)")

                # Get configuration paths from provider
                rvc_spec_path = str(rvc_config_provider._spec_path) if rvc_config_provider._spec_path else None
                device_mapping_path = str(rvc_config_provider._device_mapping_path) if rvc_config_provider._device_mapping_path else None

            else:
                logger.info("Using legacy configuration loading (fallback mode)")

                # Get configuration paths from settings (legacy mode)
                from backend.core.config import get_settings

                settings = get_settings()

                rvc_spec_path = str(settings.rvc_spec_path) if settings.rvc_spec_path else None
                device_mapping_path = (
                    str(settings.rvc_coach_mapping_path) if settings.rvc_coach_mapping_path else None
                )

            logger.info(f"Using RV-C spec path: {rvc_spec_path}")
            logger.info(f"Using device mapping path: {device_mapping_path}")

            self.populate_app_state(
                rvc_spec_path=rvc_spec_path, device_mapping_path=device_mapping_path
            )
            logger.info(f"Successfully loaded {len(self.entity_manager.get_entity_ids())} entities")
        except Exception as e:
            logger.error(f"Failed to load entity configuration during startup: {e}")
            # Don't fail startup completely, but log the error

    async def shutdown(self) -> None:
        """Clean up resources on shutdown."""
        logger.info("Shutting down AppState feature")

        # Clean up background tasks
        for task in self.background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug("Background task cancelled successfully")
            except Exception as e:
                logger.error(f"Error during background task cancellation: {e}")
        self.background_tasks.clear()

        # Clean up CAN tracking repository tasks
        await self._can_tracking_repo.cleanup_background_tasks()

    @property
    def health(self) -> str:
        """Return the health status of the feature."""
        return "healthy"  # State manager always healthy

    def set_broadcast_function(self, broadcast_func) -> None:
        """
        Set the function to broadcast CAN sniffer groups.
        """
        self._broadcast_can_sniffer_group = broadcast_func
        self._can_tracking_repo.set_broadcast_function(broadcast_func)

    def get_observed_source_addresses(self) -> list[int]:
        """Returns a sorted list of all observed CAN source addresses."""
        return self._can_tracking_repo.get_observed_source_addresses()

    def add_pending_command(self, entry) -> None:
        """
        Add a pending command and clean up old entries.
        """
        self._can_tracking_repo.add_pending_command(entry)

    def try_group_response(self, response_entry) -> bool:
        """
        Try to group a response (RX) with a pending command (TX).
        """
        # Use async method synchronously - this is safe since we're not awaiting
        # TODO: Consider making this method async in future refactoring
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, schedule as a task
            task = asyncio.create_task(
                self._can_tracking_repo.try_group_response(
                    response_entry,
                    self.known_command_status_pairs
                )
            )
            # Return False for now, the grouping will happen asynchronously
            return False
        else:
            # Synchronous context - run the coroutine
            return loop.run_until_complete(
                self._can_tracking_repo.try_group_response(
                    response_entry,
                    self.known_command_status_pairs
                )
            )

    def get_can_sniffer_grouped(self) -> list:
        """Returns the list of grouped CAN sniffer entries."""
        return self._can_tracking_repo.get_can_sniffer_grouped()

    def update_last_seen_by_source_addr(self, entry) -> None:
        """
        Update the mapping of source address to the last-seen CAN sniffer entry.
        """
        # This is handled internally by add_can_sniffer_entry now
        pass

    def add_can_sniffer_entry(self, entry) -> None:
        """
        Adds a CAN command/control message entry to the sniffer log.
        """
        self._can_tracking_repo.add_can_sniffer_entry(entry)
        self.notify_network_map_ws()

    def get_can_sniffer_log(self) -> list:
        """Returns the current CAN command/control sniffer log."""
        return self._can_tracking_repo.get_can_sniffer_log()

    def get_last_known_brightness(self, entity_id) -> int:
        """
        Retrieves the last known brightness for a given light entity.
        """
        return self._entity_state_repo.get_last_known_brightness(entity_id)

    def set_last_known_brightness(self, entity_id, brightness) -> None:
        """
        Sets the last known brightness for a given light entity.
        """
        self._entity_state_repo.set_last_known_brightness(entity_id, brightness)

    def update_entity_state_and_history(self, entity_id, payload_to_store) -> None:
        """
        Updates the state and history for a given entity using the EntityManager.
        """
        self._entity_state_repo.update_entity_state_and_history(entity_id, payload_to_store)

    def populate_app_state(
        self, rvc_spec_path=None, device_mapping_path=None, load_config_func=None
    ):
        """
        Populates the application state from configuration files.
        """
        logger.info(
            f"populate_app_state: rvc_spec_path={rvc_spec_path}, device_mapping_path={device_mapping_path}, load_config_func={load_config_func}"
        )
        logger.info("populate_app_state: Starting entity/config loading...")

        # Use the new structured config loader by default
        if load_config_func is None:
            from backend.integrations.rvc.decode import load_config_data_v2

            # Load structured configuration
            rvc_config = load_config_data_v2(rvc_spec_path, device_mapping_path)

            # Extract values from structured config for compatibility
            decoder_map_val = rvc_config.dgn_dict
            spec_meta_val = dict(rvc_config.spec_meta.dict())
            mapping_dict_val = rvc_config.mapping_dict
            entity_map_val = rvc_config.entity_map
            entity_ids_val = rvc_config.entity_ids
            inst_map_val = rvc_config.inst_map
            unique_instances_val = rvc_config.unique_instances
            pgn_hex_to_name_map_val = rvc_config.pgn_hex_to_name_map
            dgn_pairs_val = rvc_config.dgn_pairs
            coach_info_val = rvc_config.coach_info

            logger.info("populate_app_state: Using structured RVC configuration (load_config_data_v2)")
        else:
            # Support legacy tuple return for backward compatibility
            logger.info(f"populate_app_state: Using custom load_config_func={load_config_func}")

            try:
                processed_data_tuple = load_config_func(rvc_spec_path, device_mapping_path)
            except Exception as e:
                logger.error(f"populate_app_state: load_config_func failed: {e}")
                raise

            (
                decoder_map_val,
                spec_meta_val,
                mapping_dict_val,
                entity_map_val,
                entity_ids_val,
                inst_map_val,
                unique_instances_val,
                pgn_hex_to_name_map_val,
                dgn_pairs_val,
                coach_info_val,
            ) = processed_data_tuple

        # Clear previous state
        self._diagnostics_repo.clear_unknown_pgns()
        self._diagnostics_repo.clear_unmapped_entries()
        logger.info("populate_app_state: Cleared in-memory state.")

        logger.info(f"populate_app_state: entity_map has {len(entity_map_val)} entries.")
        logger.info(f"populate_app_state: entity_ids has {len(entity_ids_val)} entries.")

        # Load configuration into RVC repository
        self._rvc_config_repo.load_configuration(
            decoder_map=decoder_map_val,
            spec_meta=spec_meta_val,
            mapping_dict=mapping_dict_val,
            entity_map=entity_map_val,
            entity_ids=entity_ids_val,
            inst_map=inst_map_val,
            unique_instances=unique_instances_val,
            pgn_hex_to_name_map=pgn_hex_to_name_map_val,
            dgn_pairs=dgn_pairs_val,
            coach_info=coach_info_val
        )

        logger.info("Application state populated from configuration data.")

        # Build the correct entity ID to config mapping from entity_map
        # entity_map is keyed by (dgn_hex, instance) tuples, but EntityManager expects
        # entity configs keyed by entity_id strings
        entity_configs: dict[str, EntityConfig] = {}
        for entity_dict in entity_map_val.values():
            if isinstance(entity_dict, dict) and "entity_id" in entity_dict:
                entity_id = entity_dict["entity_id"]
                # Use the dictionary directly as it's already compatible with EntityConfig
                entity_configs[entity_id] = entity_dict

        logger.info(f"Built entity configs mapping with {len(entity_configs)} entities")

        # Count lights for verification
        light_count = sum(
            1
            for config in entity_configs.values()
            if isinstance(config, dict) and config.get("device_type") == "light"
        )
        logger.info(f"Found {light_count} light entities in entity configs")

        # Update the entity repository with loaded entities
        self._entity_state_repo.bulk_load_entities(entity_configs)

        # Initialize light states
        from backend.integrations.rvc.decode import decode_payload

        self.entity_manager.preseed_light_states(decode_payload, entity_map_val)

        logger.info("Global app state dictionaries populated.")

    def notify_network_map_ws(self) -> None:
        """Notifies WebSocket clients about network map updates."""
        with contextlib.suppress(Exception):
            logger.debug("Network map update notification requested")
            # TODO: Implement network map WebSocket notification logic here

    def get_controller_source_addr(self) -> int:
        """Returns the controller's source address."""
        return self.controller_source_addr

    def get_health_status(self) -> dict:
        """
        Return aggregated health status from all repositories.
        """
        # Get health from each repository
        entity_health = self._entity_state_repo.get_health_status()
        rvc_health = self._rvc_config_repo.get_health_status()
        can_health = self._can_tracking_repo.get_health_status()

        # Aggregate health
        all_healthy = (
            entity_health.get("healthy", False) and
            rvc_health.get("healthy", False) and
            can_health.get("healthy", False)
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "components": {
                "entities": entity_health.get("entity_count", 0),
                "unmapped_entries": entity_health.get("unmapped_count", 0),
                "unknown_pgns": rvc_health.get("unknown_pgns", 0),
            },
            "repositories": {
                "entity_state": entity_health,
                "rvc_config": rvc_health,
                "can_tracking": can_health,
            }
        }

    def start_can_sniffer(self, interface_name: str) -> None:
        """Start the CAN sniffer on the given interface."""
        from backend.core.state import CANSniffer  # for test patching

        self.can_sniffer = CANSniffer(interface_name, self.process_message)
        self.can_sniffer.start()

    def stop_can_sniffer(self) -> None:
        """Stop the CAN sniffer if running."""
        if hasattr(self, "can_sniffer") and self.can_sniffer:
            self.can_sniffer.stop()
            self.can_sniffer = None

    def get_entity_count(self) -> int:
        """Return the number of tracked entity states."""
        return len(getattr(self, "_entity_states", {}))

    def add_entity_state(self, entity_id: str, entity_data: dict) -> None:
        """Add or set the state for an entity."""
        if not hasattr(self, "_entity_states"):
            self._entity_states = {}
        self._entity_states[entity_id] = entity_data.copy()

    def get_entity_state(self, entity_id: str) -> dict | None:
        """Get the state for an entity, or None if not found."""
        return getattr(self, "_entity_states", {}).get(entity_id)

    def update_entity_state(self, entity_id: str, update_data: dict) -> None:
        """Update the state for an entity, merging with existing data."""
        if not hasattr(self, "_entity_states"):
            self._entity_states = {}
        if entity_id in self._entity_states:
            self._entity_states[entity_id].update(update_data)
        else:
            self._entity_states[entity_id] = update_data.copy()

    def remove_entity_state(self, entity_id: str) -> None:
        """Remove the state for an entity if it exists."""
        if hasattr(self, "_entity_states"):
            self._entity_states.pop(entity_id, None)

    def get_all_entity_states(self) -> dict:
        """Return a copy of all entity states."""
        return dict(getattr(self, "_entity_states", {}))

    def clear_entity_states(self) -> None:
        """Remove all entity states."""
        if hasattr(self, "_entity_states"):
            self._entity_states.clear()

    def _decode_rvc_message(self, message):
        """Stub for test patching; decodes an RVC message."""
        return {}

    def process_message(self, message):
        """Process a CAN message, decoding and handling errors gracefully (for test compatibility)."""
        try:
            self._decode_rvc_message(message)
        except Exception as e:
            logger.error(f"Error decoding RVC message: {e}")


# Dummy CANSniffer for test patching
class CANSniffer:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass


# Global app_state variable removed - use dependency injection instead


def initialize_app_state(manager, config) -> AppState:
    """
    Initialize the application state and register with feature manager.

    Note: The AppState instance is managed by FeatureManager and stored
    in app.state. Access it via dependency injection or app.state.app_state.
    """
    # Check if already registered with manager
    existing = manager.get_feature("app_state")
    if existing:
        return existing

    app_state = AppState(
        name="app_state",
        enabled=True,
        core=True,
        config=config,
        dependencies=[],
    )
    manager.register_feature(app_state)

    return app_state
