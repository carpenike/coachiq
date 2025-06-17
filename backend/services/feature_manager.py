"""
Feature management for backend services with safety classifications.

Handles feature registration, dependency resolution, startup, and shutdown
with ISO 26262-inspired safety patterns for RV-C vehicle control systems.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import ValidationError

from backend.services.feature_base import Feature, GenericFeature
from backend.services.feature_models import (
    FeatureConfigurationSet,
    FeatureDefinition,
    FeatureState,
    SafetyClassification,
)
from backend.services.feature_manager_listener import FeatureManagerLifecycleListener

logger = logging.getLogger(__name__)


class FeatureManager:
    """
    Manages features with safety classifications, dependencies, and lifecycle.

    This manager implements ISO 26262-inspired safety patterns for vehicle control systems:
    - Safety-critical features cannot be toggled at runtime
    - Position-critical features maintain current state in safe mode
    - Health monitoring and dependency-aware failure propagation
    - Controlled startup/shutdown with dependency ordering
    """

    _feature_factories: ClassVar[dict[str, Callable[..., Feature]]] = {}

    def __init__(self, config_set: FeatureConfigurationSet) -> None:
        """
        Initialize FeatureManager with validated configuration.

        Args:
            config_set: Validated FeatureConfigurationSet from YAML
        """
        self._config_set = config_set
        self._features: dict[str, Feature] = {}
        self._lifecycle_listener: FeatureManagerLifecycleListener | None = None
        self._feature_definitions: dict[str, FeatureDefinition] = config_set.features
        self._feature_states: dict[str, FeatureState] = {}
        self._reverse_dependencies: dict[str, set[str]] = {}
        self._health_check_running = False
        self._core_services = None  # Will be injected after initialization

    def set_core_services(self, core_services: Any) -> None:
        """
        Inject core services for features to use.

        Args:
            core_services: The CoreServices instance containing persistence, database_manager, etc.
        """
        self._core_services = core_services
        logger.info("Core services injected into feature manager")

    def get_core_services(self) -> Any:
        """
        Get injected core services.

        Returns:
            The CoreServices instance

        Raises:
            RuntimeError: If core services not set
        """
        if self._core_services is None:
            msg = "Core services not injected. Call set_core_services() first."
            raise RuntimeError(msg)
        return self._core_services

    def register_feature(self, feature: Feature) -> None:
        """
        Register a feature instance with safety validation.

        Args:
            feature: Feature instance to register

        Raises:
            ValueError: If feature is not defined in configuration
        """
        if feature.name not in self._feature_definitions:
            msg = f"Feature '{feature.name}' not found in configuration"
            raise ValueError(msg)

        self._features[feature.name] = feature
        self._feature_states[feature.name] = feature.state
        self._build_reverse_dependency_graph()
        logger.debug("Registered feature: %s", feature.name)

    @property
    def features(self) -> dict[str, Feature]:
        """
        Returns all registered features.
        """
        return self._features

    @property
    def feature_definitions(self) -> dict[str, FeatureDefinition]:
        """
        Returns all feature definitions from configuration.
        """
        return self._feature_definitions

    def is_enabled(self, feature_name: str) -> bool:
        """
        Check if a feature is enabled.

        Args:
            feature_name: Name of the feature to check

        Returns:
            True if the feature exists and is enabled, False otherwise
        """
        feature = self._features.get(feature_name)
        return feature is not None and getattr(feature, "enabled", False)

    def get_safety_classification(self, feature_name: str) -> SafetyClassification | None:
        """
        Get the safety classification of a feature.

        Args:
            feature_name: Name of the feature

        Returns:
            SafetyClassification if feature exists, None otherwise
        """
        definition = self._feature_definitions.get(feature_name)
        return definition.safety_classification if definition else None

    def can_be_toggled_at_runtime(self, feature_name: str) -> bool:
        """
        Check if a feature can be safely toggled at runtime.

        Args:
            feature_name: Name of the feature

        Returns:
            True if feature can be toggled, False if safety-critical
        """
        definition = self._feature_definitions.get(feature_name)
        return definition.can_be_toggled_at_runtime() if definition else False

    def is_safety_critical(self, feature_name: str) -> bool:
        """
        Check if a feature is safety-critical.

        Args:
            feature_name: Name of the feature

        Returns:
            True if safety-critical, False otherwise
        """
        definition = self._feature_definitions.get(feature_name)
        return definition.is_safety_critical() if definition else False

    def get_feature(self, feature_name: str) -> Any | None:
        """
        Get a feature instance by name.

        Args:
            feature_name: Name of the feature to retrieve

        Returns:
            Feature instance if found, None otherwise
        """
        return self._features.get(feature_name)

    def get_all_features(self) -> dict[str, Any]:
        """
        Get all registered features.

        Returns:
            Dictionary of feature name to feature instance
        """
        return self._features.copy()

    def get_enabled_features(self) -> dict[str, Any]:
        """
        Get all enabled features.

        Returns:
            Dictionary of enabled feature name to feature instance
        """
        return {
            name: feature
            for name, feature in self._features.items()
            if getattr(feature, "enabled", False)
        }

    def get_core_features(self) -> dict[str, Any]:
        """
        Get all core features.

        Returns:
            Dictionary of core feature name to feature instance
        """
        return {
            name: feature
            for name, feature in self._features.items()
            if getattr(feature, "core", False)
        }

    def get_optional_features(self) -> dict[str, Any]:
        """
        Get all optional (non-core) features.

        Returns:
            Dictionary of optional feature name to feature instance
        """
        return {
            name: feature
            for name, feature in self._features.items()
            if not getattr(feature, "core", False)
        }

    def update_feature_state(self, feature_name: str, enabled: bool) -> bool:
        """
        Update feature enabled state at runtime.

        Args:
            feature_name: Name of feature to update
            enabled: New enabled state

        Returns:
            True if updated successfully, False if feature not found
        """
        feature = self._features.get(feature_name)
        if not feature:
            return False

        if feature.enabled != enabled:
            logger.info(
                f"Updating feature '{feature_name}' enabled state: {feature.enabled} -> {enabled}"
            )
            feature.enabled = enabled

        return True

    def get_configuration_metadata(self) -> dict[str, Any]:
        """Get metadata about current configuration."""
        return {
            "total_features": len(self._features),
            "enabled_features": len(self.get_enabled_features()),
            "core_features": len(self.get_core_features()),
            "feature_dependencies": {
                name: getattr(feature, "dependencies", [])
                for name, feature in self._features.items()
            },
        }

    def _resolve_dependencies(self) -> list[str]:
        """
        Resolve feature dependencies using topological sort.

        Returns:
            List of feature names in dependency order.

        Raises:
            ValueError: If a cyclic dependency is detected.
        """
        graph: dict[str, list[str]] = {}
        for name, feature in self._features.items():
            graph[name] = feature.dependencies or []
        visited: set[str] = set()
        temp: set[str] = set()
        result: list[str] = []

        def visit(node: str) -> None:
            if node in temp:
                msg = f"Cyclic dependency detected at '{node}'"
                raise ValueError(msg)
            if node not in visited:
                temp.add(node)
                for dep in graph.get(node, []):
                    if dep not in self._features:
                        msg = f"Missing dependency '{dep}' for feature '{node}'"
                        raise ValueError(msg)
                    visit(dep)
                temp.remove(node)
                visited.add(node)
                result.append(node)

        for node in graph:
            visit(node)
        return result

    def _build_reverse_dependency_graph(self) -> None:
        """
        Build reverse dependency graph for efficient health propagation.

        Maps each feature to the set of features that depend on it.
        """
        self._reverse_dependencies.clear()

        for feature_name, feature in self._features.items():
            for dependency in feature.dependencies:
                if dependency not in self._reverse_dependencies:
                    self._reverse_dependencies[dependency] = set()
                self._reverse_dependencies[dependency].add(feature_name)

        logger.debug("Built reverse dependency graph: %s", dict(self._reverse_dependencies))

    async def _check_all_feature_health(self) -> dict[str, FeatureState]:
        """
        Check health of all enabled features and detect state changes.

        Returns:
            Dictionary mapping feature names to their current health states
        """
        current_states = {}

        for feature_name, feature in self._features.items():
            if not getattr(feature, "enabled", False):
                current_states[feature_name] = FeatureState.STOPPED
                continue

            try:
                # Check feature health (async)
                health_state = await feature.check_health()
                current_states[feature_name] = health_state

                # Update our tracking if state changed
                previous_state = self._feature_states.get(feature_name, FeatureState.STOPPED)
                if health_state != previous_state:
                    logger.info(
                        f"Feature '{feature_name}' state transition: {previous_state.value} -> {health_state.value}"
                    )
                    self._feature_states[feature_name] = health_state

                    # Update the feature's internal state to match
                    feature.state = health_state

            except Exception as e:
                logger.error(f"Health check failed for feature '{feature_name}': {e}")
                current_states[feature_name] = FeatureState.FAILED
                self._feature_states[feature_name] = FeatureState.FAILED
                feature.state = FeatureState.FAILED

        return current_states

    async def _propagate_health_changes(self, feature_name: str, new_state: FeatureState, old_state: FeatureState) -> None:
        """
        Propagate health state changes through dependency graph.

        Args:
            feature_name: Name of feature whose state changed
            new_state: New health state
            old_state: Previous health state
        """
        if new_state == old_state:
            return

        dependents = self._reverse_dependencies.get(feature_name, set())
        if not dependents:
            return

        definition = self._feature_definitions[feature_name]

        logger.info(
            f"Propagating state change from '{feature_name}' ({old_state.value} -> {new_state.value}) "
            f"to {len(dependents)} dependents: {list(dependents)}"
        )

        for dependent_name in dependents:
            dependent_feature = self._features.get(dependent_name)
            if not dependent_feature or not getattr(dependent_feature, "enabled", False):
                continue

            try:
                if new_state in [FeatureState.FAILED, FeatureState.DEGRADED]:
                    # Dependency failed or degraded
                    await dependent_feature.on_dependency_failed(feature_name, new_state)
                    logger.debug(f"Notified '{dependent_name}' of dependency '{feature_name}' failure")

                elif old_state in [FeatureState.FAILED, FeatureState.DEGRADED] and new_state == FeatureState.HEALTHY:
                    # Dependency recovered
                    await dependent_feature.on_dependency_recovered(feature_name)
                    logger.debug(f"Notified '{dependent_name}' of dependency '{feature_name}' recovery")

                # Update our tracking of the dependent's state
                dependent_new_state = dependent_feature.state
                dependent_old_state = self._feature_states.get(dependent_name, FeatureState.STOPPED)

                if dependent_new_state != dependent_old_state:
                    self._feature_states[dependent_name] = dependent_new_state

                    # Check if we need to handle safety-critical failures
                    dependent_definition = self._feature_definitions[dependent_name]
                    if (dependent_new_state == FeatureState.FAILED and
                        dependent_definition.safety_classification == SafetyClassification.CRITICAL):
                        logger.critical(
                            f"SAFETY CRITICAL: Feature '{dependent_name}' has FAILED. "
                            f"Triggering safe state procedures."
                        )
                        await self._handle_critical_failure(dependent_name)

                    # Recursively propagate this change
                    await self._propagate_health_changes(dependent_name, dependent_new_state, dependent_old_state)

            except Exception as e:
                logger.error(f"Error propagating health change to '{dependent_name}': {e}")

    async def _handle_critical_failure(self, feature_name: str) -> None:
        """
        Handle failure of a safety-critical feature.

        Args:
            feature_name: Name of the failed critical feature
        """
        definition = self._feature_definitions[feature_name]

        logger.critical(f"CRITICAL FEATURE FAILURE: {feature_name}")
        logger.critical(f"Safe state action: {definition.safe_state_action.value}")
        logger.critical(f"Maintain state on failure: {definition.maintain_state_on_failure}")

        # For RV-C systems, we follow the "maintain current position" principle
        # Critical failures should NOT cause physical retractions or movements
        if definition.safe_state_action.value == "maintain_position":
            logger.critical(
                f"SAFETY: Maintaining current physical positions for {feature_name}. "
                f"No automatic retractions will be performed."
            )

        # Notify all position-critical features to enter safe state
        position_critical_features = [
            name for name, defn in self._feature_definitions.items()
            if defn.safety_classification == SafetyClassification.POSITION_CRITICAL
        ]

        for pos_feature_name in position_critical_features:
            pos_feature = self._features.get(pos_feature_name)
            if pos_feature and getattr(pos_feature, "enabled", False):
                try:
                    # Set to safe shutdown state
                    pos_feature.state = FeatureState.SAFE_SHUTDOWN
                    self._feature_states[pos_feature_name] = FeatureState.SAFE_SHUTDOWN

                    logger.warning(
                        f"Position-critical feature '{pos_feature_name}' entered SAFE_SHUTDOWN state"
                    )
                except Exception as e:
                    logger.error(f"Error setting safe state for '{pos_feature_name}': {e}")

    async def check_system_health(self) -> dict[str, Any]:
        """
        Perform comprehensive system health check with state propagation.

        Returns:
            Dictionary containing system health status and feature states
        """
        if self._health_check_running:
            logger.debug("Health check already in progress, skipping")
            return {"status": "check_in_progress", "features": dict(self._feature_states)}

        self._health_check_running = True
        try:
            logger.debug("Starting comprehensive health check")

            # Check all feature health
            current_states = await self._check_all_feature_health()

            # Identify and propagate state changes
            state_changes = []
            for feature_name, new_state in current_states.items():
                old_state = self._feature_states.get(feature_name, FeatureState.STOPPED)
                if new_state != old_state:
                    state_changes.append((feature_name, new_state, old_state))

            # Propagate all changes
            for feature_name, new_state, old_state in state_changes:
                await self._propagate_health_changes(feature_name, new_state, old_state)

            # Calculate system health metrics
            enabled_features = {
                name: state for name, state in current_states.items()
                if self._features[name].enabled
            }

            healthy_count = sum(1 for state in enabled_features.values() if state == FeatureState.HEALTHY)
            total_enabled = len(enabled_features)

            # Count by safety classification
            critical_features = []
            failed_critical = []

            for feature_name, state in enabled_features.items():
                definition = self._feature_definitions[feature_name]
                if definition.is_safety_critical():
                    critical_features.append(feature_name)
                    if state == FeatureState.FAILED:
                        failed_critical.append(feature_name)

            system_status = "healthy"
            if failed_critical:
                system_status = "critical"
            elif healthy_count < total_enabled * 0.8:  # Less than 80% healthy
                system_status = "degraded"

            health_report = {
                "status": system_status,
                "timestamp": datetime.utcnow().isoformat(),
                "summary": {
                    "total_features": len(self._features),
                    "enabled_features": total_enabled,
                    "healthy_features": healthy_count,
                    "critical_features": len(critical_features),
                    "failed_critical_features": len(failed_critical),
                },
                "features": current_states,
                "state_changes": [
                    {"feature": name, "old_state": old.value, "new_state": new.value}
                    for name, new, old in state_changes
                ],
                "failed_critical": failed_critical,
            }

            if state_changes:
                logger.info(f"Health check completed with {len(state_changes)} state changes")
            else:
                logger.debug("Health check completed - no state changes")

            return health_report

        except Exception as e:
            logger.error(f"Error during system health check: {e}")
            return {
                "status": "error",
                "error": str(e),
                "features": dict(self._feature_states),
            }
        finally:
            self._health_check_running = False

    async def startup(self) -> None:
        """
        Start all enabled features in dependency order.

        Resolves feature dependencies and starts each enabled feature in the correct order.
        """
        logger.info("Starting features...")

        # Build reverse dependency graph for health propagation
        self._build_reverse_dependency_graph()

        try:
            order = self._resolve_dependencies()

            for name in order:
                feature = self._features[name]
                if getattr(feature, "enabled", False):
                    logger.info(f"Starting feature: {name}")

                    # Initialize state tracking
                    self._feature_states[name] = FeatureState.INITIALIZING

                    try:
                        if hasattr(feature, "startup"):
                            await feature.startup()

                        # Update state tracking after successful startup
                        self._feature_states[name] = feature.state

                    except Exception as e:
                        # Mark feature as failed
                        feature.state = FeatureState.FAILED
                        self._feature_states[name] = FeatureState.FAILED

                        # Log feature failure
                        logger.error("Feature %s startup failed: %s", name, e)
                        feature.enabled = False  # Disable failed feature

        except ValueError as e:
            logger.error("Feature startup error: %s", e)
            raise
        logger.info("All features started")

    async def shutdown(self) -> None:
        """
        Shut down all enabled features in reverse dependency order.
        """
        logger.info("Shutting down features...")
        try:
            order = self._resolve_dependencies()[::-1]  # Reverse for shutdown
            for name in order:
                feature = self._features[name]
                if getattr(feature, "enabled", False):
                    logger.info(f"Shutting down feature: {name}")
                    try:
                        if hasattr(feature, "shutdown"):
                            await feature.shutdown()
                        logger.debug(f"Feature {name} shut down successfully")
                    except Exception as e:
                        logger.error(f"Error shutting down feature {name}: {e}")
                        # Continue with other features even if one fails
        except ValueError as e:
            logger.error(f"Feature shutdown error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during feature shutdown: {e}")
        logger.info("All features shut down")

    @classmethod
    def register_feature_factory(cls, feature_name: str, factory_func: Callable[..., Any]) -> None:
        """
        Register a factory function for a specific feature.

        Args:
            feature_name: Name of the feature
            factory_func: Function that creates a feature instance
        """
        cls._feature_factories[feature_name] = factory_func

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> "FeatureManager":
        """
        Create a FeatureManager instance from a validated YAML config file.

        Args:
            yaml_path: Path to the YAML file containing feature definitions

        Returns:
            FeatureManager instance with features loaded and validated

        Raises:
            ValidationError: If YAML structure is invalid
            ValueError: If dependency validation fails
        """
        # Load and validate YAML structure
        try:
            with open(yaml_path, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)
        except Exception as e:
            msg = f"Failed to load YAML file '{yaml_path}': {e}"
            raise ValueError(msg) from e

        # Convert to feature definitions with validation
        feature_definitions = {}
        for feature_name, feature_data in raw_config.items():
            try:
                # Add feature name to data and validate
                feature_data_with_name = {"name": feature_name, **feature_data}
                feature_def = FeatureDefinition(**feature_data_with_name)
                feature_definitions[feature_name] = feature_def
            except ValidationError as e:
                logger.error(f"Invalid feature definition for '{feature_name}': {e}")
                raise

        # Create and validate configuration set
        try:
            config_set = FeatureConfigurationSet(features=feature_definitions)
            config_set.validate_dependency_graph()
        except ValidationError as e:
            msg = f"Feature configuration validation failed: {e}"
            raise ValueError(msg) from e

        # Create manager with validated configuration
        manager = cls(config_set)

        # Register feature instances
        for feature_name, feature_def in feature_definitions.items():
            if feature_name in cls._feature_factories:
                # Use factory to create specialized feature
                feature = cls._feature_factories[feature_name](
                    name=feature_name,
                    enabled=feature_def.enabled_by_default,
                    core=feature_def.is_safety_critical(),  # Map to safety classification
                    config=feature_def.config,
                    dependencies=feature_def.dependencies,
                    friendly_name=feature_def.friendly_name,
                    safety_classification=feature_def.safety_classification,
                    log_state_transitions=True,
                )
            else:
                # Create generic feature
                feature = GenericFeature(
                    name=feature_name,
                    enabled=feature_def.enabled_by_default,
                    core=feature_def.is_safety_critical(),  # Map to safety classification
                    config=feature_def.config,
                    dependencies=feature_def.dependencies,
                    friendly_name=feature_def.friendly_name,
                    safety_classification=feature_def.safety_classification,
                    log_state_transitions=True,
                )
            manager.register_feature(feature)

        logger.info(f"Loaded {len(feature_definitions)} features from {yaml_path}")
        return manager

    def apply_runtime_config(self, settings: Any) -> None:
        """
        Apply runtime configuration from application settings.

        This simplified method applies environment variable overrides to feature states.
        Environment variables have precedence over YAML defaults.

        Args:
            settings: Application settings containing feature overrides
        """
        import os

        logger.info("Applying runtime configuration to features")

        for feature_name, feature in self._features.items():
            definition = self._feature_definitions[feature_name]

            # Environment variable override (primary method)
            env_var = f"COACHIQ_FEATURES__ENABLE_{feature_name.upper()}"
            env_value = os.getenv(env_var)

            if env_value is not None:
                enabled = env_value.lower() in ("1", "true", "yes", "on")
                if feature.enabled != enabled:
                    # Safety check: prevent disabling mandatory features via env vars
                    if not enabled and definition.mandatory:
                        logger.warning(
                            f"Ignoring attempt to disable mandatory feature '{feature_name}' via {env_var}"
                        )
                        continue

                    # Safety check: prevent disabling critical features via env vars
                    if not enabled and definition.is_safety_critical():
                        logger.warning(
                            f"Ignoring attempt to disable safety-critical feature '{feature_name}' via {env_var}"
                        )
                        continue

                    logger.info(
                        f"Runtime override: '{feature_name}' enabled={enabled} (from {env_var})"
                    )
                    feature.enabled = enabled

            # Settings-based override (secondary method)
            elif hasattr(settings, "features"):
                # Direct mapping from FeaturesSettings to feature names
                settings_value = getattr(settings.features, feature_name, None)
                if settings_value is not None:
                    if feature.enabled != settings_value:
                        # Safety check: prevent disabling mandatory features
                        if not settings_value and definition.mandatory:
                            logger.warning(
                                f"Ignoring attempt to disable mandatory feature '{feature_name}' via settings"
                            )
                            continue

                        # Safety check: prevent disabling critical features
                        if not settings_value and definition.is_safety_critical():
                            logger.warning(
                                f"Ignoring attempt to disable safety-critical feature '{feature_name}' via settings"
                            )
                            continue

                        logger.info(
                            f"Runtime override: '{feature_name}' enabled={settings_value} (from settings.features)"
                        )
                        feature.enabled = settings_value

        # Log final safety-critical feature status
        critical_features = [
            name for name, feature in self._features.items()
            if self._feature_definitions[name].is_safety_critical() and feature.enabled
        ]
        logger.info(f"Safety-critical features enabled: {critical_features}")

    def integrate_with_service_registry(self, service_registry: Any) -> None:
        """
        Integrate FeatureManager with ServiceRegistry for lifecycle events.

        This enables FeatureManager to respond to service failures and
        automatically disable dependent features for safety.

        Args:
            service_registry: The EnhancedServiceRegistry instance
        """
        # Create lifecycle listener
        self._lifecycle_listener = FeatureManagerLifecycleListener(self)

        # Register with high priority to ensure safety transitions happen first
        service_registry.add_lifecycle_listener(self._lifecycle_listener, priority=100)

        logger.info(
            "FeatureManager integrated with ServiceRegistry for lifecycle events"
        )

    async def request_feature_toggle(
        self,
        feature_name: str,
        enabled: bool,
        user: str = "system",
        reason: str = "Manual request",
        override_safety: bool = False,
        authorization_code: str = "",
    ) -> tuple[bool, str]:
        """
        Request feature toggle with comprehensive safety validation.

        Args:
            feature_name: Name of feature to toggle
            enabled: Desired enabled state
            user: User requesting the toggle
            reason: Reason for the toggle request
            override_safety: Whether to override safety restrictions
            authorization_code: Authorization code for safety overrides

        Returns:
            Tuple of (success, message)
        """
        feature = self.get_feature(feature_name)
        if not feature:
            return False, f"Feature '{feature_name}' not found"

        definition = self._feature_definitions.get(feature_name)
        if not definition:
            return False, f"Feature definition for '{feature_name}' not found"

        # Check if this is actually a state change
        if feature.enabled == enabled:
            return True, f"Feature '{feature_name}' already {'enabled' if enabled else 'disabled'}"

        # Safety gate: check if toggling is allowed
        if definition.is_safety_critical():
            if not override_safety:
                message = f"Cannot toggle safety-critical feature '{feature_name}' at runtime without override"
                logger.warning(
                    "SECURITY: %s - requested by '%s'. Use override_safety=True if necessary.",
                    message, user
                )
                await self._audit_log_feature_action(
                    "toggle_rejected_safety",
                    feature_name,
                    {"user": user, "reason": reason, "enabled": enabled, "message": message}
                )
                return False, message
            # Validate authorization code for safety override
            if not self._validate_safety_override_authorization(authorization_code, user):
                message = f"Invalid authorization for safety override of '{feature_name}'"
                logger.warning("SECURITY: %s - requested by '%s'", message, user)
                await self._audit_log_feature_action(
                    "toggle_rejected_authorization",
                    feature_name,
                    {"user": user, "reason": reason, "enabled": enabled, "message": message}
                )
                return False, message

        # Position-critical devices: check if they're deployed
        if definition.safety_classification == SafetyClassification.POSITION_CRITICAL:
            if not enabled and await self._is_device_deployed(feature_name):
                message = f"Cannot disable '{feature_name}' while device is deployed - maintain current position"
                logger.warning("SAFETY: %s - requested by '%s'", message, user)
                await self._audit_log_feature_action(
                    "toggle_rejected_deployed",
                    feature_name,
                    {"user": user, "reason": reason, "enabled": enabled, "message": message}
                )
                return False, message

        # Dependency validation: check if dependent features would be affected
        if not enabled:
            dependent_features = self._get_dependent_features(feature_name)
            if dependent_features:
                critical_dependents = [
                    f for f in dependent_features
                    if self._feature_definitions[f].is_safety_critical()
                    and self._features[f].enabled
                ]
                if critical_dependents:
                    message = (
                        f"Cannot disable '{feature_name}' - safety-critical dependents would be affected: "
                        f"{critical_dependents}"
                    )
                    logger.warning("SAFETY: %s - requested by '%s'", message, user)
                    await self._audit_log_feature_action(
                        "toggle_rejected_dependents",
                        feature_name,
                        {
                            "user": user,
                            "reason": reason,
                            "enabled": enabled,
                            "critical_dependents": critical_dependents,
                            "message": message,
                        }
                    )
                    return False, message

        # Execute the toggle
        try:
            old_state = feature.state

            if enabled:
                logger.info("Enabling feature '%s' requested by '%s': %s", feature_name, user, reason)

                # Set to initializing state
                feature.state = FeatureState.INITIALIZING
                feature.enabled = True

                # Start the feature
                if hasattr(feature, "startup"):
                    await feature.startup()

                # Verify health after startup
                await self._verify_feature_health(feature_name)

                # Log successful enablement
                await self._audit_log_feature_action(
                    "feature_enabled",
                    feature_name,
                    {
                        "user": user,
                        "reason": reason,
                        "old_state": old_state.value,
                        "new_state": feature.state.value,
                        "override_safety": override_safety,
                    }
                )

                return True, f"Feature '{feature_name}' successfully enabled"

            logger.info("Disabling feature '%s' requested by '%s': %s", feature_name, user, reason)

            # Propagate shutdown to dependents first
            await self._propagate_shutdown_to_dependents(feature_name)

            # Set to safe shutdown state
            feature.state = FeatureState.SAFE_SHUTDOWN

            # Shutdown the feature
            if hasattr(feature, "shutdown"):
                await feature.shutdown()

            # Mark as disabled
            feature.enabled = False
            feature.state = FeatureState.STOPPED

            # Log successful disablement
            await self._audit_log_feature_action(
                "feature_disabled",
                feature_name,
                {
                    "user": user,
                    "reason": reason,
                    "old_state": old_state.value,
                    "new_state": feature.state.value,
                    "override_safety": override_safety,
                }
            )

            return True, f"Feature '{feature_name}' successfully disabled"

        except Exception as e:
            error_msg = f"Failed to toggle feature '{feature_name}': {e}"
            logger.error("Feature toggle error: %s", error_msg)

            # Set feature to failed state
            feature.state = FeatureState.FAILED

            # Log the failure
            await self._audit_log_feature_action(
                "toggle_failed",
                feature_name,
                {
                    "user": user,
                    "reason": reason,
                    "enabled": enabled,
                    "error": str(e),
                    "old_state": old_state.value if "old_state" in locals() else "unknown",
                    "new_state": feature.state.value,
                }
            )

            return False, error_msg

    def _validate_safety_override_authorization(self, authorization_code: str, user: str) -> bool:
        """
        Validate authorization code for safety override.

        Args:
            authorization_code: Provided authorization code
            user: User requesting the override

        Returns:
            True if authorization is valid
        """
        # Simple validation - in production, this would be more sophisticated
        # with proper cryptographic signatures, time-based tokens, etc.

        if not authorization_code:
            return False

        # Basic authorization codes (this should be encrypted/hashed in production)
        valid_codes = {
            "SAFETY_OVERRIDE_ADMIN": ["admin", "service", "technician"],
            "EMERGENCY_OVERRIDE_OPS": ["admin", "operator"],
        }

        for code, allowed_users in valid_codes.items():
            if authorization_code == code and user in allowed_users:
                logger.info("Valid safety override authorization: %s by %s", code, user)
                return True

        logger.warning("Invalid safety override authorization attempt: %s by %s", authorization_code, user)
        return False

    async def _is_device_deployed(self, feature_name: str) -> bool:
        """
        Check if a position-critical device is currently deployed.

        Args:
            feature_name: Name of the feature to check

        Returns:
            True if device is deployed (slides out, awnings extended, etc.)
        """
        # This would interface with actual device sensors
        # For now, we'll simulate based on feature type

        if feature_name == "firefly":
            # Check if any slides or awnings are deployed
            # In real implementation, this would query CAN bus
            return False  # Assume retracted for now
        if feature_name == "spartan_k2":
            # Check if leveling jacks are deployed
            return False  # Assume retracted for now

        return False  # Default to not deployed

    def _get_dependent_features(self, feature_name: str) -> list[str]:
        """
        Get list of features that depend on the given feature.

        Args:
            feature_name: Feature to check dependencies for

        Returns:
            List of feature names that depend on this feature
        """
        dependents = []
        for name, feature in self._features.items():
            if feature_name in feature.dependencies:
                dependents.append(name)
        return dependents

    async def _verify_feature_health(self, feature_name: str) -> None:
        """
        Verify that a feature is healthy after startup.

        Args:
            feature_name: Name of feature to verify

        Raises:
            RuntimeError: If feature is not healthy
        """
        feature = self._features[feature_name]

        # Give feature time to initialize
        await asyncio.sleep(1.0)

        # Check health
        health_state = await feature.check_health()

        if health_state not in [FeatureState.HEALTHY, FeatureState.INITIALIZING]:
            raise RuntimeError(f"Feature '{feature_name}' is not healthy after startup: {health_state.value}")

        logger.debug("Feature '%s' health verified: %s", feature_name, health_state.value)

    async def _propagate_shutdown_to_dependents(self, feature_name: str) -> None:
        """
        Propagate shutdown notification to dependent features.

        Args:
            feature_name: Feature being shut down
        """
        dependent_features = self._get_dependent_features(feature_name)

        if not dependent_features:
            return

        logger.info(
            "Propagating shutdown of '%s' to %d dependents: %s",
            feature_name, len(dependent_features), dependent_features
        )

        for dependent_name in dependent_features:
            dependent_feature = self._features.get(dependent_name)
            if dependent_feature and dependent_feature.enabled:
                try:
                    # Notify dependent of the shutdown
                    await dependent_feature.on_dependency_failed(feature_name, FeatureState.STOPPED)

                    # Check if dependent should be shut down too
                    dependent_def = self._feature_definitions[dependent_name]
                    if dependent_def.is_safety_critical():
                        logger.warning(
                            "Safety-critical dependent '%s' affected by '%s' shutdown - may need manual review",
                            dependent_name, feature_name
                        )

                except Exception as e:
                    logger.error(
                        "Error notifying dependent '%s' of '%s' shutdown: %s",
                        dependent_name, feature_name, e
                    )

    async def _audit_log_feature_action(
        self,
        action_type: str,
        feature_name: str,
        details: dict[str, Any]
    ) -> None:
        """
        Log feature management action to audit trail.

        Args:
            action_type: Type of action performed
            feature_name: Feature affected
            details: Additional details about the action
        """
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action_type": action_type,
            "feature_name": feature_name,
            "details": details,
        }

        # Log to standard logger
        logger.info("AUDIT FEATURE: %s - %s - %s", action_type, feature_name, details)

    async def attempt_feature_recovery(
        self,
        feature_name: str,
        user: str = "system",
        reason: str = "Automatic recovery",
        max_attempts: int = 3,
    ) -> tuple[bool, str]:
        """
        Attempt to recover a failed feature.

        Args:
            feature_name: Name of feature to recover
            user: User requesting the recovery
            reason: Reason for recovery attempt
            max_attempts: Maximum number of recovery attempts

        Returns:
            Tuple of (success, message)
        """
        feature = self.get_feature(feature_name)
        if not feature:
            return False, f"Feature '{feature_name}' not found"

        definition = self._feature_definitions.get(feature_name)
        if not definition:
            return False, f"Feature definition for '{feature_name}' not found"

        # Only attempt recovery for failed features
        if feature.state not in [FeatureState.FAILED, FeatureState.DEGRADED]:
            return True, f"Feature '{feature_name}' is not in a recoverable state: {feature.state.value}"

        logger.info("Attempting recovery of feature '%s' (user: %s, reason: %s)", feature_name, user, reason)

        await self._audit_log_feature_action(
            "recovery_started",
            feature_name,
            {
                "user": user,
                "reason": reason,
                "initial_state": feature.state.value,
                "max_attempts": max_attempts,
            }
        )

        # Attempt recovery with retries
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info("Recovery attempt %d/%d for feature '%s'", attempt, max_attempts, feature_name)

                # Reset feature state
                feature.state = FeatureState.INITIALIZING

                # Clear failed dependencies if they've recovered
                self._clear_recovered_dependencies(feature)

                # Attempt startup
                if hasattr(feature, "startup"):
                    await feature.startup()

                # Verify health
                await asyncio.sleep(2.0)  # Give more time for recovery
                health_state = await feature.check_health()

                if health_state == FeatureState.HEALTHY:
                    feature.enabled = True

                    await self._audit_log_feature_action(
                        "recovery_successful",
                        feature_name,
                        {
                            "user": user,
                            "reason": reason,
                            "attempt": attempt,
                            "final_state": feature.state.value,
                        }
                    )

                    logger.info("Successfully recovered feature '%s' on attempt %d", feature_name, attempt)
                    return True, f"Feature '{feature_name}' successfully recovered on attempt {attempt}"

                logger.warning("Recovery attempt %d failed for '%s': health state %s",
                             attempt, feature_name, health_state.value)

            except Exception as e:
                logger.error("Recovery attempt %d failed for '%s': %s", attempt, feature_name, e)

                if attempt == max_attempts:
                    # Final attempt failed
                    feature.state = FeatureState.FAILED

                    await self._audit_log_feature_action(
                        "recovery_failed",
                        feature_name,
                        {
                            "user": user,
                            "reason": reason,
                            "attempts": max_attempts,
                            "final_error": str(e),
                            "final_state": feature.state.value,
                        }
                    )

                    return False, f"Feature '{feature_name}' recovery failed after {max_attempts} attempts: {e}"

                # Wait before next attempt
                await asyncio.sleep(min(2.0 * attempt, 10.0))

        # Should not reach here, but just in case
        return False, f"Feature '{feature_name}' recovery failed after {max_attempts} attempts"

    def _clear_recovered_dependencies(self, feature: Feature) -> None:
        """
        Clear recovered dependencies from feature's failed dependency list.

        Args:
            feature: Feature to check dependencies for
        """
        recovered_deps = set()

        for dep_name in feature._failed_dependencies.copy():
            dep_feature = self._features.get(dep_name)
            if dep_feature and dep_feature.state == FeatureState.HEALTHY:
                recovered_deps.add(dep_name)
                feature._failed_dependencies.discard(dep_name)

        if recovered_deps:
            logger.info("Cleared recovered dependencies for '%s': %s", feature.name, list(recovered_deps))

    async def bulk_feature_recovery(
        self,
        user: str = "system",
        reason: str = "Bulk recovery operation",
        include_degraded: bool = True,
    ) -> dict[str, tuple[bool, str]]:
        """
        Attempt to recover multiple failed features.

        Args:
            user: User requesting the bulk recovery
            reason: Reason for bulk recovery
            include_degraded: Whether to include degraded features

        Returns:
            Dictionary mapping feature names to (success, message) tuples
        """
        target_states = [FeatureState.FAILED]
        if include_degraded:
            target_states.append(FeatureState.DEGRADED)

        failed_features = [
            name for name, feature in self._features.items()
            if feature.state in target_states
        ]

        if not failed_features:
            logger.info("No failed features found for bulk recovery")
            return {}

        logger.info("Starting bulk recovery for %d features: %s", len(failed_features), failed_features)

        await self._audit_log_feature_action(
            "bulk_recovery_started",
            "multiple",
            {
                "user": user,
                "reason": reason,
                "target_features": failed_features,
                "include_degraded": include_degraded,
            }
        )

        results = {}

        # Sort by dependency order - recover dependencies first
        try:
            ordered_features = []
            dependency_order = self._resolve_dependencies()

            # Only include failed features in dependency order
            for name in dependency_order:
                if name in failed_features:
                    ordered_features.append(name)

            # Add any failed features not in dependency order
            for name in failed_features:
                if name not in ordered_features:
                    ordered_features.append(name)

        except ValueError:
            # Fallback to original order if dependency resolution fails
            ordered_features = failed_features

        # Attempt recovery for each feature
        for feature_name in ordered_features:
            try:
                success, message = await self.attempt_feature_recovery(
                    feature_name, user=user, reason=f"Bulk recovery: {reason}"
                )
                results[feature_name] = (success, message)

                # Brief pause between recovery attempts
                await asyncio.sleep(0.5)

            except Exception as e:
                error_msg = f"Exception during recovery of '{feature_name}': {e}"
                logger.error(error_msg)
                results[feature_name] = (False, error_msg)

        # Log final results
        successful = [name for name, (success, _) in results.items() if success]
        failed = [name for name, (success, _) in results.items() if not success]

        await self._audit_log_feature_action(
            "bulk_recovery_completed",
            "multiple",
            {
                "user": user,
                "reason": reason,
                "successful_recoveries": successful,
                "failed_recoveries": failed,
                "total_attempted": len(results),
            }
        )

        logger.info("Bulk recovery completed: %d successful, %d failed", len(successful), len(failed))
        return results

    async def get_recovery_recommendations(self) -> dict[str, dict[str, Any]]:
        """
        Get recovery recommendations for failed features.

        Returns:
            Dictionary mapping feature names to recovery recommendations
        """
        recommendations = {}

        for feature_name, feature in self._features.items():
            if feature.state in [FeatureState.FAILED, FeatureState.DEGRADED]:
                definition = self._feature_definitions[feature_name]

                # Analyze failure causes and recommend actions
                rec = {
                    "feature_name": feature_name,
                    "current_state": feature.state.value,
                    "safety_classification": definition.safety_classification.value,
                    "failed_dependencies": list(feature._failed_dependencies),
                    "recommended_actions": [],
                    "recovery_priority": self._calculate_recovery_priority(feature_name),
                    "can_auto_recover": self._can_auto_recover(feature_name),
                }

                # Generate specific recommendations
                if feature._failed_dependencies:
                    rec["recommended_actions"].append(
                        f"Recover dependencies first: {list(feature._failed_dependencies)}"
                    )

                if definition.is_safety_critical():
                    rec["recommended_actions"].append(
                        "Manual verification required before recovery (safety-critical)"
                    )
                    rec["recovery_priority"] = "high"

                if definition.safety_classification == SafetyClassification.POSITION_CRITICAL:
                    rec["recommended_actions"].append(
                        "Verify physical device positions before recovery"
                    )

                if not rec["recommended_actions"]:
                    rec["recommended_actions"].append("Safe to attempt automatic recovery")

                recommendations[feature_name] = rec

        return recommendations

    def _calculate_recovery_priority(self, feature_name: str) -> str:
        """
        Calculate recovery priority for a feature.

        Args:
            feature_name: Name of the feature

        Returns:
            Priority level: "high", "medium", or "low"
        """
        definition = self._feature_definitions[feature_name]

        if definition.safety_classification == SafetyClassification.CRITICAL:
            return "high"
        if definition.safety_classification in [
            SafetyClassification.SAFETY_RELATED,
            SafetyClassification.POSITION_CRITICAL
        ]:
            return "medium"
        return "low"

    def _can_auto_recover(self, feature_name: str) -> bool:
        """
        Determine if a feature can be automatically recovered.

        Args:
            feature_name: Name of the feature

        Returns:
            True if safe for automatic recovery
        """
        definition = self._feature_definitions[feature_name]
        feature = self._features[feature_name]

        # Don't auto-recover safety-critical features
        if definition.is_safety_critical():
            return False

        # Don't auto-recover if dependencies are still failed
        if feature._failed_dependencies:
            return False

        # Don't auto-recover position-critical features that might be deployed
        if definition.safety_classification == SafetyClassification.POSITION_CRITICAL:
            return False

        return True


# Register EntityManager factory
def _create_entity_manager_feature(**kwargs):
    """Factory function for EntityManagerFeature."""
    from backend.core.entity_feature import EntityManagerFeature

    return EntityManagerFeature(**kwargs)


# NOTE: Persistence factory removed - persistence is now managed by CoreServices
# and is not registered as a feature


FeatureManager.register_feature_factory("entity_manager", _create_entity_manager_feature)


# Global instance for backward compatibility
# New code should use dependency injection with get_feature_manager_from_request
_feature_manager: FeatureManager | None = None


def get_feature_manager(
    settings: Any = None,
) -> FeatureManager:
    """
    Get the global FeatureManager instance with safety validation.

    This function maintains backward compatibility but is deprecated.
    New code should use dependency injection with get_feature_manager_from_request.

    Loads and validates feature definitions from YAML config, then applies
    runtime configuration from environment variables and settings.

    Args:
        settings: Application settings

    Returns:
        The global FeatureManager instance

    Raises:
        ValueError: If feature configuration is invalid
    """
    global _feature_manager
    from backend.core.config import get_settings

    if settings is None:
        settings = get_settings()

    # Try to get from app.state first if available
    try:
        from backend.main import app
        if hasattr(app.state, 'feature_manager') and app.state.feature_manager is not None:
            return app.state.feature_manager
    except (ImportError, AttributeError, RuntimeError):
        # App not initialized yet, fall back to global instance
        pass

    # Fallback to global instance for backward compatibility
    if _feature_manager is None:
        try:
            yaml_path = Path(__file__).parent / "feature_flags.yaml"
            _feature_manager = FeatureManager.from_yaml(yaml_path)

            # Apply runtime configuration with safety checks
            _feature_manager.apply_runtime_config(settings)

            logger.info("FeatureManager initialized successfully with safety validation")

        except Exception as e:
            logger.error(f"Failed to initialize FeatureManager: {e}")
            raise

    return _feature_manager
