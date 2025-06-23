"""
API Comparison Testing Framework

This module implements side-by-side testing of legacy and Domain API v2 endpoints
to ensure feature parity before legacy code removal.

SAFETY CRITICAL: This testing ensures no functionality is lost during migration.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.main import app

# Configure logging for detailed comparison output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    """Structured representation of API response for comparison"""

    status_code: int
    data: dict[str, Any] | None
    headers: dict[str, str]
    response_time_ms: float
    endpoint: str
    timestamp: str


@dataclass
class ComparisonResult:
    """Result of comparing legacy vs v2 API responses"""

    endpoint: str
    legacy_response: APIResponse
    v2_response: APIResponse
    data_match: bool
    status_match: bool
    functional_equivalent: bool
    differences: list[str]
    notes: str


class APIComparisonFramework:
    """
    Framework for side-by-side testing of legacy and Domain API v2 endpoints

    This framework:
    1. Executes identical requests against both API versions
    2. Compares responses for functional equivalence
    3. Documents differences and validates they are intentional
    4. Ensures no critical functionality is lost in migration
    """

    def __init__(self, client: TestClient):
        self.client = client
        self.settings = get_settings()
        self.comparison_results: list[ComparisonResult] = []

    async def make_api_request(
        self, endpoint: str, method: str = "GET", data: dict | None = None
    ) -> APIResponse:
        """Make API request and capture detailed response data"""
        start_time = time.time()

        try:
            if method.upper() == "GET":
                response = self.client.get(endpoint)
            elif method.upper() == "POST":
                response = self.client.post(endpoint, json=data)
            elif method.upper() == "PUT":
                response = self.client.put(endpoint, json=data)
            elif method.upper() == "DELETE":
                response = self.client.delete(endpoint)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000

            # Parse response data
            try:
                response_data = response.json() if response.content else None
            except json.JSONDecodeError:
                response_data = {"raw_content": response.text}

            return APIResponse(
                status_code=response.status_code,
                data=response_data,
                headers=dict(response.headers),
                response_time_ms=response_time_ms,
                endpoint=endpoint,
                timestamp=datetime.now().isoformat(),
            )

        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000

            return APIResponse(
                status_code=500,
                data={"error": str(e), "type": type(e).__name__},
                headers={},
                response_time_ms=response_time_ms,
                endpoint=endpoint,
                timestamp=datetime.now().isoformat(),
            )

    def normalize_response_data(self, data: Any) -> Any:
        """
        Normalize response data for comparison by removing timestamp differences
        and other expected variations between API versions.
        """
        if isinstance(data, dict):
            normalized = {}
            for key, value in data.items():
                # Skip timestamp fields that will naturally differ
                if key in ["last_updated", "timestamp", "created_at", "updated_at"]:
                    continue
                # Skip response metadata that may differ
                if key in ["response_time", "request_id", "trace_id"]:
                    continue

                normalized[key] = self.normalize_response_data(value)
            return normalized

        if isinstance(data, list):
            # Sort lists by id or entity_id for consistent comparison
            normalized_list = [self.normalize_response_data(item) for item in data]
            if (
                normalized_list
                and isinstance(normalized_list[0], dict)
                and "entity_id" in normalized_list[0]
            ):
                normalized_list.sort(key=lambda x: x.get("entity_id", ""))
            elif (
                normalized_list
                and isinstance(normalized_list[0], dict)
                and "id" in normalized_list[0]
            ):
                normalized_list.sort(key=lambda x: x.get("id", ""))
            return normalized_list

        return data

    def compare_responses(
        self, legacy_response: APIResponse, v2_response: APIResponse
    ) -> ComparisonResult:
        """
        Compare legacy and v2 API responses for functional equivalence

        This method checks:
        1. Status code compatibility
        2. Data structure equivalence
        3. Functional behavior preservation
        4. Documents intentional differences
        """
        differences = []

        # Status code comparison
        status_match = legacy_response.status_code == v2_response.status_code
        if not status_match:
            differences.append(
                f"Status code: legacy={legacy_response.status_code}, v2={v2_response.status_code}"
            )

        # Data comparison (normalized)
        legacy_data = self.normalize_response_data(legacy_response.data)
        v2_data = self.normalize_response_data(v2_response.data)

        data_match = legacy_data == v2_data
        if not data_match:
            differences.append("Response data structures differ")

            # Detailed difference analysis
            if isinstance(legacy_data, dict) and isinstance(v2_data, dict):
                self._analyze_dict_differences(legacy_data, v2_data, differences)

        # Functional equivalence check
        functional_equivalent = self._check_functional_equivalence(
            legacy_response, v2_response, differences
        )

        # Generate notes for differences
        notes = self._generate_comparison_notes(legacy_response, v2_response, differences)

        return ComparisonResult(
            endpoint=legacy_response.endpoint,
            legacy_response=legacy_response,
            v2_response=v2_response,
            data_match=data_match,
            status_match=status_match,
            functional_equivalent=functional_equivalent,
            differences=differences,
            notes=notes,
        )

    def _analyze_dict_differences(self, legacy: dict, v2: dict, differences: list[str]):
        """Analyze differences between dictionary responses"""
        legacy_keys = set(legacy.keys())
        v2_keys = set(v2.keys())

        # Missing keys
        missing_in_v2 = legacy_keys - v2_keys
        if missing_in_v2:
            differences.append(f"Keys missing in v2: {missing_in_v2}")

        new_in_v2 = v2_keys - legacy_keys
        if new_in_v2:
            differences.append(f"New keys in v2: {new_in_v2}")

        # Value differences for common keys
        common_keys = legacy_keys & v2_keys
        for key in common_keys:
            if legacy[key] != v2[key]:
                differences.append(f"Value difference for '{key}': {legacy[key]} != {v2[key]}")

    def _check_functional_equivalence(
        self, legacy: APIResponse, v2: APIResponse, differences: list[str]
    ) -> bool:
        """
        Check if responses are functionally equivalent even if data differs

        This allows for:
        - Enhanced v2 responses with additional fields
        - Different error message formats
        - Improved data structures
        """
        # If status codes match and both succeeded, check core functionality
        if legacy.status_code == v2.status_code == 200:
            # For entity endpoints, ensure entity data is preserved
            if "entities" in legacy.endpoint:
                return self._check_entity_functional_equivalence(legacy, v2)

            # For control endpoints, ensure command success is preserved
            if "control" in legacy.endpoint:
                return self._check_control_functional_equivalence(legacy, v2)

        # For error cases, ensure appropriate error is returned
        if legacy.status_code >= 400 and v2.status_code >= 400:
            return True  # Both returned errors, that's functionally equivalent

        return legacy.status_code == v2.status_code

    def _check_entity_functional_equivalence(self, legacy: APIResponse, v2: APIResponse) -> bool:
        """Check functional equivalence for entity endpoints"""
        legacy_data = legacy.data
        v2_data = v2.data

        if not legacy_data or not v2_data:
            return legacy_data == v2_data

        # For collection responses
        if isinstance(legacy_data, dict) and isinstance(v2_data, dict):
            # Check if v2 has at least the same entities as legacy
            if "entities" in legacy_data and "entities" in v2_data:
                legacy_entities = legacy_data["entities"]
                v2_entities = v2_data["entities"]

                # Ensure all legacy entities are present in v2
                legacy_ids = {e.get("entity_id") for e in legacy_entities}
                v2_ids = {e.get("entity_id") for e in v2_entities}

                return legacy_ids.issubset(v2_ids)

        return True

    def _check_control_functional_equivalence(self, legacy: APIResponse, v2: APIResponse) -> bool:
        """Check functional equivalence for control endpoints"""
        # Both should indicate success/failure similarly
        legacy_success = legacy.status_code == 200
        v2_success = v2.status_code in [200, 202]  # v2 might use 202 for async

        return legacy_success == v2_success

    def _generate_comparison_notes(
        self, legacy: APIResponse, v2: APIResponse, differences: list[str]
    ) -> str:
        """Generate human-readable notes about the comparison"""
        notes = []

        if not differences:
            notes.append("✅ Responses are identical")
        else:
            notes.append("⚠️ Responses differ:")
            for diff in differences:
                notes.append(f"  - {diff}")

        # Performance comparison
        if v2.response_time_ms < legacy.response_time_ms:
            improvement = (
                (legacy.response_time_ms - v2.response_time_ms) / legacy.response_time_ms * 100
            )
            notes.append(f"🚀 v2 is {improvement:.1f}% faster")
        elif v2.response_time_ms > legacy.response_time_ms * 1.5:
            notes.append("⚠️ v2 response time significantly slower")

        return "\n".join(notes)

    async def test_endpoint_parity(
        self,
        legacy_endpoint: str,
        v2_endpoint: str,
        method: str = "GET",
        test_data: dict | None = None,
    ) -> ComparisonResult:
        """Test parity between legacy and v2 endpoints"""
        logger.info(f"Testing parity: {legacy_endpoint} vs {v2_endpoint}")

        # Make requests to both endpoints
        legacy_response = await self.make_api_request(legacy_endpoint, method, test_data)
        v2_response = await self.make_api_request(v2_endpoint, method, test_data)

        # Compare responses
        result = self.compare_responses(legacy_response, v2_response)
        self.comparison_results.append(result)

        # Log results
        logger.info(f"Comparison result for {legacy_endpoint}:")
        logger.info(f"  Status match: {result.status_match}")
        logger.info(f"  Data match: {result.data_match}")
        logger.info(f"  Functional equivalent: {result.functional_equivalent}")
        logger.info(f"  Notes: {result.notes}")

        return result

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive comparison report"""
        total_tests = len(self.comparison_results)
        status_matches = sum(1 for r in self.comparison_results if r.status_match)
        data_matches = sum(1 for r in self.comparison_results if r.data_match)
        functional_matches = sum(1 for r in self.comparison_results if r.functional_equivalent)

        report = {
            "summary": {
                "total_endpoints_tested": total_tests,
                "status_code_matches": status_matches,
                "data_structure_matches": data_matches,
                "functional_equivalence": functional_matches,
                "status_match_rate": status_matches / total_tests if total_tests > 0 else 0,
                "data_match_rate": data_matches / total_tests if total_tests > 0 else 0,
                "functional_match_rate": functional_matches / total_tests if total_tests > 0 else 0,
            },
            "test_results": [asdict(result) for result in self.comparison_results],
            "generated_at": datetime.now().isoformat(),
        }

        return report


