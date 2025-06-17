"""
Standardized dependencies for dependency injection (v2).

This module provides the standardized service access patterns that eliminate
the service locator anti-pattern and standardize on ServiceRegistry + FastAPI Depends.

Phase 2L: Service Access Pattern Standardization
- ServiceRegistry-first access pattern
- Eliminates app.state service locator anti-pattern
- Type-safe service access with proper error handling
- Migration adapter support for progressive transition
"""

import logging
from typing import Any, Dict, Optional, Protocol, TypeVar

from fastapi import Request

from backend.core.service_registry_v2 import EnhancedServiceRegistry

logger = logging.getLogger(__name__)

# Type variables for better type safety
T = TypeVar("T")

class ServiceRegistry(Protocol):
    """Protocol for service registry implementations."""
    def has_service(self, service_name: str) -> bool: ...
    def get_service(self, service_name: str) -> Any: ...


def get_service_registry(request: Request) -> EnhancedServiceRegistry:
    """
    Get the service registry from the FastAPI application state.

    This is the foundation of our standardized service access pattern.
    All service access should go through ServiceRegistry when possible.

    Args:
        request: The FastAPI request object

    Returns:
        The service registry instance

    Raises:
        RuntimeError: If the service registry is not initialized
    """
    if not hasattr(request.app.state, "service_registry"):
        msg = "Service registry not initialized"
        raise RuntimeError(msg)

    return request.app.state.service_registry


def get_service_with_fallback(
    request: Request,
    service_name: str,
    fallback_attr: str | None = None
) -> Any:
    """
    Standardized service access pattern with ServiceRegistry-first and app.state fallback.

    This is the core pattern for Phase 2L standardization:
    1. Try ServiceRegistry first (preferred)
    2. Fall back to app.state access (legacy compatibility)
    3. Raise clear error if neither available

    Args:
        request: The FastAPI request object
        service_name: Name of the service in ServiceRegistry
        fallback_attr: Attribute name in app.state (defaults to service_name)

    Returns:
        The requested service instance

    Raises:
        RuntimeError: If the service is not available through either method
    """
    # Step 1: Try ServiceRegistry (preferred)
    try:
        service_registry = get_service_registry(request)
        if service_registry.has_service(service_name):
            logger.debug(f"Retrieved {service_name} from ServiceRegistry")
            return service_registry.get_service(service_name)
    except RuntimeError:
        # ServiceRegistry not available, continue to fallback
        pass

    # Step 2: Fall back to app.state (legacy compatibility)
    fallback_name = fallback_attr or service_name
    if hasattr(request.app.state, fallback_name):
        logger.debug(f"Retrieved {service_name} from app.state.{fallback_name} (legacy fallback)")
        return getattr(request.app.state, fallback_name)

    # Step 3: Service not available through either method
    msg = f"Service '{service_name}' not available via ServiceRegistry or app.state.{fallback_name}"
    raise RuntimeError(msg)


def create_service_dependency(service_name: str, fallback_attr: str | None = None):
    """
    Factory function to create standardized service dependencies.

    This creates FastAPI dependency functions that follow our standardized access pattern.

    Args:
        service_name: Name of the service in ServiceRegistry
        fallback_attr: Attribute name in app.state (defaults to service_name)

    Returns:
        A FastAPI dependency function
    """
    def dependency(request: Request) -> Any:
        return get_service_with_fallback(request, service_name, fallback_attr)

    dependency.__name__ = f"get_{service_name}"
    return dependency


# ==================================================================================
# STANDARDIZED SERVICE DEPENDENCIES (Phase 2L)
# ==================================================================================

def get_app_state(request: Request) -> Any:
    """
    Get the application state from the FastAPI application state.

    Note: AppState is being refactored to use repositories. This dependency
    is maintained for compatibility during the migration.

    Args:
        request: The FastAPI request object

    Returns:
        The application state

    Raises:
        RuntimeError: If the app state is not initialized
    """
    return get_service_with_fallback(request, "app_state", "app_state")


def get_feature_manager(request: Request) -> Any:
    """
    Get the feature manager using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The feature manager

    Raises:
        RuntimeError: If the feature manager is not initialized
    """
    return get_service_with_fallback(request, "feature_manager", "feature_manager")


