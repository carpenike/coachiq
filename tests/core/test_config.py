"""
Tests for the configuration management module.

Covers ``backend.core.config.Settings`` and ``get_settings()``.

Environment variable convention (verified against production 2026-05-12)
------------------------------------------------------------------------
All settings use the ``COACHIQ_`` prefix with hierarchical naming via the
``__`` (double-underscore) delimiter for nested fields. The previous
revision of this test file asserted against legacy unprefixed env vars
(``LOG_LEVEL``, ``CAN_BITRATE``, ``RVC_SPEC_PATH`` etc.) that production
hasn't honoured since the audit-2026-05-12 cleanup. Rewritten in PR #122
to match the actual env-var contract.

Examples of the current contract:
- ``COACHIQ_DEBUG=true`` -> ``settings.debug``
- ``COACHIQ_LOGGING__LEVEL=DEBUG`` -> ``settings.logging.level``
- ``COACHIQ_CAN__BUSTYPE=virtual`` -> ``settings.can.bustype``
- ``COACHIQ_CAN__INTERFACES=can0,can1`` -> ``settings.can.interfaces``
- ``COACHIQ_RVC_SPEC_PATH=/path/to/spec.json`` -> ``settings.rvc_spec_path``
- ``COACHIQ_FEATURES__ENABLE_NOTIFICATIONS=true``
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.core.config import Settings, get_settings
from tests._helpers.settings import (
    isolated_env as _isolated_env,
)
from tests._helpers.settings import (
    make_test_settings as _settings_no_env_file,
)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
#
# Helpers were hoisted into ``tests/_helpers/settings.py`` in audit cycle
# 2026-05-13 (PR A4). The aliases above keep the in-file call sites
# unchanged. The shared module documents the three Pydantic-Settings
# traps these helpers exist to avoid; new tests should prefer importing
# the canonical names ``isolated_env`` / ``make_test_settings`` directly.


# ----------------------------------------------------------------------------
# TestSettings - default values + env-var overrides
# ----------------------------------------------------------------------------


@pytest.mark.unit
class TestSettings:
    """Test suite for the Settings configuration class."""

    def test_default_settings(self):
        """Default settings load with their documented field defaults."""
        with patch.dict(os.environ, _isolated_env({}), clear=True):
            settings = _settings_no_env_file()

        assert settings.app_name == "CoachIQ"
        assert settings.app_description == "API for RV-C CANbus"
        assert settings.app_version == "1.0.0"  # Production default
        assert settings.debug is False
        assert settings.logging.level == "INFO"

    def test_top_level_env_override(self):
        """``COACHIQ_DEBUG=true`` flips the top-level debug flag."""
        with patch.dict(os.environ, _isolated_env({"COACHIQ_DEBUG": "true"}), clear=True):
            settings = _settings_no_env_file()
            assert settings.debug is True
            # Other top-level fields keep defaults.
            assert settings.app_name == "CoachIQ"

    def test_nested_env_override(self):
        """``COACHIQ_LOGGING__LEVEL=DEBUG`` (double-underscore) reaches nested settings."""
        with patch.dict(
            os.environ,
            _isolated_env({"COACHIQ_LOGGING__LEVEL": "DEBUG"}),
            clear=True,
        ):
            settings = _settings_no_env_file()
            assert settings.logging.level == "DEBUG"

    def test_can_configuration_defaults(self):
        """CANSettings carries its own defaults (interface=can0, socketcan, 500000)."""
        with patch.dict(os.environ, _isolated_env({}), clear=True):
            settings = _settings_no_env_file()

        assert "can0" in settings.can.all_interfaces
        assert settings.can.bustype == "socketcan"
        # Production default is 500000 (CANSettings.bitrate, line 200 of config.py).
        assert settings.can.bitrate == 500000

    def test_can_configuration_from_env(self):
        """``COACHIQ_CAN__*`` env vars flow into the nested ``can`` settings."""
        with patch.dict(
            os.environ,
            _isolated_env(
                {
                    "COACHIQ_CAN__INTERFACES": "can0,can1",
                    "COACHIQ_CAN__BUSTYPE": "virtual",
                    "COACHIQ_CAN__BITRATE": "250000",
                }
            ),
            clear=True,
        ):
            settings = _settings_no_env_file()

        # The CANSettings.parse_interfaces validator handles the comma split.
        assert settings.can.interfaces == ["can0", "can1"]
        assert settings.can.bustype == "virtual"
        assert settings.can.bitrate == 250000
        # all_interfaces helper returns the full list when interfaces != default.
        assert "can0" in settings.can.all_interfaces
        assert "can1" in settings.can.all_interfaces

    def test_file_path_configuration(self, tmp_path):
        """``COACHIQ_RVC_SPEC_PATH`` sets the top-level Path field on Settings.

        These are top-level (not nested) Settings fields, so the env var uses
        the single-underscore form ``COACHIQ_<FIELD>``, NOT
        ``COACHIQ_RVC__<FIELD>`` -- the latter would map to the nested ``rvc``
        settings group.
        """
        spec_file = tmp_path / "spec.json"
        mapping_file = tmp_path / "mapping.yml"

        with patch.dict(
            os.environ,
            _isolated_env(
                {
                    "COACHIQ_RVC_SPEC_PATH": str(spec_file),
                    "COACHIQ_RVC_COACH_MAPPING_PATH": str(mapping_file),
                }
            ),
            clear=True,
        ):
            settings = _settings_no_env_file()

        # Pydantic coerces to Path because the field type is Path | None.
        assert isinstance(settings.rvc_spec_path, Path)
        assert isinstance(settings.rvc_coach_mapping_path, Path)
        assert settings.rvc_spec_path == spec_file
        assert settings.rvc_coach_mapping_path == mapping_file

    def test_validation_errors(self):
        """Invalid integer for a CAN field raises a Pydantic ValidationError.

        Pydantic raises ``pydantic.ValidationError`` (a subclass of
        ``ValueError``) when env-var coercion fails, so ``pytest.raises(ValueError)``
        catches it correctly. Match on a substring of the expected error so
        a future Pydantic upgrade that changes the message format fails
        loudly instead of silently passing on a different ValueError.
        """
        with (
            patch.dict(
                os.environ,
                _isolated_env({"COACHIQ_CAN__BITRATE": "not_a_number"}),
                clear=True,
            ),
            pytest.raises(ValueError, match="bitrate"),
        ):
            _settings_no_env_file()

    def test_feature_flags_defaults(self):
        """FeaturesSettings defaults are stable across releases."""
        with patch.dict(os.environ, _isolated_env({}), clear=True):
            settings = _settings_no_env_file()

        assert settings.features.enable_maintenance_tracking is False
        assert settings.features.enable_notifications is False
        assert settings.features.enable_uptimerobot is False
        assert settings.features.enable_pushover is False
        assert settings.features.enable_vector_search is True

    def test_feature_flags_from_env(self):
        """Nested feature flags toggle via ``COACHIQ_FEATURES__ENABLE_*``."""
        with patch.dict(
            os.environ,
            _isolated_env(
                {
                    "COACHIQ_FEATURES__ENABLE_NOTIFICATIONS": "true",
                    "COACHIQ_FEATURES__ENABLE_VECTOR_SEARCH": "false",
                }
            ),
            clear=True,
        ):
            settings = _settings_no_env_file()

        assert settings.features.enable_notifications is True
        assert settings.features.enable_vector_search is False

    def test_settings_value_stable_after_init(self):
        """After construction, reading a field returns the same value.

        We don't enforce frozen=True (production needs occasional mutation
        for things like environment swaps in tests), but the field-read
        path is deterministic.
        """
        with patch.dict(os.environ, _isolated_env({}), clear=True):
            settings = _settings_no_env_file()
        assert settings.app_name == "CoachIQ"
        assert settings.app_name == "CoachIQ"  # Read again, same value


# ----------------------------------------------------------------------------
# TestGetSettings - module-level singleton
# ----------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSettings:
    """``get_settings()`` is the singleton accessor used by FastAPI deps."""

    def test_get_settings_returns_singleton(self):
        """Two calls to ``get_settings()`` return the same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_with_env_changes_after_cache_clear(self):
        """``get_settings()`` is ``@lru_cache``'d; clearing the cache picks up env."""
        get_settings.cache_clear()
        with patch.dict(
            os.environ,
            _isolated_env({"COACHIQ_DEBUG": "true", "COACHIQ_LOGGING__LEVEL": "DEBUG"}),
            clear=True,
        ):
            settings = get_settings()
            assert settings.debug is True
            assert settings.logging.level == "DEBUG"
        # Reset cache so other tests in the run aren't polluted.
        get_settings.cache_clear()


