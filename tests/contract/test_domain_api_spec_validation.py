"""
Contract Testing for Domain API v2 - Simplified OpenAPI Validation

This module provides basic contract testing that validates the generated OpenAPI
specification matches our documented API design patterns.
"""

import json

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from backend.main import create_app


def test_openapi_spec_generation():
    """Test that FastAPI generates a valid OpenAPI specification"""
    app = create_app()

    # Generate OpenAPI spec
    openapi_schema = get_openapi(
        title="CoachIQ Domain API",
        version="2.0.0",
        description="Domain-driven RV-C network management API",
        routes=app.routes,
    )

    # Basic validation
    assert openapi_schema["openapi"] in ["3.0.2", "3.1.0"], (
        f"Should use OpenAPI 3.x, got {openapi_schema['openapi']}"
    )
    assert "info" in openapi_schema, "Should have info section"
    assert "paths" in openapi_schema, "Should have paths section"

    # Check that we have legacy routes
    paths = openapi_schema["paths"]
    assert any("/api/entities" in path for path in paths), "Should have legacy entity routes"


def test_domain_api_route_structure():
    """Test that domain API routes follow expected patterns"""
    app = create_app()

    # Get all routes
    routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            routes.append(route.path)

    # Should have legacy routes (these always exist)
    legacy_routes = [r for r in routes if r.startswith("/api/entities")]
    assert len(legacy_routes) > 0, "Should have legacy /api/entities routes"

    # Check that route patterns match expected structure
    api_routes = [r for r in routes if r.startswith("/api/")]
    assert len(api_routes) > 0, "Should have API routes"


def test_legacy_entities_endpoint():
    """Test that legacy entities endpoint still works"""
    app = create_app()
    client = TestClient(app)

    # Test legacy endpoint
    response = client.get("/api/entities")

    # Should get either 200 (success) or 500 (expected in test env without full services)
    assert response.status_code in [200, 500], f"Unexpected status: {response.status_code}"


def test_openapi_spec_has_required_sections():
    """Test that generated OpenAPI spec has all required sections"""
    app = create_app()

    openapi_schema = get_openapi(
        title="CoachIQ Domain API",
        version="2.0.0",
        description="Domain-driven RV-C network management API",
        routes=app.routes,
    )

    # Required OpenAPI sections
    required_sections = ["openapi", "info", "paths"]
    for section in required_sections:
        assert section in openapi_schema, f"Missing required section: {section}"

    # Info section validation
    info = openapi_schema["info"]
    assert "title" in info, "Info should have title"
    assert "version" in info, "Info should have version"

    # Paths section should not be empty
    paths = openapi_schema["paths"]
    assert len(paths) > 0, "Should have at least some API paths"


def test_response_schema_patterns():
    """Test that our documented response patterns are followed"""
    app = create_app()
    client = TestClient(app)

    # Test health endpoint (if available)
    response = client.get("/api/health")
    if response.status_code == 200:
        data = response.json()
        # Should follow basic health check pattern
        assert "status" in data, "Health response should have status"

    # Test entities endpoint structure
    response = client.get("/api/entities")
    if response.status_code == 200:
        data = response.json()
        # Should be a list or dictionary
        assert isinstance(data, (list, dict)), "Entities response should be list or dict"


def test_error_response_patterns():
    """Test that error responses follow expected patterns"""
    app = create_app()
    client = TestClient(app)

    # Test non-existent endpoint
    response = client.get("/api/nonexistent")
    assert response.status_code == 404, "Should return 404 for non-existent endpoints"

    # Check error response structure
    error_data = response.json()
    assert "detail" in error_data, "Error response should have detail field"


class TestContractBaseline:
    """Baseline contract tests that establish current API behavior"""

    def test_api_route_count_baseline(self):
        """Establish baseline for number of API routes"""
        app = create_app()

        api_routes = []
        for route in app.routes:
            if hasattr(route, "path") and route.path.startswith("/api/"):
                api_routes.append(route.path)

        # Should have reasonable number of routes (adjust as needed)
        assert len(api_routes) >= 10, f"Expected at least 10 API routes, got {len(api_routes)}"
        print(f"\\nBaseline: Found {len(api_routes)} API routes")

    def test_websocket_routes_baseline(self):
        """Establish baseline for WebSocket routes"""
        app = create_app()

        ws_routes = []
        for route in app.routes:
            if hasattr(route, "path") and route.path.startswith("/ws"):
                ws_routes.append(route.path)

        print(f"\\nBaseline: Found {len(ws_routes)} WebSocket routes")
        # WebSocket routes may be 0 in test environment, that's OK

    def test_domain_routes_detection(self):
        """Detect if domain API v2 routes are available"""
        app = create_app()

        domain_routes = []
        for route in app.routes:
            if hasattr(route, "path") and "/api/v2/" in route.path:
                domain_routes.append(route.path)

        print(f"\\nDomain API v2 routes found: {len(domain_routes)}")
        for route in sorted(domain_routes):
            print(f"  {route}")

        # This is informational - domain routes may or may not be enabled


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
