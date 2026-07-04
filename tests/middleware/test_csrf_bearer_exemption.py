"""CSRF middleware must not block Bearer-authenticated API requests.

Regression test for the live bug where every POST to
/api/v1/entities/{id}/control returned 403 "CSRF validation failed":
the frontend authenticates with an Authorization: Bearer header (no
cookies), so the double-submit cookie check can never pass, and Bearer
requests are not CSRF-forgeable in the first place.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.middleware.csrf_protection import CSRFProtectionMiddleware

pytestmark = [pytest.mark.unit]


def _build_app() -> TestClient:
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware, secret_key="test-secret", secure_cookie=False)

    @app.post("/api/v1/entities/light/control")
    async def control() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/entities")
    async def list_entities() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_bearer_post_bypasses_csrf() -> None:
    client = _build_app()
    response = client.post(
        "/api/v1/entities/light/control",
        headers={"Authorization": "Bearer some.jwt.token"},
    )
    assert response.status_code == 200


def test_cookie_only_post_still_requires_csrf_token() -> None:
    client = _build_app()
    response = client.post("/api/v1/entities/light/control")
    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_get_requests_unaffected() -> None:
    client = _build_app()
    assert client.get("/api/v1/entities").status_code == 200


def test_non_bearer_authorization_still_requires_csrf_token() -> None:
    client = _build_app()
    response = client.post(
        "/api/v1/entities/light/control",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 403