def get_config_service(request: Request) -> Any:
    """
    Get the config service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The config service

    Raises:
        RuntimeError: If the config service is not initialized
    """
    return get_service_with_fallback(request, "config_service", "config_service")


def get_entity_service(request: Request) -> Any:
    """
    Get the entity service using standardized access pattern.

    This uses the migration adapter which automatically chooses between
    EntityService and EntityServiceV2 based on feature flags.

    Args:
        request: The FastAPI request object

    Returns:
        The entity service (migration adapter)

    Raises:
        RuntimeError: If the entity service is not initialized
    """
    return get_service_with_fallback(request, "entity_service", "entity_service")


def get_can_service(request: Request) -> Any:
    """
    Get the CAN service using standardized access pattern.

    This uses the migration adapter which automatically chooses between
    CANService and CANServiceV2 based on feature flags.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN service (migration adapter)

    Raises:
        RuntimeError: If the CAN service is not initialized
    """
    return get_service_with_fallback(request, "can_service", "can_service")


def get_rvc_service(request: Request) -> Any:
    """
    Get the RVC service using standardized access pattern.

    This uses the migration adapter which automatically chooses between
    RVCService and RVCServiceV2 based on feature flags.

    Args:
        request: The FastAPI request object

    Returns:
        The RVC service (migration adapter)

    Raises:
        RuntimeError: If the RVC service is not initialized
    """
    return get_service_with_fallback(request, "rvc_service", "rvc_service")


def get_docs_service(request: Request) -> Any:
    """
    Get the docs service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The docs service

    Raises:
        RuntimeError: If the docs service is not initialized
    """
    return get_service_with_fallback(request, "docs_service", "docs_service")


def get_vector_service(request: Request) -> Any:
    """
    Get the vector service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The vector service

    Raises:
        RuntimeError: If the vector service is not initialized
    """
    return get_service_with_fallback(request, "vector_service", "vector_service")


def get_security_event_manager(request: Request) -> Any:
    """
    Get the security event manager using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The security event manager

    Raises:
        RuntimeError: If the security event manager is not initialized
    """
    return get_service_with_fallback(request, "security_event_manager", "security_event_manager")


def get_websocket_manager(request: Request) -> Any:
    """
    Get the WebSocket manager using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The WebSocket manager

    Raises:
        RuntimeError: If the WebSocket manager is not initialized
    """
    return get_service_with_fallback(request, "websocket_manager", "websocket_manager")


def get_analytics_dashboard_service(request: Request) -> Any:
    """
    Get the analytics dashboard service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The analytics dashboard service

    Raises:
        RuntimeError: If the analytics dashboard service is not initialized
    """
    return get_service_with_fallback(request, "analytics_dashboard_service", "analytics_dashboard_service")


def get_device_discovery_service(request: Request) -> Any:
    """
    Get the device discovery service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The device discovery service

    Raises:
        RuntimeError: If the device discovery service is not initialized
    """
    return get_service_with_fallback(request, "device_discovery_service", "device_discovery_service")


def get_pin_manager(request: Request) -> Any:
    """
    Get the PIN manager using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The PIN manager

    Raises:
        RuntimeError: If the PIN manager is not initialized
    """
    return get_service_with_fallback(request, "pin_manager", "pin_manager")


def get_security_audit_service(request: Request) -> Any:
    """
    Get the security audit service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The security audit service

    Raises:
        RuntimeError: If the security audit service is not initialized
    """
    return get_service_with_fallback(request, "security_audit_service", "security_audit_service")


def get_network_security_service(request: Request) -> Any:
    """
    Get the network security service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The network security service

    Raises:
        RuntimeError: If the network security service is not initialized
    """
    return get_service_with_fallback(request, "network_security_service", "network_security_service")


def get_security_config_service(request: Request) -> Any:
    """
    Get the security config service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The security config service

    Raises:
        RuntimeError: If the security config service is not initialized
    """
    return get_service_with_fallback(request, "security_config_service", "security_config_service")


def get_persistence_service(request: Request) -> Any:
    """
    Get the persistence service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The persistence service

    Raises:
        RuntimeError: If the persistence service is not initialized
    """
    return get_service_with_fallback(request, "persistence_service", "persistence_service")


