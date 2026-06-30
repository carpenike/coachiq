"""
Phase-4 service registrations for the CoachIQ ServiceRegistry.

Extracted from `backend/main.py` in audit cycle 2026-05-13 PR A8 to keep
main.py focused on lifespan + app construction. The registrations
themselves are unchanged from their original location.

Note: most class imports are local-scope inside the inner ``_init_*``
helpers (matching the pre-extraction style); only the module-level
symbols `_register_phase4_services` actually evaluated at decoration
time live in the import block here.

Behavior is bit-identical to the original. See the audit cycle's
ADR (forthcoming) for the per-domain split rationale.
"""

# ruff: noqa: SLF001, PLR0913, PLR0915, E501, RET504, BLE001, G201, G202, RUF015, ARG002, ARG005, C901, EM101, F811, FIX002, PERF401
# Pre-existing patterns from the moved code (lifted from main.py in audit
# cycle 2026-05-13 PR A8). Cleanup is out of scope for the mechanical extraction.

import logging

from backend.core.safety_registry import SafetyServiceRegistry
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency

# Module-level symbols referenced inside the registration bodies. The
# inner ``_init_*`` helpers each do their own local imports for the
# class they instantiate -- that's preserved from main.py and matches
# the half-finished "Phase 3 constructor injection" TODO documented
# in `audit-2026-05-12.md`.
from backend.integrations.can.message_injector import CANMessageInjector, SafetyLevel
from backend.services.analytics.analytics_dashboard_service import AnalyticsDashboardService
from backend.services.auth.service import AuthService
from backend.services.can.can_bus_service import CANBusService
from backend.services.can.can_interface_service import CANInterfaceService
from backend.services.can.can_network_telemetry_service import CANNetworkTelemetryService
from backend.services.entities.entity_manager_service import EntityManagerService
from backend.services.protocols.protocol_manager import ProtocolManager
from backend.services.safety.safety_service import SafetyService
from backend.services.system.websocket_service import WebSocketService

logger = logging.getLogger(__name__)


