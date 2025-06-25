"""
Modern dependencies for dependency injection.

This module provides clean service access patterns using ServiceRegistry
and FastAPI's dependency injection system with no legacy fallbacks.
"""

import logging
from typing import Annotated, Any, TypeVar

from fastapi import Depends, HTTPException

from backend.core.service_registry import EnhancedServiceRegistry

logger = logging.getLogger(__name__)

# Type variables for better type safety
T = TypeVar("T")

# Module-level service registry instance
_service_registry: EnhancedServiceRegistry | None = None


def initialize_service_registry(registry: EnhancedServiceRegistry) -> None:
    """
    Initialize the module-level service registry.

    This should be called once during application startup.

    Args:
        registry: The service registry instance to use
    """
    global _service_registry
    _service_registry = registry
    logger.info("Service registry initialized for dependency injection")


def get_service_registry() -> EnhancedServiceRegistry:
    """
    Get the service registry instance.

    This is the foundation of our clean service access pattern.
    All service access goes through ServiceRegistry.

    Returns:
        The service registry instance

    Raises:
        RuntimeError: If the service registry is not initialized
    """
    if _service_registry is None:
        msg = "Service registry not initialized. Call initialize_service_registry() during startup."
        raise RuntimeError(msg)

    return _service_registry


def create_service_dependency(service_name: str):
    """
    Factory function to create service dependencies.

    This creates FastAPI dependency functions that get services from ServiceRegistry.

    Args:
        service_name: Name of the service in ServiceRegistry

    Returns:
        A FastAPI dependency function
    """

    def dependency() -> Any:
        service_registry = get_service_registry()
        if not service_registry.has_service(service_name):
            msg = f"Service '{service_name}' not available in ServiceRegistry"
            raise RuntimeError(msg)
        return service_registry.get_service(service_name)

    dependency.__name__ = f"get_{service_name}"
    return dependency


def create_optional_service_dependency(service_name: str):
    """
    Factory function to create optional service dependencies.

    This creates FastAPI dependency functions that get services from ServiceRegistry,
    returning None if the service is not available instead of raising an error.

    Args:
        service_name: Name of the service in ServiceRegistry

    Returns:
        A FastAPI dependency function that returns the service or None
    """

    def dependency() -> Any | None:
        service_registry = get_service_registry()
        if not service_registry.has_service(service_name):
            return None
        return service_registry.get_service(service_name)

    dependency.__name__ = f"get_optional_{service_name}"
    return dependency


# ==================================================================================
# MODERN SERVICE DEPENDENCIES
# ==================================================================================


def get_websocket_manager() -> Any:
    """
    Get the WebSocket manager from ServiceRegistry.

    Returns:
        The WebSocket manager instance
    """
    return create_service_dependency("websocket_manager")()


def get_entity_service() -> Any:
    """
    Get the entity service from ServiceRegistry.

    Returns:
        The entity service instance
    """
    return create_service_dependency("entity_service")()


def get_config_service() -> Any:
    """
    Get the config service from ServiceRegistry.

    Returns:
        The config service instance
    """
    return create_service_dependency("config_service")()


def get_can_facade() -> Any | None:
    """
    Get the CAN facade from ServiceRegistry.

    This is the ONLY way to access CAN functionality.
    All CAN operations go through the facade.

    Returns:
        The CAN facade instance or None if not available
    """
    return create_optional_service_dependency("can_facade")()


async def get_verified_can_facade(
    can_facade: Annotated[Any | None, Depends(get_can_facade)],
) -> Any:
    """
    FastAPI dependency that provides the CAN facade, raising a 503
    if the service is not available.

    Returns:
        The CAN facade instance (guaranteed not None)

    Raises:
        HTTPException: 503 if CAN facade is not available
    """
    if can_facade is None:
        raise HTTPException(status_code=503, detail="CAN system is not initialized or available.")
    return can_facade


# Type aliases
CANFacade = Annotated[Any, Depends(get_can_facade)]
VerifiedCANFacade = Annotated[Any, Depends(get_verified_can_facade)]


def get_can_message_injector() -> Any:
    """
    Get the CAN message injector service from ServiceRegistry.

    This service provides safe CAN message injection capabilities for
    testing and diagnostics with proper safety validation and audit logging.

    Returns:
        The CAN message injector service instance
    """
    return create_service_dependency("can_message_injector")()


