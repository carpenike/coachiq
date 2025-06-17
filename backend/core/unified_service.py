"""
Unified Service Interface for ServiceRegistry and FeatureManager Integration

This module provides a unified approach to service management that combines:
- ServiceRegistry's efficient staged startup and dependency injection
- FeatureManager's safety-critical features and runtime management

Part of Phase 2C: FeatureManager-ServiceRegistry Integration
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
import logging

from backend.core.service_registry import ServiceStatus
from backend.services.feature_base import Feature, FeatureState, SafetyClassification

logger = logging.getLogger(__name__)


@runtime_checkable
class UnifiedService(Protocol):
    """
    Protocol defining the unified service interface.

    Services can implement this protocol in two ways:
    1. Extend the Feature base class (for safety-critical services)
    2. Implement these methods directly (for simple services)
    """

    async def startup(self) -> None:
        """Initialize the service."""
        ...

    async def shutdown(self) -> None:
        """Shutdown the service gracefully."""
        ...

    async def check_health(self) -> None:
        """
        Check service health. Should raise exception if unhealthy.
        This method is called periodically by health monitoring.
        """
        ...


@runtime_checkable
class SafetyAwareService(UnifiedService, Protocol):
    """
    Extended protocol for services that require safety features.
    These services typically extend the Feature base class.
    """

    @property
    def safety_classification(self) -> SafetyClassification:
        """Return the safety classification of this service."""
        ...

    @property
    def state(self) -> FeatureState:
        """Return the current state of the service."""
        ...

    def is_healthy(self) -> bool:
        """Check if the service is in a healthy state."""
        ...

    @property
    def depends_on(self) -> List[str]:
        """Return list of service dependencies."""
        ...


class ServiceAdapter:
    """
    Adapter to make Feature instances compatible with ServiceRegistry.

    This allows FeatureManager features to be registered with ServiceRegistry
    while maintaining their safety-critical capabilities.
    """

    def __init__(self, feature: Feature):
        """
        Initialize adapter with a Feature instance.

        Args:
            feature: The Feature to adapt for ServiceRegistry
        """
        self.feature = feature
        self._logger = logging.getLogger(f"{__name__}.{feature.name}")

    @property
    def name(self) -> str:
        """Get the service name."""
        return self.feature.name

    @property
    def dependencies(self) -> List[str]:
        """Get service dependencies for ServiceRegistry."""
        return self.feature.dependencies

    async def initialize(self) -> None:
        """
        ServiceRegistry initialization method.
        Maps to Feature.startup().
        """
        self._logger.info(f"Initializing feature '{self.name}' via ServiceRegistry")
        await self.feature.startup()

    async def cleanup(self) -> None:
        """
        ServiceRegistry cleanup method.
        Maps to Feature.shutdown().
        """
        self._logger.info(f"Cleaning up feature '{self.name}' via ServiceRegistry")
        await self.feature.shutdown()

    def to_service_status(self) -> ServiceStatus:
        """Convert Feature state to ServiceRegistry status."""
        state_mapping = {
            FeatureState.STOPPED: ServiceStatus.PENDING,
            FeatureState.INITIALIZING: ServiceStatus.STARTING,
            FeatureState.HEALTHY: ServiceStatus.HEALTHY,
            FeatureState.DEGRADED: ServiceStatus.DEGRADED,
            FeatureState.FAILED: ServiceStatus.FAILED,
            FeatureState.SAFE_SHUTDOWN: ServiceStatus.FAILED,
        }
        return state_mapping.get(self.feature.state, ServiceStatus.PENDING)

    async def check_health(self) -> None:
        """Delegate health check to the feature."""
        await self.feature.check_health()

    @property
    def is_safety_critical(self) -> bool:
        """Check if this is a safety-critical service."""
        # Access the private attribute since it's not exposed as a property
        safety_class = getattr(self.feature, '_safety_classification', SafetyClassification.OPERATIONAL)
        return safety_class in (
            SafetyClassification.CRITICAL,
            SafetyClassification.SAFETY_RELATED,
            SafetyClassification.POSITION_CRITICAL,
        )


class UnifiedServiceManager:
    """
    Unified service manager that bridges FeatureManager and ServiceRegistry.

    This manager:
    - Accepts both Feature instances and simple services
    - Registers them with ServiceRegistry for dependency management
    - Maintains FeatureManager capabilities for safety-critical services
    - Provides a unified API for service management
    """

    def __init__(self, service_registry, feature_manager=None):
        """
        Initialize the unified manager.

        Args:
            service_registry: The ServiceRegistry instance
            feature_manager: Optional FeatureManager instance for feature registration
        """
        self.service_registry = service_registry
        self.feature_manager = feature_manager
        self._adapters: Dict[str, ServiceAdapter] = {}
        self._logger = logger

    def register_service(
        self,
        name: str,
        service: Any,
        dependencies: Optional[List[str]] = None,
        stage: int = 0,
    ) -> None:
        """
        Register a service with the unified system.

        This method accepts:
        - Feature instances (safety-critical services)
        - Objects implementing UnifiedService protocol
        - Simple async factory functions

        Args:
            name: Service name
            service: The service instance, Feature, or factory function
            dependencies: Optional explicit dependencies (auto-detected for Features)
            stage: Startup stage (0 = early, higher = later)
        """
        # Check if it's a Feature instance
        if isinstance(service, Feature):
            self._register_feature(service, stage)

        # Check if it implements UnifiedService protocol
        elif isinstance(service, UnifiedService):
            self._register_unified_service(name, service, dependencies, stage)

        # Otherwise treat as a factory function
        else:
            self._register_factory(name, service, dependencies, stage)

    def _register_feature(self, feature: Feature, stage: int) -> None:
        """Register a Feature with both systems."""
        # Create adapter for ServiceRegistry
        adapter = ServiceAdapter(feature)
        self._adapters[feature.name] = adapter

        # Register with ServiceRegistry for dependency management
        self.service_registry.register_service(
            name=feature.name,
            factory=lambda: adapter,  # Return the adapter
            dependencies=feature.dependencies,
        )

        # Add to appropriate startup stage
        self.service_registry.register_startup_stage([
            (feature.name, adapter.initialize, feature.dependencies)
        ], stage=stage)

        # Also register with FeatureManager if available
        if self.feature_manager and feature.name not in self.feature_manager._features:
            self.feature_manager._features[feature.name] = feature
            self._logger.info(f"Registered Feature '{feature.name}' with both systems")

    def _register_unified_service(
        self,
        name: str,
        service: UnifiedService,
        dependencies: Optional[List[str]],
        stage: int,
    ) -> None:
        """Register a service implementing UnifiedService protocol."""
        deps = dependencies or []

        # If it's also safety-aware, extract dependencies
        if isinstance(service, SafetyAwareService):
            deps = service.depends_on if hasattr(service, 'depends_on') else deps

        # Register with ServiceRegistry
        self.service_registry.register_service(
            name=name,
            factory=lambda: service,
            dependencies=deps,
        )

        # Add to startup stage
        self.service_registry.register_startup_stage([
            (name, service.startup, deps)
        ], stage=stage)

        self._logger.info(f"Registered UnifiedService '{name}'")

    def _register_factory(
        self,
        name: str,
        factory: Any,
        dependencies: Optional[List[str]],
        stage: int,
    ) -> None:
        """Register a simple factory function."""
        deps = dependencies or []

        # Register with ServiceRegistry as-is
        self.service_registry.register_service(
            name=name,
            factory=factory,
            dependencies=deps,
        )

        # If it's an async function, add to startup
        if callable(factory):
            self.service_registry.register_startup_stage([
                (name, factory, deps)
            ], stage=stage)

        self._logger.info(f"Registered factory service '{name}'")

    def get_service(self, name: str) -> Any:
        """
        Get a service by name.

        Returns:
            The service instance (or adapted Feature)
        """
        # Check if it's an adapted feature
        if name in self._adapters:
            return self._adapters[name].feature

        # Otherwise get from ServiceRegistry
        return self.service_registry.get_service(name)

    async def check_safety_critical_health(self) -> Dict[str, Any]:
        """
        Check health of all safety-critical services.

        Returns:
            Dictionary of service name to health status
        """
        health_status = {}

        for name, adapter in self._adapters.items():
            if adapter.is_safety_critical:
                try:
                    await adapter.check_health()
                    health_status[name] = {
                        "status": "healthy",
                        "state": adapter.feature.state.value,
                        "safety_class": getattr(adapter.feature, '_safety_classification', SafetyClassification.OPERATIONAL).value,
                    }
                except Exception as e:
                    health_status[name] = {
                        "status": "unhealthy",
                        "error": str(e),
                        "state": adapter.feature.state.value,
                        "safety_class": getattr(adapter.feature, '_safety_classification', SafetyClassification.OPERATIONAL).value,
                    }

        return health_status

    def get_unified_status(self) -> Dict[str, Any]:
        """
        Get unified status across both systems.

        Returns:
            Combined status information
        """
        # Get ServiceRegistry status
        service_counts = self.service_registry.get_service_count_by_status()

        # Get FeatureManager status if available
        feature_status = {}
        if self.feature_manager:
            features = self.feature_manager.get_all_features()
            feature_status = {
                "total_features": len(features),
                "enabled_features": len(self.feature_manager.get_enabled_features()),
                "safety_critical_count": sum(
                    1 for f in features.values()
                    if hasattr(f, '_safety_classification') and
                    getattr(f, '_safety_classification', SafetyClassification.OPERATIONAL) in (
                        SafetyClassification.CRITICAL,
                        SafetyClassification.SAFETY_RELATED,
                    )
                ),
            }

        return {
            "service_registry": {
                "total_services": sum(service_counts.values()),
                "status_breakdown": {
                    status.value: count
                    for status, count in service_counts.items()
                },
            },
            "feature_manager": feature_status,
            "unified": {
                "total_managed": len(self.service_registry.list_services()),
                "safety_critical_services": len([
                    a for a in self._adapters.values()
                    if a.is_safety_critical
                ]),
            },
        }


def create_unified_manager(app) -> UnifiedServiceManager:
    """
    Factory function to create a UnifiedServiceManager from app state.

    Args:
        app: FastAPI application instance

    Returns:
        Configured UnifiedServiceManager
    """
    service_registry = getattr(app.state, 'service_registry', None)
    feature_manager = getattr(app.state, 'feature_manager', None)

    if not service_registry:
        raise RuntimeError("ServiceRegistry not found in app.state")

    return UnifiedServiceManager(service_registry, feature_manager)
