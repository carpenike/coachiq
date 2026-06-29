"""
Tests for the missing DGNs functionality.

The legacy ``/api/missing-dgns`` HTTP endpoint that this file used to
exercise (``TestMissingDGNsAPI``) was retired during the
service-registry / domain-API refactor. The replacement lives at
``/api/v1/entities/debug/missing-dgns`` (see
``backend/api/domains/entities.py``) and is currently a placeholder
that returns ``{"missing_dgns": {}}`` because
``EntityService.get_missing_dgns()`` has not been implemented yet.
The original API tests are therefore skip-stubbed; if/when the v2
endpoint is wired through to ``backend.integrations.rvc.decode``,
new tests should be authored against the v2 path with the current
DI helpers (``get_entity_service``), not the removed
``get_app_state`` / ``get_feature_manager_from_request`` shims.

The ``TestMissingDGNsIntegration`` class below still exercises the
underlying tracker module (``backend.integrations.rvc.missing_dgns``)
which is alive and used by the decoder, so it remains intact.

See: PR #109 (state.py removal), PR #111 (entity service
disambiguation), issue #105 (test sweep #2).
"""

import pytest


@pytest.mark.skip(
    reason=(
        "Legacy /api/missing-dgns endpoint retired; v2 replacement "
        "(/api/v1/entities/debug/missing-dgns) is a placeholder. "
        "Mocked dependencies (get_app_state, services.feature_manager) "
        "no longer exist. See PR #109 / issue #105."
    )
)
class TestMissingDGNsAPI:
    """Skip-stub: legacy API endpoint retired (see module docstring)."""

    def test_legacy_api_retired(self) -> None:
        """Marker so pytest reports a single skip rather than nothing."""


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
