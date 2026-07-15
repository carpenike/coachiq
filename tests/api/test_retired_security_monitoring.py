"""Regression tests for retired CAN security-monitoring routes."""

from backend.main import app


def test_retired_monitoring_routes_are_absent() -> None:
    """Dead detector routes stay absent without removing real security APIs."""
    paths = {route.path for route in app.routes}
    retired_paths = {
        "/api/security/status",
        "/api/security/alerts",
        "/api/security/alerts/summary",
        "/api/security/storm-status",
        "/api/security/acl/source",
        "/api/security/acl/source/{source_address}",
        "/api/security/acl/sources",
        "/api/security/acl/policy",
        "/api/security/rate-limiting",
        "/api/security/reset",
        "/api/security/test/simulate-attack",
    }

    assert paths.isdisjoint(retired_paths)
    assert "/api/security/dashboard/data" in paths
    assert "/api/security/config/" in paths