def get_can_message_filter() -> Any:
    """
    Get the CAN message filter service from ServiceRegistry.

    This service provides CAN message filtering with real-time monitoring
    and alerting capabilities for traffic analysis and security.

    Returns:
        The CAN message filter service instance
    """
    return create_service_dependency("can_message_filter")()


def get_can_bus_recorder() -> Any:
    """
    Get the CAN bus recorder service from ServiceRegistry.

    This service provides CAN traffic recording and replay capabilities
    for diagnostics, testing, and analysis.

    Returns:
        The CAN bus recorder service instance
    """
    return create_service_dependency("can_bus_recorder")()


def get_can_protocol_analyzer() -> Any:
    """
    Get the CAN protocol analyzer service from ServiceRegistry.

    This service provides deep packet inspection and protocol detection
    for comprehensive CAN network analysis.

    Returns:
        The CAN protocol analyzer service instance
    """
    return create_service_dependency("can_protocol_analyzer")()


def get_safety_service() -> Any:
    """
    Get the safety service from ServiceRegistry.

    CRITICAL: This service provides ISO 26262-compliant safety monitoring,
    emergency stops, safety interlocks, and safety validation for RV-C vehicle control.

    Returns:
        The SafetyService instance with full safety capabilities

    Raises:
        RuntimeError: If safety service not available (critical safety issue)
    """
    return create_service_dependency("safety_service")()


def get_rvc_service() -> Any:
    """
    Get the RVC service from ServiceRegistry.

    Returns:
        The RVC service instance
    """
    return create_service_dependency("rvc_service")()


# ==================================================================================
# REPOSITORY DEPENDENCIES
# ==================================================================================


def get_entity_state_repository() -> Any:
    """
    Get the entity state repository from ServiceRegistry.

    Returns:
        The entity state repository instance
    """
    return create_service_dependency("entity_state_repository")()


def get_rvc_config_repository() -> Any:
    """
    Get the RVC config repository from ServiceRegistry.

    Returns:
        The RVC config repository instance
    """
    return create_service_dependency("rvc_config_repository")()


def get_system_state_repository() -> Any:
    """
    Get the system state repository from ServiceRegistry.

    Returns:
        The system state repository instance
    """
    return create_service_dependency("system_state_repository")()


def get_analytics_dashboard_service() -> Any:
    """
    Get the analytics dashboard service from ServiceRegistry.

    This service provides comprehensive analytics dashboard functionality including
    performance trends, system insights, historical data analysis, and intelligent
    recommendations for business intelligence and operational insights.

    Returns:
        The analytics dashboard service instance
    """
    return create_service_dependency("analytics_dashboard_service")()


def get_edge_proxy_monitor_service() -> Any:
    """
    Get the edge proxy monitor service from ServiceRegistry.

    This service monitors the health and status of the edge proxy (Caddy)
    and integrates with ServiceRegistry health monitoring system.

    Returns:
        The EdgeProxyMonitorService instance
    """
    return create_service_dependency("edge_proxy_monitor")()


# ==================================================================================
# DATABASE UPDATE SERVICE DEPENDENCIES
# ==================================================================================


def get_database_update_service() -> Any:
    """
    Get DatabaseUpdateService instance.

    Target pattern: ServiceRegistry only, no fallback.

    Returns:
        The DatabaseUpdateService instance

    Raises:
        RuntimeError: If the service is not initialized
    """
    return create_service_dependency("database_update_service")()


def get_migration_safety_validator() -> Any:
    """
    Get MigrationSafetyValidator instance.

    Target pattern: ServiceRegistry only, no fallback.

    Returns:
        The MigrationSafetyValidator instance

    Raises:
        RuntimeError: If the service is not initialized
    """
    return create_service_dependency("migration_safety_validator")()


def get_reporting_service() -> Any:
    """
    Get NotificationReportingService instance.

    Returns:
        The NotificationReportingService instance
    """
    return create_service_dependency("notification_reporting_service")()


def get_predictive_maintenance_service() -> Any:
    """
    Get PredictiveMaintenanceService instance.

    Returns:
        The PredictiveMaintenanceService instance
    """
    return create_service_dependency("predictive_maintenance_service")()


# ==================================================================================
# TYPE-SAFE DEPENDENCY ALIASES
# ==================================================================================