def register(service_registry: SafetyServiceRegistry) -> None:
    """
    Register Phase 4 migrated features as services (Phase 4).

    These are services that are now managed by ServiceRegistry with constructor injection.
    """
    logger.info("Registering Phase 4 services (migrated features)")

    # ProtocolManager - manages protocol enablement and status
    async def _init_protocol_manager():
        manager = ProtocolManager()
        await manager.start()
        return manager

    service_registry.register_service(
        name="protocol_manager",
        init_func=_init_protocol_manager,
        dependencies=[],  # No dependencies, reads from configuration
        description="Protocol enablement and status management",
        tags={"service", "protocol", "configuration"},
        health_check=lambda m: m.get_health_status()
        if hasattr(m, "get_health_status")
        else {"healthy": m is not None},
    )

    # SafetyService - API command-validation guardrail (CRITICAL classification, see ADR-0004)
    async def _init_safety_service(pin_manager, security_audit_service):
        """Initialize SafetyService - service_registry will be injected after registration."""
        service = SafetyService(
            service_registry=None,  # Will be set after registration to avoid circular dependency
            health_check_interval=5.0,  # Check health every 5 seconds
            watchdog_timeout=15.0,  # Watchdog timeout at 15 seconds
            pin_manager=pin_manager,
            security_audit_service=security_audit_service,
        )
        await service.start_monitoring()
        logger.info("SafetyService started - will set service_registry after registration")
        return service

    # Import safety classification for proper registration
    from backend.core.safety_interfaces import SafetyClassification

    service_registry.register_safety_service(
        name="safety_service",
        init_func=_init_safety_service,
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("pin_manager", DependencyType.REQUIRED),
            ServiceDependency("security_audit_service", DependencyType.REQUIRED),
            # Note: service_registry removed to avoid circular dependency
        ],
        description=(
            "API command-validation guardrails and emergency stop on the "
            "orchestration loop (see ADR-0004)"
        ),
        tags={"service", "safety", "critical", "api-guardrail"},
        health_check=lambda s: s.get_health_status(),
    )

    # AppStateService removed - services now use repositories directly

    # WebSocketService - Direct service registration without Feature inheritance
    async def _init_websocket_service(can_tracking_repository=None, system_state_repository=None):
        service = WebSocketService(
            can_tracking_repository=can_tracking_repository,
            system_state_repository=system_state_repository,
        )
        await service.start()
        return service

    service_registry.register_safety_service(
        name="websocket_manager",
        init_func=_init_websocket_service,
        # Real-time communication is important for operation.
        safety_classification=SafetyClassification.OPERATIONAL,
        dependencies=[
            ServiceDependency("can_tracking_repository", DependencyType.OPTIONAL),
            ServiceDependency("system_state_repository", DependencyType.OPTIONAL),
        ],
        description="WebSocket connection management service",
        tags={"service", "websocket", "realtime"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # EntityManagerService - central entity management
    service_registry.register_service(
        name="entity_manager_service",
        init_func=lambda database_manager, rvc_config: EntityManagerService(
            database_manager=database_manager,
            rvc_config_provider=rvc_config,
            config={},  # TODO: Load from YAML config
        ),
        dependencies=[
            ServiceDependency("database_manager", DependencyType.REQUIRED),
            ServiceDependency("rvc_config", DependencyType.OPTIONAL),  # Can work without it
        ],
        description="Entity management service with persistence (migrated from feature)",
        tags={"service", "entity", "management", "phase4"},
        health_check=lambda s: s.health_check()
        if hasattr(s, "health_check")
        else {"healthy": s is not None},
    )

    # AuthService - Direct service registration without Feature inheritance
    async def _init_auth_service(
        credential_repository,
        session_repository,
        auth_event_repository,
        mfa_repository,
        performance_monitor,
        database_manager,
        token_service,
        session_service,
        mfa_service,
        lockout_service,
        security_config_service,
        notification_service=None,
    ):
        # Create legacy AuthRepository for backward compatibility
        from backend.services.auth.repository import AuthRepository

        auth_repository = AuthRepository(database_manager) if database_manager else None

        # Get authentication configuration from SecurityConfigService
        auth_config = await security_config_service.get_auth_config()

        service = AuthService(
            credential_repository=credential_repository,
            session_repository=session_repository,
            auth_event_repository=auth_event_repository,
            mfa_repository=mfa_repository,
            notification_service=notification_service,
            performance_monitor=performance_monitor,
            auth_repository=auth_repository,  # Inject legacy repository
            token_service=token_service,
            session_service=session_service,
            mfa_service=mfa_service,
            lockout_service=lockout_service,
            auth_config=auth_config,
        )
        await service.start()
        return service

    service_registry.register_safety_service(
        name="auth_manager",
        init_func=_init_auth_service,
        # Access control is operationally critical (see ADR-0004).
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("credential_repository", DependencyType.REQUIRED),
            ServiceDependency("session_repository", DependencyType.REQUIRED),
            ServiceDependency("auth_event_repository", DependencyType.REQUIRED),
            ServiceDependency("mfa_repository", DependencyType.OPTIONAL),
            ServiceDependency("notification_service", DependencyType.OPTIONAL),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
            ServiceDependency(
                "database_manager", DependencyType.REQUIRED
            ),  # For legacy AuthRepository
            ServiceDependency("token_service", DependencyType.REQUIRED),
            ServiceDependency("session_service", DependencyType.REQUIRED),
            ServiceDependency("mfa_service", DependencyType.OPTIONAL),
            ServiceDependency("lockout_service", DependencyType.REQUIRED),
            ServiceDependency("security_config_service", DependencyType.REQUIRED),
        ],
        description="Authentication service with JWT, magic links, and MFA",
        tags={"service", "auth", "security"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # CANAnomalyDetector - Security monitoring for CAN bus
    def _init_can_anomaly_detector():
        from backend.integrations.can.anomaly_detector import CANAnomalyDetector

        detector = CANAnomalyDetector()
        logger.info("CAN Anomaly Detector initialized via ServiceRegistry")
        return detector

    service_registry.register_service(
        name="can_anomaly_detector",
        init_func=_init_can_anomaly_detector,
        dependencies=[
            ServiceDependency(
                "security_event_manager", DependencyType.OPTIONAL
            ),  # Will connect if available
        ],
        description="CAN bus anomaly detection and security monitoring",
        tags={"service", "can", "security", "monitoring"},
        health_check=lambda d: {"healthy": d is not None, "monitoring_active": True},
    )

    async def _init_diagnostic_handler():
        """Initialize the diagnostics DTC handler service."""
        from backend.core.config import get_settings
        from backend.integrations.diagnostics.handler import DiagnosticHandler

        handler = DiagnosticHandler(get_settings())
        await handler.startup()
        return handler

    service_registry.register_service(
        name="diagnostic_handler",
        init_func=_init_diagnostic_handler,
        dependencies=[],
        description="Diagnostic trouble-code handler fed by decoded CAN messages",
        tags={"service", "diagnostics", "dtc", "can"},
        health_check=lambda h: {"healthy": h is not None},
    )

    # CANBusService - Direct service registration without Feature inheritance
    async def _init_can_bus_service(
        can_tracking_repository,
        system_state_repository,
        can_anomaly_detector=None,
        diagnostic_handler=None,
    ):
        service = CANBusService(
            can_tracking_repository=can_tracking_repository,
            system_state_repository=system_state_repository,
            can_anomaly_detector=can_anomaly_detector,
            diagnostic_handler=diagnostic_handler,
        )
        await service.start()
        return service

    service_registry.register_safety_service(
        name="can_bus_service",
        init_func=_init_can_bus_service,
        # CAN bus orchestration is operationally critical (see ADR-0004).
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("can_tracking_repository", DependencyType.REQUIRED),
            ServiceDependency("system_state_repository", DependencyType.REQUIRED),
            ServiceDependency(
                "can_anomaly_detector", DependencyType.OPTIONAL
            ),  # Security monitoring
            ServiceDependency("diagnostic_handler", DependencyType.OPTIONAL),
        ],
        description="CAN bus integration service for message processing",
        tags={"service", "can", "hardware", "realtime"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # CANService registration removed - use can_facade instead

    # CAN Tools Services Registration
    def _init_can_message_injector():
        """Initialize CAN message injector service with audit callback."""

        # Create audit callback that uses ServiceRegistry
        async def audit_injection(request, result):
            try:
                # Get security audit service if available
                if service_registry.has_service("security_audit_service"):
                    security_audit = service_registry.get_service("security_audit_service")
                    if hasattr(security_audit, "log_injection"):
                        await security_audit.log_injection(request, result)
                else:
                    # Fallback to standard logging
                    logger.info(
                        "CAN message injection: user=%s, interface=%s, can_id=0x%X, "
                        "mode=%s, success=%s, sent=%d, duration=%.3fs",
                        request.user,
                        request.interface,
                        request.can_id,
                        request.mode.value,
                        result.success,
                        result.messages_sent,
                        result.duration,
                    )
            except Exception as e:
                logger.error("CAN injection audit error: %s", e)

        # Use default safety level - feature flags have been removed per CLAUDE.md
        safety_level = SafetyLevel.MODERATE  # Default safety level for CAN injection

        service = CANMessageInjector(safety_level=safety_level, audit_callback=audit_injection)
        return service

    service_registry.register_safety_service(
        name="can_message_injector",
        init_func=_init_can_message_injector,
        # CAN message injection requires guardrail oversight (see ADR-0004).
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("security_audit_service", DependencyType.OPTIONAL),
        ],
        description="Safe CAN message injection service for testing and diagnostics",
        tags={"service", "can", "testing", "diagnostics", "safety-critical"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Message Filter Service
    def _init_can_message_filter():
        """Initialize CAN message filter service with alert callback."""
        from backend.integrations.can.message_filter import MessageFilter

        # Create alert callback that uses ServiceRegistry
        async def alert_callback(alert_data):
            try:
                # Get WebSocket service for real-time alerts
                websocket_manager = None
                if service_registry.has_service("websocket_manager"):
                    websocket_manager = service_registry.get_service("websocket_manager")

                if websocket_manager:
                    # Send filter alert via WebSocket to can_filter clients
                    await websocket_manager.broadcast_can_filter_update("filter_alert", alert_data)
                else:
                    logger.warning("Filter alert - no WebSocket manager available: %s", alert_data)
            except Exception as e:
                logger.error("Error in filter alert callback: %s", e)

        # Use default configuration - feature flags have been removed per CLAUDE.md
        max_rules = 100
        capture_buffer_size = 10000

        return MessageFilter(
            max_rules=max_rules,
            alert_callback=alert_callback,
            capture_buffer_size=capture_buffer_size,
        )

    service_registry.register_safety_service(
        name="can_message_filter",
        init_func=_init_can_message_filter,
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="CAN message filtering system with real-time monitoring and alerting",
        tags={"service", "can", "filtering", "monitoring", "safety"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Bus Recorder Service
    def _init_can_bus_recorder(websocket_manager=None):
        """Initialize CAN bus recorder service."""
        from backend.core.config import get_settings
        from backend.integrations.can.can_bus_recorder import CANBusRecorder

        # Use default configuration - feature flags have been removed per CLAUDE.md
        buffer_size = 100000
        storage_path = get_settings().get_can_recorder_storage_path()
        auto_save_interval = 60.0
        max_file_size_mb = 100.0

        recorder = CANBusRecorder(
            buffer_size=buffer_size,
            storage_path=storage_path,
            auto_save_interval=auto_save_interval,
            max_file_size_mb=max_file_size_mb,
        )

        # Store WebSocket manager for broadcasting
        if websocket_manager:
            recorder._websocket_manager = websocket_manager

        return recorder

    service_registry.register_safety_service(
        name="can_bus_recorder",
        init_func=_init_can_bus_recorder,
        safety_classification=SafetyClassification.OPERATIONAL,
        dependencies=[
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="CAN bus traffic recorder with replay capabilities",
        tags={"service", "can", "recording", "replay", "diagnostics"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Protocol Analyzer Service
    def _init_can_protocol_analyzer(websocket_manager=None):
        """Initialize CAN protocol analyzer service."""
        from backend.integrations.can.protocol_analyzer import ProtocolAnalyzer

        # Use default configuration - feature flags have been removed per CLAUDE.md
        buffer_size = 10000
        pattern_window_ms = 5000.0

        analyzer = ProtocolAnalyzer(buffer_size=buffer_size, pattern_window_ms=pattern_window_ms)

        # Store WebSocket manager for broadcasting
        if websocket_manager:
            analyzer._websocket_manager = websocket_manager

        return analyzer

    service_registry.register_safety_service(
        name="can_protocol_analyzer",
        init_func=_init_can_protocol_analyzer,
        safety_classification=SafetyClassification.OPERATIONAL,
        dependencies=[
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="CAN protocol analyzer for deep packet inspection and protocol detection",
        tags={"service", "can", "analysis", "protocol", "diagnostics"},
        health_check=lambda s: {"healthy": s is not None and not s._emergency_stop_active}
        if hasattr(s, "_emergency_stop_active")
        else {"healthy": s is not None},
    )

    # Register CAN Interface Service
    service_registry.register_service(
        name="can_interface_service",
        init_func=lambda: CANInterfaceService(),
        dependencies=[],
        description="CAN interface mapping and resolution service",
        tags={"service", "can", "interface", "mapping"},
        health_check=lambda s: {"healthy": s is not None},
    )

    # Register rolling CAN network telemetry sampler
    def _init_can_network_telemetry_service() -> CANNetworkTelemetryService:
        """Initialize rolling CAN telemetry sampler from cumulative provider counters."""
        can_interface_service = service_registry.get_service("can_interface_service")
        return CANNetworkTelemetryService(can_interface_service=can_interface_service)

    def _can_network_telemetry_health_check() -> bool:
        """Check rolling CAN telemetry sampler health without service-argument injection."""
        service = service_registry.get_service("can_network_telemetry_service")
        return bool(service.get_health_status().get("healthy", False))

    service_registry.register_service(
        name="can_network_telemetry_service",
        init_func=_init_can_network_telemetry_service,
        dependencies=[ServiceDependency("can_interface_service", DependencyType.REQUIRED)],
        description="Rolling CAN network telemetry sampler for v2 networks",
        tags={"service", "can", "network", "telemetry"},
        health_check=_can_network_telemetry_health_check,
    )

    # CANFacade - Unified facade for all CAN operations
    async def _init_can_facade(
        can_bus_service,
        can_message_injector,
        can_message_filter,
        can_bus_recorder,
        can_protocol_analyzer,
        can_anomaly_detector,
        can_interface_service,
        performance_monitor,
    ):
        """Initialize CANFacade with all CAN-related services."""
        from backend.services.can.can_facade import CANFacade

        return CANFacade(
            bus_service=can_bus_service,
            injector=can_message_injector,
            message_filter=can_message_filter,
            recorder=can_bus_recorder,
            analyzer=can_protocol_analyzer,
            anomaly_detector=can_anomaly_detector,
            interface_service=can_interface_service,
            performance_monitor=performance_monitor,
        )

    service_registry.register_safety_service(
        name="can_facade",
        init_func=_init_can_facade,
        safety_classification=SafetyClassification.CRITICAL,
        dependencies=[
            ServiceDependency("can_bus_service", DependencyType.REQUIRED),
            ServiceDependency("can_message_injector", DependencyType.REQUIRED),
            ServiceDependency("can_message_filter", DependencyType.REQUIRED),
            ServiceDependency("can_bus_recorder", DependencyType.REQUIRED),
            ServiceDependency("can_protocol_analyzer", DependencyType.REQUIRED),
            ServiceDependency("can_anomaly_detector", DependencyType.REQUIRED),
            ServiceDependency("can_interface_service", DependencyType.REQUIRED),
            ServiceDependency("performance_monitor", DependencyType.REQUIRED),
        ],
        description="Unified facade for all CAN operations with safety coordination",
        tags={"facade", "can", "safety-critical", "coordination"},
        health_check=lambda s: s.get_health_status()
        if hasattr(s, "get_health_status")
        else {"healthy": s is not None},
    )

    # AnalyticsDashboardService - Analytics and business intelligence service
    def _init_analytics_dashboard_service(
        performance_monitor=None, database_manager=None, analytics_repository=None
    ):
        """Initialize AnalyticsDashboardService with direct dependencies."""
        return AnalyticsDashboardService(
            performance_monitor=performance_monitor,
            database_manager=database_manager,
            analytics_repository=analytics_repository,
        )

    service_registry.register_service(
        name="analytics_dashboard_service",
        init_func=_init_analytics_dashboard_service,
        dependencies=[
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
            ServiceDependency(
                "database_manager", DependencyType.REQUIRED
            ),  # Now required for persistence
            ServiceDependency("analytics_repository", DependencyType.OPTIONAL),
        ],
        description=(
            "Advanced analytics dashboard for business intelligence "
            "and operational insights (requires persistence)"
        ),
        tags={
            "service",
            "analytics",
            "dashboard",
            "insights",
            "business-intelligence",
            "persistence",
        },
        health_check=lambda s: {
            "healthy": s is not None,
            "running": s._running if hasattr(s, "_running") else False,
        },
    )

    # DashboardService - Frontend dashboard aggregation service
    from backend.services.system.dashboard_service import DashboardService

    def _init_dashboard_service(
        entity_state_repository=None,
        dashboard_config_repository=None,
        performance_monitor=None,
        websocket_manager=None,
    ):
        """Initialize DashboardService with direct dependencies."""
        return DashboardService(
            dashboard_repository=dashboard_config_repository,
            entity_repository=entity_state_repository,
            performance_monitor=performance_monitor,
            websocket_manager=websocket_manager,
        )

    service_registry.register_service(
        name="dashboard_service",
        init_func=_init_dashboard_service,
        dependencies=[
            ServiceDependency("entity_state_repository", DependencyType.OPTIONAL),
            ServiceDependency("dashboard_config_repository", DependencyType.OPTIONAL),
            ServiceDependency("performance_monitor", DependencyType.OPTIONAL),
            ServiceDependency("websocket_manager", DependencyType.OPTIONAL),
        ],
        description="Frontend dashboard data aggregation service with activity feeds",
        tags={"service", "dashboard", "frontend", "aggregation"},
        health_check=lambda s: {
            "healthy": s is not None,
            "activity_tracker_enabled": hasattr(s, "_activity_tracker"),
        },
    )

    logger.info("Phase 4 service registration complete")
