#!/usr/bin/env python3
"""
Router Configuration

Router configuration that uses FastAPI dependency injection for service management.
"""

import logging
from typing import Any

from fastapi import FastAPI

from backend.api.domains import register_all_domain_routers
from backend.api.routers import (
    analytics_dashboard,
    auth,
    can,
    can_analyzer,
    can_filter,
    can_recorder,
    can_tools,
    config,
    dashboard,
    dbc,
    device_discovery,
    docs,
    health,
    logs,
    migration,
    multi_network,
    network_security,
    notification_analytics,
    notification_dashboard,
    pattern_analysis,
    performance_analytics,
    pin_auth,
    predictive_maintenance,
    safety,
    schemas,
    security_config,
    security_dashboard,
    security_monitoring,
    startup_monitoring,
)
from backend.core.dependencies_v2 import get_feature_manager_from_app
from backend.websocket.routes import router as websocket_router

logger = logging.getLogger(__name__)


def configure_routers(app: FastAPI) -> None:
    """
    Configure all API routers using dependency injection.

    This approach relies on FastAPI's dependency injection system,
    allowing services to be injected as needed by route handlers.

    Args:
        app: FastAPI application instance
    """
    logger.info("Configuring API routers with dependency injection")

    # Include all routers - they will use dependency injection internally
    app.include_router(auth.router)
    app.include_router(can.router)
    app.include_router(can_tools.router)
    app.include_router(can_recorder.router)
    app.include_router(can_analyzer.router)
    app.include_router(can_filter.router)
    app.include_router(config.router)
    app.include_router(dashboard.router)
    app.include_router(dbc.router)
    app.include_router(docs.router)
    app.include_router(health.router)
    app.include_router(logs.router)
    app.include_router(multi_network.router)
    app.include_router(
        performance_analytics.router, prefix="/api/performance", tags=["performance"]
    )
    app.include_router(analytics_dashboard.router)
    app.include_router(device_discovery.router)
    app.include_router(predictive_maintenance.router)
    app.include_router(schemas.router)
    app.include_router(migration.router)
    app.include_router(safety.router)
    app.include_router(pin_auth.router)
    app.include_router(security_config.router)
    app.include_router(security_dashboard.router)
    app.include_router(network_security.router)

    # Include notification routers
    app.include_router(notification_dashboard.router)
    app.include_router(notification_analytics.router)

    # Include pattern analysis router
    app.include_router(pattern_analysis.router)

    # Include security monitoring router
    app.include_router(security_monitoring.router)

    # Include startup monitoring router
    app.include_router(startup_monitoring.router)

    # Include WebSocket routes that integrate with feature manager
    app.include_router(websocket_router)

    # Register domain API v2 routers if enabled
    try:
        feature_manager = get_feature_manager_from_app(app)
        if feature_manager.is_enabled("domain_api_v2"):
            logger.info("Registering domain API v2 routers...")
            register_all_domain_routers(app, feature_manager)
        else:
            logger.info("Domain API v2 disabled - skipping domain router registration")
    except Exception as e:
        logger.warning("Failed to register domain routers: %s", e)

    logger.info("All API routers configured successfully")


def get_router_info() -> dict[str, Any]:
    """
    Get information about all configured routers.

    Returns:
        Dictionary with router information including prefixes and tags
    """
    return {
        "routers": [
            {"prefix": "/api/auth", "tags": ["authentication"], "name": "auth"},
            {"prefix": "/api", "tags": ["can"], "name": "can"},
            {"prefix": "/api", "tags": ["config"], "name": "config"},
            {"prefix": "/api/dashboard", "tags": ["dashboard"], "name": "dashboard"},
            {"prefix": "/api/dbc", "tags": ["dbc"], "name": "dbc"},
            {"prefix": "/api", "tags": ["docs"], "name": "docs"},
            {"prefix": "/api/health", "tags": ["health", "monitoring"], "name": "health"},
            {"prefix": "/api", "tags": ["logs"], "name": "logs"},
            {"prefix": "/api/multi-network", "tags": ["multi-network"], "name": "multi_network"},
            {
                "prefix": "/api/performance",
                "tags": ["performance"],
                "name": "performance_analytics",
            },
            {
                "prefix": "/api/discovery",
                "tags": ["device_discovery"],
                "name": "device_discovery",
            },
            {
                "prefix": "/api/predictive-maintenance",
                "tags": ["predictive-maintenance"],
                "name": "predictive_maintenance",
            },
            {"prefix": "/api/schemas", "tags": ["schemas"], "name": "schemas"},
            {"prefix": "/api/migration", "tags": ["migration"], "name": "migration"},
            {"prefix": "/api/safety", "tags": ["safety"], "name": "safety"},
            {
                "prefix": "/api/notifications/dashboard",
                "tags": ["notification-dashboard"],
                "name": "notification_dashboard",
            },
            {
                "prefix": "/api/notification-analytics",
                "tags": ["notification-analytics"],
                "name": "notification_analytics",
            },
            {"prefix": "/ws", "tags": ["websocket"], "name": "websocket"},
        ],
        "total_routers": 18,
        "dependency_injection": True,
        "domain_api_v2": True,
    }