def get_database_manager(request: Request) -> Any:
    """
    Get the database manager using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The database manager

    Raises:
        RuntimeError: If the database manager is not initialized
    """
    return get_service_with_fallback(request, "database_manager", "database_manager")


def get_safety_service(request: Request) -> Any:
    """
    Get the safety service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The safety service

    Raises:
        RuntimeError: If the safety service is not initialized
    """
    return get_service_with_fallback(request, "safety_service", "safety_service")


# ==================================================================================
# REPOSITORY ACCESS DEPENDENCIES
# ==================================================================================

def get_entity_state_repository(request: Request) -> Any:
    """
    Get the entity state repository using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The entity state repository

    Raises:
        RuntimeError: If the repository is not available
    """
    return get_service_with_fallback(request, "entity_state_repository")


def get_rvc_config_repository(request: Request) -> Any:
    """
    Get the RVC config repository using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The RVC config repository

    Raises:
        RuntimeError: If the repository is not available
    """
    return get_service_with_fallback(request, "rvc_config_repository")


def get_can_tracking_repository(request: Request) -> Any:
    """
    Get the CAN tracking repository using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN tracking repository

    Raises:
        RuntimeError: If the repository is not available
    """
    return get_service_with_fallback(request, "can_tracking_repository")


def get_diagnostics_repository(request: Request) -> Any:
    """
    Get the diagnostics repository using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The diagnostics repository

    Raises:
        RuntimeError: If the repository is not available
    """
    return get_service_with_fallback(request, "diagnostics_repository")


# ==================================================================================
# V2 SERVICE DEPENDENCIES (Repository-based)
# ==================================================================================

def get_entity_service_v2(request: Request) -> Any:
    """
    Get the EntityServiceV2 with repository dependencies injected.

    This follows the new repository-based dependency injection pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The EntityServiceV2 instance

    Raises:
        RuntimeError: If required dependencies are not available
    """
    # Check if already cached in app state
    if hasattr(request.app.state, "entity_service_v2"):
        return request.app.state.entity_service_v2

    # Create with repository dependencies

    websocket_manager = get_websocket_manager(request)
    entity_state_repo = get_entity_state_repository(request)
    rvc_config_repo = get_rvc_config_repository(request)

    from backend.services.entity_service_v2 import EntityServiceV2
    service = EntityServiceV2(
        websocket_manager=websocket_manager,
        entity_state_repository=entity_state_repo,
        rvc_config_repository=rvc_config_repo,
    )

    # Cache for reuse
    request.app.state.entity_service_v2 = service

    return service


def get_can_service_v2(request: Request) -> Any:
    """
    Get the CANServiceV2 with repository dependencies injected.

    This follows the new repository-based dependency injection pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The CANServiceV2 instance

    Raises:
        RuntimeError: If required dependencies are not available
    """
    # Check if already cached
    if hasattr(request.app.state, "can_service_v2"):
        return request.app.state.can_service_v2

    # Create with repository dependencies
    from backend.services.can_service_v2 import CANServiceV2

    can_tracking_repo = get_can_tracking_repository(request)
    rvc_config_repo = get_rvc_config_repository(request)

    # Get controller source address from app state
    app_state = get_app_state(request)
    controller_addr = app_state.get_controller_source_addr()

    service = CANServiceV2(
        can_tracking_repository=can_tracking_repo,
        rvc_config_repository=rvc_config_repo,
        controller_source_addr=controller_addr,
    )

    # Cache for reuse
    request.app.state.can_service_v2 = service

    return service


def get_rvc_service_v2(request: Request) -> Any:
    """
    Get the RVCServiceV2 with repository dependencies injected.

    This follows the new repository-based dependency injection pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The RVCServiceV2 instance

    Raises:
        RuntimeError: If required dependencies are not available
    """
    # Check if already cached
    if hasattr(request.app.state, "rvc_service_v2"):
        return request.app.state.rvc_service_v2

    # Create with repository dependencies
    from backend.services.rvc_service_v2 import RVCServiceV2

    rvc_config_repo = get_rvc_config_repository(request)
    can_tracking_repo = get_can_tracking_repository(request)

    service = RVCServiceV2(
        rvc_config_repository=rvc_config_repo,
        can_tracking_repository=can_tracking_repo,
    )

    # Cache for reuse
    request.app.state.rvc_service_v2 = service

    return service


