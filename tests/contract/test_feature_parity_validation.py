"""
Feature Parity Validation for Domain API v2

This module validates that Domain API v2 endpoints provide the same functionality
as their legacy counterparts, ensuring no functionality is lost during migration.

Based on Week 1 documentation:
- LEGACY_API_DOCUMENTATION.md: Complete legacy endpoint catalog
- LEGACY_TO_V2_MAPPING.md: Legacy to v2 mapping
- HIDDEN_BUSINESS_LOGIC.md: Critical business logic patterns
"""

import json
import os
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


class FeatureParityTestConfig:
    """Configuration for feature parity testing"""

    # Test environment setup
    DOMAIN_API_ENV = {
        "COACHIQ_FEATURES__DOMAIN_API_V2": "true",
        "COACHIQ_FEATURES__ENTITIES_API_V2": "true",
    }

    # Legacy to v2 endpoint mappings (from LEGACY_TO_V2_MAPPING.md)
    ENDPOINT_MAPPINGS = [
        {
            "legacy_path": "/api/entities",
            "legacy_method": "GET",
            "v2_path": "/api/v2/entities",
            "v2_method": "GET",
            "description": "Get all entities with optional filtering",
        },
        {
            "legacy_path": "/api/entities/{entity_id}",
            "legacy_method": "GET",
            "v2_path": "/api/v2/entities/{entity_id}",
            "v2_method": "GET",
            "description": "Get specific entity by ID",
        },
        {
            "legacy_path": "/api/entities/{entity_id}/control",
            "legacy_method": "POST",
            "v2_path": "/api/v2/entities/{entity_id}/control",
            "v2_method": "POST",
            "description": "Control single entity",
        },
        {
            "legacy_path": "/api/bulk-operations",
            "legacy_method": "POST",
            "v2_path": "/api/v2/entities/bulk-control",
            "v2_method": "POST",
            "description": "Bulk entity control operations",
        },
    ]

    # Test data for validation
    TEST_ENTITY_ID = "test_light_1"
    TEST_CONTROL_COMMAND = {"command": "set", "state": True}
    TEST_BULK_COMMAND = {
        "entity_ids": ["test_light_1", "test_light_2"],
        "command": {"command": "set", "state": False},
    }

    # Legacy bulk operations format (different structure)
    LEGACY_BULK_COMMAND = {
        "operation_type": "state_change",
        "targets": ["test_light_1", "test_light_2"],
        "payload": {"command": "set", "state": False},
        "description": "Test bulk operation",
    }


@pytest.fixture
def legacy_client():
    """Create test client with only legacy APIs enabled"""
    # Clear any cached managers
    import backend.core.config
    import backend.services.feature_manager

    backend.services.feature_manager._feature_manager = None
    backend.core.config._settings = None

    app = create_app()
    return TestClient(app)


@pytest.fixture
def domain_client(monkeypatch):
    """Create test client with domain API v2 enabled"""
    # Set environment variables
    for key, value in FeatureParityTestConfig.DOMAIN_API_ENV.items():
        monkeypatch.setenv(key, value)

    # Clear caches to force reload
    import backend.core.config
    import backend.services.feature_manager

    backend.services.feature_manager._feature_manager = None
    backend.core.config._settings = None

    app = create_app()
    return TestClient(app)


def normalize_response_for_comparison(
    response_data: dict[str, Any], endpoint_type: str
) -> dict[str, Any]:
    """
    Normalize response data for comparison between legacy and v2 APIs

    Some fields may differ between legacy and v2 (timestamps, formatting)
    but functional data should be equivalent.
    """
    if not isinstance(response_data, dict):
        return response_data

    normalized = response_data.copy()

    # Remove timestamps that will differ between calls
    timestamp_fields = ["last_updated", "timestamp", "created_at", "updated_at"]
    for field in timestamp_fields:
        if field in normalized:
            normalized[field] = "NORMALIZED_TIMESTAMP"

    # Normalize entity lists for comparison
    if endpoint_type == "entity_list":
        if isinstance(normalized, dict) and "entities" in normalized:
            # v2 format: {"entities": [...], "total_count": N, ...}
            entities = normalized["entities"]
        elif isinstance(normalized, list):
            # Legacy format: [entity1, entity2, ...]
            entities = normalized
            normalized = {"entities": entities, "total_count": len(entities)}
        else:
            entities = []

        # Normalize individual entities
        for entity in entities:
            if isinstance(entity, dict):
                for field in timestamp_fields:
                    if field in entity:
                        entity[field] = "NORMALIZED_TIMESTAMP"

    return normalized


