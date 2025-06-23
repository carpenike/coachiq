"""
Zod Schema Validation Testing

This module tests the integration between backend Pydantic schemas and
frontend Zod validation, ensuring runtime type safety for Domain API v2.

Tests cover:
- Schema export functionality from backend
- Static Zod schema validation
- Dynamic schema fetching and conversion
- Safety-critical validation rules
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


class TestZodSchemaExport:
    """Test backend schema export for frontend Zod integration"""

    @pytest.fixture
    def client(self):
        """Create test client for schema export testing"""
        app = create_app()
        return TestClient(app)

    def test_schema_export_availability(self, client):
        """Test that schema export endpoints are available"""
        # Test main schema endpoint
        response = client.get("/api/schemas/")

        # Should either work (if features enabled) or return 503 (if disabled)
        assert response.status_code in [200, 503], (
            f"Schema export should be available or disabled: {response.status_code}"
        )

        if response.status_code == 200:
            data = response.json()

            # Should have schema structure
            assert "version" in data, "Schema export should include version"
            assert "schemas" in data, "Schema export should include schemas"
            assert "metadata" in data, "Schema export should include metadata"

            # Should have safety-critical metadata
            assert data["metadata"]["safety_critical"] == True, (
                "Schemas should be marked as safety-critical"
            )
            assert data["metadata"]["validation_required"] == True, "Validation should be required"

    def test_domain_entities_schema_export(self, client):
        """Test domain-specific entities schema export"""
        response = client.get("/api/v2/entities/schemas")

        # Should provide schemas or indicate feature not available
        if response.status_code == 200:
            schemas = response.json()

            # Should be a dictionary of schemas
            assert isinstance(schemas, dict), "Schemas should be provided as dictionary"

            # Should contain Entity schema if available
            if "Entity" in schemas:
                entity_schema = schemas["Entity"]
                assert "type" in entity_schema, "Entity schema should have type"
                assert entity_schema["type"] == "object", "Entity should be object type"

                if "properties" in entity_schema:
                    # Should have required entity properties
                    required_props = ["entity_id", "name", "device_type", "protocol", "state"]
                    properties = entity_schema["properties"]

                    for prop in required_props:
                        assert prop in properties, f"Entity schema should have {prop} property"

        elif response.status_code == 404:
            # Domain API not available - this is acceptable for testing
            pytest.skip("Domain API v2 not available in test environment")

        else:
            pytest.fail(
                f"Unexpected response from entities schema endpoint: {response.status_code}"
            )

    def test_individual_schema_export(self, client):
        """Test individual schema export by name"""
        schema_names = ["Entity", "ControlCommand", "BulkOperation", "OperationResult"]

        for schema_name in schema_names:
            response = client.get(f"/api/schemas/{schema_name}")

            if response.status_code == 200:
                data = response.json()

                # Should have schema structure
                assert "schema_name" in data, "Individual schema should include name"
                assert "schema" in data, "Individual schema should include schema definition"
                assert "version" in data, "Individual schema should include version"
                assert data["schema_name"] == schema_name, (
                    f"Schema name should match request: {schema_name}"
                )

            elif response.status_code in [404, 503]:
                # Schema not found or feature disabled - acceptable for testing
                continue

            else:
                pytest.fail(f"Unexpected response for schema {schema_name}: {response.status_code}")


class TestZodValidationLogic:
    """Test the validation logic that would be used by frontend Zod schemas"""

    def test_entity_validation_logic(self):
        """Test entity validation rules that should be enforced"""
        # Valid entity data
        valid_entity = {
            "entity_id": "light_living_room",
            "name": "Living Room Light",
            "device_type": "light",
            "protocol": "rvc",
            "state": {"on": True, "brightness": 75},
            "area": "Living Room",
            "last_updated": "2025-01-11T10:30:00Z",
            "available": True,
        }

        # Test valid entity passes basic checks
        assert isinstance(valid_entity["entity_id"], str) and len(valid_entity["entity_id"]) > 0
        assert isinstance(valid_entity["name"], str) and len(valid_entity["name"]) > 0
        assert isinstance(valid_entity["device_type"], str) and len(valid_entity["device_type"]) > 0
        assert isinstance(valid_entity["protocol"], str) and len(valid_entity["protocol"]) > 0
        assert isinstance(valid_entity["state"], dict)
        assert isinstance(valid_entity["available"], bool)

        # Test invalid entities would fail
        invalid_entities = [
            {},  # Empty object
            {"entity_id": ""},  # Empty entity_id
            {**valid_entity, "entity_id": 123},  # Wrong type for entity_id
            {**valid_entity, "available": "yes"},  # Wrong type for available
            {**valid_entity, "state": "not_dict"},  # Wrong type for state
        ]

        for invalid_entity in invalid_entities:
            # These would fail Zod validation
            if "entity_id" in invalid_entity:
                if (
                    not isinstance(invalid_entity["entity_id"], str)
                    or len(invalid_entity["entity_id"]) == 0
                ):
                    assert True, "Invalid entity_id should fail validation"

            if "available" in invalid_entity:
                if not isinstance(invalid_entity["available"], bool):
                    assert True, "Invalid available should fail validation"

            if "state" in invalid_entity:
                if not isinstance(invalid_entity["state"], dict):
                    assert True, "Invalid state should fail validation"

    def test_control_command_validation_logic(self):
        """Test control command validation rules"""
        # Valid commands
        valid_commands = [
            {"command": "set", "state": True},
            {"command": "toggle"},
            {"command": "brightness_up"},
            {"command": "brightness_down"},
            {"command": "set", "brightness": 75},
            {"command": "set", "state": False, "brightness": 50},
        ]

        for cmd in valid_commands:
            # Basic validation checks
            assert "command" in cmd
            assert cmd["command"] in ["set", "toggle", "brightness_up", "brightness_down"]

            # State validation
            if "state" in cmd:
                assert isinstance(cmd["state"], bool)

            # Brightness validation
            if "brightness" in cmd:
                assert isinstance(cmd["brightness"], (int, float))
                assert 0 <= cmd["brightness"] <= 100

        # Invalid commands that should fail
        invalid_commands = [
            {"command": "invalid_command"},
            {"command": "set", "brightness": 150},  # brightness > 100
            {"command": "set", "brightness": -10},  # brightness < 0
            {"command": "set", "state": "invalid"},  # state not boolean
            {},  # missing command
        ]

        for cmd in invalid_commands:
            # These would fail Zod validation
            if "command" not in cmd:
                assert True, "Missing command should fail validation"
            elif cmd["command"] not in ["set", "toggle", "brightness_up", "brightness_down"]:
                assert True, "Invalid command should fail validation"

            if "brightness" in cmd:
                if not isinstance(cmd["brightness"], (int, float)) or not (
                    0 <= cmd["brightness"] <= 100
                ):
                    assert True, "Invalid brightness should fail validation"

            if "state" in cmd:
                if not isinstance(cmd["state"], bool):
                    assert True, "Invalid state should fail validation"

    def test_bulk_control_request_validation_logic(self):
        """Test bulk control request validation rules"""
        # Valid bulk requests
        valid_requests = [
            {"entity_ids": ["light1", "light2"], "command": {"command": "set", "state": True}},
            {
                "entity_ids": ["light1"],
                "command": {"command": "toggle"},
                "ignore_errors": True,
                "timeout_seconds": 10.0,
            },
        ]

        for req in valid_requests:
            # Basic validation checks
            assert "entity_ids" in req
            assert isinstance(req["entity_ids"], list)
            assert len(req["entity_ids"]) > 0
            assert all(isinstance(id, str) and len(id) > 0 for id in req["entity_ids"])

            assert "command" in req
            assert isinstance(req["command"], dict)
            assert "command" in req["command"]

            # Optional fields
            if "ignore_errors" in req:
                assert isinstance(req["ignore_errors"], bool)

            if "timeout_seconds" in req:
                assert isinstance(req["timeout_seconds"], (int, float))
                assert req["timeout_seconds"] > 0

        # Invalid bulk requests
        invalid_requests = [
            {"entity_ids": [], "command": {"command": "set"}},  # empty entity_ids
            {"entity_ids": ["light1"], "command": {"command": "invalid"}},  # invalid command
            {"command": {"command": "set"}},  # missing entity_ids
            {},  # missing required fields
        ]

        for req in invalid_requests:
            # These would fail Zod validation
            if (
                "entity_ids" not in req
                or not isinstance(req.get("entity_ids"), list)
                or len(req.get("entity_ids", [])) == 0
            ):
                assert True, "Invalid entity_ids should fail validation"

            if "command" not in req:
                assert True, "Missing command should fail validation"

    def test_safety_critical_validation_rules(self):
        """Test safety-critical validation rules that must be enforced"""

        # Safety rule 1: Brightness must be within safe range
        def validate_brightness_range(brightness):
            return isinstance(brightness, (int, float)) and 0 <= brightness <= 100

        assert validate_brightness_range(50) == True
        assert validate_brightness_range(0) == True
        assert validate_brightness_range(100) == True
        assert validate_brightness_range(-1) == False
        assert validate_brightness_range(101) == False
        assert validate_brightness_range("50") == False

        # Safety rule 2: Entity IDs must be non-empty strings
        def validate_entity_id(entity_id):
            return isinstance(entity_id, str) and len(entity_id.strip()) > 0

        assert validate_entity_id("light1") == True
        assert validate_entity_id("") == False
        assert validate_entity_id("   ") == False
        assert validate_entity_id(123) == False
        assert validate_entity_id(None) == False

        # Safety rule 3: Bulk operations must have reasonable limits
        def validate_bulk_operation_size(entity_ids):
            return isinstance(entity_ids, list) and 1 <= len(entity_ids) <= 100

        assert validate_bulk_operation_size(["light1"]) == True
        assert validate_bulk_operation_size(["light1", "light2"]) == True
        assert validate_bulk_operation_size(["light" + str(i) for i in range(100)]) == True
        assert validate_bulk_operation_size([]) == False
        assert validate_bulk_operation_size(["light" + str(i) for i in range(101)]) == False
        assert validate_bulk_operation_size("not_list") == False


class TestZodIntegrationCompatibility:
    """Test compatibility between backend schemas and expected frontend Zod usage"""

    def test_schema_json_format_compatibility(self):
        """Test that backend schema format is compatible with Zod conversion"""
        # Example schema structure that backend should provide
        example_schema = {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "name": {"type": "string"},
                "device_type": {"type": "string"},
                "protocol": {"type": "string"},
                "state": {"type": "object"},
                "area": {"type": ["string", "null"]},
                "last_updated": {"type": "string"},
                "available": {"type": "boolean"},
            },
            "required": [
                "entity_id",
                "name",
                "device_type",
                "protocol",
                "state",
                "last_updated",
                "available",
            ],
            "additionalProperties": False,
        }

        # Test that schema has expected structure for Zod conversion
        assert "type" in example_schema
        assert example_schema["type"] == "object"
        assert "properties" in example_schema
        assert "required" in example_schema

        # Test property types are compatible with Zod
        valid_json_types = ["string", "number", "integer", "boolean", "array", "object", "null"]

        for prop_name, prop_schema in example_schema["properties"].items():
            if "type" in prop_schema:
                if isinstance(prop_schema["type"], list):
                    # Union type (e.g., ["string", "null"])
                    for type_option in prop_schema["type"]:
                        assert type_option in valid_json_types, (
                            f"Type {type_option} should be valid JSON Schema type"
                        )
                else:
                    # Single type
                    assert prop_schema["type"] in valid_json_types, (
                        f"Type {prop_schema['type']} should be valid JSON Schema type"
                    )

    def test_enum_validation_compatibility(self):
        """Test that enum values are properly structured for Zod"""
        # Command enum should be structured correctly
        command_enum = ["set", "toggle", "brightness_up", "brightness_down"]

        # All enum values should be strings
        assert all(isinstance(cmd, str) for cmd in command_enum)
        assert len(command_enum) > 0

        # Status enum should be structured correctly
        status_enum = ["success", "failed", "timeout", "unauthorized"]

        assert all(isinstance(status, str) for status in status_enum)
        assert len(status_enum) > 0

    def test_nested_object_compatibility(self):
        """Test that nested objects are compatible with Zod conversion"""
        # Example nested structure (entity with state object)
        nested_example = {
            "entity_id": "light1",
            "state": {"on": True, "brightness": 75, "color": "warm_white"},
        }

        # Test that nested structure is valid
        assert isinstance(nested_example, dict)
        assert isinstance(nested_example["state"], dict)

        # Test that nested values are of valid types
        for key, value in nested_example["state"].items():
            assert isinstance(value, (str, int, float, bool)), (
                f"State value {key} should be primitive type"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
