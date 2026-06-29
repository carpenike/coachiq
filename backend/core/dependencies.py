"""
Modern dependencies for dependency injection.

This module provides clean service access patterns using ServiceRegistry
and FastAPI's dependency injection system with no legacy fallbacks.
"""

import logging
from typing import Annotated, Any, TypeVar

from fastapi import Depends, Header, HTTPException, status

from backend.core.service_registry import ServiceRegistry as _ServiceRegistryClass

# Real service classes for typed DI aliases (ADR-0006).
# Imported under underscore-prefixed names so the public alias name
# (e.g. ``CANFacade``) matches what the rest of the codebase already
# uses. The runtime ServiceRegistry lookup remains string-keyed; these
# imports exist purely so pyright + IDEs see real return types.
from backend.integrations.can.can_bus_recorder import CANBusRecorder as _CANBusRecorder
from backend.integrations.can.message_filter import MessageFilter as _MessageFilter
from backend.integrations.can.message_injector import CANMessageInjector as _CANMessageInjector
from backend.integrations.can.protocol_analyzer import ProtocolAnalyzer as _ProtocolAnalyzer

# Real repository classes for typed DI aliases (ADR-0006).
# Imported under underscore-prefixed names so the public alias name
# matches what the rest of the codebase already uses. The runtime
# ServiceRegistry lookup remains string-keyed; these imports exist
# purely so pyright + IDEs see real return types.
#
# NOTE: ``EntityStateRepository`` exists in TWO files under the same
# class name -- the canonical one (re-exported by
# ``backend/repositories/__init__.py`` and registered by
# ``backend/repositories/service_registration.py``) AND a competing
# subclass in ``backend/repositories/entity_repository.py`` that
# main.py registers later (overriding the first registration with a
# different constructor signature). Tracked as #167. The typed alias
# here points at the canonical one; if #167 picks the other class,
# this single import is the one-line update.
from backend.repositories.entity_state_repository import (
    EntityStateRepository as _EntityStateRepository,
)
from backend.repositories.rvc_config_repository import RVCConfigRepository as _RVCConfigRepository
from backend.repositories.system_state_repository import (
    SystemStateRepository as _SystemStateRepository,
)

# Real service classes for typed DI aliases (ADR-0006).
# Imported under underscore-prefixed names so the public alias name
# matches what the rest of the codebase already uses. The runtime
# ServiceRegistry lookup remains string-keyed; these imports exist
# purely so pyright + IDEs see real return types.
from backend.services.analytics.analytics_dashboard_service import (
    AnalyticsDashboardService as _AnalyticsDashboardService,
)

# NOTE: ``AnalyticsService`` alias points at ``NotificationAnalyticsService``
# to match what the router annotations already promise. The registry
# key ``"analytics_service"`` is NOT currently registered anywhere --
# every endpoint in ``backend/api/routers/notification_analytics.py``
# raises ``RuntimeError`` at request time. Tracked as #169.
# Real service classes for typed DI aliases (ADR-0006).
# Imported under underscore-prefixed names so the public alias name
# matches what the rest of the codebase already uses. The runtime
# ServiceRegistry lookup remains string-keyed; these imports exist
# purely so pyright + IDEs see real return types.
#
# NOTE: ``EntityService`` is intentionally NOT typed here -- importing
# ``backend.services.entity_service`` triggers a circular import via
# ``backend.websocket.handlers`` -> ``backend.websocket.routes`` ->
# ``backend.core.dependencies.WebSocketManager``. Tracked separately;
# fix likely requires making entity_service's websocket import lazy.
from backend.services.auth.manager import AuthManager as _AuthManager
from backend.services.can.can_facade import CANFacade as _CANFacade
from backend.services.can.can_network_telemetry_service import (
    CANNetworkTelemetryService as _CANNetworkTelemetryService,
)
from backend.services.database.database_update_service import (
    DatabaseUpdateService as _DatabaseUpdateService,
)
from backend.services.edge_proxy_monitor_service import (
    EdgeProxyMonitorService as _EdgeProxyMonitorService,
)
from backend.services.database.migration_safety_validator import (
    MigrationSafetyValidator as _MigrationSafetyValidator,
)
from backend.services.notifications.notification_analytics_service import (
    NotificationAnalyticsService as _NotificationAnalyticsService,
)
from backend.services.notifications.notification_manager import (
    NotificationManager as _NotificationManager,
)
from backend.services.notifications.notification_reporting_service import (
    NotificationReportingService as _NotificationReportingService,
)
from backend.services.auth.pin_manager import PINManager as _PINManager
from backend.services.predictive_maintenance_service import (
    PredictiveMaintenanceService as _PredictiveMaintenanceService,
)
from backend.services.rvc.rvc_config_facade import RVCConfigFacade as _RVCConfigFacade
from backend.services.rvc.rvc_service import RVCService as _RVCService
from backend.services.safety_service import SafetyService as _SafetyService
from backend.services.security.security_audit_service import (
    SecurityAuditService as _SecurityAuditService,
)
from backend.services.security.security_config_service import (
    SecurityConfigService as _SecurityConfigService,
)
from backend.services.security.security_event_manager import (
    SecurityEventManager as _SecurityEventManager,
)

