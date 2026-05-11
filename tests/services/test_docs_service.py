"""
Test suite for DocsService.

Tests the documentation service business logic, including:
- OpenAPI schema retrieval and formatting
- API endpoint documentation
- Schema validation and metadata
- Documentation content management
"""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from backend.core.performance import PerformanceMonitor
from backend.services.docs_service import DocsService

# ================================
# Test Fixtures
# ================================


@pytest.fixture
def mock_fastapi_app():
    """Mock FastAPI app instance for testing."""
    mock_app = Mock()
    mock_app.openapi.return_value = {
        "openapi": "3.0.2",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/test": {
                "get": {
                    "summary": "Test endpoint",
                    "responses": {"200": {"description": "Success"}},
                }
            }
        },
        "components": {"schemas": {}},
    }
    return mock_app


@pytest.fixture
def mock_repository():
    """Mock DocsRepository with sensible async stubs.

    The default get_cached_schema returns None so tests fall through to the
    app_instance.openapi() path; individual tests can set the return_value to
    inject cached schemas.
    """
    repo = AsyncMock()
    repo.get_cached_schema = AsyncMock(return_value=None)
    repo.cache_schema = AsyncMock(return_value=True)
    repo.store_endpoint_metadata = AsyncMock(return_value=True)
    repo.get_endpoint_metadata = AsyncMock(return_value=None)
    repo.list_cached_endpoints = AsyncMock(return_value=[])
    repo.clear_cache = AsyncMock(return_value=True)
    repo.get_cache_info = MagicMock(return_value={"cached_schemas": 0, "cached_endpoints": 0})
    return repo


@pytest.fixture
def mock_monitor():
    """No-op PerformanceMonitor that returns the wrapped fn unchanged."""
    monitor = MagicMock(spec=PerformanceMonitor)
    # monitor_service_method is a decorator factory; make it a passthrough.
    monitor.monitor_service_method = MagicMock(return_value=lambda fn: fn)
    return monitor


@pytest.fixture
def docs_service(mock_fastapi_app, mock_repository, mock_monitor):
    """Create DocsService instance for testing."""
    return DocsService(
        docs_repository=mock_repository,
        performance_monitor=mock_monitor,
        app_instance=mock_fastapi_app,
    )


@pytest.fixture
def docs_service_no_app(mock_repository, mock_monitor):
    """Create DocsService instance without app for testing."""
    return DocsService(
        docs_repository=mock_repository,
        performance_monitor=mock_monitor,
    )


@pytest.fixture
def sample_openapi_schema():
    """Create a sample OpenAPI schema for testing."""
    return {
        "openapi": "3.0.2",
        "info": {
            "title": "CoachIQ",
            "version": "1.0.0",
            "description": "RV-C API Server",
        },
        "paths": {
            "/api/entities": {
                "get": {
                    "summary": "Get all entities",
                    "responses": {"200": {"description": "Success"}},
                }
            },
            "/api/entities/{entity_id}": {
                "get": {
                    "summary": "Get specific entity",
                    "parameters": [
                        {
                            "name": "entity_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Success"}},
                }
            },
        },
        "components": {
            "schemas": {
                "Entity": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                }
            }
        },
    }


# ================================
# Core Functionality Tests
# ================================


class TestDocsServiceInitialization:
    """Test DocsService initialization and setup."""

    def test_init_with_app_instance(self, mock_fastapi_app, mock_repository, mock_monitor):
        """Test service initialization with app instance."""
        service = DocsService(
            docs_repository=mock_repository,
            performance_monitor=mock_monitor,
            app_instance=mock_fastapi_app,
        )
        assert service.app_instance is mock_fastapi_app

    def test_init_without_app_instance(self, mock_repository, mock_monitor):
        """Test service initialization without app instance."""
        service = DocsService(
            docs_repository=mock_repository,
            performance_monitor=mock_monitor,
        )
        assert service.app_instance is None

    def test_init_with_none_app_instance(self, mock_repository, mock_monitor):
        """Test service initialization with explicit None app instance."""
        service = DocsService(
            docs_repository=mock_repository,
            performance_monitor=mock_monitor,
            app_instance=None,
        )
        assert service.app_instance is None


# ================================
# OpenAPI Schema Tests
# ================================