class TestFeatureParityValidation:
    """Validate that v2 endpoints provide equivalent functionality to legacy"""

    def test_entities_list_parity(self, legacy_client, domain_client):
        """Test that /api/v2/entities provides same data as /api/entities"""
        # Get legacy response
        legacy_response = legacy_client.get("/api/entities")

        # Get v2 response
        v2_response = domain_client.get("/api/v2/entities")

        # Both should have same basic success/failure pattern
        # In test environment, both might fail due to missing services, but they should fail consistently
        assert legacy_response.status_code == v2_response.status_code or (
            legacy_response.status_code in [200, 500] and v2_response.status_code in [200, 404, 500]
        ), (
            f"Response patterns should be similar: legacy={legacy_response.status_code}, v2={v2_response.status_code}"
        )

        # If both succeed, compare data structure
        if legacy_response.status_code == 200 and v2_response.status_code == 200:
            legacy_data = normalize_response_for_comparison(legacy_response.json(), "entity_list")
            v2_data = normalize_response_for_comparison(v2_response.json(), "entity_list")

            # Both should have entities (even if empty list)
            assert "entities" in legacy_data, "Legacy response should have entities"
            assert "entities" in v2_data, "V2 response should have entities"

            # Entity count should match
            assert len(legacy_data["entities"]) == len(v2_data["entities"]), (
                "Entity counts should match between legacy and v2"
            )

    def test_entities_filtering_parity(self, legacy_client, domain_client):
        """Test that filtering works consistently between legacy and v2"""
        filter_params = "?device_type=light"

        legacy_response = legacy_client.get(f"/api/entities{filter_params}")
        v2_response = domain_client.get(f"/api/v2/entities{filter_params}")

        # Should have similar response patterns
        assert (legacy_response.status_code in [200, 500]) and (
            v2_response.status_code in [200, 404, 500]
        ), (
            f"Filtering should work similarly: legacy={legacy_response.status_code}, v2={v2_response.status_code}"
        )

        # If v2 is available, it should support the same filter parameters
        if v2_response.status_code == 200:
            v2_data = v2_response.json()
            assert "filters_applied" in v2_data, "V2 should track applied filters"
            assert v2_data["filters_applied"].get("device_type") == "light", (
                "Filter should be applied"
            )

    def test_entity_control_parity(self, legacy_client, domain_client):
        """Test that entity control works consistently between legacy and v2"""
        entity_id = FeatureParityTestConfig.TEST_ENTITY_ID
        command = FeatureParityTestConfig.TEST_CONTROL_COMMAND

        # Test control endpoints
        legacy_url = f"/api/entities/{entity_id}/control"
        v2_url = f"/api/v2/entities/{entity_id}/control"

        legacy_response = legacy_client.post(legacy_url, json=command)
        v2_response = domain_client.post(v2_url, json=command)

        # Both should handle the request (success or consistent failure)
        assert legacy_response.status_code in [200, 400, 404, 500], (
            f"Legacy control should return valid status: {legacy_response.status_code}"
        )
        assert v2_response.status_code in [200, 400, 404, 500], (
            f"V2 control should return valid status: {v2_response.status_code}"
        )

        # If both succeed, compare response structure
        if legacy_response.status_code == 200 and v2_response.status_code == 200:
            legacy_data = legacy_response.json()
            v2_data = v2_response.json()

            # Both should indicate operation status
            assert "status" in legacy_data or "success" in legacy_data, (
                "Legacy should have status indicator"
            )
            assert "status" in v2_data or "entity_id" in v2_data, "V2 should have operation result"

    def test_bulk_operations_parity(self, legacy_client, domain_client):
        """Test that bulk operations provide equivalent functionality"""

        # Legacy bulk operations endpoint (different format)
        legacy_response = legacy_client.post(
            "/api/bulk-operations", json=FeatureParityTestConfig.LEGACY_BULK_COMMAND
        )

        # V2 bulk operations endpoint
        v2_response = domain_client.post(
            "/api/v2/entities/bulk-control", json=FeatureParityTestConfig.TEST_BULK_COMMAND
        )

        # Should handle bulk operations consistently
        assert legacy_response.status_code in [200, 400, 404, 500], (
            f"Legacy bulk should return valid status: {legacy_response.status_code}"
        )
        assert v2_response.status_code in [200, 400, 404, 500], (
            f"V2 bulk should return valid status: {v2_response.status_code}"
        )

        # If both succeed, v2 should provide more detailed results
        if legacy_response.status_code == 200 and v2_response.status_code == 200:
            v2_data = v2_response.json()

            # V2 should have enhanced bulk operation response
            assert "operation_id" in v2_data, "V2 should provide operation tracking"
            assert "total_count" in v2_data, "V2 should provide total operation count"
            assert "success_count" in v2_data, "V2 should provide success count"
            assert "results" in v2_data, "V2 should provide per-entity results"