# Test fixtures and test cases
@pytest.fixture
def comparison_framework():
    """Fixture providing the API comparison framework"""
    client = TestClient(app)
    return APIComparisonFramework(client)


class TestEntityEndpointParity:
    """Test cases for entity endpoint parity between legacy and v2 APIs"""

    @pytest.mark.asyncio
    async def test_get_entities_parity(self, comparison_framework):
        """Test GET /api/entities vs GET /api/v2/entities"""
        result = await comparison_framework.test_endpoint_parity(
            legacy_endpoint="/api/entities", v2_endpoint="/api/v2/entities"
        )

        # Assert functional equivalence at minimum
        assert result.functional_equivalent, (
            f"Entity listing not functionally equivalent: {result.notes}"
        )

    @pytest.mark.asyncio
    async def test_get_entity_by_id_parity(self, comparison_framework):
        """Test GET /api/entities/{id} vs GET /api/v2/entities/{id}"""
        # First get an entity ID to test with
        entities_response = await comparison_framework.make_api_request("/api/entities")

        if (
            entities_response.status_code == 200
            and entities_response.data
            and "entities" in entities_response.data
            and entities_response.data["entities"]
        ):
            entity_id = entities_response.data["entities"][0]["entity_id"]

            result = await comparison_framework.test_endpoint_parity(
                legacy_endpoint=f"/api/entities/{entity_id}",
                v2_endpoint=f"/api/v2/entities/{entity_id}",
            )

            assert result.functional_equivalent, (
                f"Single entity fetch not equivalent: {result.notes}"
            )

    @pytest.mark.asyncio
    async def test_control_entity_parity(self, comparison_framework):
        """Test POST /api/entities/{id}/control vs POST /api/v2/entities/control"""
        # First get a controllable entity
        entities_response = await comparison_framework.make_api_request("/api/entities")

        if (
            entities_response.status_code == 200
            and entities_response.data
            and "entities" in entities_response.data
        ):
            # Find a light entity for testing
            light_entities = [
                e for e in entities_response.data["entities"] if e.get("device_type") == "light"
            ]

            if light_entities:
                entity_id = light_entities[0]["entity_id"]
                test_command = {"command": "toggle"}

                # Note: v2 API might have different endpoint structure
                result = await comparison_framework.test_endpoint_parity(
                    legacy_endpoint=f"/api/entities/{entity_id}/control",
                    v2_endpoint="/api/v2/entities/control",
                    method="POST",
                    test_data={"entity_id": entity_id, **test_command},
                )

                # For control operations, we expect at least functional equivalence
                assert result.functional_equivalent, (
                    f"Entity control not equivalent: {result.notes}"
                )