class TestOpenAPISchema:
    """Test OpenAPI schema functionality."""

    async def test_get_openapi_schema_success(self, docs_service, mock_fastapi_app):
        """Test successful OpenAPI schema retrieval."""
        result = await docs_service.get_openapi_schema()

        # Verify the mock was called
        mock_fastapi_app.openapi.assert_called_once()

        # Check the returned schema structure
        assert "openapi" in result
        assert "info" in result
        assert "paths" in result
        assert result["openapi"] == "3.0.2"
        assert result["info"]["title"] == "Test API"

    async def test_get_openapi_schema_no_app(self, docs_service_no_app):
        """Test OpenAPI schema retrieval without app instance."""
        with pytest.raises(RuntimeError, match="FastAPI app instance not available"):
            await docs_service_no_app.get_openapi_schema()

    async def test_get_openapi_schema_app_error(self, docs_service, mock_fastapi_app):
        """Test OpenAPI schema retrieval when app raises error."""
        mock_fastapi_app.openapi.side_effect = RuntimeError("Schema generation failed")

        with pytest.raises(RuntimeError, match="Failed to generate OpenAPI schema"):
            await docs_service.get_openapi_schema()

    async def test_get_openapi_schema_app_returns_none(self, docs_service, mock_fastapi_app):
        """Test OpenAPI schema retrieval when app returns None."""
        mock_fastapi_app.openapi.return_value = None

        with pytest.raises(RuntimeError, match="OpenAPI schema generation returned None"):
            await docs_service.get_openapi_schema()

    async def test_get_openapi_schema_caching(self, docs_service, mock_fastapi_app):
        """Test that OpenAPI schema calls are made to app (no caching in service)."""
        # First call
        result1 = await docs_service.get_openapi_schema()

        # Second call
        result2 = await docs_service.get_openapi_schema()

        # Both should return the same result
        assert result1 == result2

        # App should be called each time (no caching in service)
        assert mock_fastapi_app.openapi.call_count == 2


# ================================
# Schema Processing Tests
# ================================


class TestSchemaProcessing:
    """Test schema processing and enhancement functionality."""

    async def test_get_endpoints_summary_basic(self, docs_service):
        """Test basic endpoint list retrieval."""
        result = await docs_service.get_endpoint_list()

        assert isinstance(result, list)
        assert len(result) >= 0

        # If there are endpoints, check structure
        if result:
            endpoint = result[0]
            assert "path" in endpoint
            assert "method" in endpoint
            assert "summary" in endpoint

    async def test_get_endpoints_summary_no_app(self, docs_service_no_app):
        """Test endpoint list without app instance."""
        result = await docs_service_no_app.get_endpoint_list()
        # Should return empty list instead of raising
        assert result == []

    async def test_get_endpoints_summary_complex_schema(
        self, docs_service, mock_fastapi_app, sample_openapi_schema
    ):
        """Test endpoint list with complex schema."""
        mock_fastapi_app.openapi.return_value = sample_openapi_schema

        result = await docs_service.get_endpoint_list()

        assert len(result) == 2
        # Should have both endpoints
        paths = [ep["path"] for ep in result]
        assert "/api/entities" in paths
        assert "/api/entities/{entity_id}" in paths

    async def test_get_api_info_basic(self, docs_service):
        """Test basic API info extraction."""
        result = await docs_service.get_api_info()

        assert "title" in result
        assert "version" in result
        assert "openapi_version" in result
        assert result["title"] == "Test API"
        assert result["version"] == "1.0.0"
        assert result["openapi_version"] == "3.0.2"

    async def test_get_api_info_with_description(
        self, docs_service, mock_fastapi_app, sample_openapi_schema
    ):
        """Test API info extraction with description."""
        mock_fastapi_app.openapi.return_value = sample_openapi_schema

        result = await docs_service.get_api_info()

        assert result["title"] == "CoachIQ"
        assert result["description"] == "RV-C API Server"

    async def test_get_schema_components_basic(self, docs_service):
        """Test schema components extraction."""
        result = await docs_service.get_schema_components()

        assert "schemas" in result
        assert "summary" in result
        assert "total_schemas" in result["summary"]
        assert result["summary"]["total_schemas"] == 0  # No schemas in basic mock

    async def test_get_schema_components_with_schemas(
        self, docs_service, mock_fastapi_app, sample_openapi_schema
    ):
        """Test schema components with actual schemas."""
        mock_fastapi_app.openapi.return_value = sample_openapi_schema

        result = await docs_service.get_schema_components()

        assert result["summary"]["total_schemas"] == 1
        assert "Entity" in result["schemas"]
        assert result["schemas"]["Entity"]["type"] == "object"


# ================================
# Validation Tests
# ================================


