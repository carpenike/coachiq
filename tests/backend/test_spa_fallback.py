"""Tests for serving the built React SPA from the FastAPI app."""

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.main import _SPA_FALLBACK_ROUTE_NAME, app, configure_spa_fallback, create_app


@pytest.fixture
def spa_client(tmp_path) -> Generator[TestClient, None, None]:
    """Mount a temporary SPA dist on the module app for fallback behavior tests."""
    index_path = tmp_path / "index.html"
    index_path.write_text(
        '<!doctype html><html><head><title>CoachIQ SPA</title></head><body id="spa-root"></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('coachiq');", encoding="utf-8")

    original_routes = list(app.router.routes)
    previous_state = {
        name: getattr(app.state, name, None)
        for name in ("spa_static_dir", "spa_index_path", "spa_reserved_route_families")
    }
    previous_state_present = {
        name: hasattr(app.state, name)
        for name in ("spa_static_dir", "spa_index_path", "spa_reserved_route_families")
    }

    try:
        mounted = configure_spa_fallback(app, SimpleNamespace(static_dir=str(tmp_path)))
        assert mounted is True
        client = TestClient(app)
        try:
            yield client
        finally:
            client.close()
    finally:
        app.router.routes[:] = original_routes
        for name, was_present in previous_state_present.items():
            if was_present:
                setattr(app.state, name, previous_state[name])
            elif hasattr(app.state, name):
                delattr(app.state, name)


def test_spa_fallback_not_mounted_when_dist_is_absent(tmp_path) -> None:
    """Missing dist/index.html leaves the backend route table unchanged."""
    test_app = create_app()

    mounted = configure_spa_fallback(test_app, SimpleNamespace(static_dir=str(tmp_path)))

    assert mounted is False
    assert all(route.name != _SPA_FALLBACK_ROUTE_NAME for route in test_app.routes)


def test_spa_fallback_serves_browser_deeplink(spa_client: TestClient) -> None:
    """Browser navigation to a client-side route returns the SPA index."""
    response = spa_client.get("/settings", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "CoachIQ SPA" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_spa_fallback_serves_static_assets(spa_client: TestClient) -> None:
    """Existing files under the SPA dist are served as static assets."""
    response = spa_client.get("/assets/app.js")

    assert response.status_code == 200
    assert "coachiq" in response.text


def test_spa_fallback_ignores_non_browser_requests(spa_client: TestClient) -> None:
    """Non-browser requests to unknown paths keep the normal 404 envelope."""
    response = spa_client.get("/settings", headers={"Accept": "application/json"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"
    assert "CoachIQ SPA" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        "/openapi.json",
        "/docs",
        "/health",
        "/healthz",
        "/readyz",
        "/metrics",
        "/api/v1/unknown-spa-probe",
        "/oauth/unknown-spa-probe",
        "/.well-known/unknown-spa-probe",
    ],
)
def test_spa_fallback_does_not_shadow_backend_routes(
    spa_client: TestClient,
    path: str,
) -> None:
    """Backend-owned route families keep their native responses instead of SPA HTML."""
    response = spa_client.get(path, headers={"Accept": "text/html"})

    assert "CoachIQ SPA" not in response.text
    if path == "/openapi.json":
        assert response.status_code == 200
        assert response.json()["openapi"].startswith("3.")
    elif path == "/docs":
        assert response.status_code == 200
        assert "Swagger UI" in response.text
    elif path.startswith(("/api/", "/oauth/", "/.well-known/")):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "HTTP_404"
    else:
        assert response.status_code in {200, 500, 503}
        assert response.headers["content-type"] != "text/html; charset=utf-8"
