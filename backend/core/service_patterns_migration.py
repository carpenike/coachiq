"""
Migration Guide for Service Patterns

This module demonstrates how to migrate existing WebSocket handlers and
background services to use the new service patterns.
"""

from typing import Any

from backend.core.service_patterns import get_lifecycle_manager
from backend.core.service_registry import ServiceRegistry


async def initialize_long_lived_services(
    service_registry: ServiceRegistry,
    app_state: Any
) -> None:
    """
    Initialize all long-lived services using the new patterns.

    This function should be called during application startup after
    the ServiceRegistry has initialized all core services.

    Args:
        service_registry: The ServiceRegistry instance
        app_state: FastAPI app.state for storing references
    """
    lifecycle_manager = get_lifecycle_manager()

    # Get required services from ServiceRegistry
    security_event_manager = service_registry.get_service('security_event_manager')

    # Initialize WebSocket handlers with dependency injection
    if security_event_manager:
        from backend.websocket.security_handler_v2 import SecurityWebSocketHandlerV2

        security_ws_handler = SecurityWebSocketHandlerV2(
            security_event_manager=security_event_manager
        )

        lifecycle_manager.register_websocket_handler(
            'security_websocket',
            security_ws_handler
        )

        # Store reference in app.state for route access
        app_state.security_websocket_handler = security_ws_handler

    # Initialize background services
    from backend.services.device_discovery_service_v2 import DeviceDiscoveryServiceV2

    device_discovery = DeviceDiscoveryServiceV2()
    lifecycle_manager.register_background_service(
        'device_discovery',
        device_discovery
    )

    # Store reference in app.state
    app_state.device_discovery_service = device_discovery

    # Start all services
    await lifecycle_manager.startup_all()


async def shutdown_long_lived_services() -> None:
    """
    Shutdown all long-lived services gracefully.

    This should be called during application shutdown.
    """
    lifecycle_manager = get_lifecycle_manager()
    await lifecycle_manager.shutdown_all()


# Example: How to update a WebSocket route to use the new handler
def create_security_websocket_route(app):
    """
    Example of creating a WebSocket route with the new handler pattern.

    Args:
        app: FastAPI application instance
    """
    from fastapi import WebSocket

    @app.websocket("/ws/security")
    async def security_websocket_endpoint(websocket: WebSocket):
        """Security monitoring WebSocket endpoint."""
        # Get handler from app.state (initialized at startup)
        handler = app.state.security_websocket_handler

        if not handler:
            await websocket.close(code=1011)
            return

        # Delegate to handler
        await handler.handle_client(websocket)


# Example: Migrating existing services incrementally
class MigrationExample:
    """
    Example showing how to migrate services incrementally while
    maintaining backward compatibility.
    """

    @staticmethod
    def migrate_websocket_handler():
        """
        Step-by-step migration for WebSocket handlers:

        1. Create new handler extending WebSocketHandlerBase
        2. Move service dependencies to constructor injection
        3. Implement _register_listeners and _unregister_listeners
        4. Update startup to use lifecycle manager
        5. Update routes to get handler from app.state
        6. Test thoroughly
        7. Remove old handler code
        """
        pass

    @staticmethod
    def migrate_background_service():
        """
        Step-by-step migration for background services:

        1. Create new service extending BackgroundServiceBase
        2. Replace direct service access with ServiceProxy
        3. Move initialization to _initialize_services
        4. Move cleanup to _cleanup_services
        5. Update main loop to use _run method
        6. Register with lifecycle manager
        7. Test service startup/shutdown
        8. Remove old service code
        """
        pass


# Example: Using service proxies in existing code
def example_service_proxy_usage():
    """
    Example of using ServiceProxy for gradual migration.

    This allows existing code to work while transitioning
    to the new patterns.
    """
    from backend.core.service_patterns import ServiceProxy

    class ExistingBackgroundTask:
        def __init__(self):
            # Use proxy instead of direct access
            self._security_proxy = ServiceProxy(
                'security_event_manager',
                getter_func=self._get_security_manager_fallback
            )

        def _get_security_manager_fallback(self):
            """Custom fallback for getting security manager."""
            try:
                # Try old singleton pattern first
                from backend.services.security_event_manager import get_security_event_manager
                return get_security_event_manager()
            except:
                return None

        async def process_event(self, event):
            """Process an event using proxied service."""
            security_manager = self._security_proxy.get()
            if security_manager:
                await security_manager.record_event(event)
            else:
                # Handle case where service not available
                pass
