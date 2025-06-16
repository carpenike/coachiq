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

from backend.api.router_config import configure_routers
from backend.core.config import get_settings
from backend.core.dependencies import get_app_state, get_feature_manager_from_request
from backend.core.logging_config import configure_unified_logging, setup_early_logging
from backend.core.metrics import initialize_backend_metrics
from backend.integrations.registration import register_custom_features
from backend.middleware.auth import AuthenticationMiddleware
from backend.middleware.http import configure_cors
from backend.middleware.rate_limiting import limiter, rate_limit_exceeded_handler
from backend.middleware.validation import RuntimeValidationMiddleware
from backend.services.analytics_dashboard_service import AnalyticsDashboardService
from backend.services.auth_manager import AccountLockedError
from backend.services.can_interface_service import CANInterfaceService
from backend.services.can_service import CANService
from backend.services.config_service import ConfigService
from backend.services.device_discovery_service import DeviceDiscoveryService
from backend.services.docs_service import DocsService
from backend.services.entity_service import EntityService
from backend.services.feature_manager import get_feature_manager
from backend.services.predictive_maintenance_service import PredictiveMaintenanceService
from backend.services.rvc_service import RVCService
from backend.services.safety_service import SafetyService
from backend.services.vector_service import VectorService
from backend.services.pin_manager import PINManager, PINConfig
from backend.services.security_audit_service import SecurityAuditService, RateLimitConfig
from backend.services.security_config_service import SecurityConfigService
from backend.services.network_security_service import NetworkSecurityService
from backend.middleware.network_security import NetworkSecurityMiddleware, NetworkSecurityConfig
from backend.monitoring import record_health_probe, get_health_monitoring_summary

# Set up early logging before anything else
setup_early_logging()

logger = logging.getLogger(__name__)

