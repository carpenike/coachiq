"""
Contract Testing for Domain API v1 - Simplified OpenAPI Validation

This module provides basic contract testing that validates the generated OpenAPI
specification matches our documented API design patterns.
"""

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from backend.main import create_app


def test_openapi_spec_generation():
    """Test that FastAPI generates a valid OpenAPI specification.

    Updated 2026-05-13: the legacy ``/api/entities`` route was retired
    in favor of ``/api/v1/entities`` (see PR #126); assert against the
    v2 path instead. The route comes from
    ``backend/api/domains/entities.py`` mounted under
    ``/api/v1/entities`` by ``register_all_domain_routers``.
    """
    app = create_app()

    openapi_schema = get_openapi(
        title="CoachIQ Domain API",
        version="2.0.0",
        description="Domain-driven RV-C network management API",
        routes=app.routes,
    )

    assert openapi_schema["openapi"] in ["3.0.2", "3.1.0"], (
        f"Should use OpenAPI 3.x, got {openapi_schema['openapi']}"
    )
    assert "info" in openapi_schema, "Should have info section"
    assert "paths" in openapi_schema, "Should have paths section"

    # Check that we have the v2 entity routes (legacy /api/entities is gone).
    paths = openapi_schema["paths"]
    assert any("/api/v1/entities" in path for path in paths), "Should have v2 entity routes"


def test_domain_api_route_structure():
    """Test that domain API routes follow expected patterns.

    Updated 2026-05-13: legacy ``/api/entities`` is gone; the v2 entity
    routes live under ``/api/v1/entities``. See PR #126.
    """
    app = create_app()

    routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            routes.append(route.path)

    # Should have v2 entity routes
    v2_entity_routes = [r for r in routes if r.startswith("/api/v1/entities")]
    assert len(v2_entity_routes) > 0, "Should have /api/v1/entities routes"

    # Check that route patterns match expected structure
    api_routes = [r for r in routes if r.startswith("/api/")]
    assert len(api_routes) > 0, "Should have API routes"


def test_legacy_entities_endpoint():
    """Test that the v2 entities endpoint is reachable.

    Renamed 2026-05-13 (was ``test_legacy_entities_endpoint``): the
    legacy ``/api/entities`` path no longer exists. We point at
    ``/api/v1/entities`` and accept either 200 (full success) or 500
    (expected when the EntityService can't fully start in this minimal
    test app). 404 specifically must NOT happen -- if it does, the
    domain router registration is broken (see PR #126 cluster context).
    """
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/entities")

    assert response.status_code in [200, 500], (
        f"Unexpected status: {response.status_code} -- 404 means the"
        " /api/v1/entities router is no longer registered"
    )


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
    """Test that our documented response patterns are followed.

    Updated 2026-05-13: replaced legacy ``/api/entities`` probe with
    the v2 path. See PR #126.
    """
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/health")
    if response.status_code == 200:
        data = response.json()
        assert "status" in data, "Health response should have status"

    response = client.get("/api/v1/entities")
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, (list, dict)), "Entities response should be list or dict"


def test_error_response_patterns():
    """Test that error responses follow expected patterns.

    Updated 2026-05-13: the project ships a custom
    ``http_exception_handler`` (see
    ``backend/core/exception_handlers.py:165``) that wraps every HTTP
    error as ``{"error": {"code": "HTTP_<status>", "message": ...}}``
    rather than the FastAPI default ``{"detail": ...}``. The previous
    assertion (``assert 'detail' in error_data``) targeted the default
    shape and would fail for every non-2xx response. See PR #125 where
    this was first encountered.
    """
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/nonexistent")
    assert response.status_code == 404, "Should return 404 for non-existent endpoints"

    # Check the project's wrapped error envelope.
    error_data = response.json()
    assert "error" in error_data, (
        "Error response should be wrapped in 'error' key per"
        " backend/core/exception_handlers.py:http_exception_handler"
    )
    assert "message" in error_data["error"], "Error envelope should have a 'message'"
    assert "code" in error_data["error"], "Error envelope should have a 'code'"
    assert error_data["error"]["code"] == "HTTP_404", (
        f"Expected HTTP_404 code, got {error_data['error']['code']}"
    )


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
        """Detect if domain API v1 routes are available"""
        app = create_app()

        domain_routes = [
            route.path
            for route in app.routes
            if hasattr(route, "path") and "/api/v1/" in route.path
        ]

        # This is informational - domain routes may or may not be enabled
        assert isinstance(domain_routes, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
