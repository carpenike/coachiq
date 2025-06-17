"""
FeatureManager Lifecycle Listener

Implements the IServiceLifecycleListener interface to enable FeatureManager
to respond to service lifecycle events from ServiceRegistry.

Part of Phase 2Q: Service Lifecycle Event System
"""

import logging
from typing import TYPE_CHECKING, Dict, Set

from backend.core.service_lifecycle import (
    IServiceLifecycleListener,
    ServiceLifecycleEvent,
)

if TYPE_CHECKING:
    from backend.services.feature_manager import FeatureManager

logger = logging.getLogger(__name__)


class FeatureManagerLifecycleListener(IServiceLifecycleListener):
    """
    Lifecycle listener that enables FeatureManager to respond to
    service failures and state changes in ServiceRegistry.

    This is critical for safety compliance - when a service fails,
    dependent features must be disabled to prevent unsafe operation.
    """

    def __init__(self, feature_manager: "FeatureManager"):
        self.feature_manager = feature_manager
        # Track which services each feature depends on
        self._feature_service_deps: Dict[str, Set[str]] = {}
        self._initialize_dependency_mapping()

    def _initialize_dependency_mapping(self) -> None:
        """Build mapping of features to their service dependencies."""
        # Map known service names to feature dependencies
        service_to_features = {
            "persistence_service": ["persistence", "analytics", "diagnostics"],
            "database_manager": ["persistence", "analytics"],
            "entity_service": ["app_state", "entities"],
            "safety_service": ["safety", "pin_auth"],
            "can_interface": ["can_feature", "can_tools", "multi_network_can"],
            "websocket_manager": ["websocket"],
            "rvc_config_provider": ["rvc", "app_state"],
        }

        # Invert to get feature -> services mapping
        for service, features in service_to_features.items():
            for feature in features:
                if feature not in self._feature_service_deps:
                    self._feature_service_deps[feature] = set()
                self._feature_service_deps[feature].add(service)

    async def on_service_pre_shutdown(self, event: ServiceLifecycleEvent) -> None:
        """
        Handle pre-shutdown notification.

        Prepare features for service unavailability.
        """
        logger.info(f"FeatureManager: Preparing for shutdown of service '{event.service_name}'")

        # Find affected features
        affected_features = [
            feature_name
            for feature_name, deps in self._feature_service_deps.items()
            if event.service_name in deps
        ]

        if affected_features:
            logger.warning(
                f"Service '{event.service_name}' shutdown will affect features: "
                f"{', '.join(affected_features)}"
            )

    def on_service_failed(self, event: ServiceLifecycleEvent) -> None:
        """
        Handle service failure - CRITICAL for safety.

        This method is synchronous and blocking to ensure safety
        transitions complete before continuing.
        """
        failure_reason = event.failure_reason.value if event.failure_reason else "unknown"
        logger.critical(
            f"FeatureManager: Service '{event.service_name}' failed "
            f"(reason: {failure_reason})"
        )

        # Find and disable affected features
        affected_features = [
            feature_name
            for feature_name, deps in self._feature_service_deps.items()
            if event.service_name in deps
        ]

        for feature_name in affected_features:
            feature = self.feature_manager.get_feature(feature_name)
            if feature and feature.enabled:
                logger.warning(
                    f"Disabling feature '{feature_name}' due to "
                    f"service '{event.service_name}' failure"
                )

                # Disable the feature synchronously
                try:
                    # Use synchronous shutdown if available
                    if hasattr(feature, "shutdown_sync"):
                        feature.shutdown_sync()
                    else:
                        # Log warning - feature may not shut down cleanly
                        logger.error(
                            f"Feature '{feature_name}' does not support synchronous "
                            "shutdown - safety may be compromised"
                        )

                    # Mark as disabled
                    feature.enabled = False

                    # Transition to safe state if safety-critical
                    if hasattr(feature, "safety_classification") and feature.safety_classification:
                        logger.critical(
                            f"Safety-critical feature '{feature_name}' disabled - "
                            "transitioning to SAFE_SHUTDOWN"
                        )
                        if hasattr(feature, "transition_to_safe_state"):
                            feature.transition_to_safe_state()

                except Exception as e:
                    logger.error(
                        f"Failed to disable feature '{feature_name}': {e}",
                        exc_info=True
                    )

        # Log impacted services from event metadata
        if "impacted_services" in event.metadata:
            logger.warning(
                f"Service failure cascade - impacted services: "
                f"{', '.join(event.metadata['impacted_services'])}"
            )

    async def on_service_stopped(self, event: ServiceLifecycleEvent) -> None:
        """
        Handle service stopped notification.

        Update feature availability based on missing service.
        """
        logger.info(f"FeatureManager: Service '{event.service_name}' has stopped")

        # Features depending on this service should already be disabled
        # from on_service_failed, but verify
        affected_features = [
            feature_name
            for feature_name, deps in self._feature_service_deps.items()
            if event.service_name in deps
        ]

        for feature_name in affected_features:
            feature = self.feature_manager.get_feature(feature_name)
            if feature and feature.enabled:
                logger.error(
                    f"Feature '{feature_name}' still enabled after service "
                    f"'{event.service_name}' stopped - disabling now"
                )
                feature.enabled = False

    async def on_service_started(self, event: ServiceLifecycleEvent) -> None:
        """
        Handle service started notification.

        Re-enable features if all dependencies are available.
        """
        logger.info(f"FeatureManager: Service '{event.service_name}' has started")

        # Check if any features can be re-enabled
        affected_features = [
            feature_name
            for feature_name, deps in self._feature_service_deps.items()
            if event.service_name in deps
        ]

        if event.metadata.get("restart"):
            logger.info(
                f"Service '{event.service_name}' restarted - "
                "checking feature availability"
            )

        for feature_name in affected_features:
            feature = self.feature_manager.get_feature(feature_name)
            if feature and not feature.enabled:
                # Check if all dependencies are now available
                # This would require ServiceRegistry access - simplified for now
                logger.info(
                    f"Feature '{feature_name}' may now be re-enabled after "
                    f"service '{event.service_name}' started"
                )

    def register_feature_dependencies(self, feature_name: str, service_deps: Set[str]) -> None:
        """
        Register service dependencies for a feature.

        Args:
            feature_name: Name of the feature
            service_deps: Set of service names the feature depends on
        """
        self._feature_service_deps[feature_name] = service_deps
        logger.debug(
            f"Registered dependencies for feature '{feature_name}': "
            f"{', '.join(service_deps)}"
        )