# Store startup time for health checks
SERVER_START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown logic for the FastAPI application,
    including service initialization and cleanup.
    """
    logger.info("Starting coachiq backend application")

    # Initialize backend metrics FIRST to avoid collisions
    initialize_backend_metrics()

    try:
        # PHASE 1: Initialize Core Services (persistence, database)
        from backend.core.services import initialize_core_services

        logger.info("Initializing core services...")
        core_services = await initialize_core_services()
        logger.info("Core services initialized successfully")

        # Get application settings
        settings = get_settings()
        logger.info("Application settings loaded successfully")

        # Note: Unified logging is already configured in run_server.py
        # No need to reconfigure here to avoid overriding early setup

        # PHASE 2: Initialize feature manager with core services
        feature_manager = get_feature_manager()
        feature_manager.set_core_services(core_services)
        logger.info("Feature manager initialized with core services")

        # Note: Features will be initialized from YAML configuration
        # This ensures proper dependency resolution with entity_manager → app_state
        logger.info("Features will be initialized from YAML configuration")

        # Start all enabled features (this will initialize entity_manager, app_state, websocket, etc.)
        await feature_manager.startup()
        logger.info("All features started successfully")

        # Get initialized features from feature manager
        app_state = feature_manager.get_feature("app_state")
        websocket_manager = feature_manager.get_feature("websocket")
        entity_manager_feature = feature_manager.get_feature("entity_manager")
        if not app_state or not websocket_manager or not entity_manager_feature:
            msg = "Required features (app_state, websocket, entity_manager) failed to initialize"
            raise RuntimeError(msg)

        # Update logging configuration to include WebSocket handler now that manager is available
        from backend.core.logging_config import update_websocket_logging

        update_websocket_logging(websocket_manager)
        logger.info("WebSocket logging integration completed")

        # Initialize services with correct constructor signatures
        config_service = ConfigService(app_state)
        entity_service = EntityService(
            websocket_manager, entity_manager_feature.get_entity_manager()
        )
        can_service = CANService(app_state)
        rvc_service = RVCService(app_state)
        docs_service = DocsService()
        vector_service = VectorService() if settings.features.enable_vector_search else None
        can_interface_service = CANInterfaceService()
        predictive_maintenance_service = PredictiveMaintenanceService(
            core_services.database_manager
        )
        device_discovery_service = DeviceDiscoveryService(can_service)
        analytics_dashboard_service = AnalyticsDashboardService()

        # Initialize Security Configuration Service for centralized security management
        security_config_service = SecurityConfigService()
        logger.info("Security Configuration Service initialized")

        # Initialize PIN Manager for enhanced security using centralized config
        pin_config_dict = security_config_service.get_pin_config()
        pin_config = PINConfig(**pin_config_dict)
        pin_manager = PINManager(pin_config)
        logger.info("PIN Manager initialized for RV safety operations with centralized config")

        # Initialize Security Audit Service for enhanced logging and rate limiting using centralized config
        rate_limit_config_dict = security_config_service.get_rate_limit_config()
        rate_limit_config = RateLimitConfig(**rate_limit_config_dict)
        security_audit_service = SecurityAuditService(rate_limit_config)
        logger.info("Security Audit Service initialized for RV safety monitoring with centralized config")

        # Initialize Network Security Service for comprehensive network protection
        network_security_service = NetworkSecurityService(security_config_service)
        logger.info("Network Security Service initialized for RV network protection")

        # Initialize SafetyService for ISO 26262-compliant safety monitoring
        safety_service = SafetyService(
            feature_manager,
            health_check_interval=5.0,  # Check health every 5 seconds
            watchdog_timeout=15.0,  # Watchdog timeout at 15 seconds
            pin_manager=pin_manager,  # Enhanced security integration
            security_audit_service=security_audit_service,  # Security audit integration
        )
        logger.info("Backend services initialized")

        # CAN service initialization is handled by the can_feature in the feature manager

        # Register custom features with the feature manager
        register_custom_features(feature_manager)
        logger.info("Custom features registered")

        # Authentication middleware will be configured dynamically via the middleware itself

        # Store services in app state for dependency injection
        app.state.app_state = app_state
        # --- Ensure global app_state is the same instance ---
        import backend.core.state as core_state

        core_state.app_state = app_state
        # ---------------------------------------------------
        app.state.core_services = core_services  # Add core services
        app.state.persistence_service = core_services.persistence  # For legacy dependencies
        app.state.database_manager = core_services.database_manager  # For legacy dependencies
        app.state.feature_manager = feature_manager
        app.state.config_service = config_service
        app.state.entity_service = entity_service
        app.state.can_service = can_service
        app.state.rvc_service = rvc_service
        app.state.docs_service = docs_service
        app.state.vector_service = vector_service
        app.state.can_interface_service = can_interface_service
        app.state.predictive_maintenance_service = predictive_maintenance_service
        app.state.device_discovery_service = device_discovery_service
        app.state.analytics_dashboard_service = analytics_dashboard_service
        app.state.safety_service = safety_service
        app.state.pin_manager = pin_manager
        app.state.security_audit_service = security_audit_service
        app.state.security_config_service = security_config_service
        app.state.network_security_service = network_security_service

        # Start analytics dashboard service
        await analytics_dashboard_service.start()

        # Start safety monitoring
        await safety_service.start_monitoring()
        logger.info("Safety monitoring started")

        logger.info("Backend services initialized successfully")

        yield

    except Exception as e:
        logger.error("Error during application startup: %s", e)
        raise
    finally:
        # Cleanup
        logger.info("Shutting down coachiq backend application")

        # Stop safety monitoring
        if hasattr(app.state, "safety_service"):
            await app.state.safety_service.stop_monitoring()
            logger.info("Safety monitoring stopped")

        # Stop analytics dashboard service
        if hasattr(app.state, "analytics_dashboard_service"):
            await app.state.analytics_dashboard_service.stop()

        # Shut down all enabled features
        if hasattr(app.state, "feature_manager"):
            await app.state.feature_manager.shutdown()

        # Shut down core services (AFTER features)
        from backend.core.services import shutdown_core_services

        await shutdown_core_services()

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

    # Configure CORS middleware using settings
    configure_cors(app)

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

    network_security_config = NetworkSecurityConfig(
        # Default settings - will be overridden by security config service
        require_https=require_https_validation,
        https_redirect=(not disable_https_redirect),
        enable_ddos_protection=True,
        enable_security_headers=True,
        safety_whitelist_only=False,  # Can be overridden per deployment
    )
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
                "proxy_headers_required": True
            }
        )
    else:
        mode = "development" if is_dev_mode else "production"
        logger.info(
            f"Security Configuration: Application is self-enforcing HTTPS in {mode} mode.",
            extra={
                "event": "security_configuration",
                "tls_termination": "internal",
                "https_redirect": "enabled" if not disable_https_redirect else "disabled",
                "mode": mode
            }
        )

    network_security_middleware = NetworkSecurityMiddleware(app, network_security_config)
    app.add_middleware(NetworkSecurityMiddleware, config=network_security_config)

    # Configure authentication middleware
    # The middleware will obtain the auth manager from app state at runtime
    app.add_middleware(AuthenticationMiddleware)

    # Add runtime validation middleware for safety-critical operations
    app.add_middleware(
        RuntimeValidationMiddleware, validate_requests=True, validate_responses=False
    )

    # Add rate limiting middleware
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[attr-defined]

    # Add custom exception handler for account lockout
    @app.exception_handler(AccountLockedError)
    async def account_locked_exception_handler(request: Request, exc: AccountLockedError):
        logger = logging.getLogger(__name__)
        logger.warning("Account locked: %s", exc)

        return JSONResponse(
            status_code=423,  # HTTP_423_LOCKED
            content={
                "error": "account_locked",
                "message": str(exc),
                "lockout_until": (exc.lockout_until.isoformat() if exc.lockout_until else None),
                "failed_attempts": exc.attempts,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    app_state = get_app_state(request)
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

    # Get enabled protocols
    feature_manager = get_feature_manager_from_request(request)
    enabled_protocols = []
    if feature_manager.is_enabled("rvc"):
        enabled_protocols.append("rvc")
    if feature_manager.is_enabled("j1939"):
        enabled_protocols.append("j1939")
    if feature_manager.is_enabled("firefly"):
        enabled_protocols.append("firefly")

    return {
        "status": "online",
        "service_name": settings.app_name,
        "version": version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "uptime_seconds": uptime_seconds,
        "uptime_human": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s",
        "timestamp": datetime.now(UTC).isoformat(),
        "entity_count": len(app_state.entity_manager.get_entity_ids()),
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
            _ = get_app_state(request)
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
async def startupz(request: Request) -> Response:
    """
    Startup probe for hardware initialization following Kubernetes patterns.

    Focuses specifically on hardware readiness (CAN transceivers) to protect
    against slow initialization in RV-C environments.
    """
    logger.debug("GET /startupz - Startup probe requested")
    start_time = time.time()

    try:
        feature_manager = get_feature_manager_from_request(request)

        # Check CAN interface hardware initialization only
        can_interface_ready = feature_manager.is_enabled("can_interface")
        can_feature_ready = feature_manager.is_enabled("can_feature")

        # Hardware is considered ready when CAN interfaces are initialized
        # This is the minimum requirement for the application to start receiving traffic
        startup_ready = can_interface_ready and can_feature_ready

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
                "can_feature": {"status": "pass" if can_feature_ready else "fail"},
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
                "can_feature_ready": can_feature_ready,
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
        feature_manager = get_feature_manager_from_request(request)
        app_state = get_app_state(request)

        # Comprehensive readiness checks
        readiness_checks = {}
        critical_failures = []
        warning_failures = []

        # 1. Hardware initialization (from startup probe)
        can_interface_ready = feature_manager.is_enabled("can_interface")
        can_feature_ready = feature_manager.is_enabled("can_feature")
        hardware_ready = can_interface_ready and can_feature_ready
        readiness_checks["hardware_initialization"] = {
            "status": "pass" if hardware_ready else "fail",
            "details": {"can_interface": can_interface_ready, "can_feature": can_feature_ready},
        }
        if not hardware_ready:
            critical_failures.append("hardware_initialization")

        # 2. Core services operational
        entity_manager_ready = feature_manager.is_enabled("entity_manager")
        app_state_ready = feature_manager.is_enabled("app_state")
        websocket_ready = feature_manager.is_enabled("websocket")
        core_services_ready = entity_manager_ready and app_state_ready and websocket_ready
        readiness_checks["core_services"] = {
            "status": "pass" if core_services_ready else "fail",
            "details": {
                "entity_manager": entity_manager_ready,
                "app_state": app_state_ready,
                "websocket": websocket_ready,
            },
        }
        if not core_services_ready:
            critical_failures.append("core_services")

        # 3. Entity discovery (traffic readiness indicator)
        entity_count = len(app_state.entity_manager.get_entity_ids())
        entities_discovered = entity_count > 0
        readiness_checks["entity_discovery"] = {
            "status": "pass" if entities_discovered else "fail",
            "details": {"entity_count": entity_count, "discovery_complete": entities_discovered},
        }
        if not entities_discovered:
            warning_failures.append("entity_discovery")

        # 4. Protocol readiness
        rvc_ready = feature_manager.is_enabled("rvc")
        protocol_health = {}
        if rvc_ready:
            rvc_feature = feature_manager.get_feature("rvc")
            rvc_healthy = rvc_feature.is_healthy() if hasattr(rvc_feature, "is_healthy") else True
            protocol_health["rvc"] = rvc_healthy

        j1939_ready = feature_manager.is_enabled("j1939")
        if j1939_ready:
            j1939_feature = feature_manager.get_feature("j1939")
            j1939_healthy = (
                j1939_feature.is_healthy() if hasattr(j1939_feature, "is_healthy") else True
            )
            protocol_health["j1939"] = j1939_healthy

        protocols_healthy = all(protocol_health.values()) if protocol_health else rvc_ready
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
        brake_safety_ready = True
        if feature_manager.is_enabled("brake_safety_monitoring"):
            brake_feature = feature_manager.get_feature("brake_safety_monitoring")
            brake_safety_ready = (
                brake_feature.is_healthy() if hasattr(brake_feature, "is_healthy") else True
            )

        auth_ready = True
        if feature_manager.is_enabled("authentication"):
            auth_feature = feature_manager.get_feature("authentication")
            auth_ready = auth_feature.is_healthy() if hasattr(auth_feature, "is_healthy") else True

        safety_systems_ready = brake_safety_ready and auth_ready
        readiness_checks["safety_systems"] = {
            "status": "pass" if safety_systems_ready else "fail",
            "details": {
                "brake_safety_monitoring": brake_safety_ready,
                "authentication": auth_ready,
            },
        }
        if not safety_systems_ready:
            critical_failures.append("safety_systems")

        # 6. API readiness
        domain_api_ready = feature_manager.is_enabled("domain_api_v2")
        entities_api_ready = feature_manager.is_enabled("entities_api_v2")
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
                "enabled_features": len(
                    [
                        f
                        for f in feature_manager.get_all_features().values()
                        if feature_manager.is_enabled(getattr(f, "name", ""))
                    ]
                ),
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