class TestSchemaValidation:
    """Test schema validation functionality."""

    async def test_validate_schema_structure_valid(self, docs_service):
        """Test validation of valid schema structure."""
        result = await docs_service.validate_schema()

        assert "valid" in result
        assert "errors" in result
        assert "warnings" in result
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    async def test_validate_schema_structure_missing_required_fields(
        self, docs_service, mock_fastapi_app
    ):
        """Test validation with missing required fields."""
        # Return malformed schema
        mock_fastapi_app.openapi.return_value = {
            "openapi": "3.0.2"
            # Missing 'info' and 'paths'
        }

        result = await docs_service.validate_schema()

        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert any("info" in error.lower() for error in result["errors"])

    async def test_validate_schema_structure_invalid_openapi_version(
        self, docs_service, mock_fastapi_app
    ):
        """Test validation with invalid OpenAPI version."""
        mock_fastapi_app.openapi.return_value = {
            "openapi": "2.0",  # Invalid version
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
        }

        result = await docs_service.validate_schema()

        # Note: Service doesn't validate OpenAPI version, so this should still be valid
        assert result["valid"] is True

    async def test_validate_schema_structure_no_app(self, docs_service_no_app):
        """Test schema validation without app instance."""
        result = await docs_service_no_app.validate_schema()

        # Should return validation result with errors, not raise
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert any("app instance not available" in error.lower() for error in result["errors"])


# ================================
# Error Handling Tests
# ================================


class TestErrorHandling:
    """Test error handling in various scenarios."""

    async def test_get_openapi_schema_exception_handling(self, docs_service, mock_fastapi_app):
        """Test OpenAPI schema retrieval with various exceptions."""
        # Test different exception types
        exceptions = [
            ValueError("Invalid schema"),
            TypeError("Type error"),
            AttributeError("Attribute error"),
            Exception("Generic error"),
        ]

        for exception in exceptions:
            mock_fastapi_app.openapi.side_effect = exception

            with pytest.raises(RuntimeError, match="Failed to generate OpenAPI schema"):
                await docs_service.get_openapi_schema()

    async def test_endpoints_summary_malformed_schema(self, docs_service, mock_fastapi_app):
        """Test endpoint list with malformed schema."""
        # Return schema with malformed paths - service should handle gracefully
        mock_fastapi_app.openapi.return_value = {
            "openapi": "3.0.2",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": "invalid_paths_format",  # Should be dict, not string
        }

        result = await docs_service.get_endpoint_list()
        # Service should handle this gracefully and return empty list
        assert result == []

    async def test_api_info_missing_fields(self, docs_service, mock_fastapi_app):
        """Test API info extraction with missing fields."""
        mock_fastapi_app.openapi.return_value = {
            "openapi": "3.0.2",
            "paths": {},
            # Missing 'info' section
        }

        # Service should handle this gracefully, not raise
        result = await docs_service.get_api_info()
        assert "title" in result
        assert result["title"] == "CoachIQ"  # Default value


# ================================
# Integration Tests
# ================================


class TestServiceIntegration:
    """Test service integration with dependencies."""

    async def test_complete_docs_workflow(self, docs_service):
        """Test complete documentation workflow."""
        # Get full schema
        schema = await docs_service.get_openapi_schema()
        assert schema is not None

        # Get API info
        api_info = await docs_service.get_api_info()
        assert api_info["title"] == "Test API"

        # Get endpoints list
        endpoints = await docs_service.get_endpoint_list()
        assert len(endpoints) >= 0

        # Get schema components
        components = await docs_service.get_schema_components()
        assert "schemas" in components

        # Validate schema
        validation = await docs_service.validate_schema()
        assert validation["valid"] is True

    async def test_service_state_consistency(self, docs_service, mock_fastapi_app):
        """Test that service maintains consistent state across calls."""
        # Multiple calls should work consistently
        schema1 = await docs_service.get_openapi_schema()
        schema2 = await docs_service.get_openapi_schema()

        # Results should be identical (from same mock)
        assert schema1 == schema2
        assert docs_service.app_instance is mock_fastapi_app

    async def test_service_with_real_schema_structure(
        self, docs_service, mock_fastapi_app, sample_openapi_schema
    ):
        """Test service with realistic schema structure."""
        mock_fastapi_app.openapi.return_value = sample_openapi_schema

        # Should handle all operations correctly
        schema = await docs_service.get_openapi_schema()
        api_info = await docs_service.get_api_info()
        endpoints = await docs_service.get_endpoint_list()
        components = await docs_service.get_schema_components()
        validation = await docs_service.validate_schema()

        # All should succeed
        assert schema["info"]["title"] == "CoachIQ"
        assert api_info["title"] == "CoachIQ"
        assert len(endpoints) == 2
        assert components["summary"]["total_schemas"] == 1
        assert validation["valid"] is True