logger = logging.getLogger(__name__)

# Type variables for better type safety
T = TypeVar("T")

# Module-level service registry instance
_service_registry: _ServiceRegistryClass | None = None


def initialize_service_registry(registry: _ServiceRegistryClass) -> None:
    """
    Initialize the module-level service registry.

    This should be called once during application startup.

    Args:
        registry: The service registry instance to use
    """
    global _service_registry  # noqa: PLW0603 - intentional module-level state
    _service_registry = registry
    logger.info("Service registry initialized for dependency injection")


def get_service_registry() -> _ServiceRegistryClass:
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


def get_rvc_config_facade() -> _RVCConfigFacade:
    """Get the RV-C config facade from ServiceRegistry.

    Returns:
        The RVCConfigFacade instance
    """
    return create_service_dependency("rvc_config_facade")()


def get_can_facade() -> _CANFacade | None:
    """
    Get the CAN facade from ServiceRegistry.

    This is the ONLY way to access CAN functionality.
    All CAN operations go through the facade.

    Returns:
        The CAN facade instance or None if not available
    """
    return create_optional_service_dependency("can_facade")()


async def get_verified_can_facade(
    can_facade: Annotated[_CANFacade | None, Depends(get_can_facade)],
) -> _CANFacade:
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


# Type aliases (ADR-0006: typed DI). The public alias names match what
# routers already import; only the underlying type narrows from Any.
CANFacade = Annotated[_CANFacade, Depends(get_can_facade)]
VerifiedCANFacade = Annotated[_CANFacade, Depends(get_verified_can_facade)]


def get_can_network_telemetry_service() -> _CANNetworkTelemetryService:
    """Get the rolling CAN network telemetry service from ServiceRegistry."""
    return create_service_dependency("can_network_telemetry_service")()


CANNetworkTelemetryService = Annotated[
    _CANNetworkTelemetryService, Depends(get_can_network_telemetry_service)
]


def get_can_message_injector() -> _CANMessageInjector:
    """
    Get the CAN message injector service from ServiceRegistry.

    This service provides safe CAN message injection capabilities for
    testing and diagnostics with proper safety validation and audit logging.

    Returns:
        The CAN message injector service instance
    """
    return create_service_dependency("can_message_injector")()


def get_can_message_filter() -> _MessageFilter:
    """
    Get the CAN message filter service from ServiceRegistry.

    This service provides CAN message filtering with real-time monitoring
    and alerting capabilities for traffic analysis and security.

    Note: the underlying class is named ``MessageFilter``; the public
    typed alias is ``CANMessageFilter`` to match the existing
    ``Pydantic`` ``CANMessageFilter`` model only by spelling. They are
    distinct types.

    Returns:
        The CAN message filter service instance
    """
    return create_service_dependency("can_message_filter")()


def get_can_bus_recorder() -> _CANBusRecorder:
    """
    Get the CAN bus recorder service from ServiceRegistry.

    This service provides CAN traffic recording and replay capabilities
    for diagnostics, testing, and analysis.

    Returns:
        The CAN bus recorder service instance
    """
    return create_service_dependency("can_bus_recorder")()


