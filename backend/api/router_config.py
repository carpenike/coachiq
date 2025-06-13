#!/usr/bin/env python3
"""
Router Configuration

Router configuration that uses FastAPI dependency injection for service management.
"""

import logging
from typing import Any

from fastapi import FastAPI

from backend.api.routers import (
    analytics_dashboard,
    auth,
    can,
    config,
    dashboard,
    device_discovery,
    docs,
    logs,
    migration,
    multi_network,
    performance_analytics,
    predictive_maintenance,
    schemas,
)
from backend.websocket.routes import router as websocket_router
from backend.core.dependencies import get_feature_manager_from_app
from backend.api.domains import register_all_domain_routers

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
    app.include_router(auth.router, prefix="/api")
    app.include_router(can.router)
    app.include_router(config.router)
    app.include_router(dashboard.router)
    app.include_router(docs.router)
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
        logger.warning(f"Failed to register domain routers: {e}")

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
            {"prefix": "/api", "tags": ["docs"], "name": "docs"},
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
            {"prefix": "/ws", "tags": ["websocket"], "name": "websocket"},
        ],
        "total_routers": 13,
        "dependency_injection": True,
        "domain_api_v2": True,
    }
