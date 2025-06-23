"""
Entity Schema Definitions for Domain API v2

Provides Pydantic schemas with Zod export capability for runtime type safety.
These schemas are based on the safety-critical models from EntityDomainService.
"""

from typing import Any

from pydantic import BaseModel, Field


class EntitySchemaV2(BaseModel):
    """Enhanced entity schema with comprehensive metadata"""

    entity_id: str = Field(..., description="Unique entity identifier")
    name: str = Field(..., description="Human-readable entity name")
    device_type: str = Field(..., description="Device type: light, lock, tank, etc.")
    protocol: str = Field(..., description="Communication protocol: rvc, j1939, etc.")
    state: dict[str, Any] = Field(..., description="Current entity state")
    last_updated: str = Field(..., description="ISO datetime of last update")
    capabilities: list[str] = Field(
        default_factory=list, description="Available entity capabilities"
    )
    suggested_area: str | None = Field(None, description="Suggested location/area")
    groups: list[str] = Field(default_factory=list, description="Entity group memberships")
    safety_critical: bool = Field(False, description="Whether this entity is safety-critical")
    safety_status: str = Field("unknown", description="Safety validation status")
    status: str = Field("unknown", description="Entity operational status")
    last_seen: str | None = Field(None, description="ISO datetime when entity was last seen")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional entity metadata")

    @classmethod
    def to_zod_schema(cls) -> dict[str, Any]:
        """Export Zod-compatible schema for frontend validation"""
        return {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "name": {"type": "string"},
                "device_type": {"type": "string"},
                "protocol": {"type": "string"},
                "state": {"type": "object"},
                "last_updated": {"type": "string", "format": "date-time"},
                "capabilities": {"type": "array", "items": {"type": "string"}},
                "suggested_area": {"type": ["string", "null"]},
                "groups": {"type": "array", "items": {"type": "string"}},
                "safety_critical": {"type": "boolean", "default": False},
                "safety_status": {"type": "string"},
                "status": {"type": "string"},
                "last_seen": {"type": ["string", "null"], "format": "date-time"},
                "metadata": {"type": "object"},
            },
            "required": ["entity_id", "name", "device_type", "protocol", "state", "last_updated"],
            "additionalProperties": False,
        }


class ControlCommandSchemaV2(BaseModel):
    """Enhanced control command schema with safety validation"""

    command: str = Field(
        ...,
        description="Command type: set, toggle, brightness_up, brightness_down, emergency_stop, clear_emergency_stop",
    )
    entity_ids: list[str] = Field(default_factory=list, description="Target entity IDs")
    state: bool | None = Field(None, description="Target state for set commands")
    brightness: int | None = Field(None, ge=0, le=100, description="Brightness level 0-100")
    parameters: dict[str, Any] | None = Field(None, description="Additional command parameters")
    safety_critical: bool = Field(
        False, description="Whether this command affects safety-critical systems"
    )
    safety_confirmation: bool = Field(False, description="Explicit safety confirmation required")
    timeout_seconds: float = Field(5.0, ge=0.1, le=30.0, description="Command timeout")
    command_metadata: dict[str, Any] | None = Field(None, description="Command-specific metadata")

    @classmethod
    def to_zod_schema(cls) -> dict[str, Any]:
        """Export Zod-compatible schema for frontend validation"""
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": [
                        "set",
                        "toggle",
                        "brightness_up",
                        "brightness_down",
                        "emergency_stop",
                        "clear_emergency_stop",
                    ],
                },
                "entity_ids": {"type": "array", "items": {"type": "string"}},
                "state": {"type": ["boolean", "null"]},
                "brightness": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                "parameters": {"type": ["object", "null"]},
                "safety_critical": {"type": "boolean", "default": False},
                "safety_confirmation": {"type": "boolean", "default": False},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 0.1,
                    "maximum": 30.0,
                    "default": 5.0,
                },
                "command_metadata": {"type": ["object", "null"]},
            },
            "required": ["command"],
            "additionalProperties": False,
        }


class OperationResultSchemaV2(BaseModel):
    """Operation result schema with safety tracking"""

    operation_id: str = Field(..., description="Unique operation identifier")
    entity_id: str = Field(..., description="Entity ID that was operated on")
    status: str = Field(
        ..., description="Operation status: success, failed, timeout, unauthorized, safety_abort"
    )
    acknowledged: bool = Field(
        False, description="Whether operation was acknowledged by physical system"
    )
    acknowledgment_time_ms: float | None = Field(None, description="Time to receive acknowledgment")
    error_message: str | None = Field(None, description="Error details if failed")
    error_code: str | None = Field(None, description="Machine-readable error code")
    execution_time_ms: float | None = Field(None, description="Operation execution time")
    safety_validation: dict[str, Any] = Field(
        default_factory=dict, description="Safety validation results"
    )

    @classmethod
    def to_zod_schema(cls) -> dict[str, Any]:
        """Export Zod-compatible schema for frontend validation"""
        return {
            "type": "object",
            "properties": {
                "operation_id": {"type": "string"},
                "entity_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["success", "failed", "timeout", "unauthorized", "safety_abort"],
                },
                "acknowledged": {"type": "boolean", "default": False},
                "acknowledgment_time_ms": {"type": ["number", "null"]},
                "error_message": {"type": ["string", "null"]},
                "error_code": {"type": ["string", "null"]},
                "execution_time_ms": {"type": ["number", "null"]},
                "safety_validation": {"type": "object"},
            },
            "required": ["operation_id", "entity_id", "status"],
            "additionalProperties": False,
        }