# ==================================================================================
# AUTHENTICATION DEPENDENCIES
# ==================================================================================

def get_authenticated_user(request: Request) -> dict:
    """
    Get authenticated user from request state.

    This dependency ensures that the request is authenticated and returns
    the user information that was set by the authentication middleware.

    Args:
        request: The FastAPI request object

    Returns:
        dict: User information with user_id, username, email, role, authenticated

    Raises:
        HTTPException: If the request is not authenticated (401)
    """
    from backend.middleware.auth import require_authentication
    user = require_authentication(request)
    return user


def get_authenticated_admin(request: Request) -> dict:
    """
    Get authenticated admin user from request state.

    This dependency ensures that the request is authenticated with admin privileges.

    Args:
        request: The FastAPI request object

    Returns:
        dict: Admin user information

    Raises:
        HTTPException: If not authenticated (401) or not admin (403)
    """
    from backend.middleware.auth import require_admin_role
    admin_user = require_admin_role(request)
    return admin_user


def get_auth_manager(request: Request) -> Any:
    """
    Get the authentication manager using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The authentication manager

    Raises:
        RuntimeError: If the auth manager is not available
    """
    # Try to get from feature manager first
    try:
        feature_manager = get_feature_manager(request)
        auth_feature = feature_manager.get_feature("authentication")
        if auth_feature:
            auth_manager = auth_feature.get_auth_manager()
            if auth_manager:
                return auth_manager
    except Exception:
        pass

    # Fallback to service registry or app state
    return get_service_with_fallback(request, "auth_manager")


# ==================================================================================
# OPTIONAL SERVICES (May not be available in all deployments)
# ==================================================================================

def get_notification_manager(request: Request) -> Any | None:
    """
    Get the notification manager if available.

    Args:
        request: The FastAPI request object

    Returns:
        The notification manager or None if not available
    """
    try:
        feature_manager = get_feature_manager(request)
        notification_feature = feature_manager.get_feature("notifications")
        if notification_feature:
            return notification_feature.get_notification_manager()
    except Exception:
        pass

    try:
        return get_service_with_fallback(request, "notification_manager")
    except RuntimeError:
        return None


def get_github_update_checker(request: Request) -> Any | None:
    """
    Get the GitHub update checker if available.

    Args:
        request: The FastAPI request object

    Returns:
        The GitHub update checker or None if not available
    """
    try:
        feature_manager = get_feature_manager(request)
        update_checker_feature = feature_manager.get_feature("github_update_checker")
        if update_checker_feature and getattr(update_checker_feature, "enabled", False):
            return update_checker_feature.get_update_checker()
    except Exception:
        pass

    return None


# Note: get_auth_manager is defined above in the authentication dependencies section


def get_can_interface_service(request: Request) -> Any:
    """
    Get the CAN interface service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN interface service

    Raises:
        RuntimeError: If the CAN interface service is not initialized
    """
    return get_service_with_fallback(request, "can_interface_service")


def get_dashboard_service(request: Request) -> Any:
    """
    Get the dashboard service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The dashboard service

    Raises:
        RuntimeError: If the dashboard service is not initialized
    """
    return get_service_with_fallback(request, "dashboard_service")


def get_predictive_maintenance_service(request: Request) -> Any:
    """
    Get the predictive maintenance service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The predictive maintenance service

    Raises:
        RuntimeError: If the predictive maintenance service is not initialized
    """
    return get_service_with_fallback(request, "predictive_maintenance_service")


def get_can_analyzer_service(request: Request) -> Any:
    """
    Get the CAN analyzer service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN analyzer service

    Raises:
        RuntimeError: If the CAN analyzer service is not initialized
    """
    return get_service_with_fallback(request, "can_analyzer_service")


def get_can_filter_service(request: Request) -> Any:
    """
    Get the CAN filter service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN filter service

    Raises:
        RuntimeError: If the CAN filter service is not initialized
    """
    return get_service_with_fallback(request, "can_filter_service")


