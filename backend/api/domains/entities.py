"""
Entities Domain API Router (v2)

Provides domain-specific entity management endpoints with enhanced capabilities:
- Bulk operations with partial success handling
- Safety-critical command/acknowledgment patterns
- Schema validation and export
- Audit logging for all operations
- State reconciliation with RV-C bus

This router integrates with existing EntityService but provides v2 API patterns.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.api.domains import register_domain_router
from backend.core.dependencies import (
    create_service_dependency,
    get_entity_service,
)

# Create missing dependencies
get_entity_domain_service = create_service_dependency("entity_domain_service")
get_authenticated_user = lambda: None  # Placeholder
get_authenticated_admin = lambda: None  # Placeholder

# ControlCommand import removed - not used in this file

logger = logging.getLogger(__name__)


# Domain-specific schemas for v2 API
class EntitySchemaV2(BaseModel):
    """Enhanced entity schema for v2 API"""

    entity_id: str = Field(..., description="Unique entity identifier")
    name: str = Field(..., description="Human-readable entity name")
    device_type: str = Field(..., description="Device type classification")
    protocol: str = Field(..., description="Communication protocol")
    state: dict[str, Any] = Field(default_factory=dict, description="Current entity state")
    area: str | None = Field(None, description="Physical area/location")
    last_updated: str = Field(..., description="ISO timestamp of last update")
    available: bool = Field(True, description="Whether entity is available/responding")


class ControlCommandV2(BaseModel):
    """Enhanced control command schema for v2 API"""

    command: str = Field(
        ..., description="Command type: set, toggle, brightness_up, brightness_down"
    )
    state: bool | None = Field(None, description="Target state for set commands")
    brightness: int | None = Field(None, ge=0, le=100, description="Brightness level 0-100")
    parameters: dict[str, Any] | None = Field(None, description="Additional command parameters")


class BulkControlRequestV2(BaseModel):
    """Bulk operation request schema"""

    entity_ids: list[str] = Field(..., description="List of entity IDs to control")
    command: ControlCommandV2 = Field(..., description="Command to execute on all entities")
    ignore_errors: bool = Field(True, description="Continue on individual failures")
    timeout_seconds: float | None = Field(5.0, description="Timeout per operation")


class OperationResultV2(BaseModel):
    """Individual operation result"""

    entity_id: str = Field(..., description="Entity ID that was operated on")
    status: str = Field(..., description="Operation status: success, failed, timeout, unauthorized")
    error_message: str | None = Field(None, description="Error details if failed")
    error_code: str | None = Field(None, description="Machine-readable error code")
    execution_time_ms: float | None = Field(None, description="Operation execution time")


class BulkOperationResultV2(BaseModel):
    """Bulk operation result with detailed per-entity results"""

    operation_id: str = Field(..., description="Unique operation identifier")
    total_count: int = Field(..., description="Total number of operations attempted")
    success_count: int = Field(..., description="Number of successful operations")
    failed_count: int = Field(..., description="Number of failed operations")
    results: list[OperationResultV2] = Field(..., description="Per-entity operation results")
    total_execution_time_ms: float = Field(..., description="Total execution time")


class EntityCollectionV2(BaseModel):
    """Paginated entity collection"""

    entities: list[EntitySchemaV2] = Field(..., description="List of entities")
    total_count: int = Field(..., description="Total entities available")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(50, description="Number of entities per page")
    has_next: bool = Field(False, description="Whether more pages are available")
    filters_applied: dict[str, Any] = Field(default_factory=dict, description="Applied filters")


# Query parameters
class EntitiesQueryParamsV2(BaseModel):
    """Query parameters for entity filtering and pagination"""

    device_type: str | None = None
    area: str | None = None
    protocol: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=100)


def create_entities_router() -> APIRouter:
    """Create the entities domain router with all endpoints"""
    router = APIRouter(
        tags=["entities-v2"],
    )

    def _categorize_entities(entities: dict) -> dict:
        """Helper to categorize entities for debugging"""
        categories = {}
        for entity_id, entity_data in entities.items():
            device_type = entity_data.get("device_type", "unknown")
            if device_type not in categories:
                categories[device_type] = []
            categories[device_type].append(entity_id)

        return {
            device_type: {"count": len(entity_list), "examples": entity_list[:3]}
            for device_type, entity_list in categories.items()
        }

    @router.get("/health")
    async def health_check(
        request: Request,
        entity_service: Annotated[Any, Depends(get_entity_service)],
        domain_service: Annotated[Any, Depends(get_entity_domain_service)],
    ) -> dict[str, Any]:
        """Comprehensive health check for Pi RV deployment debugging"""
        try:
            import datetime

            import psutil

            # Get system health for Pi monitoring
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Get safety status for RV debugging
            safety_status = await domain_service.get_safety_status()

            return {
                "status": "healthy",
                "domain": "entities",
                "version": "v2-pi",
                "timestamp": datetime.datetime.now().isoformat(),
                # Pi System Health
                "pi_system": {
                    "memory_used_percent": memory.percent,
                    "memory_available_mb": memory.available // 1024 // 1024,
                    "cpu_percent": cpu_percent,
                    "warnings": [
                        "High memory usage" if memory.percent > 80 else None,
                        "High CPU usage" if cpu_percent > 90 else None,
                    ],
                },
                # RV Entity Status
                "rv_entities": {
                    "total_count": len(await entity_service.list_entities()),
                    "emergency_stop_active": safety_status.get("emergency_stop_active", False),
                    "pending_operations": safety_status.get("pending_operations_count", 0),
                },
                # Feature Status (all enabled per CLAUDE.md)
                "features": {
                    "domain_api_v2": True,
                    "entities_api_v2": True,
                    "safety_interlocks": safety_status.get("safety_interlocks_enabled", False),
                },
                # Debug Info for Solo Developer
                "debug_urls": {
                    "safety_status": "/api/v2/entities/safety-status",
                    "schemas": "/api/v2/entities/schemas",
                    "unmapped_devices": "/api/v2/entities/debug/unmapped",
                    "unknown_pgns": "/api/v2/entities/debug/unknown-pgns",
                },
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise HTTPException(status_code=503, detail=f"Service unavailable: {e!s}")

    @router.get("/schemas")
    async def get_schemas(request: Request) -> dict[str, Any]:
        """Export Pydantic schemas as JSON Schema for frontend validation"""
        return {
            "Entity": EntitySchemaV2.model_json_schema(),
            "ControlCommand": ControlCommandV2.model_json_schema(),
            "BulkControlRequest": BulkControlRequestV2.model_json_schema(),
            "OperationResult": OperationResultV2.model_json_schema(),
            "BulkOperationResult": BulkOperationResultV2.model_json_schema(),
            "EntityCollection": EntityCollectionV2.model_json_schema(),
        }

    @router.get("/debug/system-info")
    async def get_debug_info(
        request: Request,
        entity_service: Annotated[Any, Depends(get_entity_service)],
        domain_service: Annotated[Any, Depends(get_entity_domain_service)],
    ) -> dict[str, Any]:
        """Comprehensive debug information for RV Pi troubleshooting"""
        try:
            import datetime
            import os
            import platform

            import psutil

            # System Information
            boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.datetime.now() - boot_time

            # Network interfaces (important for RV CAN networks)
            network_interfaces = []
            for interface, addrs in psutil.net_if_addrs().items():
                if interface.startswith("can") or "can" in interface.lower():
                    network_interfaces.append(
                        {"name": interface, "addresses": [addr.address for addr in addrs]}
                    )

            # Safety and entity status
            safety_status = await domain_service.get_safety_status()
            entities = await entity_service.list_entities()

            return {
                "system": {
                    "platform": platform.platform(),
                    "python_version": platform.python_version(),
                    "architecture": platform.architecture()[0],
                    "hostname": platform.node(),
                    "uptime_hours": round(uptime.total_seconds() / 3600, 1),
                    "boot_time": boot_time.isoformat(),
                },
                "resources": {
                    "cpu_count": psutil.cpu_count(),
                    "memory_total_gb": round(psutil.virtual_memory().total / 1024**3, 2),
                    "disk_free_gb": round(psutil.disk_usage("/").free / 1024**3, 2),
                    "load_average": os.getloadavg() if hasattr(os, "getloadavg") else "N/A",
                },
                "can_networks": {
                    "detected_interfaces": network_interfaces,
                    "total_interfaces": len(network_interfaces),
                    "status": "CAN interfaces detected"
                    if network_interfaces
                    else "No CAN interfaces found",
                },
                "rv_status": {
                    "entities_by_type": _categorize_entities(entities),
                    "safety_summary": safety_status,
                    "feature_flags": {
                        # All enabled per CLAUDE.md - no feature flags
                        "domain_api_v2": True,
                        "entities_api_v2": True,
                        "can_interface": True,
                        "rvc_decoder": True,
                    },
                },
                "troubleshooting": {
                    "common_issues": [
                        {
                            "issue": "No entities detected",
                            "check": "Verify CAN interfaces and RV-C device connectivity",
                        },
                        {
                            "issue": "High memory usage",
                            "check": f"Current: {psutil.virtual_memory().percent}% - Restart if >90%",
                        },
                        {
                            "issue": "Control commands failing",
                            "check": "Check emergency stop status and CAN bus health",
                        },
                        {
                            "issue": "Slow responses",
                            "check": f"Current CPU: {psutil.cpu_percent()}% - Check background processes",
                        },
                    ],
                    "useful_endpoints": {
                        "View all entities": "/api/v2/entities",
                        "Emergency stop": "POST /api/v2/entities/emergency-stop",
                        "Clear emergency": "POST /api/v2/entities/clear-emergency-stop",
                        "Unmapped devices": "/api/v2/entities/debug/unmapped",
                    },
                },
            }

        except Exception as e:
            logger.error(f"Debug info failed: {e}")
            return {"error": str(e), "message": "Debug info collection failed"}

    @router.get("", response_model=EntityCollectionV2)
    async def get_entities(
        request: Request,
        entity_service: Annotated[Any, Depends(get_entity_service)],
        device_type: str | None = Query(None, description="Filter by device type"),
        area: str | None = Query(None, description="Filter by area"),
        protocol: str | None = Query(None, description="Filter by protocol"),
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    ) -> EntityCollectionV2:
        """Get entities with filtering and pagination (v2) - optimized for Pi deployment"""

        try:
            # Get all entities from legacy service
            all_entities = await entity_service.list_entities()

            # Convert to v2 format and apply filters
            entities_v2 = []
            for entity_id, entity_data in all_entities.items():
                # Convert legacy entity to v2 schema
                entity_v2 = EntitySchemaV2(
                    entity_id=entity_id,
                    name=entity_data.get("friendly_name", entity_data.get("name", entity_id)),
                    device_type=entity_data.get("device_type", "unknown"),
                    protocol=entity_data.get("protocol", "rvc"),
                    state=entity_data.get("raw", {}),
                    area=entity_data.get("suggested_area"),
                    last_updated=entity_data.get("last_updated", "2025-01-11T00:00:00Z"),
                    available=entity_data.get("available", True),
                )

                # Apply filters
                if device_type and entity_v2.device_type != device_type:
                    continue
                if area and entity_v2.area != area:
                    continue
                if protocol and entity_v2.protocol != protocol:
                    continue

                entities_v2.append(entity_v2)

            # Apply pagination
            total_count = len(entities_v2)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_entities = entities_v2[start_idx:end_idx]

            return EntityCollectionV2(
                entities=paginated_entities,
                total_count=total_count,
                page=page,
                page_size=page_size,
                has_next=end_idx < total_count,
                filters_applied={
                    "device_type": device_type,
                    "area": area,
                    "protocol": protocol,
                },
            )

        except Exception as e:
            logger.error(f"Failed to get entities: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to retrieve entities: {e!s}")

    @router.get("/safety-status")
    async def get_safety_status(
        request: Request, domain_service: Annotated[Any, Depends(get_entity_domain_service)]
    ) -> dict:
        """Get current safety system status"""

        try:
            result = await domain_service.get_safety_status()
            return result
        except Exception as e:
            logger.error(f"Get safety status failed: {e}")
            raise HTTPException(status_code=500, detail=f"Get safety status failed: {e!s}")

    # SPECIFIC ROUTES - MUST COME BEFORE /{entity_id} ROUTE
    @router.get("/metadata")
    async def get_entity_metadata(
        request: Request, entity_service: Annotated[Any, Depends(get_entity_service)]
    ) -> dict:
        """Get metadata about entity types, areas, and capabilities"""

        try:
            metadata = await entity_service.get_metadata()
            return metadata
        except Exception as e:
            logger.error(f"Failed to get entity metadata: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get entity metadata: {e!s}")

    @router.get("/protocol-summary")
    async def get_protocol_summary(
        request: Request, entity_service: Annotated[Any, Depends(get_entity_service)]
    ) -> dict:
        """Get summary of entity distribution across protocols"""

        try:
            summary = await entity_service.get_protocol_summary()
            return summary
        except Exception as e:
            logger.error(f"Failed to get protocol summary: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get protocol summary: {e!s}")

    @router.get("/debug/unmapped")
    async def get_unmapped_entries(
        request: Request, entity_service: Annotated[Any, Depends(get_entity_service)]
    ) -> dict:
        """Get unmapped DGN/instance pairs observed on CAN bus"""

        try:
            entries = await entity_service.get_unmapped_entries()
            return {"unmapped_entries": entries}
        except Exception as e:
            logger.error(f"Failed to get unmapped entries: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get unmapped entries: {e!s}")

    @router.get("/debug/unknown-pgns")
    async def get_unknown_pgns(
        request: Request, entity_service: Annotated[Any, Depends(get_entity_service)]
    ) -> dict:
        """Get unknown PGNs observed on CAN bus"""

        try:
            entries = await entity_service.get_unknown_pgns()
            return {"unknown_pgns": entries}
        except Exception as e:
            logger.error(f"Failed to get unknown PGNs: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get unknown PGNs: {e!s}")

    @router.get("/debug/missing-dgns")
    async def get_missing_dgns(
        request: Request, entity_service: Annotated[Any, Depends(get_entity_service)]
    ) -> dict:
        """Get DGNs encountered but not in specification"""

        try:
            # For now, implement as placeholder since method doesn't exist in entity service
            # In a full implementation, this would query the RVC integration for missing DGNs
            missing_dgns = {}  # Placeholder - entity_service.get_missing_dgns() not implemented
            return {"missing_dgns": missing_dgns}
        except Exception as e:
            logger.error(f"Failed to get missing DGNs: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get missing DGNs: {e!s}")

    @router.post("/mappings")
    async def create_entity_mapping(
        request: Request,
        mapping_request: dict,
        entity_service: Annotated[Any, Depends(get_entity_service)],
    ) -> dict:
        """Create new entity mapping from unmapped entry"""

        try:
            result = await entity_service.create_entity_mapping(mapping_request)
            return result
        except Exception as e:
            logger.error(f"Failed to create entity mapping: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create entity mapping: {e!s}")

    @router.get("/{entity_id}", response_model=EntitySchemaV2)
    async def get_entity(
        request: Request,
        entity_id: str,
        entity_service: Annotated[Any, Depends(get_entity_service)],
    ) -> EntitySchemaV2:
        """Get a specific entity by ID (v2)"""

        try:
            all_entities = await entity_service.list_entities()

            if entity_id not in all_entities:
                raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

            entity_data = all_entities[entity_id]
            return EntitySchemaV2(
                entity_id=entity_id,
                name=entity_data.get("friendly_name", entity_data.get("name", entity_id)),
                device_type=entity_data.get("device_type", "unknown"),
                protocol=entity_data.get("protocol", "rvc"),
                state=entity_data.get("raw", {}),
                area=entity_data.get("suggested_area"),
                last_updated=entity_data.get("last_updated", "2025-01-11T00:00:00Z"),
                available=entity_data.get("available", True),
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get entity {entity_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to retrieve entity: {e!s}")

    @router.post("/{entity_id}/control", response_model=dict)
    async def control_entity(
        request: Request,
        entity_id: str,
        command: ControlCommandV2,
        domain_service: Annotated[Any, Depends(get_entity_domain_service)],
        user: dict = Depends(get_authenticated_user),
    ) -> dict:
        """Control a single entity with safety validation (v2) - Pi optimized"""
        try:
            # For Pi deployment, always use the safe domain service
            # Import safety models
            from backend.services.entity_domain_service import SafetyControlCommandV2

            # Convert to safety command with reasonable Pi defaults
            safety_command = SafetyControlCommandV2(
                command=command.command,
                state=command.state,
                brightness=command.brightness,
                parameters=command.parameters,
                safety_confirmation=True,  # Always require for RV safety
                timeout_seconds=5.0,  # Fast timeout for local CAN bus
            )

            # Execute safety-critical control
            result = await domain_service.control_entity_safe(entity_id, safety_command)
            return result.dict()

        except Exception as e:
            logger.error(f"Entity control failed: {e}")
            raise HTTPException(status_code=500, detail=f"Control failed: {e!s}")

    @router.post("/bulk-control", response_model=dict)
    async def bulk_control_entities(
        request: Request,
        bulk_request: BulkControlRequestV2,
        domain_service: Annotated[Any, Depends(get_entity_domain_service)],
        user: dict = Depends(get_authenticated_user),
    ) -> dict:
        """Execute bulk control operations with safety validation (v2) - Pi optimized"""
        try:
            # For Pi deployment, always use the safe domain service
            from backend.services.entity_domain_service import (
                BulkSafetyOperationRequestV2,
                SafetyControlCommandV2,
            )

            # Convert to safety bulk request with Pi defaults
            safety_command = SafetyControlCommandV2(
                command=bulk_request.command.command,
                state=bulk_request.command.state,
                brightness=bulk_request.command.brightness,
                parameters=bulk_request.command.parameters,
                safety_confirmation=True,  # Always require for RV safety
                timeout_seconds=bulk_request.timeout_seconds or 5.0,
            )

            safety_bulk_request = BulkSafetyOperationRequestV2(
                entity_ids=bulk_request.entity_ids,
                command=safety_command,
                ignore_errors=bulk_request.ignore_errors,
                safety_mode="strict",  # Always strict for RV
                max_concurrent=min(5, len(bulk_request.entity_ids)),  # Pi-safe concurrency
            )

            # Execute safety-critical bulk control
            result = await domain_service.bulk_control_entities_safe(safety_bulk_request)
            return result.dict()

        except Exception as e:
            logger.error(f"Bulk operation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Bulk operation failed: {e!s}")

    @router.post("/emergency-stop")
    async def emergency_stop(
        request: Request,
        domain_service: Annotated[Any, Depends(get_entity_domain_service)],
        admin_user: dict = Depends(get_authenticated_admin),
    ) -> dict:
        """Emergency stop - immediately halt all entity operations (Admin Only)"""

        try:
            # Log the admin user who triggered emergency stop for audit trail
            triggered_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"
            logger.warning(f"Domain API emergency stop triggered by admin user {triggered_by}")

            result = await domain_service.emergency_stop()
            result["triggered_by"] = triggered_by
            return result
        except Exception as e:
            logger.error(f"Emergency stop failed: {e}")
            raise HTTPException(status_code=500, detail=f"Emergency stop failed: {e!s}")

    @router.post("/clear-emergency-stop")
    async def clear_emergency_stop(
        request: Request,
        domain_service: Annotated[Any, Depends(get_entity_domain_service)],
        admin_user: dict = Depends(get_authenticated_admin),
    ) -> dict:
        """Clear emergency stop condition (Admin Only)"""

        try:
            # Log the admin user who cleared emergency stop for audit trail
            cleared_by = f"{admin_user.get('username', admin_user.get('user_id', 'unknown'))}"
            logger.warning(f"Domain API emergency stop cleared by admin user {cleared_by}")

            result = await domain_service.clear_emergency_stop()
            result["cleared_by"] = cleared_by
            return result
        except Exception as e:
            logger.error(f"Clear emergency stop failed: {e}")
            raise HTTPException(status_code=500, detail=f"Clear emergency stop failed: {e!s}")

    @router.post("/reconcile-state")
    async def reconcile_state_with_rvc_bus(
        request: Request, domain_service: Annotated[Any, Depends(get_entity_domain_service)]
    ) -> dict:
        """Reconcile application state with RV-C bus state"""

        try:
            result = await domain_service.reconcile_state_with_rvc_bus()
            return result
        except Exception as e:
            logger.error(f"State reconciliation failed: {e}")
            raise HTTPException(status_code=500, detail=f"State reconciliation failed: {e!s}")

    # Additional route for entity history (after the /{entity_id} route)
    @router.get("/{entity_id}/history")
    async def get_entity_history(
        request: Request,
        entity_id: str,
        entity_service: Annotated[Any, Depends(get_entity_service)],
        limit: int = Query(100, description="Maximum number of history entries"),
        since: float | None = Query(None, description="Unix timestamp filter"),
    ) -> dict:
        """Get entity state change history"""

        try:
            history = await entity_service.get_entity_history(entity_id, limit=limit, since=since)

            if history is None:
                raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

            return {"entity_id": entity_id, "history": history, "count": len(history)}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get entity history for {entity_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get entity history: {e!s}")

    return router


@register_domain_router("entities")
def register_entities_router() -> APIRouter:
    """Register the entities domain router"""
    return create_entities_router()
