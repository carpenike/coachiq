"""
Zod Schema Exporter

Provides centralized schema export functionality for frontend type safety.
Exports Pydantic schemas in Zod-compatible JSON format for runtime validation.
"""

from typing import Any

from pydantic import BaseModel

from .entity_schemas import (
    BulkOperationResultSchemaV2,
    BulkOperationSchemaV2,
    ControlCommandSchemaV2,
    EntityCollectionSchemaV2,
    EntitySchemaV2,
    OperationResultSchemaV2,
)


class ZodSchemaExporter:
    """
    Exports Pydantic schemas in Zod-compatible format for frontend validation.

    Provides centralized schema management and version tracking for Domain API v2.
    """

    # Schema registry with version tracking
    SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
        "Entity": EntitySchemaV2,
        "ControlCommand": ControlCommandSchemaV2,
        "OperationResult": OperationResultSchemaV2,
        "BulkOperation": BulkOperationSchemaV2,
        "BulkOperationResult": BulkOperationResultSchemaV2,
        "EntityCollection": EntityCollectionSchemaV2,
    }

    SCHEMA_VERSION = "2.0.0"

    @classmethod
    def export_all_schemas(cls) -> dict[str, Any]:
        """Export all registered schemas in Zod-compatible format"""
        schemas = {}

        for name, schema_class in cls.SCHEMA_REGISTRY.items():
            try:
                if hasattr(schema_class, "to_zod_schema") and callable(schema_class.to_zod_schema):
                    schemas[name] = schema_class.to_zod_schema()  # type: ignore
                else:
                    # Fallback to basic Pydantic schema conversion
                    schemas[name] = cls._convert_pydantic_to_zod(schema_class)
            except Exception as e:
                # Log error but continue with other schemas
                import logging

                logger = logging.getLogger(__name__)
                logger.error(f"Failed to export schema {name}: {e}")

        return {
            "version": cls.SCHEMA_VERSION,
            "schemas": schemas,
            "metadata": {
                "generated_at": cls._get_iso_timestamp(),
                "domain_api_version": "v2",
                "safety_critical": True,
                "validation_required": True,
            },
        }

    @classmethod
    def export_schema(cls, schema_name: str) -> dict[str, Any]:
        """Export a specific schema by name"""
        if schema_name not in cls.SCHEMA_REGISTRY:
            raise ValueError(f"Schema '{schema_name}' not found in registry")

        schema_class = cls.SCHEMA_REGISTRY[schema_name]

        if hasattr(schema_class, "to_zod_schema") and callable(schema_class.to_zod_schema):
            return schema_class.to_zod_schema()  # type: ignore
        return cls._convert_pydantic_to_zod(schema_class)

    @classmethod
    def get_schema_list(cls) -> list[str]:
        """Get list of available schema names"""
        return list(cls.SCHEMA_REGISTRY.keys())

    @classmethod
    def get_schema_metadata(cls) -> dict[str, Any]:
        """Get schema metadata information"""
        return {
            "version": cls.SCHEMA_VERSION,
            "domain_api_version": "v2",
            "available_schemas": cls.get_schema_list(),
            "safety_critical": True,
            "validation_required": True,
            "generated_at": cls._get_iso_timestamp(),
        }

    @classmethod
    def _convert_pydantic_to_zod(cls, schema_class: type[BaseModel]) -> dict[str, Any]:
        """
        Fallback conversion from Pydantic schema to Zod format.
        Used when schema doesn't have custom to_zod_schema method.
        """
        # This is a simplified conversion - in production you might want
        # to use a more sophisticated conversion library
        try:
            json_schema = schema_class.model_json_schema()

            # Convert JSON Schema to Zod-compatible format
            return {
                "type": json_schema.get("type", "object"),
                "properties": json_schema.get("properties", {}),
                "required": json_schema.get("required", []),
                "additionalProperties": json_schema.get("additionalProperties", False),
            }
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to convert Pydantic schema {schema_class.__name__}: {e}")
            return {"type": "object", "properties": {}}

    @classmethod
    def _get_iso_timestamp(cls) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime

        return datetime.utcnow().isoformat() + "Z"

    @classmethod
    def validate_schema_integrity(cls) -> dict[str, Any]:
        """
        Validate that all schemas can be properly exported.
        Returns validation report.
        """
        validation_report = {
            "valid_schemas": [],
            "invalid_schemas": [],
            "total_schemas": len(cls.SCHEMA_REGISTRY),
            "validation_passed": True,
        }

        for name, schema_class in cls.SCHEMA_REGISTRY.items():
            try:
                # Attempt to export the schema
                if hasattr(schema_class, "to_zod_schema") and callable(schema_class.to_zod_schema):
                    schema_class.to_zod_schema()  # type: ignore
                else:
                    cls._convert_pydantic_to_zod(schema_class)

                validation_report["valid_schemas"].append(name)
            except Exception as e:
                validation_report["invalid_schemas"].append({"name": name, "error": str(e)})
                validation_report["validation_passed"] = False

        return validation_report
