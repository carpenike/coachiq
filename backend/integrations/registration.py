"""
Integration registrations for CoachIQ.

This module registers custom feature implementations with the feature manager.
"""

import logging

from backend.can.feature import CANBusFeature
from backend.core.state import AppState
from backend.integrations.analytics.registration import (
    register_performance_analytics_feature,
)
from backend.integrations.auth.registration import register_authentication_feature
from backend.integrations.can.can_tools_registration import (
    register_can_tools_features,
)
from backend.integrations.can.multi_network_registration import (
    register_multi_network_feature,
)
from backend.integrations.device_discovery.registration import (
    register_device_discovery_feature,
)
from backend.integrations.diagnostics.registration import (
    register_advanced_diagnostics_feature,
)
from backend.integrations.j1939.registration import register_j1939_feature
from backend.integrations.j1939.spartan_k2_registration import (
    register_spartan_k2_feature,
)
from backend.integrations.notifications.registration import (
    register_notification_feature,
)
from backend.integrations.rvc.firefly_registration import register_firefly_feature
from backend.integrations.rvc.registration import register_rvc_feature
from backend.services.feature_manager import FeatureManager
from backend.services.github_update_checker import (
    register_github_update_checker_feature,
)
# Note: persistence_feature factory is now registered in feature_manager.py
from backend.websocket.handlers import WebSocketManager

logger = logging.getLogger(__name__)


def _create_websocket_feature(**kwargs):
    """Factory function for WebSocketManager feature."""
    return WebSocketManager(**kwargs)


def _create_can_feature(**kwargs):
    """Factory function for CANBusFeature."""
    return CANBusFeature(**kwargs)


def _create_app_state_feature(**kwargs):
    """Factory function for AppState feature."""
    return AppState(**kwargs)


def _create_security_event_manager_feature(**kwargs):
    """Factory function for SecurityEventManager feature (DEPRECATED - now managed by ServiceRegistry)."""
    # SecurityEventManager is now managed by ServiceRegistry, not FeatureManager
    # This factory is kept for compatibility but should not be called since enabled=false
    from backend.services.security_event_manager import SecurityEventManager
    return SecurityEventManager(**kwargs)


# Note: persistence feature factory is registered in backend.services.feature_manager

# Register custom feature factories
# Note: persistence factory registered in feature_manager.py to use core implementation
FeatureManager.register_feature_factory("websocket", _create_websocket_feature)
FeatureManager.register_feature_factory("can_feature", _create_can_feature)
FeatureManager.register_feature_factory("app_state", _create_app_state_feature)
FeatureManager.register_feature_factory("security_event_manager", _create_security_event_manager_feature)
FeatureManager.register_feature_factory("rvc", register_rvc_feature)
FeatureManager.register_feature_factory("j1939", register_j1939_feature)
FeatureManager.register_feature_factory("multi_network_can", register_multi_network_feature)
FeatureManager.register_feature_factory(
    "advanced_diagnostics", register_advanced_diagnostics_feature
)
FeatureManager.register_feature_factory(
    "performance_analytics", register_performance_analytics_feature
)
FeatureManager.register_feature_factory("device_discovery", register_device_discovery_feature)
FeatureManager.register_feature_factory(
    "github_update_checker", register_github_update_checker_feature
)
FeatureManager.register_feature_factory("notifications", register_notification_feature)
FeatureManager.register_feature_factory("authentication", register_authentication_feature)
FeatureManager.register_feature_factory("firefly", register_firefly_feature)
FeatureManager.register_feature_factory("spartan_k2", register_spartan_k2_feature)


def register_custom_features(feature_manager: FeatureManager | None = None) -> None:
    """
    Register all custom features with the feature manager.

    This function is called during application startup to register
    any custom feature implementations that aren't loaded automatically
    from the feature_flags.yaml file.

    Args:
        feature_manager: Optional feature manager instance for direct registrations
    """
    logger.info("Registering custom feature implementations")
    # All feature factory registrations are done at module import time above
    # This function exists to provide a clear entry point during startup
    # and to allow for any additional dynamic registrations in the future

    # Register CAN tools if feature manager provided
    if feature_manager:
        try:
            register_can_tools_features(feature_manager)
        except Exception as e:
            logger.error("Failed to register CAN tools features: %s", e)