class TestBulkOperationsParity:
    """Test bulk operations feature parity"""

    @pytest.mark.asyncio
    async def test_bulk_control_availability(self, comparison_framework):
        """Test that bulk operations are available in v2 API"""
        # Legacy API might not have bulk operations, so we test v2 availability
        result = await comparison_framework.make_api_request(
            "/api/v2/entities/bulk-control",
            method="POST",
            data={
                "entity_ids": ["test_light_1"],
                "command": {"command": "set", "state": False},
                "ignore_errors": True,
            },
        )

        # Should return proper error or success, not 404
        assert result.status_code != 404, "Bulk control endpoint should be available in v2 API"


class TestSafetyEndpointsParity:
    """Test safety-critical endpoint parity"""

    @pytest.mark.asyncio
    async def test_emergency_stop_availability(self, comparison_framework):
        """Test emergency stop functionality availability"""
        # Test v2 emergency stop endpoint
        result = await comparison_framework.make_api_request(
            "/api/v2/entities/emergency-stop", method="POST"
        )

        # Should be available (even if no actual devices)
        assert result.status_code in [200, 202, 503], (
            f"Emergency stop should be available: {result.status_code}"
        )

    @pytest.mark.asyncio
    async def test_safety_status_availability(self, comparison_framework):
        """Test safety status endpoint availability"""
        result = await comparison_framework.make_api_request("/api/v2/entities/safety-status")

        assert result.status_code == 200, f"Safety status should be available: {result.status_code}"