def get_can_recorder_service(request: Request) -> Any:
    """
    Get the CAN recorder service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN recorder service

    Raises:
        RuntimeError: If the CAN recorder service is not initialized
    """
    return get_service_with_fallback(request, "can_recorder_service")


def get_dbc_service(request: Request) -> Any:
    """
    Get the DBC service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The DBC service

    Raises:
        RuntimeError: If the DBC service is not initialized
    """
    return get_service_with_fallback(request, "dbc_service")


def get_pattern_analysis_service(request: Request) -> Any:
    """
    Get the pattern analysis service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The pattern analysis service

    Raises:
        RuntimeError: If the pattern analysis service is not initialized
    """
    return get_service_with_fallback(request, "pattern_analysis_service")


def get_security_monitoring_service(request: Request) -> Any:
    """
    Get the security monitoring service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The security monitoring service

    Raises:
        RuntimeError: If the security monitoring service is not initialized
    """
    return get_service_with_fallback(request, "security_monitoring_service")


def get_analytics_service(request: Request) -> Any:
    """
    Get the analytics service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The analytics service

    Raises:
        RuntimeError: If the analytics service is not initialized
    """
    return get_service_with_fallback(request, "analytics_service")


def get_reporting_service(request: Request) -> Any:
    """
    Get the reporting service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The reporting service

    Raises:
        RuntimeError: If the reporting service is not initialized
    """
    return get_service_with_fallback(request, "reporting_service")


def get_config_repository(request: Request) -> Any:
    """
    Get the config repository using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The config repository

    Raises:
        RuntimeError: If the config repository is not initialized
    """
    return get_service_with_fallback(request, "config_repository")


def get_dashboard_repository(request: Request) -> Any:
    """
    Get the dashboard repository using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The dashboard repository

    Raises:
        RuntimeError: If the dashboard repository is not initialized
    """
    return get_service_with_fallback(request, "dashboard_repository")


def get_settings(request: Request = None) -> Any:
    """
    Get the application settings.

    Args:
        request: The FastAPI request object (optional)

    Returns:
        The application settings

    Raises:
        RuntimeError: If the settings are not available
    """
    # For settings, we can import directly since they're typically global
    from backend.core.config import get_settings as get_global_settings
    return get_global_settings()


def get_entity_domain_service(request: Request) -> Any:
    """
    Get the entity domain service using standardized access pattern.

    Args:
        request: The FastAPI request object

    Returns:
        The entity domain service

    Raises:
        RuntimeError: If the entity domain service is not initialized
    """
    return get_service_with_fallback(request, "entity_domain_service")


# ==================================================================================
# LEGACY COMPATIBILITY FUNCTIONS
# ==================================================================================

def get_feature_manager_from_request(request: Request) -> Any:
    """Legacy compatibility function - use get_feature_manager() instead."""
    logger.warning("get_feature_manager_from_request() is deprecated, use get_feature_manager()")
    return get_feature_manager(request)


def get_feature_manager_from_app(app) -> Any:
    """Legacy compatibility function for app-level access."""
    logger.warning("get_feature_manager_from_app() is deprecated")
    if hasattr(app.state, "feature_manager"):
        return app.state.feature_manager

    # Fallback to global feature manager
    from backend.services.feature_manager import get_feature_manager as get_global_feature_manager
    return get_global_feature_manager()


# Note: get_settings is defined above in the settings section


# ==================================================================================
# SERVICE PROXY PATTERN INTEGRATION (Phase 2O)
# ==================================================================================

# Optional enhanced service access using ServiceProxy pattern
# This provides additional resilience features like caching, health checks,
# circuit breakers, and metrics for production deployments.

