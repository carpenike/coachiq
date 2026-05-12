"""
Tests for the missing DGNs API endpoint.

This test suite verifies the /api/missing-dgns endpoint functionality
including proper dependency injection and error handling.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import app


class TestMissingDGNsAPI:
    """Test the missing DGNs API endpoint."""

    @pytest.fixture
    def mock_feature_manager(self):
        """Create a mock feature manager with RVC enabled."""
        mock = Mock()
        mock.is_feature_enabled.return_value = True
        return mock

    @pytest.fixture
    def client_with_mocks(self, mock_feature_manager):
        """Create a test client with properly mocked dependencies."""
        # Mock all required services to avoid initialization issues
        mock_can_service = Mock()
        mock_entity_service = Mock()
        mock_config_service = Mock()
        mock_docs_service = Mock()
        mock_vector_service = Mock()
        mock_app_state = Mock()

        with (
            patch(
                "backend.services.feature_manager.get_feature_manager",
                return_value=mock_feature_manager,
            ),
            patch("backend.services.can_service.CANService"),
            patch("backend.services.entity_service.EntityService"),
            patch("backend.services.config_service.ConfigService"),
            patch("backend.services.rvc_service.RVCService"),
            patch("backend.websocket.handlers.WebSocketManager"),
            # Patch all dependency injection functions
            patch(
                "backend.core.dependencies.get_feature_manager_from_request",
                return_value=mock_feature_manager,
            ),
            patch("backend.core.dependencies.get_can_service", return_value=mock_can_service),
            patch("backend.core.dependencies.get_entity_service", return_value=mock_entity_service),
            patch("backend.core.dependencies.get_config_service", return_value=mock_config_service),
            patch("backend.core.dependencies.get_docs_service", return_value=mock_docs_service),
            patch("backend.core.dependencies.get_vector_service", return_value=mock_vector_service),
            patch("backend.core.dependencies.get_app_state", return_value=mock_app_state),
            TestClient(app) as client,
        ):
            yield client

    def test_missing_dgns_endpoint_empty_response(self, client_with_mocks):
        """Test missing DGNs endpoint returns empty response when no missing DGNs."""
        with patch("backend.integrations.rvc.decode.get_missing_dgns", return_value={}):
            response = client_with_mocks.get("/api/missing-dgns")

            assert response.status_code == 200
            assert response.json() == {}

    def test_missing_dgns_endpoint_with_data(self, client_with_mocks):
        """Test missing DGNs endpoint returns properly formatted data."""
        # Mock missing DGNs data with sets that need to be serialized
        mock_missing_dgns = {
            "65280": {
                "dgn_id": 65280,
                "dgn_hex": "0xFF00",
                "first_seen": "2024-01-01T12:00:00",
                "encounter_count": 5,
                "can_ids": {0x1234, 0x5678},
                "contexts": {"engine", "transmission"},
            },
            "65281": {
                "dgn_id": 65281,
                "dgn_hex": "0xFF01",
                "first_seen": "2024-01-01T12:30:00",
                "encounter_count": 2,
                "can_ids": {0x9ABC},
                "contexts": {"hvac"},
            },
        }

        with patch(
            "backend.integrations.rvc.decode.get_missing_dgns", return_value=mock_missing_dgns
        ):
            response = client_with_mocks.get("/api/missing-dgns")

            assert response.status_code == 200
            data = response.json()

            # Verify structure
            assert "65280" in data
            assert "65281" in data

            # Verify first DGN data (sets should be converted to lists)
            dgn_65280 = data["65280"]
            assert dgn_65280["dgn_id"] == 65280
            assert dgn_65280["dgn_hex"] == "0xFF00"
            assert dgn_65280["first_seen"] == "2024-01-01T12:00:00"
            assert dgn_65280["encounter_count"] == 5
            assert isinstance(dgn_65280["can_ids"], list)
            assert set(dgn_65280["can_ids"]) == {0x1234, 0x5678}
            assert isinstance(dgn_65280["contexts"], list)
            assert set(dgn_65280["contexts"]) == {"engine", "transmission"}

            # Verify second DGN data
            dgn_65281 = data["65281"]
            assert dgn_65281["dgn_id"] == 65281
            assert dgn_65281["dgn_hex"] == "0xFF01"
            assert dgn_65281["encounter_count"] == 2
            assert isinstance(dgn_65281["can_ids"], list)
            assert dgn_65281["can_ids"] == [0x9ABC]
            assert isinstance(dgn_65281["contexts"], list)
            assert dgn_65281["contexts"] == ["hvac"]

    def test_missing_dgns_endpoint_rvc_disabled(self, client_with_mocks):
        """Test missing DGNs endpoint returns 404 when RVC feature is disabled."""
        # Patch the feature check function directly to return False
        with patch(
            "backend.api.routers.entities._check_rvc_feature_enabled",
            side_effect=HTTPException(status_code=404, detail="rvc feature is disabled"),
        ):
            response = client_with_mocks.get("/api/missing-dgns")

            assert response.status_code == 404
            assert "rvc feature is disabled" in response.json()["detail"]

    def test_missing_dgns_endpoint_import_error_handling(self, client_with_mocks):
        """Test missing DGNs endpoint handles import errors gracefully."""
        # Mock an import error for the RVC decode module
        with patch(
            "backend.integrations.rvc.decode.get_missing_dgns",
            side_effect=ImportError("Module not found"),
        ):
            response = client_with_mocks.get("/api/missing-dgns")

            # The endpoint should handle the error and return a 500 status
            assert response.status_code == 500

    def test_missing_dgns_endpoint_json_serialization(self, client_with_mocks):
        """Test that complex data structures are properly JSON serialized."""
        # Test with edge cases in data structures
        mock_missing_dgns = {
            "65282": {
                "dgn_id": 65282,
                "dgn_hex": "0xFF02",
                "first_seen": "2024-01-01T13:00:00",
                "encounter_count": 1,
                "can_ids": set(),  # Empty set
                "contexts": {"test_context_with_special_chars_!@#"},
            }
        }

        with patch(
            "backend.integrations.rvc.decode.get_missing_dgns", return_value=mock_missing_dgns
        ):
            response = client_with_mocks.get("/api/missing-dgns")

            assert response.status_code == 200
            data = response.json()

            # Verify empty set is converted to empty list
            assert data["65282"]["can_ids"] == []
            assert data["65282"]["contexts"] == ["test_context_with_special_chars_!@#"]

    def test_missing_dgns_api_documentation_compliance(self, client_with_mocks):
        """Test that the API response matches the documented schema."""
        mock_missing_dgns = {
            "65283": {
                "dgn_id": 65283,
                "dgn_hex": "0xFF03",
                "first_seen": "2024-01-01T14:00:00",
                "encounter_count": 10,
                "can_ids": {0x1111, 0x2222},
                "contexts": {"brake", "abs"},
            }
        }

        with patch(
            "backend.integrations.rvc.decode.get_missing_dgns", return_value=mock_missing_dgns
        ):
            response = client_with_mocks.get("/api/missing-dgns")

            assert response.status_code == 200
            data = response.json()

            # Verify all documented fields are present
            dgn_data = data["65283"]
            expected_fields = {
                "dgn_id",
                "dgn_hex",
                "first_seen",
                "encounter_count",
                "can_ids",
                "contexts",
            }
            assert set(dgn_data.keys()) == expected_fields

            # Verify data types match documentation
            assert isinstance(dgn_data["dgn_id"], int)
            assert isinstance(dgn_data["dgn_hex"], str)
            assert isinstance(dgn_data["first_seen"], str)
            assert isinstance(dgn_data["encounter_count"], int)
            assert isinstance(dgn_data["can_ids"], list)
            assert isinstance(dgn_data["contexts"], list)


class TestMissingDGNsIntegration:
    """Integration tests for missing DGNs functionality."""

    def test_missing_dgns_integration_with_real_decoder(self):
        """Test missing DGNs functionality with the actual RVC decoder."""
        from backend.integrations.rvc.decode import (
            clear_missing_dgns,
            get_missing_dgns,
            record_missing_dgn,
        )

        # Clear any existing missing DGNs
        clear_missing_dgns()

        # Verify empty state
        missing_dgns = get_missing_dgns()
        assert missing_dgns == {}

        # Record a missing DGN
        record_missing_dgn(65400, 0x1234, "test_context")
        # Verify it was recorded
        missing_dgns = get_missing_dgns()
        assert 65400 in missing_dgns  # Integer key, not string
        assert missing_dgns[65400]["dgn_id"] == 65400
        assert missing_dgns[65400]["encounter_count"] == 1
        assert 0x1234 in missing_dgns[65400]["can_ids"]
        assert "test_context" in missing_dgns[65400]["contexts"]

        # Record the same DGN again with different context
        record_missing_dgn(65400, 0x5678, "another_context")

        # Verify encounter count increased and new data added
        missing_dgns = get_missing_dgns()
        assert missing_dgns[65400]["encounter_count"] == 2
        assert 0x1234 in missing_dgns[65400]["can_ids"]
        assert 0x5678 in missing_dgns[65400]["can_ids"]
        assert "test_context" in missing_dgns[65400]["contexts"]
        assert "another_context" in missing_dgns[65400]["contexts"]

        # Clean up
        clear_missing_dgns()
        missing_dgns = get_missing_dgns()
        assert missing_dgns == {}
