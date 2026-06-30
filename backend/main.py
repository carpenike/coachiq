#!/usr/bin/env python3
"""
Clean main application entry point for the coachiq backend.

This module provides a simplified FastAPI application setup with proper
initialization order to avoid metrics collisions and circular imports.
"""

import argparse
import json
import logging
import os
import platform
import signal
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.api.router_config import configure_routers
from backend.core.config import Settings, get_settings, is_real_secret
from backend.core.dependencies import ServiceRegistry
from backend.core.guardrail_coordinator import GuardrailCoordinator
from backend.core.logging_config import configure_unified_logging, setup_early_logging
from backend.core.metrics import initialize_backend_metrics
from backend.core.security_config_validator import validate_security_config
from backend.core.security_hardening import configure_security_hardening
from backend.core.service_registry import ServiceStatus

# CAN Tools Services
# from backend.integrations.registration import register_custom_features  # No longer needed - all services in ServiceRegistry
from backend.middleware.auth import AuthenticationMiddleware
from backend.middleware.csrf_protection import CSRFProtectionMiddleware
from backend.middleware.logging_middleware import LoggingMiddleware

# CORS handling moved to Caddy edge layer - see config/Caddyfile.example
from backend.middleware.rate_limiting import limiter, rate_limit_exceeded_handler
from backend.middleware.validation import RuntimeValidationMiddleware
from backend.monitoring import get_health_monitoring_summary, record_health_probe

# Group 2 repository imports

# Phase 4 service imports

# Group 2 service imports

# CANService import removed - not used in this file

# Set up early logging before anything else
setup_early_logging()

logger = logging.getLogger(__name__)

# Store startup time for health checks
SERVER_START_TIME = time.time()

_DEVELOPMENT_CSRF_SECRET = "development-only-csrf-secret-do-not-use-in-production"  # noqa: S105


def _resolve_csrf_secret(settings: Settings) -> str:
    """Resolve the CSRF signing secret, failing closed outside development."""
    if settings.auth.secret_key:
        return settings.auth.secret_key

    security_secret = (
        settings.security.secret_key.get_secret_value() if settings.security.secret_key else ""
    )
    if is_real_secret(security_secret):
        return security_secret

    if settings.is_development():
        return _DEVELOPMENT_CSRF_SECRET

    msg = (
        "CSRF secret key is required when CSRF protection is enabled. "
        "Set COACHIQ_AUTH__SECRET_KEY or COACHIQ_SECURITY__SECRET_KEY to a secure "
        "random value. Generate one with: openssl rand -hex 32"
    )
    raise RuntimeError(msg)


async def _configure_service_startup_stages(service_registry: GuardrailCoordinator) -> None:
    """Core service-startup-stage configuration.

    Extracted to ``backend/core/registrations/core_startup`` in
    audit cycle 2026-05-13 PR A8.
    """
    from backend.core.registrations.core_startup import configure

    await configure(service_registry)


def _register_group2_repositories(service_registry: GuardrailCoordinator) -> None:
    """Group-2 repository registrations.

    Extracted to ``backend/core/registrations/group2_repositories``
    in audit cycle 2026-05-13 PR A8.
    """
    from backend.core.registrations.group2_repositories import register

    register(service_registry)


def _register_group2_services(service_registry: GuardrailCoordinator) -> None:
    """Group-2 service registrations.

    Extracted to ``backend/core/registrations/group2_services`` in
    audit cycle 2026-05-13 PR A8.
    """
    from backend.core.registrations.group2_services import register

    register(service_registry)


def _create_database_engine():
    """Create a database engine instance."""
    from backend.core.config import get_settings
    from backend.services.database.database_engine import DatabaseEngine

    settings = get_settings()
    return DatabaseEngine(settings)


