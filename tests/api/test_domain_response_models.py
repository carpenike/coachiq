"""Contract tests for typed Domain API v1 response models."""

from collections.abc import Generator
from typing import Any, Protocol

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from backend.api.domains import entities as entities_domain
from backend.core.dependencies import get_authenticated_user
from backend.main import app
from backend.schemas.domain_api import (
    DiagnosticsHealthResponse,
    DiagnosticStatisticsResponse,
    DiagnosticTroubleCodeCollection,
    IETFHealthStatusResponse,
    SystemHealthResponse,
)
from backend.services.entities.entity_domain_service import (
    BulkSafetyOperationResultV2,
    SafetyOperationResultV2,
)

pytestmark = pytest.mark.api


class BulkRequestLike(Protocol):
    """Protocol for the bulk request attributes used by the fake service."""

    entity_ids: list[str]


class FakeDomainService:
    """Minimal entity domain service test double for control responses."""

    async def control_entity_safe(
        self, entity_id: str, command: object, user_context: dict[str, Any] | None = None
    ) -> SafetyOperationResultV2:
        """Return a representative single control result."""
        return SafetyOperationResultV2(
            operation_id="op-1",
            entity_id=entity_id,
            status="success",
            acknowledged=True,
            acknowledgment_time_ms=12.5,
            execution_time_ms=34.5,
            safety_validation={"passed": True, "issues": []},
        )

    async def bulk_control_entities_safe(
        self, request: BulkRequestLike, user_context: dict[str, Any] | None = None
    ) -> BulkSafetyOperationResultV2:
        """Return a representative bulk control result."""
        entity_ids = request.entity_ids
        results = [
            SafetyOperationResultV2(
                operation_id=f"bulk-1-{index}",
                entity_id=entity_id,
                status="success",
                acknowledged=True,
                acknowledgment_time_ms=10.0,
                execution_time_ms=20.0,
                safety_validation={"passed": True, "issues": []},
            )
            for index, entity_id in enumerate(entity_ids)
        ]
        return BulkSafetyOperationResultV2(
            operation_id="bulk-1",
            total_count=len(entity_ids),
            success_count=len(entity_ids),
            failed_count=0,
            timeout_count=0,
            safety_abort_count=0,
            results=results,
            total_execution_time_ms=50.0,
            safety_summary={
                "command_halt_active": False,
                "safety_interlocks_enabled": True,
                "acknowledgment_rate": 1.0,
                "average_execution_time": 20.0,
            },
        )


@pytest.fixture
def domain_client() -> Generator[TestClient, None, None]:
    """TestClient with auth and entity domain services overridden."""
    app.dependency_overrides[get_authenticated_user] = lambda: {
        "user_id": "reviewer",
        "role": "admin",
    }
    app.dependency_overrides[entities_domain.get_entity_domain_service] = (
        lambda: FakeDomainService()
    )

    with TestClient(app=app) as client:
        yield client

    app.dependency_overrides.clear()


def _response_schema_for(path: str, method: str = "get") -> dict[str, Any]:
    """Return the OpenAPI 200 response schema for a path and method."""
    return app.openapi()["paths"][path][method]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]


@pytest.mark.parametrize(
    ("path", "method", "component"),
    [
        ("/api/v1/entities/{entity_id}/control", "post", "SafetyOperationResultV2"),
        ("/api/v1/entities/bulk-control", "post", "BulkSafetyOperationResultV2"),
        ("/api/v1/diagnostics/health", "get", "DiagnosticsHealthResponse"),
        ("/api/v1/diagnostics/dtcs", "get", "DiagnosticTroubleCodeCollection"),
        ("/api/v1/diagnostics/statistics", "get", "DiagnosticStatisticsResponse"),
        (
            "/api/v1/system/health",
            "get",
            "backend__schemas__domain_api__SystemHealthResponse",
        ),
    ],
)
def test_loose_endpoints_now_use_component_response_models(
    path: str, method: str, component: str
) -> None:
    """The HOF-021 single-shape endpoints now reference concrete components."""
    assert _response_schema_for(path, method) == {"$ref": f"#/components/schemas/{component}"}


def test_system_status_documents_default_and_ietf_response_shapes() -> None:
    """System status OpenAPI preserves both default and IETF health response contracts."""
    schema = _response_schema_for("/api/v1/system/status")

    refs = {entry["$ref"] for entry in schema["anyOf"]}
    assert refs == {
        "#/components/schemas/backend__api__domains__system__SystemStatus",
        "#/components/schemas/IETFHealthStatusResponse",
    }
    assert "additionalProperties" not in schema


def test_sample_domain_responses_validate_against_models(domain_client: TestClient) -> None:
    """Representative HOF-021 endpoint responses validate against their declared models."""
    assert DiagnosticsHealthResponse.model_validate(
        domain_client.get("/api/v1/diagnostics/health").json()
    )
    assert DiagnosticTroubleCodeCollection.model_validate(
        domain_client.get("/api/v1/diagnostics/dtcs").json()
    )
    assert DiagnosticStatisticsResponse.model_validate(
        domain_client.get("/api/v1/diagnostics/statistics").json()
    )
    assert SystemHealthResponse.model_validate(domain_client.get("/api/v1/system/health").json())
    assert IETFHealthStatusResponse.model_validate(
        domain_client.get("/api/v1/system/status?format=ietf").json()
    )
    assert SafetyOperationResultV2.model_validate(
        domain_client.post(
            "/api/v1/entities/light_1/control", json={"command": "set", "state": True}
        ).json()
    )
    assert BulkSafetyOperationResultV2.model_validate(
        domain_client.post(
            "/api/v1/entities/bulk-control",
            json={
                "operation_type": "control",
                "entity_ids": ["light_1", "light_2"],
                "command": {"command": "toggle"},
            },
        ).json()
    )


def test_system_status_default_shape_validates(domain_client: TestClient) -> None:
    """The default system status branch still returns the existing SystemStatus shape."""
    from backend.api.domains.system import SystemStatus

    assert TypeAdapter(SystemStatus).validate_python(
        domain_client.get("/api/v1/system/status").json()
    )
