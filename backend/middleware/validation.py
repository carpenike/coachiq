"""
Runtime Validation Middleware

Provides runtime validation for API requests and responses using Pydantic schemas.
Ensures type safety and data integrity for safety-critical vehicle control operations.

Note: "safety-critical" / "safety" naming in this file is historical and
refers to **API guardrail / command-validation** behavior, NOT vehicle safety.
The OEM Firefly MIRA panel owns the actual vehicle safety case. See
`docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`.
"""

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.schemas.entity_schemas import (
    BulkOperationSchemaV2,
    ControlCommandSchemaV2,
)

logger = logging.getLogger(__name__)


class RuntimeValidationMiddleware(BaseHTTPMiddleware):
    """
    Runtime validation middleware for safety-critical API operations.

    Validates requests and responses against Pydantic schemas to ensure
    type safety and prevent dangerous vehicle control operations.
    """

    # Endpoints that require strict validation
    CRITICAL_ENDPOINTS = {
        "/api/v2/entities/control": ControlCommandSchemaV2,
        "/api/v2/entities/bulk-control": BulkOperationSchemaV2,
        "/api/v2/entities/control-safe": ControlCommandSchemaV2,
    }

    def __init__(self, app, validate_requests: bool = True, validate_responses: bool = False):
        super().__init__(app)
        self.validate_requests = validate_requests
        self.validate_responses = validate_responses

    async def dispatch(self, request: Request, call_next):
        """Process request with optional validation"""
        start_time = time.time()

        # Skip validation for non-API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Skip validation for schema endpoints to avoid circular dependency
        if request.url.path.startswith("/api/schemas"):
            return await call_next(request)

        validation_errors = []

        # Validate request if enabled and endpoint is critical
        if self.validate_requests and request.method in ["POST", "PUT", "PATCH"]:
            request_validation = await self._validate_request(request)
            if request_validation["errors"]:
                return self._create_validation_error_response(
                    request_validation["errors"], "request"
                )

        # Process the request
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Request processing failed: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "validation_context": "request_processing",
                },
            )

        # Validate response if enabled
        if self.validate_responses and response.status_code < 400:
            response_validation = await self._validate_response(request, response)
            if response_validation["errors"]:
                logger.warning(f"Response validation failed: {response_validation['errors']}")
                # Don't return error for response validation - just log

        # Add validation metadata to response headers
        processing_time = (time.time() - start_time) * 1000
        response.headers["X-Validation-Time-Ms"] = str(round(processing_time, 2))
        response.headers["X-Validation-Enabled"] = "true"

        return response

    async def _validate_request(self, request: Request) -> dict[str, Any]:
        """Validate request body against appropriate schema"""
        validation_result = {"errors": [], "schema_used": None}

        # Check if this endpoint requires validation
        endpoint_path = request.url.path
        schema_class = None

        # Find matching schema for endpoint
        for pattern, schema in self.CRITICAL_ENDPOINTS.items():
            if endpoint_path.startswith(pattern.replace("/api/v2", "/api")):
                schema_class = schema
                validation_result["schema_used"] = schema.__name__
                break

        if not schema_class:
            return validation_result

        try:
            # Read and parse request body
            body = await request.body()
            if not body:
                validation_result["errors"].append("Request body is required")
                return validation_result

            try:
                request_data = json.loads(body)
            except json.JSONDecodeError as e:
                validation_result["errors"].append(f"Invalid JSON: {e!s}")
                return validation_result

            # Validate against schema
            try:
                schema_class(**request_data)
                logger.debug(f"Request validation passed for {endpoint_path}")
            except ValidationError as e:
                for error in e.errors():
                    field_path = " -> ".join(str(loc) for loc in error["loc"])
                    validation_result["errors"].append(
                        {
                            "field": field_path,
                            "message": error["msg"],
                            "value": error.get("input"),
                            "type": error["type"],
                        }
                    )
                logger.warning(
                    f"Request validation failed for {endpoint_path}: {validation_result['errors']}"
                )

        except Exception as e:
            logger.error(f"Request validation error: {e}")
            validation_result["errors"].append(f"Validation system error: {e!s}")

        return validation_result

    async def _validate_response(self, request: Request, response: Response) -> dict[str, Any]:
        """Validate response body against appropriate schema"""
        validation_result = {"errors": [], "schema_used": None}

        # Only validate JSON responses
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return validation_result

        try:
            # This is a simplified implementation
            # In production, you'd need to buffer the response body
            # and potentially re-create the response
            logger.debug(f"Response validation skipped for {request.url.path} (not implemented)")

        except Exception as e:
            logger.error(f"Response validation error: {e}")
            validation_result["errors"].append(f"Response validation error: {e!s}")

        return validation_result

    def _create_validation_error_response(self, errors: list, validation_type: str) -> JSONResponse:
        """Create standardized validation error response"""

        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation failed",
                "validation_type": validation_type,
                "details": errors,
                "safety_critical": True,
                "message": (
                    "Request validation failed for safety-critical operation. "
                    "Please ensure all required fields are provided with valid values."
                ),
            },
            headers={"X-Validation-Failed": "true", "X-Safety-Critical": "true"},
        )


class SchemaValidationMixin:
    """
    Mixin for route handlers that need explicit schema validation.

    Provides utility methods for validating data against specific schemas.
    """

    @staticmethod
    def validate_data(data: dict[str, Any], schema_class: type[BaseModel]) -> dict[str, Any]:
        """
        Validate data against a specific schema.

        Args:
            data: Data to validate
            schema_class: Pydantic schema class

        Returns:
            Dictionary with validation results

        Raises:
            ValidationError: If validation fails
        """
        try:
            validated_data = schema_class(**data)
            return {"valid": True, "data": validated_data.model_dump(), "errors": []}
        except ValidationError as e:
            errors = []
            for error in e.errors():
                field_path = " -> ".join(str(loc) for loc in error["loc"])
                errors.append(
                    {
                        "field": field_path,
                        "message": error["msg"],
                        "value": error.get("input"),
                        "type": error["type"],
                    }
                )

            return {"valid": False, "data": None, "errors": errors}

    @staticmethod
    def validate_control_command(data: dict[str, Any]) -> dict[str, Any]:
        """Validate control command data"""
        return SchemaValidationMixin.validate_data(data, ControlCommandSchemaV2)

    @staticmethod
    def validate_bulk_operation(data: dict[str, Any]) -> dict[str, Any]:
        """Validate bulk operation data"""
        return SchemaValidationMixin.validate_data(data, BulkOperationSchemaV2)


def create_validation_middleware(validate_requests: bool = True, validate_responses: bool = False):
    """
    Factory function to create validation middleware with configuration.

    Args:
        validate_requests: Enable request validation
        validate_responses: Enable response validation

    Returns:
        Configured validation middleware class
    """

    class ConfiguredValidationMiddleware(RuntimeValidationMiddleware):
        def __init__(self, app):
            super().__init__(app, validate_requests, validate_responses)

    return ConfiguredValidationMiddleware
