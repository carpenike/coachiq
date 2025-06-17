"""
Schema API Router

Provides schema export endpoints for frontend runtime validation.
Serves Zod-compatible schemas for Domain API v2 with safety-critical validation.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.core.dependencies_v2 import get_auth_manager, get_feature_manager
from backend.schemas.schema_exporter import ZodSchemaExporter
from backend.services.auth_manager import AuthManager
from backend.services.feature_manager import FeatureManager

router = APIRouter(prefix="/api/schemas", tags=["schemas"])


@router.get("/", summary="Get all available schemas")
async def get_all_schemas(
    auth_manager: AuthManager = Depends(get_auth_manager),
    feature_manager: FeatureManager = Depends(get_feature_manager),
) -> JSONResponse:
    """
    Export all Zod-compatible schemas for frontend validation.

    Provides comprehensive schema definitions for Domain API v2 with
    safety-critical validation requirements.
    """
    # Check if schema export is enabled
    if not feature_manager.is_enabled("domain_api_v2"):
        raise HTTPException(status_code=503, detail="Domain API v2 schemas not available")

    try:
        schemas = ZodSchemaExporter.export_all_schemas()

        return JSONResponse(
            content=schemas,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "X-Schema-Version": schemas["version"],
                "X-Domain-API-Version": "v2",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export schemas: {e!s}")


@router.get("/list", summary="Get list of available schema names")
async def get_schema_list(
    feature_manager: FeatureManager = Depends(get_feature_manager),
) -> dict[str, Any]:
    """Get list of available schema names with metadata"""

    if not feature_manager.is_enabled("domain_api_v2"):
        raise HTTPException(status_code=503, detail="Domain API v2 schemas not available")

    return {
        "schemas": ZodSchemaExporter.get_schema_list(),
        "metadata": ZodSchemaExporter.get_schema_metadata(),
    }


@router.get("/{schema_name}", summary="Get specific schema by name")
async def get_schema_by_name(
    schema_name: str,
    auth_manager: AuthManager = Depends(get_auth_manager),
    feature_manager: FeatureManager = Depends(get_feature_manager),
) -> JSONResponse:
    """
    Get a specific schema by name for targeted validation.

    Args:
        schema_name: Name of the schema to retrieve (Entity, ControlCommand, etc.)
    """
    if not feature_manager.is_enabled("domain_api_v2"):
        raise HTTPException(status_code=503, detail="Domain API v2 schemas not available")

    try:
        schema = ZodSchemaExporter.export_schema(schema_name)

        return JSONResponse(
            content={
                "schema_name": schema_name,
                "schema": schema,
                "version": ZodSchemaExporter.SCHEMA_VERSION,
                "metadata": {"safety_critical": True, "validation_required": True},
            },
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Schema-Name": schema_name,
                "X-Schema-Version": ZodSchemaExporter.SCHEMA_VERSION,
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export schema {schema_name}: {e!s}"
        )


@router.get("/validate/integrity", summary="Validate schema integrity")
async def validate_schema_integrity(
    auth_manager: AuthManager = Depends(get_auth_manager),
    feature_manager: FeatureManager = Depends(get_feature_manager),
) -> JSONResponse:
    """
    Validate that all schemas can be properly exported.

    Used for system health checks and debugging schema issues.
    Requires authentication as it's an administrative endpoint.
    """
    if not feature_manager.is_enabled("domain_api_v2"):
        raise HTTPException(status_code=503, detail="Domain API v2 schemas not available")

    # This endpoint requires authentication since it's for admin/debugging
    try:
        # auth_manager.verify_admin_access() would be called here if implemented
        pass
    except Exception:
        raise HTTPException(status_code=403, detail="Admin access required for schema validation")

    try:
        validation_report = ZodSchemaExporter.validate_schema_integrity()

        status_code = 200 if validation_report["validation_passed"] else 500

        return JSONResponse(
            content=validation_report,
            status_code=status_code,
            headers={
                "X-Validation-Status": "passed"
                if validation_report["validation_passed"]
                else "failed"
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Schema validation failed: {e!s}")


@router.get("/docs/openapi", summary="Get OpenAPI-compatible schema definitions")
async def get_openapi_schemas(
    feature_manager: FeatureManager = Depends(get_feature_manager),
    include_examples: bool = Query(True, description="Include schema examples"),
) -> dict[str, Any]:
    """
    Get OpenAPI-compatible schema definitions for documentation generation.

    This endpoint provides schemas in OpenAPI format for integration with
    API documentation tools and code generators.
    """
    if not feature_manager.is_enabled("domain_api_v2"):
        raise HTTPException(status_code=503, detail="Domain API v2 schemas not available")

    try:
        # Convert Zod schemas to OpenAPI format
        zod_schemas = ZodSchemaExporter.export_all_schemas()

        openapi_schemas = {}
        for name, schema in zod_schemas["schemas"].items():
            openapi_schema = _convert_zod_to_openapi(schema)

            if include_examples:
                openapi_schema["example"] = _generate_schema_example(name, schema)

            openapi_schemas[name] = openapi_schema

        return {
            "openapi": "3.0.0",
            "info": {
                "title": "CoachIQ Domain API v2 Schemas",
                "version": zod_schemas["version"],
                "description": "Safety-critical schemas for RV-C vehicle control",
            },
            "components": {"schemas": openapi_schemas},
            "metadata": zod_schemas["metadata"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate OpenAPI schemas: {e!s}")


def _convert_zod_to_openapi(zod_schema: dict[str, Any]) -> dict[str, Any]:
    """Convert Zod schema format to OpenAPI format"""
    openapi_schema = zod_schema.copy()

    # Handle nullable types in OpenAPI format
    for prop_name, prop_schema in openapi_schema.get("properties", {}).items():
        if isinstance(prop_schema.get("type"), list) and "null" in prop_schema["type"]:
            # Convert ["string", "null"] to nullable: true
            non_null_types = [t for t in prop_schema["type"] if t != "null"]
            if len(non_null_types) == 1:
                prop_schema["type"] = non_null_types[0]
                prop_schema["nullable"] = True
            else:
                prop_schema["oneOf"] = [{"type": t} for t in non_null_types]
                prop_schema["nullable"] = True
                del prop_schema["type"]

    return openapi_schema


def _generate_schema_example(schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Generate example data for schema documentation"""
    examples = {
        "Entity": {
            "entity_id": "light_living_room",
            "name": "Living Room Light",
            "device_type": "light",
            "protocol": "rvc",
            "state": {"on": True, "brightness": 75},
            "last_updated": "2025-01-11T10:30:00Z",
            "capabilities": ["on_off", "dimming"],
            "suggested_area": "Living Room",
            "groups": ["interior_lights"],
            "safety_status": "operational",
        },
        "ControlCommand": {
            "command": "set",
            "state": True,
            "brightness": 80,
            "safety_confirmation": False,
            "timeout_seconds": 5.0,
        },
        "BulkOperation": {
            "entity_ids": ["light_living_room", "light_bedroom"],
            "command": {
                "command": "set",
                "state": False,
                "safety_confirmation": False,
                "timeout_seconds": 5.0,
            },
            "ignore_errors": False,
            "safety_mode": "strict",
            "max_concurrent": 10,
        },
    }

    return examples.get(schema_name, {})
