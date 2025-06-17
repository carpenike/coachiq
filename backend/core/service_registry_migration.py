"""
Migration utilities for transitioning to enhanced ServiceRegistry

This module provides helpers to migrate from the basic ServiceRegistry
to the enhanced version with advanced dependency resolution.

Part of Phase 2F: Service Dependency Resolution Enhancement
"""

import logging
from typing import Any, Dict, List, Optional, Set

from backend.core.service_dependency_resolver import ServiceDependency, DependencyType
from backend.core.service_registry import ServiceRegistry
from backend.core.service_registry_v2 import EnhancedServiceRegistry, ServiceDefinition

logger = logging.getLogger(__name__)


def migrate_to_enhanced_registry(
    old_registry: ServiceRegistry,
    enhanced_registry: Optional[EnhancedServiceRegistry] = None
) -> EnhancedServiceRegistry:
    """
    Migrate from basic ServiceRegistry to enhanced version.

    Args:
        old_registry: Existing ServiceRegistry instance
        enhanced_registry: Optional pre-configured EnhancedServiceRegistry

    Returns:
        Configured EnhancedServiceRegistry with migrated services
    """
    if enhanced_registry is None:
        enhanced_registry = EnhancedServiceRegistry()

    logger.info("Migrating to enhanced ServiceRegistry...")

    # Migrate existing services
    migrated_count = 0
    for stage_services in old_registry._startup_stages:
        for name, init_func, deps in stage_services:
            # Convert basic dependencies to enhanced format
            enhanced_deps = [
                ServiceDependency(name=dep, type=DependencyType.REQUIRED)
                for dep in deps
            ]

            enhanced_registry.register_service(
                name=name,
                init_func=init_func,
                dependencies=enhanced_deps,
                tags=_infer_tags(name),
                description=_infer_description(name),
            )
            migrated_count += 1

    logger.info(f"Migrated {migrated_count} services to enhanced registry")

    # Copy runtime state if services already started
    if old_registry._services:
        logger.info("Copying runtime state from old registry...")
        enhanced_registry._services = old_registry._services.copy()
        enhanced_registry._service_status = old_registry._service_status.copy()
        enhanced_registry._background_tasks = old_registry._background_tasks.copy()
        enhanced_registry._startup_time = old_registry._startup_time

    return enhanced_registry


def _infer_tags(service_name: str) -> Set[str]:
    """Infer service tags from name patterns."""
    tags = set()

    # Core services
    if any(keyword in service_name for keyword in ["settings", "config", "core", "database", "persistence"]):
        tags.add("core")

    # Feature services
    if "feature" in service_name or "service" in service_name:
        tags.add("feature")

    # Integration services
    if any(keyword in service_name for keyword in ["rvc", "can", "websocket", "auth"]):
        tags.add("integration")

    # API services
    if "api" in service_name or "router" in service_name:
        tags.add("api")

    # Security services
    if any(keyword in service_name for keyword in ["security", "auth", "pin"]):
        tags.add("security")

    return tags


def _infer_description(service_name: str) -> str:
    """Infer service description from name."""
    descriptions = {
        "app_settings": "Application configuration and settings management",
        "rvc_config": "RV-C protocol configuration provider",
        "core_services": "Core infrastructure services (database, persistence)",
        "security_event_manager": "Security event logging and monitoring",
        "device_discovery_service": "RV-C device discovery and enumeration",
        "feature_manager": "Feature flag and lifecycle management",
        "entity_service": "Entity state management and control",
        "can_service": "CAN bus communication service",
        "websocket_manager": "WebSocket connection management",
        "auth_manager": "Authentication and authorization service",
    }

    return descriptions.get(service_name, f"Service: {service_name}")


