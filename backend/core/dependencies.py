"""
Core dependencies for dependency injection.

This module provides functions to access the application state and services
from FastAPI's dependency injection system.
"""

import logging
from typing import Any

from fastapi import HTTPException, Request
from backend.middleware.auth import require_authentication

logger = logging.getLogger(__name__)


def get_app_state(request: Request) -> Any:
    """
    Get the application state from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The application state

    Raises:
        RuntimeError: If the app state is not initialized
    """
    if not hasattr(request.app.state, "app_state"):
        msg = "Application state not initialized"
        raise RuntimeError(msg)
    return request.app.state.app_state


def get_entity_service(request: Request) -> Any:
    """
    Get the entity service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The entity service

    Raises:
        RuntimeError: If the entity service is not initialized
    """
    if not hasattr(request.app.state, "entity_service"):
        msg = "Entity service not initialized"
        raise RuntimeError(msg)
    return request.app.state.entity_service


def get_can_service(request: Request) -> Any:
    """
    Get the CAN service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN service

    Raises:
        RuntimeError: If the CAN service is not initialized
    """
    if not hasattr(request.app.state, "can_service"):
        msg = "CAN service not initialized"
        raise RuntimeError(msg)
    return request.app.state.can_service


def get_feature_manager_from_request(request: Request) -> Any:
    """
    Get the feature manager from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The feature manager

    Raises:
        RuntimeError: If the feature manager is not initialized
    """
    if not hasattr(request.app.state, "feature_manager"):
        msg = "Feature manager not initialized"
        raise RuntimeError(msg)
    return request.app.state.feature_manager


def get_config_service(request: Request) -> Any:
    """
    Get the config service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The config service

    Raises:
        RuntimeError: If the config service is not initialized
    """
    if not hasattr(request.app.state, "config_service"):
        msg = "Config service not initialized"
        raise RuntimeError(msg)
    return request.app.state.config_service


def get_docs_service(request: Request) -> Any:
    """
    Get the docs service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The docs service

    Raises:
        RuntimeError: If the docs service is not initialized
    """
    if not hasattr(request.app.state, "docs_service"):
        msg = "Docs service not initialized"
        raise RuntimeError(msg)
    return request.app.state.docs_service


def get_vector_service(request: Request) -> Any:
    """
    Get the vector service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The vector service

    Raises:
        RuntimeError: If the vector service is not initialized
    """
    if not hasattr(request.app.state, "vector_service"):
        msg = "Vector service not initialized"
        raise RuntimeError(msg)
    return request.app.state.vector_service


def get_github_update_checker(request: Request) -> Any:
    """
    Get the GitHub update checker feature from the feature manager.

    Args:
        request: The FastAPI request object

    Returns:
        The GitHub update checker feature

    Raises:
        RuntimeError: If the feature manager is not initialized or the feature is not found
    """
    feature_manager = get_feature_manager_from_request(request)
    if "github_update_checker" not in feature_manager.features:
        msg = "GitHub update checker feature not found"
        raise RuntimeError(msg)

    update_checker_feature = feature_manager.features["github_update_checker"]
    if not getattr(update_checker_feature, "enabled", False):
        msg = "GitHub update checker feature is not enabled"
        raise RuntimeError(msg)

    return update_checker_feature.get_update_checker()


def get_can_interface_service(request: Request) -> Any:
    """
    Get the CAN interface service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The CAN interface service

    Raises:
        RuntimeError: If the CAN interface service is not initialized
    """
    if not hasattr(request.app.state, "can_interface_service"):
        msg = "CAN interface service not initialized"
        raise RuntimeError(msg)
    return request.app.state.can_interface_service


def get_websocket_manager(request: Request) -> Any:
    """
    Get the WebSocket manager from the feature manager.

    Args:
        request: The FastAPI request object

    Returns:
        The WebSocket manager

    Raises:
        RuntimeError: If the feature manager is not initialized or websocket feature is not found
    """
    feature_manager = get_feature_manager_from_request(request)
    websocket_feature = feature_manager.get_feature("websocket")
    if not websocket_feature:
        msg = "WebSocket feature not found or not enabled"
        raise RuntimeError(msg)
    return websocket_feature


