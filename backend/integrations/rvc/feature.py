"""
RV-C feature module for the feature management system.

This module provides a Feature class implementation for RV-C protocol integration,
allowing it to be dynamically enabled/disabled and managed by the FeatureManager.

Enhanced with Phase 1 improvements:
- RVC Encoder for bidirectional communication
- Message Validator for enhanced validation
- Security Manager for CANbus security
- Performance Handler for message prioritization
"""

import logging
from typing import Any

from backend.services.feature_base import Feature
from backend.services.feature_models import SafetyClassification

logger = logging.getLogger(__name__)


class RVCFeature(Feature):
    """
    RVC protocol integration feature with Phase 1 enhancements.

    This feature manages the RV-C protocol integration, providing:
    - Decoding and encoding of RV-C messages
    - Enhanced message validation
    - Security monitoring and protection
    - Performance optimization and prioritization
    - State management for RV-C devices
    """

    def __init__(
        self,
        name: str = "rvc",
        enabled: bool = True,
        core: bool = True,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        friendly_name: str | None = None,
        safety_classification: SafetyClassification | None = None,
        log_state_transitions: bool = True,
    ):
        """
        Initialize the RVC feature.

        Args:
            name: The name of the feature (default: "rvc")
            enabled: Whether the feature is enabled (default: True)
            core: Whether this is a core feature (default: True)
            config: Optional configuration dictionary
            dependencies: List of feature names this feature depends on
            friendly_name: Human-readable display name for the feature
            safety_classification: Safety classification for state validation
            log_state_transitions: Whether to log state transitions for audit
        """
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            config=config,
            dependencies=dependencies,
            friendly_name=friendly_name,
            safety_classification=safety_classification,
            log_state_transitions=log_state_transitions,
        )
        self.config = config or {}
        self._rvc_spec_path = self.config.get("rvc_spec_path")
        self._device_mapping_path = self.config.get("device_mapping_path")
        self._data_loaded = False

        # Phase 1 enhancement components
        self.encoder = None
        self.validator = None
        self.security_manager = None
        self.performance_handler = None

        # Phase 1 feature flags from config
        self._enable_encoder = self.config.get("enable_encoder", True)
        self._enable_validator = self.config.get("enable_validator", True)
        self._enable_security = self.config.get("enable_security", True)
        self._enable_performance = self.config.get("enable_performance", True)

    async def startup(self) -> None:
        """
        Start the RVC feature.

        This loads the RVC spec and device mapping data, then initializes
        the Phase 1 enhancement components.
        """
        logger.info("Starting RVC feature with Phase 1 enhancements")
        await self._load_rvc_data()

        if self._data_loaded:
            await self._initialize_phase1_components()

    async def shutdown(self) -> None:
        """
        Stop the RVC feature and clean up Phase 1 components.
        """
        logger.info("Stopping RVC feature")

        # Shutdown Phase 1 components
        if self.performance_handler:
            self.performance_handler.stop_processing()

        self.encoder = None
        self.validator = None
        self.security_manager = None
        self.performance_handler = None
        self._data_loaded = False

    async def _load_rvc_data(self) -> None:
        """
        Load RVC spec and device mapping data.
        """
        from backend.core.config import get_settings
        from backend.integrations.rvc.decode import load_config_data_v2

        try:
            # Get settings to check for environment variable overrides
            settings = get_settings()

            # Use environment variables if available, otherwise fall back to config or defaults
            spec_path_override = None
            map_path_override = None

            if settings.rvc_spec_path:
                spec_path_override = str(settings.rvc_spec_path)
                logger.info(f"Using RVC spec path from environment: {spec_path_override}")
            elif self._rvc_spec_path:
                spec_path_override = self._rvc_spec_path
                logger.info(f"Using RVC spec path from config: {spec_path_override}")

            if settings.rvc_coach_mapping_path:
                map_path_override = str(settings.rvc_coach_mapping_path)
                logger.info(f"Using device mapping path from environment: {map_path_override}")
            elif self._device_mapping_path:
                map_path_override = self._device_mapping_path
                logger.info(f"Using device mapping path from config: {map_path_override}")

            # Load data using the new structured configuration
            self.rvc_config = load_config_data_v2(
                rvc_spec_path_override=spec_path_override,
                device_mapping_path_override=map_path_override,
            )

            # For backward compatibility, expose individual attributes
            self.dgn_dict = self.rvc_config.dgn_dict
            self.spec_meta = dict(self.rvc_config.spec_meta.dict())  # Convert back to dict for compatibility
            self.mapping_dict = self.rvc_config.mapping_dict
            self.entity_map = self.rvc_config.entity_map
            self.entity_ids = self.rvc_config.entity_ids
            self.inst_map = self.rvc_config.inst_map
            self.unique_instances = self.rvc_config.unique_instances
            self.pgn_hex_to_name_map = self.rvc_config.pgn_hex_to_name_map
            self.dgn_pairs = self.rvc_config.dgn_pairs
            self.coach_info = self.rvc_config.coach_info

            self._data_loaded = True
            logger.info(f"RVC data loaded - coach: {self.rvc_config.coach_info}")
        except FileNotFoundError as e:
            logger.warning(f"RVC configuration files not found: {e}")
            self._data_loaded = False
        except Exception as e:
            logger.error(f"Failed to load RVC data: {e}")
            self._data_loaded = False

    async def _initialize_phase1_components(self) -> None:
        """Initialize Phase 1 enhancement components."""
        from backend.core.config import get_settings

        settings = get_settings()

        try:
            # Initialize RVC Encoder
            if self._enable_encoder:
                from backend.integrations.rvc.encoder import RVCEncoder

                self.encoder = RVCEncoder(settings)
                logger.info("RVC Encoder initialized")

            # Initialize Message Validator
            if self._enable_validator:
                from backend.integrations.rvc.validator import MessageValidator

                self.validator = MessageValidator(settings)
                logger.info("Message Validator initialized")

            # Initialize Security Manager
            if self._enable_security:
                from backend.integrations.rvc.security import SecurityManager

                self.security_manager = SecurityManager(settings)
                logger.info("Security Manager initialized")

            # Initialize Performance Handler
            if self._enable_performance:
                from backend.integrations.rvc.performance import PriorityMessageHandler

                max_queue_size = self.config.get("max_queue_size", 10000)
                self.performance_handler = PriorityMessageHandler(settings, max_queue_size)
                logger.info("Performance Handler initialized")

            logger.info("Phase 1 enhancement components initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Phase 1 components: {e}")
            # Continue operation with basic functionality
            self.encoder = None
            self.validator = None
            self.security_manager = None
            self.performance_handler = None

    def is_data_loaded(self) -> bool:
        """
        Check if RVC data is loaded.

        Returns:
            True if data is loaded, False otherwise
        """
        return self._data_loaded

    @property
    def health(self) -> str:
        """
        Returns the health status of the feature including Phase 1 components.

        Returns:
            - "healthy": Feature is functioning correctly
            - "degraded": Feature has non-critical issues
            - "failed": Feature is not functioning correctly
        """
        if not self.enabled:
            return "healthy"  # Disabled is considered healthy

        if not self.is_data_loaded():
            return "failed"

        # Check Phase 1 component health
        component_issues = 0

        if self._enable_encoder and not self.encoder:
            component_issues += 1
        if self._enable_validator and not self.validator:
            component_issues += 1
        if self._enable_security and not self.security_manager:
            component_issues += 1
        if self._enable_performance and not self.performance_handler:
            component_issues += 1

        # Encoder failure is more critical than others
        if self._enable_encoder and not self.encoder:
            return "degraded"

        # Multiple component failures indicate degraded state
        if component_issues > 1:
            return "degraded"

        return "healthy"

    def get_component_status(self) -> dict[str, Any]:
        """
        Get detailed status of all RVC components.

        Returns:
            Dictionary with component status information
        """
        return {
            "data_loaded": self.is_data_loaded(),
            "coach_info": getattr(self, "coach_info", None),
            "spec_version": getattr(self, "spec_meta", {}).get("version", "unknown"),
            "components": {
                "encoder": {
                    "enabled": self._enable_encoder,
                    "available": self.encoder is not None,
                    "ready": self.encoder.is_ready() if self.encoder else False,
                    "info": self.encoder.get_encoder_info() if self.encoder else None,
                },
                "validator": {
                    "enabled": self._enable_validator,
                    "available": self.validator is not None,
                    "stats": self.validator.get_validation_stats() if self.validator else None,
                },
                "security": {
                    "enabled": self._enable_security,
                    "available": self.security_manager is not None,
                    "status": self.security_manager.get_security_status()
                    if self.security_manager
                    else None,
                },
                "performance": {
                    "enabled": self._enable_performance,
                    "available": self.performance_handler is not None,
                    "metrics": self.performance_handler.get_performance_metrics()
                    if self.performance_handler
                    else None,
                },
            },
        }