# ----------------------------------------------------------------------------
# Integration: real filesystem paths
# ----------------------------------------------------------------------------


@pytest.mark.integration
class TestSettingsIntegration:
    """Tests that touch the filesystem (via tmp_path) for the path fields."""

    def test_settings_with_real_paths(self, tmp_path):
        """When the path fields point at real files, the file content isn't
        loaded -- the Settings object just carries the Path through."""
        spec_file = tmp_path / "test_spec.json"
        mapping_file = tmp_path / "test_mapping.yml"
        spec_file.write_text('{"test": "spec"}')
        mapping_file.write_text("test: mapping")

        with patch.dict(
            os.environ,
            _isolated_env(
                {
                    "COACHIQ_RVC_SPEC_PATH": str(spec_file),
                    "COACHIQ_RVC_COACH_MAPPING_PATH": str(mapping_file),
                }
            ),
            clear=True,
        ):
            settings = _settings_no_env_file()

        assert settings.rvc_spec_path == spec_file
        assert settings.rvc_coach_mapping_path == mapping_file

    def test_settings_with_missing_optional_files(self):
        """Pointing the path fields at nonexistent files does NOT raise.

        These fields are documented as optional file references; the
        consumers (e.g. RVC decoder) handle missing files at use time, not
        at config construction.
        """
        with patch.dict(
            os.environ,
            _isolated_env(
                {
                    "COACHIQ_RVC_SPEC_PATH": "/nonexistent/spec.json",
                    "COACHIQ_RVC_COACH_MAPPING_PATH": "/nonexistent/mapping.yml",
                }
            ),
            clear=True,
        ):
            settings = _settings_no_env_file()

        assert str(settings.rvc_spec_path) == "/nonexistent/spec.json"
        assert str(settings.rvc_coach_mapping_path) == "/nonexistent/mapping.yml"

    def test_settings_env_file_loading(self):
        """Settings construction succeeds even without explicit env or .env tweaks."""
        with patch.dict(os.environ, _isolated_env({}), clear=True):
            settings = _settings_no_env_file()
        assert isinstance(settings.app_name, str)
        assert isinstance(settings.app_description, str)

    @pytest.mark.performance
    def test_settings_creation_performance(self):
        """Settings construction is fast enough that it isn't a bottleneck."""
        with patch.dict(os.environ, _isolated_env({}), clear=True):
            start_time = time.time()
            for _ in range(10):
                _settings_no_env_file()
            end_time = time.time()

        # 10 instances in <1s is comfortably above realistic perf.
        assert (end_time - start_time) < 1.0