def get_can_protocol_analyzer() -> _ProtocolAnalyzer:
    """
    Get the CAN protocol analyzer service from ServiceRegistry.

    This service provides deep packet inspection and protocol detection
    for comprehensive CAN network analysis.

    Returns:
        The CAN protocol analyzer service instance
    """
    return create_service_dependency("can_protocol_analyzer")()


def get_safety_service() -> _SafetyService:
    """
    Get the API guardrail service from ServiceRegistry.

    Provides command-validation interlocks, emergency stop on the
    orchestration loop, and watchdog monitoring of CRITICAL-classified
    services. "Safety" naming is historical -- the OEM Firefly MIRA panel
    owns the actual vehicle safety case. See ADR-0004.

    Returns:
        The SafetyService instance.

    Raises:
        RuntimeError: If the service is not available (orchestration tier
            cannot accept commands without it).
    """
    return create_service_dependency("safety_service")()


def get_rvc_service() -> _RVCService:
    """
    Get the RVC service from ServiceRegistry.

    Returns:
        The RVC service instance
    """
    return create_service_dependency("rvc_service")()


# ==================================================================================
# REPOSITORY DEPENDENCIES
# ==================================================================================


def get_entity_state_repository() -> _EntityStateRepository:
    """
    Get the entity state repository from ServiceRegistry.

    Returns:
        The entity state repository instance
    """
    return create_service_dependency("entity_state_repository")()


def get_rvc_config_repository() -> _RVCConfigRepository:
    """
    Get the RVC config repository from ServiceRegistry.

    Returns:
        The RVC config repository instance
    """
    return create_service_dependency("rvc_config_repository")()


def get_system_state_repository() -> _SystemStateRepository:
    """
    Get the system state repository from ServiceRegistry.

    Returns:
        The system state repository instance
    """
    return create_service_dependency("system_state_repository")()


def get_analytics_dashboard_service() -> _AnalyticsDashboardService:
    """
    Get the analytics dashboard service from ServiceRegistry.

    This service provides comprehensive analytics dashboard functionality including
    performance trends, system insights, historical data analysis, and intelligent
    recommendations for business intelligence and operational insights.

    Returns:
        The analytics dashboard service instance
    """
    return create_service_dependency("analytics_dashboard_service")()


def get_edge_proxy_monitor_service() -> _EdgeProxyMonitorService:
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


def get_database_update_service() -> _DatabaseUpdateService:
    """
    Get DatabaseUpdateService instance.

    Target pattern: ServiceRegistry only, no fallback.

    Returns:
        The DatabaseUpdateService instance

    Raises:
        RuntimeError: If the service is not initialized
    """
    return create_service_dependency("database_update_service")()


def get_migration_safety_validator() -> _MigrationSafetyValidator:
    """
    Get MigrationSafetyValidator instance.

    Target pattern: ServiceRegistry only, no fallback.

    Returns:
        The MigrationSafetyValidator instance

    Raises:
        RuntimeError: If the service is not initialized
    """
    return create_service_dependency("migration_safety_validator")()


def get_reporting_service() -> _NotificationReportingService:
    """
    Get NotificationReportingService instance.

    Returns:
        The NotificationReportingService instance
    """
    return create_service_dependency("notification_reporting_service")()


def get_predictive_maintenance_service() -> _PredictiveMaintenanceService:
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
RVCConfigFacade = Annotated[_RVCConfigFacade, Depends(get_rvc_config_facade)]

CANMessageInjector = Annotated[_CANMessageInjector, Depends(get_can_message_injector)]
CANMessageFilter = Annotated[_MessageFilter, Depends(get_can_message_filter)]
CANBusRecorder = Annotated[_CANBusRecorder, Depends(get_can_bus_recorder)]
CANProtocolAnalyzer = Annotated[_ProtocolAnalyzer, Depends(get_can_protocol_analyzer)]
RVCService = Annotated[_RVCService, Depends(get_rvc_service)]

# Repository dependencies
EntityStateRepository = Annotated[_EntityStateRepository, Depends(get_entity_state_repository)]
RVCConfigRepository = Annotated[_RVCConfigRepository, Depends(get_rvc_config_repository)]
SystemStateRepository = Annotated[_SystemStateRepository, Depends(get_system_state_repository)]

# Analytics dependencies
AnalyticsDashboardService = Annotated[
    _AnalyticsDashboardService, Depends(get_analytics_dashboard_service)
]

