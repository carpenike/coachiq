"""
Entity Initialization Service

Handles loading and preseeding entities from coach mapping configurations.
This service replaces the entity initialization functionality that was previously
in AppState.
"""

import contextlib
import logging
from typing import Any

from backend.core.config import get_settings
from backend.core.entity_manager import EntityManager
from backend.integrations.rvc.config_loader import get_default_paths
from backend.integrations.rvc.decode import decode_payload, load_config_data_v2
from backend.models.entity_model import EntityConfig
from backend.repositories.entity_repository import EntityRuntimeStateRepository
from backend.repositories.rvc_config_repository import RVCConfigRepository

logger = logging.getLogger(__name__)


class EntityInitializationService:
    """Service responsible for loading and initializing entities from coach mapping."""

    def __init__(
        self,
        entity_state_repository: EntityRuntimeStateRepository,
        rvc_config_repository: RVCConfigRepository,
        entity_manager: EntityManager | None = None,
    ):
        """
        Initialize the entity initialization service.

        Args:
            entity_state_repository: Repository for entity state
            rvc_config_repository: Repository for RVC configuration
            entity_manager: Optional entity manager
        """
        self._entity_state_repo = entity_state_repository
        self._rvc_config_repo = rvc_config_repository
        self._entity_manager = entity_manager or EntityManager()
        self._initialized = False

    async def startup(self) -> None:
        """Initialize entities from coach mapping on service startup."""
        if self._initialized:
            logger.warning("EntityInitializationService already initialized, skipping")
            return

        try:
            logger.info("Starting entity initialization from coach mapping")

            # Get configuration paths
            settings = get_settings()
            rvc_spec_path, device_mapping_path = get_default_paths()

            # Log coach model if specified
            if settings.rvc.coach_model:
                logger.info("Using coach model from settings: %s", settings.rvc.coach_model)
                # The get_default_paths already handles coach model selection

            logger.info(
                "Loading configuration from: RVC spec: %s, Device mapping: %s",
                rvc_spec_path,
                device_mapping_path,
            )

            # Load configuration using the structured loader
            rvc_config = load_config_data_v2(rvc_spec_path, device_mapping_path)

            # Extract data from structured config
            decoder_map = rvc_config.dgn_dict
            spec_meta = dict(rvc_config.spec_meta.dict())
            mapping_dict = rvc_config.mapping_dict
            entity_map = rvc_config.entity_map
            entity_ids = rvc_config.entity_ids
            inst_map = rvc_config.inst_map
            unique_instances = rvc_config.unique_instances
            pgn_hex_to_name_map = rvc_config.pgn_hex_to_name_map
            dgn_pairs = rvc_config.dgn_pairs
            coach_info = rvc_config.coach_info

            logger.info(
                "Loaded configuration: %d entity mappings, %d entity IDs, Coach: %s %s %s",
                len(entity_map),
                len(entity_ids),
                coach_info.make if coach_info else "Unknown",
                coach_info.model if coach_info else "Unknown",
                coach_info.year if coach_info else "Unknown",
            )

            # Load configuration into RVC repository
            self._rvc_config_repo.load_configuration(
                decoder_map=decoder_map,
                spec_meta=spec_meta,
                mapping_dict=mapping_dict,
                entity_map=entity_map,
                entity_ids=entity_ids,
                inst_map=inst_map,
                unique_instances=unique_instances,
                pgn_hex_to_name_map=pgn_hex_to_name_map,
                dgn_pairs=dgn_pairs,
                coach_info=coach_info,
            )

            # Build entity configs from entity_map
            entity_configs: dict[str, EntityConfig] = {}
            for entity_dict in entity_map.values():
                if isinstance(entity_dict, dict) and "entity_id" in entity_dict:
                    entity_id = entity_dict["entity_id"]
                    # Use the dictionary directly as it's compatible with EntityConfig
                    entity_configs[entity_id] = entity_dict

            logger.info("Built %d entity configurations", len(entity_configs))

            # Count specific entity types for verification
            light_count = sum(
                1
                for config in entity_configs.values()
                if isinstance(config, dict) and config.get("device_type") == "light"
            )
            lock_count = sum(
                1
                for config in entity_configs.values()
                if isinstance(config, dict) and config.get("device_type") == "lock"
            )

            logger.info(
                "Entity breakdown: %d lights, %d locks, %d other devices",
                light_count,
                lock_count,
                len(entity_configs) - light_count - lock_count,
            )

            # Convert entity configs to EntityConfig objects
            entity_config_objs = {}
            for entity_id, config in entity_configs.items():
                entity_config = EntityConfig(
                    device_type=config.get("device_type", "unknown"),
                    # Coach mapping YAML uses `area` (e.g. "interior.bedroom");
                    # older mappings used `suggested_area`.
                    suggested_area=config.get("suggested_area") or config.get("area") or "Unknown",
                    friendly_name=config.get("friendly_name"),
                    capabilities=config.get("capabilities", []),
                    groups=config.get("groups", []),
                    protocol=config.get("protocol", "rvc"),
                    command_dgn=config.get("command_dgn"),
                    read_only=config.get("read_only", False),
                )
                # The DGN instance lives in inst_map (keyed by entity_id), not
                # in the per-entity mapping dict; without it the control path
                # cannot build CAN messages.
                inst_info = inst_map.get(entity_id)
                raw_instance = inst_info.get("instance") if inst_info else None
                # inst_map values may be non-numeric (e.g. "default" instances),
                # which the CAN command path cannot address anyway.
                if raw_instance is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        entity_config["instance"] = int(raw_instance)
                # Multi-channel lights fan a command out to several instances;
                # the list is carried on the inst_map entry from the coach mapping.
                raw_cmd_instances = inst_info.get("command_instances") if inst_info else None
                if isinstance(raw_cmd_instances, list | tuple):
                    fan: list[int] = []
                    for value in raw_cmd_instances:
                        with contextlib.suppress(TypeError, ValueError):
                            fan.append(int(value))
                    if fan:
                        entity_config["command_instances"] = fan
                entity_config_objs[entity_id] = entity_config

            # Register with local entity manager for preseeding and then persist
            # the same dict-shaped state payloads EntityService reads.
            for entity_id, entity_config in entity_config_objs.items():
                self._entity_manager.register_entity(entity_id, entity_config)

            # Preseed light states
            self._entity_manager.preseed_light_states(decode_payload, entity_map)
            saved_count = await self._entity_state_repo.save_bulk_states(
                self._entity_manager.to_api_response()
            )
            logger.info("Saved %d initialized entity states", saved_count)

            self._initialized = True
            logger.info("Entity initialization completed successfully")

        except Exception as e:
            logger.exception("Failed to initialize entities: %s", e)
            raise

    async def reload_entities(self) -> None:
        """Reload entities from coach mapping (for hot reload support)."""
        logger.info("Reloading entities from coach mapping")
        self._initialized = False
        await self.startup()

    def get_initialization_status(self) -> dict[str, Any]:
        """Get the current initialization status."""
        return {
            "initialized": self._initialized,
            "entity_count": len(self._entity_manager.get_entity_ids()),
            "light_count": len(self._entity_manager.get_light_entity_ids()),
            "coach_info": self._rvc_config_repo.get_coach_info() if self._initialized else None,
        }

    async def cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        logger.info("EntityInitializationService cleanup")
        # No specific cleanup needed
