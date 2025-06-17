"""
Enhanced FeatureManager with ServiceRegistry Integration

This module extends the FeatureManager to work seamlessly with ServiceRegistry,
enabling unified service management while maintaining backward compatibility
and safety-critical features.

Part of Phase 2C: FeatureManager-ServiceRegistry Integration
"""

import logging
from typing import Any, Dict, List, Optional

from backend.core.service_registry import ServiceRegistry
from backend.core.unified_service import ServiceAdapter, UnifiedServiceManager
from backend.services.feature_base import Feature
from backend.services.feature_manager import FeatureManager
from backend.services.feature_models import FeatureState

logger = logging.getLogger(__name__)


class IntegratedFeatureManager(FeatureManager):
    """
    Enhanced FeatureManager that integrates with ServiceRegistry.

    This class extends the standard FeatureManager to:
    - Register features with ServiceRegistry for unified management
    - Use ServiceRegistry's dependency resolution and staged startup
    - Maintain backward compatibility with existing feature APIs
    - Preserve safety-critical capabilities
    """

    def __init__(
        self,
        config_set=None,
        service_registry: Optional[ServiceRegistry] = None,
    ):
        """
        Initialize the integrated feature manager.

        Args:
            config_set: Feature configuration set
            service_registry: Optional ServiceRegistry for integration
        """
        super().__init__(config_set)
        self.service_registry = service_registry
        self.unified_manager: Optional[UnifiedServiceManager] = None
        self._service_adapters: Dict[str, ServiceAdapter] = {}

        # Initialize unified manager if ServiceRegistry provided
        if service_registry:
            self.unified_manager = UnifiedServiceManager(
                service_registry=service_registry,
                feature_manager=self,
            )

    def register_feature(self, feature: Feature) -> None:
        """
        Register a feature with both FeatureManager and ServiceRegistry.

        Args:
            feature: The Feature instance to register
        """
        # Register with parent FeatureManager
        super().register_feature(feature)

        # Also register with ServiceRegistry if available
        if self.service_registry and self.unified_manager:
            try:
                # Determine startup stage based on dependencies
                stage = self._calculate_startup_stage(feature)

                # Register via unified manager
                self.unified_manager.register_service(
                    name=feature.name,
                    service=feature,
                    dependencies=feature.dependencies,
                    stage=stage,
                )

                logger.info(
                    f"Registered feature '{feature.name}' with ServiceRegistry "
                    f"(stage={stage}, deps={feature.dependencies})"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to register feature '{feature.name}' with ServiceRegistry: {e}. "
                    "Feature will still work via FeatureManager."
                )

    def _calculate_startup_stage(self, feature: Feature) -> int:
        """
        Calculate the appropriate startup stage for a feature.

        Features are assigned to stages based on:
        - 0: Core infrastructure (no dependencies)
        - 1: Basic services (depend only on core)
        - 2: Application features (depend on basic services)
        - 3+: Higher-level features

        Args:
            feature: The feature to analyze

        Returns:
            Startup stage number
        """
        if not feature.dependencies:
            # No dependencies = stage 0 (core)
            return 0

        # Calculate max stage of dependencies + 1
        max_dep_stage = 0
        for dep_name in feature.dependencies:
            if dep_name in self._features:
                dep_feature = self._features[dep_name]
                dep_stage = self._calculate_startup_stage(dep_feature)
                max_dep_stage = max(max_dep_stage, dep_stage)

        return max_dep_stage + 1

    async def startup_features(self, app=None) -> None:
        """
        Start up features using ServiceRegistry if available.

        This method delegates to ServiceRegistry for efficient staged
        startup with parallelization, falling back to standard
        FeatureManager startup if ServiceRegistry is not available.

        Args:
            app: Optional FastAPI app instance
        """
        if self.service_registry:
            logger.info("Starting features via ServiceRegistry staged startup")

            # ServiceRegistry will handle startup orchestration
            # Features were already registered with their stages
            # The registry will call each feature's startup() method

            # Note: ServiceRegistry startup is typically called from main.py
            # This method ensures features are ready for that process

            logger.info(
                f"Features prepared for ServiceRegistry startup. "
                f"Total stages: {len(self.service_registry._startup_stages)}"
            )

            # Set all enabled features to INITIALIZING state
            # ServiceRegistry will update to HEALTHY after startup
            for name, feature in self._features.items():
                if feature.enabled:
                    feature._state = FeatureState.INITIALIZING
        else:
            # Fall back to standard FeatureManager startup
            logger.info("Starting features via standard FeatureManager")
            # Call parent's startup_features method
            # Note: FeatureManager doesn't have this method, we need to implement it
            await self._standard_startup_features(app)

    async def shutdown_features(self) -> None:
        """
        Shutdown features, coordinating with ServiceRegistry if available.

        ServiceRegistry handles shutdown in reverse dependency order,
        but we ensure proper state transitions for safety compliance.
        """
        if self.service_registry:
            logger.info("Shutting down features via ServiceRegistry")

            # Mark features as shutting down for safety compliance
            for name, feature in self._features.items():
                if feature.enabled and feature._state != FeatureState.STOPPED:
                    # Transition to SAFE_SHUTDOWN first
                    if feature._state in (FeatureState.HEALTHY, FeatureState.DEGRADED):
                        feature._state = FeatureState.SAFE_SHUTDOWN

            # ServiceRegistry will call shutdown() on each service
            # in reverse dependency order
        else:
            # Fall back to standard shutdown
            # Call standard shutdown logic
            await self._standard_shutdown_features()

    def get_service_from_registry(self, name: str) -> Any:
        """
        Get a service from ServiceRegistry.

        This enables features to access services managed by
        ServiceRegistry, not just other features.

        Args:
            name: Service name

        Returns:
            Service instance or None
        """
        if self.service_registry and self.service_registry.has_service(name):
            return self.service_registry.get_service(name)
        return None

    def get_unified_health_status(self) -> Dict[str, Any]:
        """
        Get combined health status from both systems.

        Returns:
            Unified health information
        """
        health = {
            "feature_manager": {
                "total_features": len(self._features),
                "enabled_features": len([f for f in self._features.values() if f.enabled]),
                "healthy_features": len([
                    f for f in self._features.values()
                    if f.enabled and f._state == FeatureState.HEALTHY
                ]),
            }
        }

        if self.unified_manager:
            health["unified_status"] = self.unified_manager.get_unified_status()

        if self.service_registry:
            health["service_registry"] = {
                "total_services": len(self.service_registry.list_services()),
                "service_status": dict(self.service_registry.get_service_count_by_status()),
            }

        return health

    @classmethod
    def create_integrated(
        cls,
        yaml_path: str,
        service_registry: ServiceRegistry,
    ) -> "IntegratedFeatureManager":
        """
        Create an integrated FeatureManager from YAML config.

        Args:
            yaml_path: Path to feature configuration YAML
            service_registry: ServiceRegistry instance

        Returns:
            Configured IntegratedFeatureManager
        """
        # Load configuration using parent class method
        base_manager = FeatureManager.from_yaml(yaml_path)

        # Create integrated manager with loaded config
        integrated = cls(
            config_set=base_manager._config_set,
            service_registry=service_registry,
        )

        # Transfer registered features
        for name, feature in base_manager._features.items():
            integrated.register_feature(feature)

        # Transfer enabled states
        # Transfer feature definitions
        integrated._feature_definitions = base_manager._feature_definitions.copy()

        logger.info(
            f"Created IntegratedFeatureManager with {len(integrated._features)} features"
        )

        return integrated

    async def _standard_startup_features(self, app=None) -> None:
        """
        Standard feature startup logic (from FeatureManager).

        This is used when ServiceRegistry is not available.
        """
        # Build startup order based on dependencies
        startup_order = self._build_startup_order()

        # Start features in dependency order
        for feature_name in startup_order:
            feature = self._features.get(feature_name)
            if feature and feature.enabled:
                try:
                    logger.info(f"Starting feature: {feature_name}")
                    await feature.startup()
                    feature._state = FeatureState.HEALTHY
                except Exception as e:
                    logger.error(f"Failed to start feature {feature_name}: {e}")
                    feature._state = FeatureState.FAILED
                    # Propagate failure to dependents
                    await self._propagate_feature_failure(feature_name)

    async def _standard_shutdown_features(self) -> None:
        """
        Standard feature shutdown logic (from FeatureManager).

        This is used when ServiceRegistry is not available.
        """
        # Shutdown in reverse dependency order
        shutdown_order = list(reversed(self._build_startup_order()))

        for feature_name in shutdown_order:
            feature = self._features.get(feature_name)
            if feature and feature.enabled:
                try:
                    logger.info(f"Shutting down feature: {feature_name}")
                    await feature.shutdown()
                    feature._state = FeatureState.STOPPED
                except Exception as e:
                    logger.error(f"Error shutting down feature {feature_name}: {e}")

    def _build_startup_order(self) -> List[str]:
        """Build feature startup order based on dependencies."""
        from graphlib import TopologicalSorter

        # Build dependency graph
        graph = {}
        for name, feature in self._features.items():
            graph[name] = feature.dependencies

        # Topological sort for startup order
        ts = TopologicalSorter(graph)
        return list(ts.static_order())

    async def _propagate_feature_failure(self, failed_feature: str) -> None:
        """Propagate feature failure to dependent features."""
        # This would need access to reverse dependency graph
        # For now, just log the failure
        logger.warning(f"Feature {failed_feature} failed - dependents may be affected")


