"""
Example of main.py using the new service patterns.

This demonstrates how to integrate the ServiceLifecycleManager with
the existing ServiceRegistry for unified service management.
"""

# ... (imports remain the same) ...

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager using enhanced patterns."""
    try:
        logger.info("=" * 50)
        logger.info("Starting CoachIQ backend services...")
        logger.info("=" * 50)

        # Initialize ServiceRegistry for core services
        service_registry = ServiceRegistry()

        # ... (existing ServiceRegistry setup) ...

        # Start core services via ServiceRegistry
        startup_report = await service_registry.startup_all()

        if not startup_report['success']:
            logger.error("Failed to start core services: %s", startup_report['errors'])
            raise RuntimeError("Core service startup failed")

        logger.info("ServiceRegistry: All core services initialized successfully in %.2fs",
                   startup_report['total_time'])

        # Store core services in app.state
        for service_name, service_instance in service_registry._services.items():
            setattr(app.state, service_name, service_instance)

        # NEW: Initialize long-lived services with the new pattern
        from backend.core.service_patterns_migration import (
            initialize_long_lived_services,
            shutdown_long_lived_services
        )

        # Initialize WebSocket handlers and background services
        await initialize_long_lived_services(service_registry, app.state)
        logger.info("Long-lived services initialized with lifecycle manager")

        # ... (rest of startup remains the same) ...

        logger.info("Backend services initialized successfully")

        yield

    except Exception as e:
        logger.error("Error during application startup: %s", e)
        raise
    finally:
        logger.info("=" * 50)
        logger.info("Shutting down CoachIQ backend services...")
        logger.info("=" * 50)

        try:
            # NEW: Shutdown long-lived services first
            await shutdown_long_lived_services()
            logger.info("Long-lived services shut down")

            # Shutdown core services via ServiceRegistry
            shutdown_report = await service_registry.shutdown_all()

            if not shutdown_report['success']:
                logger.error("Errors during shutdown: %s", shutdown_report['errors'])
            else:
                logger.info("All services shut down successfully in %.2fs",
                           shutdown_report['total_time'])

            # ... (rest of shutdown remains the same) ...

        except Exception as e:
            logger.error("Error during shutdown: %s", e)
            raise


# Example of updated WebSocket route
@app.websocket("/ws/security")
async def security_websocket_endpoint(websocket: WebSocket):
    """
    Security monitoring WebSocket endpoint using new handler pattern.

    The handler is initialized at startup with proper dependencies
    and retrieved from app.state.
    """
    handler = app.state.security_websocket_handler

    if not handler:
        await websocket.close(code=1011, reason="Security handler not available")
        return

    # Delegate to handler which manages the full lifecycle
    await handler.handle_client(websocket)