# Modern typed dependencies using Annotated
WebSocketManager = Annotated[Any, Depends(get_websocket_manager)]
EntityService = Annotated[Any, Depends(get_entity_service)]
ConfigService = Annotated[Any, Depends(get_config_service)]

CANMessageInjector = Annotated[Any, Depends(get_can_message_injector)]
CANMessageFilter = Annotated[Any, Depends(get_can_message_filter)]
CANBusRecorder = Annotated[Any, Depends(get_can_bus_recorder)]
CANProtocolAnalyzer = Annotated[Any, Depends(get_can_protocol_analyzer)]
RVCService = Annotated[Any, Depends(get_rvc_service)]

# Repository dependencies
EntityStateRepository = Annotated[Any, Depends(get_entity_state_repository)]
RVCConfigRepository = Annotated[Any, Depends(get_rvc_config_repository)]
SystemStateRepository = Annotated[Any, Depends(get_system_state_repository)]

# Analytics dependencies
AnalyticsDashboardService = Annotated[Any, Depends(get_analytics_dashboard_service)]

# Edge proxy monitor dependency
EdgeProxyMonitorService = Annotated[Any, Depends(get_edge_proxy_monitor_service)]


def get_analytics_service() -> Any:
    """Get the analytics service from ServiceRegistry."""
    return create_service_dependency("analytics_service")()


AnalyticsService = Annotated[Any, Depends(get_analytics_service)]


# Database update dependencies
DatabaseUpdateService = Annotated[Any, Depends(get_database_update_service)]
MigrationSafetyValidator = Annotated[Any, Depends(get_migration_safety_validator)]

# Predictive maintenance
PredictiveMaintenanceService = Annotated[Any, Depends(get_predictive_maintenance_service)]

ServiceRegistry = Annotated[EnhancedServiceRegistry, Depends(get_service_registry)]


# ==================================================================================
# AUTHENTICATION DEPENDENCIES
# ==================================================================================


def get_auth_manager() -> Any:
    """
    Get the auth manager from ServiceRegistry.

    Note: The service registry contains an AuthService under the name "auth_manager",
    and we need to call get_auth_manager() on it to get the actual AuthManager instance.

    Returns:
        The AuthManager instance
    """
    auth_service = create_service_dependency("auth_manager")()
    # AuthService has a get_auth_manager() method that returns the actual AuthManager
    if hasattr(auth_service, "get_auth_manager"):
        manager = auth_service.get_auth_manager()
        if manager is None:
            raise RuntimeError(
                "AuthService failed to provide an AuthManager instance. Check service startup logs."
            )
        return manager
    return auth_service


def get_pin_manager() -> Any:
    """Get the PIN manager from ServiceRegistry."""
    return create_service_dependency("pin_manager")()


def get_security_audit_service() -> Any:
    """Get the security audit service from ServiceRegistry."""
    return create_service_dependency("security_audit_service")()


def get_notification_manager() -> Any:
    """Get the notification manager from ServiceRegistry."""
    return create_service_dependency("notification_manager")()


def get_security_config_service() -> Any:
    """Get the security config service from ServiceRegistry."""
    return create_service_dependency("security_config_service")()


def get_security_event_manager() -> Any:
    """Get the security event manager from ServiceRegistry."""
    return create_service_dependency("security_event_manager")()


# Placeholder authentication dependencies - these should be replaced with proper auth implementation
async def get_authenticated_user():
    """Get the authenticated user - placeholder implementation."""
    # TODO: Implement proper user authentication
    return {"user_id": "user123", "id": "user123", "email": "user@example.com", "role": "user"}


async def get_authenticated_admin():
    """Get the authenticated admin - placeholder implementation."""
    # TODO: Implement proper admin authentication
    return {"user_id": "admin123", "id": "admin123", "email": "admin@example.com", "role": "admin"}


# Type aliases for authentication dependencies
AuthManager = Annotated[Any, Depends(get_auth_manager)]
PINManager = Annotated[Any, Depends(get_pin_manager)]
SecurityAuditService = Annotated[Any, Depends(get_security_audit_service)]
SecurityConfigService = Annotated[Any, Depends(get_security_config_service)]
SecurityEventManager = Annotated[Any, Depends(get_security_event_manager)]
NotificationManager = Annotated[Any, Depends(get_notification_manager)]
AuthenticatedUser = Annotated[dict, Depends(get_authenticated_user)]
AuthenticatedAdmin = Annotated[dict, Depends(get_authenticated_admin)]