def create_enhanced_service_stages() -> List[List[ServiceDefinition]]:
    """
    Create service definitions with enhanced dependency information.

    Returns:
        List of service definition stages for the application
    """
    stages = []

    # Stage 0: Core Configuration (no dependencies)
    stage0 = [
        ServiceDefinition(
            name="app_settings",
            init_func=lambda: _init_placeholder("app_settings"),
            dependencies=[],
            tags={"core", "configuration"},
            description="Application settings and configuration management",
        ),
        ServiceDefinition(
            name="rvc_config",
            init_func=lambda: _init_placeholder("rvc_config"),
            dependencies=[],
            tags={"core", "configuration", "rvc"},
            description="RV-C protocol specification and configuration",
        ),
    ]
    stages.append(stage0)

    # Stage 1: Core Infrastructure
    stage1 = [
        ServiceDefinition(
            name="persistence_service",
            init_func=lambda: _init_placeholder("persistence_service"),
            dependencies=[
                ServiceDependency(name="app_settings", type=DependencyType.REQUIRED),
            ],
            tags={"core", "storage"},
            description="Persistent storage service for application state",
        ),
        ServiceDefinition(
            name="database_manager",
            init_func=lambda: _init_placeholder("database_manager"),
            dependencies=[
                ServiceDependency(name="app_settings", type=DependencyType.REQUIRED),
            ],
            tags={"core", "storage"},
            description="Database connection and migration management",
        ),
    ]
    stages.append(stage1)

    # Stage 2: Security and Events
    stage2 = [
        ServiceDefinition(
            name="security_event_manager",
            init_func=lambda: _init_placeholder("security_event_manager"),
            dependencies=[
                ServiceDependency(name="database_manager", type=DependencyType.OPTIONAL),
                ServiceDependency(name="persistence_service", type=DependencyType.REQUIRED),
            ],
            tags={"security", "monitoring"},
            description="Security event logging and audit trail management",
        ),
        ServiceDefinition(
            name="pin_manager",
            init_func=lambda: _init_placeholder("pin_manager"),
            dependencies=[
                ServiceDependency(name="database_manager", type=DependencyType.REQUIRED),
                ServiceDependency(
                    name="security_event_manager",
                    type=DependencyType.OPTIONAL,
                    fallback="persistence_service"
                ),
            ],
            tags={"security", "authentication"},
            description="PIN-based authentication and authorization",
        ),
    ]
    stages.append(stage2)

    # Stage 3: Communication Services
    stage3 = [
        ServiceDefinition(
            name="can_service",
            init_func=lambda: _init_placeholder("can_service"),
            dependencies=[
                ServiceDependency(name="app_settings", type=DependencyType.REQUIRED),
                ServiceDependency(name="rvc_config", type=DependencyType.REQUIRED),
            ],
            tags={"integration", "communication", "can"},
            description="CAN bus interface and message handling",
        ),
        ServiceDefinition(
            name="websocket_manager",
            init_func=lambda: _init_placeholder("websocket_manager"),
            dependencies=[
                ServiceDependency(name="app_settings", type=DependencyType.REQUIRED),
            ],
            tags={"integration", "communication", "realtime"},
            description="WebSocket connection and message routing",
        ),
    ]
    stages.append(stage3)

    # Stage 4: Application Services
    stage4 = [
        ServiceDefinition(
            name="entity_service",
            init_func=lambda: _init_placeholder("entity_service"),
            dependencies=[
                ServiceDependency(name="persistence_service", type=DependencyType.REQUIRED),
                ServiceDependency(name="can_service", type=DependencyType.REQUIRED),
                ServiceDependency(name="rvc_config", type=DependencyType.REQUIRED),
                ServiceDependency(name="websocket_manager", type=DependencyType.RUNTIME),
            ],
            tags={"feature", "core"},
            description="RV-C entity state management and control",
        ),
        ServiceDefinition(
            name="device_discovery_service",
            init_func=lambda: _init_placeholder("device_discovery_service"),
            dependencies=[
                ServiceDependency(name="can_service", type=DependencyType.REQUIRED),
                ServiceDependency(name="entity_service", type=DependencyType.OPTIONAL),
            ],
            tags={"feature", "discovery"},
            description="Automatic RV-C device discovery and enumeration",
        ),
    ]
    stages.append(stage4)

    return stages


