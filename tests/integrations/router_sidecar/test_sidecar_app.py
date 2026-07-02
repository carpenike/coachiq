"""Tests for the RouterOS sidecar plain-text app."""

import pytest
from fastapi.testclient import TestClient

from backend.core.config import RouterSidecarSettings
from backend.integrations.router_sidecar import RouterSidecarService

pytestmark = [pytest.mark.integration, pytest.mark.smoke]


def test_sidecar_endpoints_return_plain_text_tokens() -> None:
    """Sidecar endpoints return bare tokens from cache without main app middleware."""
    service = RouterSidecarService(RouterSidecarSettings(enabled=True))
    client = TestClient(service.app)

    expected = {
        "/healthz": "ok\n",
        "/location-state": "unknown\n",
        "/starlink/verdict": "unknown\n",
        "/starlink/raw": "unknown=1\n",
    }
    for path, body in expected.items():
        response = client.get(path)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == body