def get_persistence_service(request: Request) -> Any:
    """
    Get the persistence service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The persistence service

    Raises:
        RuntimeError: If the persistence service is not initialized
    """
    if not hasattr(request.app.state, "persistence_service"):
        msg = "Persistence service not initialized"
        raise RuntimeError(msg)
    return request.app.state.persistence_service


def get_database_manager(request: Request) -> Any:
    """
    Get the database manager from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The database manager

    Raises:
        RuntimeError: If the database manager is not initialized
    """
    if not hasattr(request.app.state, "database_manager"):
        msg = "Database manager not initialized"
        raise RuntimeError(msg)
    return request.app.state.database_manager


def get_config_repository(request: Request) -> Any:
    """
    Get the configuration repository from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The configuration repository

    Raises:
        RuntimeError: If the configuration repository is not initialized
    """
    if not hasattr(request.app.state, "config_repository"):
        msg = "Configuration repository not initialized"
        raise RuntimeError(msg)
    return request.app.state.config_repository


def get_dashboard_repository(request: Request) -> Any:
    """
    Get the dashboard repository from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The dashboard repository

    Raises:
        RuntimeError: If the dashboard repository is not initialized
    """
    if not hasattr(request.app.state, "dashboard_repository"):
        msg = "Dashboard repository not initialized"
        raise RuntimeError(msg)
    return request.app.state.dashboard_repository


def get_auth_manager(request: Request = None) -> Any:
    """
    Get the authentication manager from the feature manager.

    Args:
        request: The FastAPI request object (optional)

    Returns:
        The authentication manager

    Raises:
        RuntimeError: If the feature manager is not initialized or auth feature is not found
    """
    # Import here to avoid circular imports
    from backend.services.feature_manager import get_feature_manager

    if request:
        feature_manager = get_feature_manager_from_request(request)
    else:
        feature_manager = get_feature_manager()

    auth_feature = feature_manager.get_feature("authentication")
    if not auth_feature:
        msg = "Authentication feature not found or not enabled"
        raise RuntimeError(msg)

    auth_manager = auth_feature.get_auth_manager()
    if not auth_manager:
        msg = "Authentication manager not initialized"
        raise RuntimeError(msg)

    return auth_manager


def get_notification_manager(request: Request = None) -> Any:
    """
    Get the notification manager from the feature manager.

    Args:
        request: The FastAPI request object (optional)

    Returns:
        The notification manager or None if not available

    Raises:
        RuntimeError: If the feature manager is not initialized
    """
    # Import here to avoid circular imports
    from backend.services.feature_manager import get_feature_manager

    if request:
        feature_manager = get_feature_manager_from_request(request)
    else:
        feature_manager = get_feature_manager()

    notification_feature = feature_manager.get_feature("notifications")
    if not notification_feature:
        return None  # Notification manager is optional

    return notification_feature.get_notification_manager()


def get_predictive_maintenance_service(request: Request) -> Any:
    """
    Get the predictive maintenance service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The predictive maintenance service

    Raises:
        RuntimeError: If the predictive maintenance service is not initialized
    """
    if not hasattr(request.app.state, "predictive_maintenance_service"):
        msg = "Predictive maintenance service not initialized"
        raise RuntimeError(msg)
    return request.app.state.predictive_maintenance_service


def get_feature_manager_from_app(app) -> Any:
    """
    Get the feature manager from the FastAPI application state.

    Args:
        app: The FastAPI application instance

    Returns:
        The feature manager

    Raises:
        RuntimeError: If the feature manager is not initialized
    """
    if not hasattr(app.state, "feature_manager"):
        # Fallback to global feature manager if not in app state
        from backend.services.feature_manager import get_feature_manager

        return get_feature_manager()
    return app.state.feature_manager


def get_config_manager_from_request(request: Request) -> Any:
    """
    Get the config manager from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The config manager

    Raises:
        RuntimeError: If the config manager is not initialized
    """
    if not hasattr(request.app.state, "config_manager"):
        msg = "Config manager not initialized"
        raise RuntimeError(msg)
    return request.app.state.config_manager


def get_feature_manager(request: Request = None) -> Any:
    """
    Get the feature manager from the FastAPI application state or global instance.

    Args:
        request: The FastAPI request object (optional)

    Returns:
        The feature manager

    Raises:
        RuntimeError: If the feature manager is not initialized
    """
    if request:
        return get_feature_manager_from_request(request)
    else:
        # Fallback to global feature manager
        from backend.services.feature_manager import (
            get_feature_manager as get_global_feature_manager,
        )

        return get_global_feature_manager()