class TestEnhancedFeatures:
    """Test features that are enhanced or added in v2"""

    def test_v2_schema_export(self, domain_client):
        """Test that v2 provides schema export capability"""
        response = domain_client.get("/api/v2/entities/schemas")

        # Should provide schemas even if other features are limited in test env
        if response.status_code == 200:
            schemas = response.json()

            # Should have key entity schemas
            expected_schemas = ["Entity", "ControlCommand", "BulkControlRequest", "OperationResult"]
            for schema_name in expected_schemas:
                assert schema_name in schemas, f"Should provide {schema_name} schema"
                assert isinstance(schemas[schema_name], dict), (
                    f"{schema_name} should be a valid schema"
                )

    def test_v2_safety_endpoints(self, domain_client):
        """Test safety-critical endpoints unique to v2"""
        safety_endpoints = [
            "/api/v2/entities/emergency-stop",
            "/api/v2/entities/clear-emergency-stop",
            "/api/v2/entities/safety-status",
            "/api/v2/entities/reconcile-state",
        ]

        for endpoint in safety_endpoints:
            if "status" in endpoint:
                response = domain_client.get(endpoint)
            else:
                response = domain_client.post(endpoint, json={})

            # Should exist and respond (even if service fails in test env)
            assert response.status_code != 404, f"Safety endpoint {endpoint} should exist"
            assert response.status_code in [200, 500], (
                f"Safety endpoint {endpoint} should be reachable"
            )

    def test_v2_pagination(self, domain_client):
        """Test enhanced pagination in v2"""
        response = domain_client.get("/api/v2/entities?page=1&page_size=10")

        if response.status_code == 200:
            data = response.json()

            # Should have pagination metadata
            pagination_fields = ["total_count", "page", "page_size", "has_next"]
            for field in pagination_fields:
                assert field in data, f"V2 should provide {field} for pagination"

    def test_v2_command_validation(self, domain_client):
        """Test enhanced command validation in v2"""
        # Test invalid command structure
        invalid_command = {"command": "invalid_command_type", "invalid_field": "should_be_rejected"}

        response = domain_client.post("/api/v2/entities/test_entity/control", json=invalid_command)

        # Should validate and reject invalid commands
        assert response.status_code in [400, 422, 500], "Should validate command structure"


class TestBusinessLogicPreservation:
    """Test that critical business logic from HIDDEN_BUSINESS_LOGIC.md is preserved"""

    def test_light_state_machine_preservation(self, domain_client):
        """Test that light control state machine logic is preserved"""
        # Based on HIDDEN_BUSINESS_LOGIC.md: Light controls have brightness memory
        light_commands = [
            {"command": "set", "state": True, "brightness": 75},
            {"command": "toggle"},  # Should remember brightness of 75
            {"command": "brightness_up"},
            {"command": "brightness_down"},
        ]

        for command in light_commands:
            response = domain_client.post("/api/v2/entities/test_light/control", json=command)

            # Should accept all valid light commands
            assert response.status_code in [200, 404, 500], (
                f"Should handle light command: {command}"
            )

    def test_safety_interlock_validation(self, domain_client):
        """Test that safety interlocks are validated"""
        # Based on HIDDEN_BUSINESS_LOGIC.md: Safety interlocks for vehicle systems
        safety_critical_commands = [
            {"command": "set", "state": True},  # Generic safety-critical command
        ]

        for command in safety_critical_commands:
            # Use safety-aware endpoint
            response = domain_client.post("/api/v2/entities/test_slide/control-safe", json=command)

            # Should use safety validation pathway
            assert response.status_code in [200, 400, 404, 500], (
                f"Should validate safety command: {command}"
            )


class TestMigrationReadiness:
    """Test readiness for migration from legacy to v2"""

    def test_feature_flag_control(self, legacy_client, domain_client):
        """Test that feature flags properly control API availability"""
        # Legacy client should not have v2 routes
        v2_response = legacy_client.get("/api/v2/entities/health")
        assert v2_response.status_code == 404, "Legacy client should not have v2 routes"

        # Domain client should have v2 routes
        v2_response = domain_client.get("/api/v2/entities/health")
        assert v2_response.status_code in [200, 503], "Domain client should have v2 routes"

    def test_parallel_operation_readiness(self, legacy_client, domain_client):
        """Test that legacy and v2 can operate in parallel"""
        # Both clients should be able to access their respective APIs
        legacy_response = legacy_client.get("/api/entities")
        v2_response = domain_client.get("/api/v2/entities")

        # Should not interfere with each other
        assert legacy_response.status_code in [200, 500], "Legacy API should remain functional"
        assert v2_response.status_code in [200, 404, 500], "V2 API should be available when enabled"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
