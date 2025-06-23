"""
Docs Service (Refactored with Repository Pattern)

Handles business logic for API documentation and OpenAPI schema generation, including:
- OpenAPI schema retrieval and formatting
- API endpoint documentation
- Schema validation and metadata
- Documentation content management

This service extracts documentation-related business logic from the API router layer.
"""

import logging
from typing import Any, Optional

from backend.core.performance import PerformanceMonitor
from backend.repositories.docs_repository import DocsRepository

logger = logging.getLogger(__name__)


class DocsService:
    """
    Service for managing API documentation and OpenAPI schemas.

    This service provides business logic for documentation operations while being
    agnostic to the presentation layer (HTTP, WebSocket, etc.).
    Refactored to use repository pattern with performance monitoring.
    """

    def __init__(
        self,
        docs_repository: DocsRepository,
        performance_monitor: PerformanceMonitor,
        app_instance: Any | None = None,
    ):
        """
        Initialize the docs service with repository.

        Args:
            docs_repository: Repository for documentation data
            performance_monitor: Performance monitoring instance
            app_instance: FastAPI app instance for schema generation
        """
        self._repository = docs_repository
        self._monitor = performance_monitor
        self.app_instance = app_instance

        # Apply performance monitoring
        self._apply_monitoring()

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        # Wrap methods with performance monitoring
        self.get_openapi_schema = self._monitor.monitor_service_method(
            "DocsService", "get_openapi_schema"
        )(self.get_openapi_schema)

        self.get_api_info = self._monitor.monitor_service_method("DocsService", "get_api_info")(
            self.get_api_info
        )

        self.get_endpoint_list = self._monitor.monitor_service_method(
            "DocsService", "get_endpoint_list"
        )(self.get_endpoint_list)

        self.get_schema_components = self._monitor.monitor_service_method(
            "DocsService", "get_schema_components"
        )(self.get_schema_components)

        self.validate_schema = self._monitor.monitor_service_method(
            "DocsService", "validate_schema"
        )(self.validate_schema)

    async def get_openapi_schema(self) -> dict[str, Any]:
        """
        Get the complete OpenAPI schema for the API.

        Returns:
            Dictionary containing the full OpenAPI schema

        Raises:
            RuntimeError: If app instance is not available or schema generation fails
        """
        # Try to get from cache first
        cached_schema = await self._repository.get_cached_schema()
        if cached_schema:
            logger.debug("Using cached OpenAPI schema")
            return cached_schema

        if not self.app_instance:
            msg = "FastAPI app instance not available for schema generation"
            raise RuntimeError(msg)

        try:
            # Get the OpenAPI schema from FastAPI
            schema = self.app_instance.openapi()

            # Handle case where openapi() returns None
            if schema is None:
                msg = "OpenAPI schema generation returned None"
                raise RuntimeError(msg)

            # Add custom metadata if needed
            if "info" in schema:
                schema["info"]["x-generated-by"] = "coachiq-backend"
                schema["info"]["x-schema-version"] = "1.0"

            # Cache the schema
            await self._repository.cache_schema(schema)

            return schema

        except Exception as e:
            logger.error(f"Failed to generate OpenAPI schema: {e}")
            msg = f"Failed to generate OpenAPI schema: {e}"
            raise RuntimeError(msg) from e

    async def get_api_info(self) -> dict[str, Any]:
        """
        Get basic API information and metadata.

        Returns:
            Dictionary containing API metadata
        """
        try:
            schema = await self.get_openapi_schema()
            info = schema.get("info", {})

            # Count endpoints by method
            paths = schema.get("paths", {})
            endpoint_count = {}
            total_endpoints = 0

            for methods in paths.values():
                for method in methods:
                    if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        endpoint_count[method.upper()] = endpoint_count.get(method.upper(), 0) + 1
                        total_endpoints += 1

            return {
                "title": info.get("title", "coachiq"),
                "description": info.get("description", ""),
                "version": info.get("version", "unknown"),
                "openapi_version": schema.get("openapi", "unknown"),
                "endpoints": {
                    "total": total_endpoints,
                    "by_method": endpoint_count,
                },
                "has_components": bool(schema.get("components")),
                "has_security": bool(schema.get("security")),
            }

        except Exception as e:
            logger.error(f"Failed to get API info: {e}")
            return {
                "title": "coachiq",
                "description": "API information unavailable",
                "version": "unknown",
                "error": str(e),
            }

    async def get_endpoint_list(self) -> list[dict[str, Any]]:
        """
        Get a list of all available API endpoints with their details.

        Returns:
            List of endpoint information dictionaries
        """
        try:
            schema = await self.get_openapi_schema()
            paths = schema.get("paths", {})

            endpoints = []

            for path, methods in paths.items():
                for method, details in methods.items():
                    if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        endpoint_info = {
                            "path": path,
                            "method": method.upper(),
                            "summary": details.get("summary", ""),
                            "description": details.get("description", ""),
                            "tags": details.get("tags", []),
                            "operation_id": details.get("operationId", ""),
                            "deprecated": details.get("deprecated", False),
                            "has_parameters": bool(details.get("parameters")),
                            "has_request_body": bool(details.get("requestBody")),
                            "response_codes": list(details.get("responses", {}).keys()),
                        }
                        endpoints.append(endpoint_info)

            # Sort by path then method
            endpoints.sort(key=lambda x: (x["path"], x["method"]))

            return endpoints

        except Exception as e:
            logger.error(f"Failed to get endpoint list: {e}")
            return []

    async def get_schema_components(self) -> dict[str, Any]:
        """
        Get information about schema components (models, parameters, etc.).

        Returns:
            Dictionary containing component information
        """
        try:
            schema = await self.get_openapi_schema()
            components = schema.get("components", {})

            component_info = {
                "schemas": {},
                "parameters": {},
                "responses": {},
                "security_schemes": {},
                "summary": {
                    "total_schemas": 0,
                    "total_parameters": 0,
                    "total_responses": 0,
                    "total_security_schemes": 0,
                },
            }

            # Analyze schemas (data models)
            schemas = components.get("schemas", {})
            for schema_name, schema_def in schemas.items():
                component_info["schemas"][schema_name] = {
                    "type": schema_def.get("type", "unknown"),
                    "title": schema_def.get("title", schema_name),
                    "description": schema_def.get("description", ""),
                    "properties": list(schema_def.get("properties", {}).keys()),
                    "required": schema_def.get("required", []),
                }
            component_info["summary"]["total_schemas"] = len(schemas)

            # Analyze parameters
            parameters = components.get("parameters", {})
            for param_name, param_def in parameters.items():
                component_info["parameters"][param_name] = {
                    "name": param_def.get("name", param_name),
                    "in": param_def.get("in", "unknown"),
                    "required": param_def.get("required", False),
                    "schema_type": param_def.get("schema", {}).get("type", "unknown"),
                    "description": param_def.get("description", ""),
                }
            component_info["summary"]["total_parameters"] = len(parameters)

            # Analyze responses
            responses = components.get("responses", {})
            component_info["summary"]["total_responses"] = len(responses)

            # Analyze security schemes
            security_schemes = components.get("securitySchemes", {})
            component_info["summary"]["total_security_schemes"] = len(security_schemes)

            return component_info

        except Exception as e:
            logger.error(f"Failed to get schema components: {e}")
            return {
                "error": str(e),
                "summary": {
                    "total_schemas": 0,
                    "total_parameters": 0,
                    "total_responses": 0,
                    "total_security_schemes": 0,
                },
            }

    async def validate_schema(self) -> dict[str, Any]:
        """
        Validate the OpenAPI schema for correctness and completeness.

        Returns:
            Dictionary containing validation results
        """
        try:
            schema = await self.get_openapi_schema()

            validation_results = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "info": {},
            }

            # Check required OpenAPI fields
            required_fields = ["openapi", "info", "paths"]
            for field in required_fields:
                if field not in schema:
                    validation_results["errors"].append(f"Missing required field: {field}")
                    validation_results["valid"] = False

            # Check info section
            info = schema.get("info", {})
            if not info.get("title"):
                validation_results["warnings"].append("API title not specified")
            if not info.get("version"):
                validation_results["warnings"].append("API version not specified")

            # Check paths
            paths = schema.get("paths", {})
            if not paths:
                validation_results["warnings"].append("No API paths defined")
            else:
                # Check for common issues in paths
                for path, methods in paths.items():
                    for method, details in methods.items():
                        if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                            if not details.get("summary"):
                                validation_results["warnings"].append(
                                    f"Endpoint {method.upper()} {path} missing summary"
                                )
                            if not details.get("responses"):
                                validation_results["errors"].append(
                                    f"Endpoint {method.upper()} {path} missing responses"
                                )
                                validation_results["valid"] = False

            validation_results["info"] = {
                "openapi_version": schema.get("openapi"),
                "total_paths": len(paths),
                "has_components": bool(schema.get("components")),
                "has_security": bool(schema.get("security")),
            }

            return validation_results

        except Exception as e:
            logger.error(f"Failed to validate schema: {e}")
            return {
                "valid": False,
                "errors": [f"Validation failed: {e}"],
                "warnings": [],
                "info": {},
            }

    async def store_endpoint_metadata(
        self, endpoint_path: str, method: str, metadata: dict[str, Any]
    ) -> bool:
        """
        Store additional metadata for an endpoint.

        Args:
            endpoint_path: API endpoint path
            method: HTTP method
            metadata: Additional metadata to store

        Returns:
            True if storage successful
        """
        return await self._repository.store_endpoint_metadata(endpoint_path, method, metadata)

    async def get_endpoint_metadata(self, endpoint_path: str, method: str) -> dict[str, Any] | None:
        """
        Get stored metadata for an endpoint.

        Args:
            endpoint_path: API endpoint path
            method: HTTP method

        Returns:
            Metadata if available, None otherwise
        """
        return await self._repository.get_endpoint_metadata(endpoint_path, method)

    async def clear_cache(self) -> bool:
        """
        Clear all cached documentation data.

        Returns:
            True if cache cleared successfully
        """
        return await self._repository.clear_cache()

    def get_cache_info(self) -> dict[str, Any]:
        """
        Get information about current cache state.

        Returns:
            Cache information
        """
        return self._repository.get_cache_info()