# Edge proxy monitor dependency
EdgeProxyMonitorService = Annotated[
    _EdgeProxyMonitorService, Depends(get_edge_proxy_monitor_service)
]


def get_analytics_service() -> _NotificationAnalyticsService:
    """Get the analytics service from ServiceRegistry.

    See #169 -- the registry key ``"analytics_service"`` is currently
    NOT registered anywhere; this accessor will raise ``RuntimeError``
    at request time. The typed annotation matches what the router
    consumers in ``backend/api/routers/notification_analytics.py``
    already promise, so the contract is explicit until the registration
    is fixed in main.py.
    """
    return create_service_dependency("analytics_service")()


AnalyticsService = Annotated[_NotificationAnalyticsService, Depends(get_analytics_service)]


# Database update dependencies
DatabaseUpdateService = Annotated[_DatabaseUpdateService, Depends(get_database_update_service)]
MigrationSafetyValidator = Annotated[
    _MigrationSafetyValidator, Depends(get_migration_safety_validator)
]

# Predictive maintenance
PredictiveMaintenanceService = Annotated[
    _PredictiveMaintenanceService, Depends(get_predictive_maintenance_service)
]

ServiceRegistry = Annotated[_ServiceRegistryClass, Depends(get_service_registry)]


# ==================================================================================
# AUTHENTICATION DEPENDENCIES
# ==================================================================================


def get_auth_manager() -> _AuthManager:
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
            msg = (
                "AuthService failed to provide an AuthManager instance. Check service startup logs."
            )
            raise RuntimeError(msg)
        return manager
    msg = "Registered auth_manager service does not provide an AuthManager instance."
    raise RuntimeError(msg)


def get_pin_manager() -> _PINManager:
    """Get the PIN manager from ServiceRegistry."""
    return create_service_dependency("pin_manager")()


async def get_security_audit_service() -> _SecurityAuditService:
    """Get the security audit service from ServiceRegistry."""
    return create_service_dependency("security_audit_service")()


def get_notification_manager() -> _NotificationManager:
    """Get the notification manager from ServiceRegistry."""
    return create_service_dependency("notification_manager")()


def get_security_config_service() -> _SecurityConfigService:
    """Get the security config service from ServiceRegistry."""
    return create_service_dependency("security_config_service")()


def get_security_event_manager() -> _SecurityEventManager:
    """Get the security event manager from ServiceRegistry."""
    return create_service_dependency("security_event_manager")()


# Authentication dependencies with proper JWT validation
async def get_authenticated_user(
    auth_manager: Annotated[_AuthManager, Depends(get_auth_manager)],
    authorization: str | None = Header(None),
) -> dict:
    """
    Get the authenticated user from JWT token.

    Args:
        auth_manager: The authentication manager service
        authorization: Authorization header with Bearer token

    Returns:
        User data dictionary with id, email, and role

    Raises:
        HTTPException: 401 if authentication fails
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract token from Bearer scheme
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. Use Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Validate token and get user data
        user_data = auth_manager.validate_token(token)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_data
    except HTTPException:
        # Re-raise HTTPException as-is
        raise
    except Exception as e:
        logger.warning("Authentication failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_authenticated_admin(
    user: Annotated[dict, Depends(get_authenticated_user)],
) -> dict:
    """
    Get the authenticated admin user.

    Verifies that the authenticated user has admin role.

    Args:
        user: The authenticated user from get_authenticated_user

    Returns:
        Admin user data dictionary

    Raises:
        HTTPException: 403 if user is not an admin
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# Type aliases for authentication dependencies
AuthManager = Annotated[_AuthManager, Depends(get_auth_manager)]
PINManager = Annotated[_PINManager, Depends(get_pin_manager)]
SecurityAuditService = Annotated[_SecurityAuditService, Depends(get_security_audit_service)]
SecurityConfigService = Annotated[_SecurityConfigService, Depends(get_security_config_service)]
SecurityEventManager = Annotated[_SecurityEventManager, Depends(get_security_event_manager)]
NotificationManager = Annotated[_NotificationManager, Depends(get_notification_manager)]
AuthenticatedUser = Annotated[dict, Depends(get_authenticated_user)]
AuthenticatedAdmin = Annotated[dict, Depends(get_authenticated_admin)]