def create_proxied_service_dependency(
    service_name: str,
    fallback_attr: str | None = None,
    cache_ttl: float = 300.0,  # 5 minutes default
    enable_circuit_breaker: bool = True,
):
    """
    Factory function to create FastAPI dependencies using ServiceProxy pattern.

    This provides enhanced service access with:
    - Lazy loading and caching (5 min default TTL)
    - Health checks and service validation
    - Circuit breaker pattern for resilience
    - Performance monitoring and metrics

    Args:
        service_name: Name of the service in ServiceRegistry
        fallback_attr: Attribute name in app.state (defaults to service_name)
        cache_ttl: Cache time-to-live in seconds
        enable_circuit_breaker: Whether to enable circuit breaker pattern

    Returns:
        A FastAPI dependency function with ServiceProxy capabilities
    """
    from backend.core.service_proxy import (
        CircuitBreakerConfig,
        CircuitOpenError,
        ServiceUnavailableError,
        create_service_proxy,
    )

    # Create circuit breaker config if enabled
    circuit_config = CircuitBreakerConfig() if enable_circuit_breaker else None

    def dependency(request: Request) -> Any:
        """Enhanced dependency with ServiceProxy pattern."""

        # Service registry getter
        def get_registry():
            return get_service_registry(request)

        # App state getter (fallback)
        def get_app_state_fallback():
            return request.app.state

        # Create or get service proxy
        proxy = create_service_proxy(
            service_name=service_name,
            service_registry_getter=get_registry,
            app_state_getter=get_app_state_fallback,
            cache_ttl=cache_ttl,
            circuit_config=circuit_config,
        )

        try:
            # Use asyncio to run the async proxy method
            import asyncio
            try:
                # Try to get current event loop
                loop = asyncio.get_running_loop()
                # Create a task and return immediately (for sync context)
                task = loop.create_task(proxy.get())
                return asyncio.run_coroutine_threadsafe(task, loop).result(timeout=5.0)
            except RuntimeError:
                # No event loop, create one
                return asyncio.run(proxy.get())

        except (ServiceUnavailableError, CircuitOpenError) as e:
            # Fall back to standard access pattern
            logger.warning(f"ServiceProxy failed for {service_name}, using fallback: {e}")
            return get_service_with_fallback(request, service_name, fallback_attr)

    dependency.__name__ = f"get_{service_name}_proxied"
    return dependency


# Enhanced service dependencies using ServiceProxy (optional)
# These provide additional resilience and monitoring capabilities

def get_feature_manager_proxied(request: Request) -> Any:
    """Get feature manager using ServiceProxy for enhanced resilience."""
    proxy_dep = create_proxied_service_dependency("feature_manager", cache_ttl=60.0)
    return proxy_dep(request)


def get_entity_service_proxied(request: Request) -> Any:
    """Get entity service using ServiceProxy for enhanced resilience."""
    proxy_dep = create_proxied_service_dependency("entity_service", cache_ttl=30.0)
    return proxy_dep(request)


def get_can_service_proxied(request: Request) -> Any:
    """Get CAN service using ServiceProxy for enhanced resilience."""
    proxy_dep = create_proxied_service_dependency("can_service", cache_ttl=60.0)
    return proxy_dep(request)


def get_rvc_service_proxied(request: Request) -> Any:
    """Get RVC service using ServiceProxy for enhanced resilience."""
    proxy_dep = create_proxied_service_dependency("rvc_service", cache_ttl=60.0)
    return proxy_dep(request)


def get_config_service_proxied(request: Request) -> Any:
    """Get config service using ServiceProxy for enhanced resilience."""
    proxy_dep = create_proxied_service_dependency("config_service", cache_ttl=300.0)
    return proxy_dep(request)


def get_security_audit_service_proxied(request: Request) -> Any:
    """Get security audit service using ServiceProxy for enhanced resilience."""
    proxy_dep = create_proxied_service_dependency("security_audit_service", cache_ttl=30.0)
    return proxy_dep(request)


# Service proxy management utilities

def get_service_proxy_metrics() -> dict[str, Any]:
    """
    Get metrics from all active service proxies.

    Returns:
        Dictionary with service proxy metrics and health status
    """
    from backend.core.service_proxy import get_proxy_manager

    manager = get_proxy_manager()
    return {
        "metrics": manager.get_all_metrics(),
        "health": manager.get_health_status(),
    }


def invalidate_all_service_caches() -> None:
    """Invalidate all service proxy caches (useful for development/debugging)."""
    from backend.core.service_proxy import get_proxy_manager

    manager = get_proxy_manager()
    manager.invalidate_all_caches()
    logger.info("All service proxy caches invalidated")


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers (useful for recovery scenarios)."""
    from backend.core.service_proxy import get_proxy_manager

    manager = get_proxy_manager()
    manager.reset_all_circuit_breakers()
    logger.info("All circuit breakers reset")
