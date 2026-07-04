"""Tests for the startup-monitoring metrics endpoint."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routers.startup_monitoring import router
from backend.core.dependencies import get_composition_root

pytestmark = pytest.mark.api


def _make_root_with_timings(service_timings: dict[str, float]) -> Mock:
    root = Mock()
    root.get_startup_metrics.return_value = {
        "total_startup_time_ms": sum(service_timings.values()),
        "service_count": len(service_timings),
        "average_service_time_ms": 0.0,
        "startup_errors": {},
    }
    root.get_service_timings.return_value = service_timings
    root.has_service.return_value = True
    return root


def test_startup_metrics_reports_slow_service_bottlenecks() -> None:
    """Slow services (>200ms) appear as bottlenecks instead of 500ing.

    Regression: the bottleneck comprehension subscripted ServiceTimingInfo
    models (service["name"]), so any run with a >200ms service startup
    turned /api/startup/metrics into an HTTP 500.
    """
    app = FastAPI()
    app.include_router(router)
    root = _make_root_with_timings({"slow_service": 350.0, "fast_service": 10.0})
    app.dependency_overrides[get_composition_root] = lambda: root

    response = TestClient(app).get("/api/startup/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["performance_analysis"]["bottlenecks"] == ["slow_service"]
    assert [service["name"] for service in body["slowest_services"]] == [
        "slow_service",
        "fast_service",
    ]