class BulkOperationSchemaV2(BaseModel):
    """Bulk operation request schema with safety controls"""

    operation_type: str = Field(..., description="Type of bulk operation")
    entity_ids: list[str] = Field(default_factory=list, description="List of entity IDs to control")
    entity_filters: dict[str, Any] = Field(
        default_factory=dict, description="Filters to select entities"
    )
    command: ControlCommandSchemaV2 = Field(..., description="Command to execute on all entities")
    ignore_errors: bool = Field(False, description="Continue on individual failures")
    safety_mode: str = Field(
        "strict", description="Safety mode: strict, permissive, emergency_stop"
    )
    safety_validation: dict[str, Any] = Field(
        default_factory=dict, description="Safety validation configuration"
    )
    max_concurrent: int = Field(10, ge=1, le=50, description="Maximum concurrent operations")

    @classmethod
    def to_zod_schema(cls) -> dict[str, Any]:
        """Export Zod-compatible schema for frontend validation"""
        return {
            "type": "object",
            "properties": {
                "operation_type": {"type": "string"},
                "entity_ids": {"type": "array", "items": {"type": "string"}},
                "entity_filters": {"type": "object"},
                "command": ControlCommandSchemaV2.to_zod_schema(),
                "ignore_errors": {"type": "boolean", "default": False},
                "safety_mode": {
                    "type": "string",
                    "enum": ["strict", "permissive", "emergency_stop"],
                    "default": "strict",
                },
                "safety_validation": {"type": "object"},
                "max_concurrent": {"type": "number", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["operation_type", "command"],
            "additionalProperties": False,
        }


class BulkOperationResultSchemaV2(BaseModel):
    """Bulk operation result schema with safety tracking"""

    operation_id: str = Field(..., description="Unique bulk operation identifier")
    total_count: int = Field(..., description="Total number of operations attempted")
    success_count: int = Field(..., description="Number of successful operations")
    failed_count: int = Field(..., description="Number of failed operations")
    timeout_count: int = Field(..., description="Number of timed out operations")
    safety_abort_count: int = Field(..., description="Number of operations aborted for safety")
    results: list[OperationResultSchemaV2] = Field(..., description="Per-entity operation results")
    total_execution_time_ms: float = Field(..., description="Total execution time")
    safety_summary: dict[str, Any] = Field(
        default_factory=dict, description="Safety operation summary"
    )

    @classmethod
    def to_zod_schema(cls) -> dict[str, Any]:
        """Export Zod-compatible schema for frontend validation"""
        return {
            "type": "object",
            "properties": {
                "operation_id": {"type": "string"},
                "total_count": {"type": "number"},
                "success_count": {"type": "number"},
                "failed_count": {"type": "number"},
                "timeout_count": {"type": "number"},
                "safety_abort_count": {"type": "number"},
                "results": {"type": "array", "items": OperationResultSchemaV2.to_zod_schema()},
                "total_execution_time_ms": {"type": "number"},
                "safety_summary": {"type": "object"},
            },
            "required": [
                "operation_id",
                "total_count",
                "success_count",
                "failed_count",
                "timeout_count",
                "safety_abort_count",
                "results",
                "total_execution_time_ms",
            ],
            "additionalProperties": False,
        }


class EntityCollectionSchemaV2(BaseModel):
    """Entity collection schema with metadata"""

    entities: list[EntitySchemaV2] = Field(..., description="Collection of entities")
    total_count: int = Field(..., description="Total number of entities available")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(100, description="Number of entities per page")
    filters_applied: dict[str, Any] = Field(default_factory=dict, description="Applied filters")

    @classmethod
    def to_zod_schema(cls) -> dict[str, Any]:
        """Export Zod-compatible schema for frontend validation"""
        return {
            "type": "object",
            "properties": {
                "entities": {"type": "array", "items": EntitySchemaV2.to_zod_schema()},
                "total_count": {"type": "number"},
                "page": {"type": "number", "default": 1},
                "page_size": {"type": "number", "default": 100},
                "filters_applied": {"type": "object"},
            },
            "required": ["entities", "total_count"],
            "additionalProperties": False,
        }