def _init_placeholder(name: str) -> Any:
    """Placeholder initialization function for examples."""
    logger.info(f"Placeholder initialization for: {name}")
    return {"name": name, "initialized": True}


def apply_enhanced_stages_to_main(
    registry: EnhancedServiceRegistry,
    app_context: Dict[str, Any]
) -> None:
    """
    Apply enhanced service stages to main.py context.

    Args:
        registry: Enhanced service registry
        app_context: Application context with actual init functions
    """
    # Map of service names to actual initialization functions
    init_functions = {
        "app_settings": app_context.get("_init_app_settings"),
        "rvc_config": app_context.get("_init_rvc_config_provider"),
        "core_services": app_context.get("_init_core_services"),
        "persistence_service": app_context.get("_init_persistence_service"),
        "database_manager": app_context.get("_init_database_manager"),
        "security_event_manager": app_context.get("_init_security_event_manager"),
        "device_discovery_service": app_context.get("_init_device_discovery_service"),
        "feature_manager": app_context.get("_init_feature_manager"),
        "entity_service": app_context.get("_init_entity_service"),
        "can_service": app_context.get("_init_can_service"),
        "websocket_manager": app_context.get("_init_websocket_manager"),
        "pin_manager": app_context.get("_init_pin_manager"),
    }

    # Get enhanced stage definitions
    stages = create_enhanced_service_stages()

    # Register services with actual init functions
    for stage in stages:
        for service_def in stage:
            actual_init = init_functions.get(service_def.name)
            if actual_init:
                registry.register_service(
                    name=service_def.name,
                    init_func=actual_init,
                    dependencies=service_def.dependencies,
                    tags=service_def.tags,
                    description=service_def.description,
                )
            else:
                logger.warning(
                    f"No initialization function found for service: {service_def.name}"
                )


def generate_dependency_documentation(
    registry: EnhancedServiceRegistry,
    output_path: Optional[str] = None
) -> str:
    """
    Generate comprehensive dependency documentation.

    Args:
        registry: Enhanced service registry
        output_path: Optional path to save documentation

    Returns:
        Generated documentation as string
    """
    lines = [
        "# Service Dependency Documentation",
        "",
        "## Overview",
        "",
        f"Total Services: {len(registry._service_definitions)}",
        f"Startup Stages: {len(registry._resolver._stages)}",
        "",
        "## Dependency Report",
        "",
        "```",
        registry.get_dependency_report(),
        "```",
        "",
        "## Mermaid Dependency Diagram",
        "",
        "```mermaid",
        registry.export_dependency_diagram(),
        "```",
        "",
        "## Service Details",
        "",
    ]

    # Add service details
    for name in sorted(registry._service_definitions.keys()):
        info = registry.get_service_info(name)
        lines.extend([
            f"### {name}",
            "",
            f"**Description**: {info.get('description', 'N/A')}",
            f"**Status**: {info.get('status', 'PENDING')}",
            f"**Tags**: {', '.join(info.get('tags', []))}",
            "",
        ])

        if info.get('dependencies'):
            lines.append("**Dependencies**:")
            for dep in info['dependencies']:
                dep_line = f"- {dep['name']} ({dep['type']})"
                if dep.get('fallback'):
                    dep_line += f" [fallback: {dep['fallback']}]"
                lines.append(dep_line)
            lines.append("")

        if info.get('impacted_services'):
            lines.append("**Impacted Services**:")
            for service in info['impacted_services']:
                lines.append(f"- {service}")
            lines.append("")

    documentation = "\n".join(lines)

    if output_path:
        with open(output_path, 'w') as f:
            f.write(documentation)
        logger.info(f"Dependency documentation written to: {output_path}")

    return documentation