def migrate_to_integrated_manager(
    app,
    feature_manager: FeatureManager,
    service_registry: ServiceRegistry,
) -> IntegratedFeatureManager:
    """
    Migrate an existing FeatureManager to use ServiceRegistry integration.

    This function helps with progressive migration by:
    1. Creating an IntegratedFeatureManager
    2. Transferring all existing features
    3. Registering them with ServiceRegistry
    4. Updating app.state

    Args:
        app: FastAPI application instance
        feature_manager: Existing FeatureManager
        service_registry: ServiceRegistry to integrate with

    Returns:
        New IntegratedFeatureManager instance
    """
    logger.info("Migrating FeatureManager to ServiceRegistry integration")

    # Create integrated manager
    integrated = IntegratedFeatureManager(
        config_set=feature_manager._config_set,
        service_registry=service_registry,
    )

    # Transfer all features
    for name, feature in feature_manager._features.items():
        integrated.register_feature(feature)

    # Transfer state
    integrated._feature_definitions = feature_manager._feature_definitions.copy()
    integrated._feature_states = feature_manager._feature_states.copy()

    # Update app.state
    app.state.feature_manager = integrated

    logger.info(
        f"Migration complete. {len(integrated._features)} features now managed "
        f"by both FeatureManager and ServiceRegistry"
    )

    return integrated