def get_entity_domain_service(request: Request) -> Any:
    """
    Get or create the entity domain service with all required dependencies.

    This creates a safety-critical domain service for entity operations with
    comprehensive safety interlocks, command/acknowledgment patterns, and
    state reconciliation capabilities.

    Args:
        request: The FastAPI request object

    Returns:
        The entity domain service

    Raises:
        RuntimeError: If any required dependencies are not initialized
    """
    # Import here to avoid circular imports
    from backend.services.entity_domain_service import EntityDomainService

    # Check if already cached in app state
    if hasattr(request.app.state, "entity_domain_service"):
        return request.app.state.entity_domain_service

    # Get all required dependencies
    try:
        config_service = get_config_service(request)
        auth_manager = get_auth_manager(request)
        feature_manager = get_feature_manager_from_request(request)
        entity_service = get_entity_service(request)
        websocket_manager = get_websocket_manager(request)

        # Get entity manager from feature manager
        entity_manager_feature = feature_manager.get_feature("entity_manager")
        if not entity_manager_feature:
            msg = "Entity manager feature not found or not enabled"
            raise RuntimeError(msg)
        entity_manager = entity_manager_feature.get_entity_manager()

        # Create domain service
        domain_service = EntityDomainService(
            config_service=config_service,
            auth_manager=auth_manager,
            feature_manager=feature_manager,
            entity_service=entity_service,
            websocket_manager=websocket_manager,
            entity_manager=entity_manager,
        )

        # Cache in app state for reuse
        request.app.state.entity_domain_service = domain_service

        return domain_service

    except Exception as e:
        msg = f"Failed to create entity domain service: {e}"
        raise RuntimeError(msg)


def get_safety_service(request: Request) -> Any:
    """
    Get the safety service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The safety service

    Raises:
        RuntimeError: If the safety service is not initialized
    """
    if not hasattr(request.app.state, "safety_service"):
        msg = "Safety service not initialized"
        raise RuntimeError(msg)
    return request.app.state.safety_service


def get_analytics_service(request: Request) -> Any:
    """
    Get the notification analytics service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The notification analytics service

    Raises:
        RuntimeError: If the analytics service is not initialized
    """
    if not hasattr(request.app.state, "notification_analytics_service"):
        # Try to create it if we have the database manager
        try:
            from backend.services.notification_analytics_service import NotificationAnalyticsService

            db_manager = get_database_manager(request)
            analytics_service = NotificationAnalyticsService(db_manager)

            # Start the service
            import asyncio

            loop = asyncio.get_event_loop()
            loop.create_task(analytics_service.start())

            # Cache in app state
            request.app.state.notification_analytics_service = analytics_service
            return analytics_service

        except Exception as e:
            msg = f"Notification analytics service not initialized: {e}"
            raise RuntimeError(msg)

    return request.app.state.notification_analytics_service


def get_reporting_service(request: Request) -> Any:
    """
    Get the notification reporting service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The notification reporting service

    Raises:
        RuntimeError: If the reporting service is not initialized
    """
    if not hasattr(request.app.state, "notification_reporting_service"):
        # Try to create it if we have the required dependencies
        try:
            from backend.services.notification_reporting_service import NotificationReportingService

            db_manager = get_database_manager(request)
            analytics_service = get_analytics_service(request)

            reporting_service = NotificationReportingService(db_manager, analytics_service)

            # Start the service
            import asyncio

            loop = asyncio.get_event_loop()
            loop.create_task(reporting_service.start())

            # Cache in app state
            request.app.state.notification_reporting_service = reporting_service
            return reporting_service

        except Exception as e:
            msg = f"Notification reporting service not initialized: {e}"
            raise RuntimeError(msg)

    return request.app.state.notification_reporting_service


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


def get_security_audit_service(request: Request):
    """
    Get the security audit service from the FastAPI application state.

    Args:
        request: The FastAPI request object

    Returns:
        The security audit service or None if not available
    """
    if hasattr(request.app.state, "security_audit_service"):
        return request.app.state.security_audit_service
    return None