def _register_phase4_services(service_registry: GuardrailCoordinator) -> None:
    """Phase-4 service registrations.

    Extracted to ``backend/core/registrations/phase4`` in audit
    cycle 2026-05-13 PR A8. This shim is kept so existing call
    sites in `lifespan()` need no changes.
    """
    from backend.core.registrations.phase4 import register

    register(service_registry)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager with ServiceRegistry integration.

    Handles startup and shutdown logic using the new ServiceRegistry for
    improved dependency management and orchestrated service lifecycle.
    """
    logger.info("Starting coachiq backend application")

    # Initialize ServiceRegistry for advanced dependency management.
    # Use GuardrailCoordinator for guardrail-tier classification + emergency
    # stop ("safety" naming is historical -- see ADR-0004).
    service_registry = GuardrailCoordinator()

    # Initialize the module-level service registry for dependency injection
    from backend.core.dependencies import initialize_service_registry

    initialize_service_registry(service_registry)

    # Initialize backend metrics FIRST to avoid collisions
    initialize_backend_metrics()

    try:
        # Configure service startup stages with explicit dependencies
        await _configure_service_startup_stages(service_registry)

        # Execute orchestrated startup via ServiceRegistry
        await service_registry.startup_all()

        # CRITICAL: Inject service_registry into command_guardrail_service after startup to avoid circular dependency
        command_guardrail_service = service_registry.get_service("command_guardrail_service")
        if command_guardrail_service and hasattr(command_guardrail_service, "set_service_registry"):
            command_guardrail_service.set_service_registry(service_registry)
            logger.info(
                "ServiceRegistry injected into CommandGuardrailService for emergency stop coordination"
            )
        elif command_guardrail_service:
            # If CommandGuardrailService doesn't have set_service_registry method, set directly
            command_guardrail_service._service_registry = service_registry
            logger.info(
                "ServiceRegistry directly assigned to CommandGuardrailService._service_registry"
            )
        else:
            logger.error(
                "CommandGuardrailService not found in ServiceRegistry - emergency stop coordination unavailable"
            )

        # Get services from registry
        settings = service_registry.get_service("app_settings")
        rvc_config_provider = service_registry.get_service("rvc_config")
        security_event_manager = service_registry.get_service("security_event_manager")

        # Validate security configuration
        if not settings.is_development():
            logger.info("Validating security configuration for production mode")
            if not validate_security_config(settings):
                logger.error("Security configuration validation failed - see errors above")
                # In production, we should fail fast on security misconfigurations
                # For now, just log the error and continue

        device_discovery_service = service_registry.get_service("device_discovery_service")
        persistence_service = service_registry.get_service("persistence_service")
        database_manager = service_registry.get_service("database_manager")

        logger.info("ServiceRegistry startup completed successfully")
        logger.info(f"RVC Config Summary: {rvc_config_provider.get_configuration_summary()}")

        # Phase 0: Add dependency visualization
        try:
            # Get dependency diagram
            diagram = service_registry.export_dependency_diagram()
            logger.info("ServiceRegistry Dependency Diagram:\n%s", diagram)

            # Get startup metrics
            metrics = service_registry.get_enhanced_metrics()
            logger.info("ServiceRegistry Startup Metrics:")
            logger.info(f"  Total startup time: {metrics.get('total_startup_time_ms', 0):.2f}ms")
            logger.info(f"  Service count: {metrics.get('service_count', 0)}")
            logger.info(f"  Total stages: {metrics.get('total_stages', 0)}")
            logger.info(f"  Startup errors: {metrics.get('startup_errors', 0)}")

            # Show slowest services
            slowest = metrics.get("slowest_services", [])
            if slowest:
                logger.info("  Slowest services:")
                for service_name, timing in slowest[:5]:
                    logger.info(f"    - {service_name}: {timing:.2f}ms")

        except Exception as e:
            logger.warning(f"Could not generate dependency visualization: {e}")

        # Get services from ServiceRegistry
        websocket_manager = service_registry.get_service("websocket_manager")
        entity_manager_service = service_registry.get_service("entity_manager_service")

        if not websocket_manager or not entity_manager_service:
            msg = "Required services (websocket, entity_manager) failed to initialize"
            raise RuntimeError(msg)

        # Update logging configuration to include WebSocket handler now that manager is available
        from backend.core.logging_config import update_websocket_logging

        update_websocket_logging(websocket_manager)
        logger.info("WebSocket logging integration completed")

        # Services are now managed by ServiceRegistry - no need for manual initialization
        # TODO(Phase 3): These services need to be updated for constructor injection
        # For now, they're getting dependencies via service locator pattern internally
        docs_service = None  # DocsService() - needs docs_repository, performance_monitor
        vector_service = None  # VectorService() - needs vector_repository, performance_monitor
        can_interface_service = None  # CANInterfaceService() - needs performance_monitor
        # Get database_manager from ServiceRegistry
        database_manager = service_registry.get_service("database_manager")
        # TODO: Migrate these services to ServiceRegistry
        # For now, create with None until properly migrated
        predictive_maintenance_service = (
            None  # PredictiveMaintenanceService - needs maintenance_repository, performance_monitor
        )
        # analytics_dashboard_service now registered in ServiceRegistry

        # Get security services from ServiceRegistry (already initialized)
        security_config_service = service_registry.get_service("security_config_service")
        pin_manager = service_registry.get_service("pin_manager")
        security_audit_service = service_registry.get_service("security_audit_service")

        logger.info("Security services retrieved from ServiceRegistry")

        # Get services from ServiceRegistry
        pin_manager = service_registry.get_service("pin_manager")
        security_audit_service = service_registry.get_service("security_audit_service")

        # CommandGuardrailService is now registered in ServiceRegistry
        command_guardrail_service = service_registry.get_service("command_guardrail_service")
        logger.info("Backend services initialized")

        # Authentication middleware will be configured dynamically via the middleware itself

        # Services are now accessed via ServiceRegistry and dependency injection

        # Initialize Security WebSocket Handler with dependency injection
        # ARCHITECTURE NOTE: The SecurityWebSocketHandler is created as a singleton
        # instance for the entire application lifespan. This ensures it can register
        # its listeners with the SecurityEventManager at startup and not miss any
        # events that occur before the first client connects.
        #
        # CRITICAL LIMITATION: This approach is only safe in a SINGLE-PROCESS
        # environment. In a multi-process setup, each worker would have its own
        # handler instance, and events would not be broadcast to clients connected
        # to other workers.
        #
        # MIGRATION PATH: To support multiple workers, replace with a message broker
        # backend (e.g., Redis Pub/Sub) using a library like encode/broadcaster.
        from backend.websocket.security_handler import SecurityWebSocketHandler

        security_websocket_handler = SecurityWebSocketHandler(event_manager=security_event_manager)
        await security_websocket_handler.startup()
        # Security websocket handler is available via ServiceRegistry
        logger.info("Security WebSocket handler initialized with dependency injection")

        # Analytics dashboard service now started via ServiceRegistry lifecycle

        # Safety monitoring already started during service initialization
        logger.info("Safety monitoring active via ServiceRegistry")

        logger.info("Backend services initialized successfully")

        yield

    except Exception as e:
        logger.error("Error during application startup: %s", e)
        raise
    finally:
        # Cleanup with ServiceRegistry orchestration
        logger.info("Shutting down coachiq backend application")

        # Services shutdown is now handled by ServiceRegistry
        # Individual service shutdown calls removed - ServiceRegistry handles proper shutdown order

        # Shutdown Security WebSocket handler
        # Use ServiceRegistry for orchestrated shutdown
        try:
            from backend.core.dependencies import get_service_registry

            service_registry = get_service_registry()
            logger.info("Using ServiceRegistry for orchestrated shutdown")
            await service_registry.shutdown_all()
        except Exception as e:
            logger.error(f"Error during ServiceRegistry shutdown: {e}")
            logger.info("Using legacy shutdown (ServiceRegistry not available)")

            # Feature manager removed - all services managed by ServiceRegistry

            # CoreServices removed - individual services shutdown by ServiceRegistry

        logger.info("Backend services stopped")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="CoachIQ Backend",
        description="Modernized backend API for RV-C CANbus monitoring and control",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS handling moved to Caddy edge layer for better performance
    # See config/Caddyfile.example for CORS configuration

    # Add network security middleware for RV-C protection (FIRST for security)
    # Configuration will be loaded from security config service during runtime
    settings = get_settings()

    # Determine HTTPS configuration based on environment and explicit settings
    is_dev_mode = settings.is_development()
    is_behind_trusted_proxy = settings.security.tls_termination_is_external

    # The proxy will handle the redirect, or we're in dev mode
    disable_https_redirect = is_dev_mode or is_behind_trusted_proxy

    # Require HTTPS validation for defense-in-depth, except in development mode
    # In production with external TLS, this protects against requests that bypass the proxy
    # In development mode, allow HTTP for convenience
    require_https_validation = not is_dev_mode

    # Log security configuration for audit trail
    if is_behind_trusted_proxy:
        logger.warning(
            "Security Configuration: External TLS termination enabled. "
            "Operator is responsible for HTTPS redirection and HSTS. "
            "Application MUST be run with proxy headers support enabled.",
            extra={
                "event": "security_configuration",
                "tls_termination": "external",
                "https_redirect": "disabled",
                "proxy_headers_required": True,
            },
        )
    else:
        mode = "development" if is_dev_mode else "production"
        logger.info(
            f"Security Configuration: Application is self-enforcing HTTPS in {mode} mode.",
            extra={
                "event": "security_configuration",
                "tls_termination": "internal",
                "https_redirect": "enabled" if not disable_https_redirect else "disabled",
                "mode": mode,
            },
        )

    # Add comprehensive logging middleware
    # This should be one of the first middleware to capture all requests
    app.add_middleware(
        LoggingMiddleware,
        exclude_paths=["/healthz", "/api/healthz", "/metrics", "/readyz", "/startupz"],
        log_request_body=False,  # Set to True with caution - can log sensitive data
        log_response_body=False,  # Set to True with caution - can be large
        slow_request_threshold_ms=1000,
    )

    # Configure authentication middleware
    # The middleware will obtain the auth manager from app state at runtime
    app.add_middleware(AuthenticationMiddleware)

    # Add CSRF protection for state-changing operations
    # Only in production mode when HTTPS is enabled
    if not settings.is_development():
        csrf_secret = _resolve_csrf_secret(settings)
        app.add_middleware(
            CSRFProtectionMiddleware,
            secret_key=csrf_secret,
            secure_cookie=not settings.is_development(),
        )

    # Add runtime validation middleware for command-validation operations
    app.add_middleware(
        RuntimeValidationMiddleware, validate_requests=True, validate_responses=False
    )

    # Add rate limiting middleware. SlowAPIMiddleware reads
    # ``app.state.limiter`` on every request (see slowapi/middleware.py:121),
    # so the limiter MUST be attached to app.state before any request is
    # dispatched. We do this here rather than in lifespan startup because
    # the middleware can fire before lifespan completes for some clients
    # (notably Starlette's TestClient when used without lifespan).
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[attr-defined]

    # Configure security hardening (security headers, session security, etc.)
    configure_security_hardening(app, settings)

    # Register comprehensive exception handlers for the custom exception hierarchy
    # This replaces the previous inline handlers for AccountLockedError and
    # ServiceNotAvailableError with a unified handler covering all custom exceptions.
    from backend.core.exception_handlers import register_exception_handlers

    register_exception_handlers(app)

    # Configure and include routers
    configure_routers(app)

    return app


# Create the FastAPI application
app = create_app()


@app.get("/")
async def root():
    """Root endpoint for health checking."""
    return {"message": "CoachIQ Backend is running", "version": "2.0.0"}


@app.get("/health")
async def health_check(request: Request):
    """
    Human-readable diagnostic endpoint for technicians and simple connectivity tests.

    Always returns 200 OK with system information. For automated health monitoring,
    use /readyz (external monitors) or /healthz (internal orchestration).
    """
    settings = get_settings()

    # Calculate uptime
    uptime_seconds = round(time.time() - SERVER_START_TIME)

    # Get version info
    version = "unknown"
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            version = version_file.read_text().strip()
        else:
            version = os.getenv("VERSION", "development")
    except Exception:
        version = "unknown"

    # Get enabled protocols from the protocol manager
    from backend.core.dependencies import get_service_registry

    service_registry = get_service_registry()
    protocol_manager = service_registry.get_service("protocol_manager")

    if protocol_manager:
        # Get enabled protocols with runtime health checks
        enabled_protocols = protocol_manager.get_enabled_protocols(service_registry)
    else:
        # Fallback if protocol manager not available
        enabled_protocols = ["rvc"]  # RVC is always enabled

    return {
        "status": "online",
        "service_name": settings.app_name,
        "version": version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "uptime_seconds": uptime_seconds,
        "uptime_human": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s",
        "timestamp": datetime.now(UTC).isoformat(),
        "entity_count": 0,  # Entity count removed - use /api/v1/entities endpoint for entity info
        "can_interfaces": settings.can.interfaces,
        "protocols_enabled": enabled_protocols,
        "hostname": platform.node(),
        "platform": platform.system(),
        "python_version": platform.python_version(),
    }


@app.get(
    "/healthz",
    summary="Liveness probe",
    description="Minimal IETF-compliant liveness probe. Checks only process health, not dependencies. Optimized for <5ms response time.",
)
async def healthz(request: Request) -> Response:
    """
    Minimal liveness probe following Kubernetes patterns.

    Only checks if the process is alive and responsive - no dependency checking.
    Optimized for ultra-fast response time (<5ms target).

    Use /readyz for comprehensive dependency checking.
    Use /startupz for hardware initialization status.
    """
    start_time = time.time()

    try:
        # Minimal liveness checks - only process health
        # 1. Check if we can access basic application state (proves process is alive)
        try:
            _ = request.app.state
            process_alive = True
        except Exception:
            process_alive = False

        # 2. Check if event loop is responsive (basic async health)
        import asyncio

        try:
            # Simple async operation to verify event loop isn't blocked
            await asyncio.sleep(0)
            event_loop_responsive = True
        except Exception:
            event_loop_responsive = False

        # Overall liveness is just: process alive + event loop responsive
        is_alive = process_alive and event_loop_responsive
        ietf_status = "pass" if is_alive else "fail"

        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # Minimal IETF health+json response optimized for speed
        response_data = {
            "status": ietf_status,
            "version": "1",
            "serviceId": "coachiq-liveness",
            "description": "Process alive and responsive" if is_alive else "Process unresponsive",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {
                "process": {"status": "pass" if process_alive else "fail"},
                "event_loop": {"status": "pass" if event_loop_responsive else "fail"},
            },
            "response_time_ms": response_time_ms,
        }

        # Only add minimal metadata to keep response small and fast
        response_data["service"] = {
            "name": "coachiq",
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

        # Use appropriate HTTP status code
        status_code = 200 if is_alive else 503

        # Record metrics for monitoring
        record_health_probe(
            endpoint="healthz",
            response_time_ms=response_time_ms,
            status_code=status_code,
            status=ietf_status,
        )

        # Log only on failure or if response is slow (>5ms)
        if not is_alive:
            logger.warning(
                f"Liveness check failed - process_alive: {process_alive}, event_loop: {event_loop_responsive}"
            )
        elif response_time_ms > 5.0:
            logger.warning(f"Liveness check slow - {response_time_ms}ms (target: <5ms)")
        else:
            logger.debug(f"Liveness check passed - {response_time_ms}ms")

        return Response(
            content=json.dumps(response_data),
            status_code=status_code,
            media_type="application/health+json",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    except Exception as e:
        # Even exception handling is minimal for speed
        logger.error(f"Liveness probe error: {e}")
        error_response_time = round((time.time() - start_time) * 1000, 2)

        # Record error metrics
        record_health_probe(
            endpoint="healthz",
            response_time_ms=error_response_time,
            status_code=503,
            status="fail",
            error=str(e),
        )

        error_response = {
            "status": "fail",
            "version": "1",
            "serviceId": "coachiq-liveness",
            "description": "Liveness probe exception",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return Response(
            content=json.dumps(error_response),
            status_code=503,
            media_type="application/health+json",
        )


@app.get(
    "/startupz",
    summary="Startup probe",
    description="Returns IETF-compliant health status for hardware initialization. Succeeds when CAN transceivers are initialized.",
)
async def startupz(request: Request, service_registry: ServiceRegistry) -> Response:
    """
    Startup probe for hardware initialization following Kubernetes patterns.

    Focuses specifically on hardware readiness (CAN transceivers) to protect
    against slow initialization in RV-C environments.
    """
    logger.debug("GET /startupz - Startup probe requested")
    start_time = time.time()

    try:
        # Check CAN bus service status from ServiceRegistry
        can_interface_ready = (
            service_registry.has_service("can_interface_service")
            and service_registry.get_service_status("can_interface_service")
            == ServiceStatus.HEALTHY
        )
        can_bus_ready = (
            service_registry.has_service("can_bus_service")
            and service_registry.get_service_status("can_bus_service") == ServiceStatus.HEALTHY
        )

        # Hardware is considered ready when CAN services are initialized
        # This is the minimum requirement for the application to start receiving traffic
        startup_ready = can_interface_ready and can_bus_ready

        # IETF-compliant status
        ietf_status = "pass" if startup_ready else "fail"

        # Get service version
        version = "unknown"
        try:
            version_file = Path(__file__).parent.parent / "VERSION"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                version = os.getenv("VERSION", "development")
        except Exception:
            version = "unknown"

        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # IETF health+json response for startup probe
        response_data = {
            "status": ietf_status,
            "version": "1",
            "releaseId": version,
            "serviceId": "coachiq-startup",
            "description": "Hardware initialization complete"
            if startup_ready
            else "Waiting for CAN transceiver initialization",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {
                "can_interface": {"status": "pass" if can_interface_ready else "fail"},
                "can_bus": {"status": "pass" if can_bus_ready else "fail"},
            },
            "response_time_ms": response_time_ms,
        }

        # Add service metadata
        response_data["service"] = {
            "name": "coachiq",
            "version": version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "hostname": platform.node(),
            "platform": platform.system(),
        }

        # Use appropriate HTTP status code
        status_code = 200 if startup_ready else 503

        # Record metrics for monitoring
        record_health_probe(
            endpoint="startupz",
            response_time_ms=response_time_ms,
            status_code=status_code,
            status=ietf_status,
            details={
                "can_interface_ready": can_interface_ready,
                "can_bus_ready": can_bus_ready,
            },
        )

        logger.info(
            f"Startup probe completed - status: {ietf_status}, "
            f"can_ready: {startup_ready}, "
            f"response_time: {response_time_ms}ms, "
            f"status_code: {status_code}"
        )

        return Response(
            content=json.dumps(response_data),
            status_code=status_code,
            media_type="application/health+json",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    except Exception as e:
        logger.error(f"Error in startup probe: {e}")
        error_response_time = round((time.time() - start_time) * 1000, 2)

        # Record error metrics
        record_health_probe(
            endpoint="startupz",
            response_time_ms=error_response_time,
            status_code=503,
            status="fail",
            error=str(e),
        )

        # Return a minimal failure response even if feature manager fails
        error_response = {
            "status": "fail",
            "version": "1",
            "serviceId": "coachiq-startup",
            "description": f"Startup probe error: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return Response(
            content=json.dumps(error_response),
            status_code=503,
            media_type="application/health+json",
        )


@app.get(
    "/readyz",
    summary="Readiness probe",
    description="Returns IETF-compliant comprehensive readiness status with dependency checking. Includes safety-critical monitoring.",
)
async def readyz(request: Request, details: bool = False) -> Response:
    """
    Comprehensive readiness probe following Kubernetes patterns.

    Checks all critical system dependencies and safety requirements.
    Returns 200 only when the service can safely handle traffic.
    """
    logger.debug(f"GET /readyz - Readiness probe requested with details={details}")
    start_time = time.time()

    try:
        # Comprehensive readiness checks
        readiness_checks = {}
        critical_failures = []
        warning_failures = []

        # Get ServiceRegistry for health checks
        service_registry = None
        try:
            from backend.core.dependencies import get_service_registry

            service_registry = get_service_registry()
        except Exception:
            pass

        # ServiceRegistry health aggregation
        if service_registry:
            try:
                service_counts = service_registry.get_service_count_by_status()
                healthy_services = service_counts.get(ServiceStatus.HEALTHY, 0)
                total_services = sum(service_counts.values())

                readiness_checks["service_registry"] = {
                    "status": "pass" if healthy_services >= 3 else "fail",
                    "details": {
                        "healthy_services": healthy_services,
                        "total_services": total_services,
                        "service_breakdown": {
                            status.value: count for status, count in service_counts.items()
                        },
                    },
                }
                if healthy_services < 3:
                    critical_failures.append("service_registry")
            except Exception:
                readiness_checks["service_registry"] = {
                    "status": "fail",
                    "details": {"error": "ServiceRegistry error"},
                }
                critical_failures.append("service_registry")
        else:
            readiness_checks["service_registry"] = {
                "status": "fail",
                "details": {"error": "ServiceRegistry not available"},
            }
            critical_failures.append("service_registry")

        # 1. Hardware initialization (from startup probe)
        can_interface_ready = False
        can_bus_ready = False
        if service_registry:
            can_interface_ready = (
                service_registry.has_service("can_interface_service")
                and service_registry.get_service_status("can_interface_service")
                == ServiceStatus.HEALTHY
            )
            can_bus_ready = (
                service_registry.has_service("can_bus_service")
                and service_registry.get_service_status("can_bus_service") == ServiceStatus.HEALTHY
            )
        hardware_ready = can_interface_ready and can_bus_ready
        readiness_checks["hardware_initialization"] = {
            "status": "pass" if hardware_ready else "fail",
            "details": {"can_interface": can_interface_ready, "can_bus": can_bus_ready},
        }
        if not hardware_ready:
            critical_failures.append("hardware_initialization")

        # 2. Core services operational (now using ServiceRegistry)
        entity_manager_ready = (
            service_registry.has_service("entity_manager_service")
            and service_registry.get_service_status("entity_manager_service")
            == ServiceStatus.HEALTHY
        )
        # app_state_service removed - check repositories instead
        app_state_ready = True  # Now using repositories directly
        websocket_ready = (
            service_registry.has_service("websocket_service")
            and service_registry.get_service_status("websocket_service") == ServiceStatus.HEALTHY
        )
        persistence_ready = service_registry.has_service("persistence_service")
        database_ready = service_registry.has_service("database_manager")

        core_services_ready = (
            entity_manager_ready and websocket_ready and persistence_ready and database_ready
        )
        readiness_checks["core_services"] = {
            "status": "pass" if core_services_ready else "fail",
            "details": {
                "entity_manager": entity_manager_ready,
                "websocket": websocket_ready,
                "persistence": persistence_ready,
                "database": database_ready,
            },
        }
        if not core_services_ready:
            critical_failures.append("core_services")

        # 3. Entity discovery (traffic readiness indicator)
        entity_manager = (
            service_registry.get_service("entity_manager_service") if service_registry else None
        )
        entity_count = (
            len(entity_manager.get_entity_ids())
            if entity_manager and hasattr(entity_manager, "get_entity_ids")
            else 0
        )
        entities_discovered = entity_count > 0
        readiness_checks["entity_discovery"] = {
            "status": "pass" if entities_discovered else "fail",
            "details": {"entity_count": entity_count, "discovery_complete": entities_discovered},
        }
        if not entities_discovered:
            warning_failures.append("entity_discovery")

        # 4. Protocol readiness
        # RVC is always enabled in modern architecture
        rvc_ready = True
        protocol_health = {"rvc": True}

        # J1939 is optional and not yet migrated
        j1939_ready = False

        protocols_healthy = all(protocol_health.values())
        readiness_checks["protocol_systems"] = {
            "status": "pass" if protocols_healthy else "fail",
            "details": {
                "rvc_enabled": rvc_ready,
                "j1939_enabled": j1939_ready,
                "protocol_health": protocol_health,
            },
        }
        if not protocols_healthy:
            critical_failures.append("protocol_systems")

        # 5. Safety-critical systems
        # Check safety service and auth service from ServiceRegistry
        command_guardrail_service_ready = (
            service_registry.has_service("command_guardrail_service")
            and service_registry.get_service_status("command_guardrail_service")
            == ServiceStatus.HEALTHY
        )
        auth_ready = (
            service_registry.has_service("auth_manager")
            and service_registry.get_service_status("auth_manager") == ServiceStatus.HEALTHY
        )

        safety_systems_ready = command_guardrail_service_ready and auth_ready
        readiness_checks["safety_systems"] = {
            "status": "pass" if safety_systems_ready else "fail",
            "details": {
                "command_guardrail_service": command_guardrail_service_ready,
                "authentication": auth_ready,
            },
        }
        if not safety_systems_ready:
            critical_failures.append("safety_systems")

        # 6. API readiness
        # Domain API v1 is always enabled in modern architecture
        domain_api_ready = True
        entities_api_ready = True
        api_systems_ready = domain_api_ready and entities_api_ready
        readiness_checks["api_systems"] = {
            "status": "pass" if api_systems_ready else "fail",
            "details": {"domain_api_v2": domain_api_ready, "entities_api_v2": entities_api_ready},
        }
        if not api_systems_ready:
            warning_failures.append("api_systems")

        # Overall readiness determination
        # Critical failures prevent readiness, warning failures are noted but don't block
        overall_ready = len(critical_failures) == 0
        ietf_status = "pass" if overall_ready else "fail"

        # Get service version
        version = "unknown"
        try:
            version_file = Path(__file__).parent.parent / "VERSION"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                version = os.getenv("VERSION", "development")
        except Exception:
            version = "unknown"

        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # Generate description
        if critical_failures:
            description = f"Service not ready: {len(critical_failures)} critical system(s) failed"
        elif warning_failures:
            description = f"Service ready with warnings: {len(warning_failures)} non-critical system(s) degraded"
        else:
            description = "All systems ready to handle traffic"

        # IETF health+json response for readiness probe
        response_data = {
            "status": ietf_status,
            "version": "1",
            "releaseId": version,
            "serviceId": "coachiq-readiness",
            "description": description,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {
                name: {"status": check["status"]} for name, check in readiness_checks.items()
            },
            "response_time_ms": response_time_ms,
        }

        # Add service metadata
        response_data["service"] = {
            "name": "coachiq",
            "version": version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "hostname": platform.node(),
            "platform": platform.system(),
        }

        # Add failure categorization for safety-aware orchestration
        if critical_failures or warning_failures:
            response_data["issues"] = {"critical": critical_failures, "warning": warning_failures}

        # Add detailed check information if requested
        if details:
            response_data["detailed_checks"] = readiness_checks

            # Add system metrics
            response_data["metrics"] = {
                "entity_count": entity_count,
                "enabled_services": healthy_services,
                "total_services": total_services,
                "critical_systems_healthy": len(critical_failures) == 0,
                "warning_systems_healthy": len(warning_failures) == 0,
            }

        # Use appropriate HTTP status code
        status_code = 200 if overall_ready else 503

        # Record metrics for monitoring
        record_health_probe(
            endpoint="readyz",
            response_time_ms=response_time_ms,
            status_code=status_code,
            status=ietf_status,
            details={
                "entity_count": entity_count,
                "critical_failures": critical_failures,
                "warning_failures": warning_failures,
                "hardware_ready": hardware_ready,
                "core_services_ready": core_services_ready,
                "safety_systems_ready": safety_systems_ready,
            },
        )

        logger.info(
            f"Readiness probe completed - status: {ietf_status}, "
            f"critical_failures: {len(critical_failures)}, "
            f"warning_failures: {len(warning_failures)}, "
            f"entities: {entity_count}, "
            f"response_time: {response_time_ms}ms, "
            f"status_code: {status_code}"
        )

        if critical_failures:
            logger.warning(f"Readiness check failed - critical systems: {critical_failures}")
        elif warning_failures:
            logger.info(f"Readiness check passed with warnings: {warning_failures}")

        return Response(
            content=json.dumps(response_data),
            status_code=status_code,
            media_type="application/health+json",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    except Exception as e:
        logger.error(f"Error in readiness probe: {e}")
        error_response_time = round((time.time() - start_time) * 1000, 2)

        # Record error metrics
        record_health_probe(
            endpoint="readyz",
            response_time_ms=error_response_time,
            status_code=503,
            status="fail",
            error=str(e),
        )

        # Return a minimal failure response
        error_response = {
            "status": "fail",
            "version": "1",
            "serviceId": "coachiq-readiness",
            "description": f"Readiness probe error: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return Response(
            content=json.dumps(error_response),
            status_code=503,
            media_type="application/health+json",
        )


@app.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Returns Prometheus-format metrics for monitoring.",
)
def metrics() -> Response:
    """Prometheus metrics endpoint."""
    logger.debug("GET /metrics - Prometheus metrics requested")
    data = generate_latest()
    logger.debug(f"Prometheus metrics generated - {len(data)} bytes")
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get(
    "/health/monitoring",
    summary="Health probe monitoring",
    description="Returns comprehensive monitoring data for health probe performance and reliability.",
)
async def health_monitoring(request: Request) -> JSONResponse:
    """
    Health probe monitoring endpoint.

    Provides detailed metrics about health endpoint performance, success rates,
    and alerting information for production monitoring.
    """
    logger.debug("GET /health/monitoring - Health monitoring requested")

    try:
        monitoring_summary = get_health_monitoring_summary()

        return JSONResponse(
            status_code=200,
            content={
                "monitoring_summary": monitoring_summary,
                "timestamp": datetime.now(UTC).isoformat(),
                "description": "Health probe monitoring data",
            },
        )

    except Exception as e:
        logger.error(f"Error in health monitoring endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "monitoring_error",
                "message": f"Failed to retrieve monitoring data: {e}",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )


def main():
    """
    Main entry point for running the backend as a script.

    This function is used when the backend is run via the project scripts
    defined in pyproject.toml.
    """
    import os

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Get settings to use as CLI defaults
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Start the coachiq backend server.")
    parser.add_argument(
        "--host",
        type=str,
        default=settings.server.host,
        help=f"Host to bind the server (default: {settings.server.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.server.port,
        help=f"Port to bind the server (default: {settings.server.port})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("COACHIQ_RELOAD", "false").lower() == "true",
        help="Enable auto-reload (development only, or COACHIQ_RELOAD=true)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=settings.logging.level.lower(),
        help=f"Uvicorn log level (default: {settings.logging.level.lower()})",
    )
    args = parser.parse_args()

    # Set up early logging before anything else
    setup_early_logging()

    # Get settings to potentially configure more comprehensive logging
    settings = get_settings()

    # Configure unified logging for standalone script execution
    log_config, root_logger = configure_unified_logging(settings.logging)

    logger.info("Starting coachiq backend server in standalone mode")

    # Get SSL configuration if available
    ssl_config = settings.get_uvicorn_ssl_config()

    # Build uvicorn run arguments
    uvicorn_args = {
        "app": "backend.main:app",
        "host": args.host,
        "port": args.port,
        "reload": args.reload,
        "log_level": args.log_level,
        "log_config": log_config,
    }

    # Add reload directories to prevent PermissionError on protected directories
    if args.reload:
        # Use absolute path to backend directory to handle cases where working directory is /
        import os

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        uvicorn_args["reload_dirs"] = [os.path.join(backend_dir, "backend")]

    # Add SSL configuration if available
    uvicorn_args.update(ssl_config)

    # Log SSL status
    if ssl_config:
        logger.info("SSL/TLS enabled - server will run on HTTPS")
    else:
        logger.info("SSL/TLS not configured - server will run on HTTP")

    # Run the application using the top-level uvicorn import with unified log config
    uvicorn.run(**uvicorn_args)


if __name__ == "__main__":
    main()