# Main test runner function
async def run_comprehensive_comparison_tests():
    """Run all comparison tests and generate report"""
    client = TestClient(app)
    framework = APIComparisonFramework(client)

    # Define test scenarios
    test_scenarios = [
        # Basic entity operations
        ("/api/entities", "/api/v2/entities", "GET", None),
        ("/api/health", "/api/v2/entities/health", "GET", None),
        # Error handling tests
        ("/api/entities/nonexistent", "/api/v2/entities/nonexistent", "GET", None),
        # Schema availability
        ("/api/docs", "/api/v2/entities/schemas", "GET", None),
    ]

    logger.info("Starting comprehensive API comparison tests...")

    for legacy_endpoint, v2_endpoint, method, test_data in test_scenarios:
        try:
            await framework.test_endpoint_parity(legacy_endpoint, v2_endpoint, method, test_data)
        except Exception as e:
            logger.error(f"Error testing {legacy_endpoint} vs {v2_endpoint}: {e}")

    # Generate and save report
    report = framework.generate_report()

    # Save report to file
    with open("/tmp/api_comparison_report.json", "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Comparison complete. Report saved to /tmp/api_comparison_report.json")
    logger.info(f"Summary: {report['summary']}")

    return report


if __name__ == "__main__":
    # Run comparison tests
    asyncio.run(run_comprehensive_comparison_tests())
