"""
Tests for the ConfigService.

ConfigService is a thin facade over RVCConfigRepository that exposes
sync queries for coach info / PGN names / DGN command-status pairs and
a few async wrappers for raw config content. Tests fully mock the
repository.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.common import CoachInfo
from backend.repositories import RVCConfigRepository
from backend.services.config_service import ConfigService


@pytest.fixture
def mock_repository() -> MagicMock:
    """Build a mock RVCConfigRepository with sensible defaults."""
    repo = MagicMock(spec=RVCConfigRepository)
    repo.get_coach_info = MagicMock(return_value=None)
    repo.get_pgn_name = MagicMock(return_value=None)
    repo.get_command_status_pair = MagicMock(return_value=None)
    repo.get_configuration_summary = MagicMock(
        return_value={
            "loaded": False,
            "pgn_count": 0,
            "device_count": 0,
        }
    )
    repo.is_loaded = MagicMock(return_value=False)
    repo.get_health_status = MagicMock(
        return_value={"healthy": False, "reason": "no config loaded"}
    )
    return repo


@pytest.fixture
def config_service(mock_repository) -> ConfigService:
    """Create ConfigService instance for testing."""
    return ConfigService(rvc_config_repository=mock_repository)


class TestConfigServiceConstruction:
    def test_init_stores_repository(self, mock_repository):
        service = ConfigService(rvc_config_repository=mock_repository)
        assert service._rvc_config_repo is mock_repository


class TestConfigServiceQueries:
    """Verify that each public method delegates correctly to the repository."""

    def test_get_coach_info_delegates(self, config_service, mock_repository):
        mock_repository.get_coach_info.return_value = CoachInfo(
            make="Entegra",
            model="Aspire",
            year="2021",
            trim="44R",
            filename="2021_Entegra_Aspire_44R.yml",
            notes=None,
        )

        result = config_service.get_coach_info()

        assert result is not None
        assert result.make == "Entegra"
        assert result.model == "Aspire"
        mock_repository.get_coach_info.assert_called_once()

    def test_get_coach_info_returns_none_when_unconfigured(self, config_service, mock_repository):
        mock_repository.get_coach_info.return_value = None

        assert config_service.get_coach_info() is None

    def test_get_pgn_name_delegates(self, config_service, mock_repository):
        mock_repository.get_pgn_name.return_value = "DC_DIMMER_COMMAND_2"

        result = config_service.get_pgn_name("0x1FEDA")

        assert result == "DC_DIMMER_COMMAND_2"
        mock_repository.get_pgn_name.assert_called_once_with("0x1FEDA")

    def test_get_pgn_name_returns_none_for_unknown_pgn(self, config_service, mock_repository):
        mock_repository.get_pgn_name.return_value = None

        assert config_service.get_pgn_name("0xFFFFF") is None

    def test_get_command_status_pair_delegates(self, config_service, mock_repository):
        mock_repository.get_command_status_pair.return_value = "1FFB1"

        result = config_service.get_command_status_pair("1FEDA")

        assert result == "1FFB1"
        mock_repository.get_command_status_pair.assert_called_once_with("1FEDA")

    def test_get_configuration_summary_delegates(self, config_service, mock_repository):
        expected = {"loaded": True, "pgn_count": 100, "device_count": 25}
        mock_repository.get_configuration_summary.return_value = expected

        assert config_service.get_configuration_summary() == expected
        mock_repository.get_configuration_summary.assert_called_once()

    def test_is_configuration_loaded_delegates(self, config_service, mock_repository):
        mock_repository.is_loaded.return_value = True

        assert config_service.is_configuration_loaded() is True
        mock_repository.is_loaded.assert_called_once()


class TestConfigServiceHealth:
    """get_health_status combines the repo's health with service-level fields."""

    def test_health_status_when_repo_healthy(self, config_service, mock_repository):
        mock_repository.get_health_status.return_value = {"healthy": True, "items": 100}
        mock_repository.is_loaded.return_value = True

        health = config_service.get_health_status()

        assert health["service"] == "ConfigService"
        assert health["healthy"] is True
        assert health["configuration_loaded"] is True
        assert health["repository_health"] == {"healthy": True, "items": 100}

    def test_health_status_when_repo_unhealthy(self, config_service, mock_repository):
        mock_repository.get_health_status.return_value = {
            "healthy": False,
            "reason": "config file missing",
        }
        mock_repository.is_loaded.return_value = False

        health = config_service.get_health_status()

        assert health["service"] == "ConfigService"
        assert health["healthy"] is False
        assert health["configuration_loaded"] is False
        assert health["repository_health"]["reason"] == "config file missing"

    def test_health_status_handles_missing_healthy_key(self, config_service, mock_repository):
        # If the repository's health dict omits 'healthy', the service should
        # default to False rather than raising KeyError.
        mock_repository.get_health_status.return_value = {"some_other_field": 1}
        mock_repository.is_loaded.return_value = False

        health = config_service.get_health_status()

        assert health["healthy"] is False


class TestConfigServiceAsyncContent:
    """The async content getters currently return placeholders."""

    @pytest.mark.asyncio
    async def test_get_device_mapping_content(self, config_service):
        result = await config_service.get_device_mapping_content()
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_spec_content(self, config_service):
        result = await config_service.get_spec_content()
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_config_status_combines_loaded_summary_and_health(
        self, config_service, mock_repository
    ):
        mock_repository.is_loaded.return_value = True
        mock_repository.get_configuration_summary.return_value = {
            "loaded": True,
            "pgn_count": 50,
        }
        mock_repository.get_health_status.return_value = {"healthy": True}

        status = await config_service.get_config_status()

        assert status["loaded"] is True
        assert status["summary"]["pgn_count"] == 50
        assert status["health"]["service"] == "ConfigService"
        assert status["health"]["healthy"] is True


class TestCreateConfigServiceFactory:
    """The factory function is documented as not-yet-wired."""

    def test_factory_raises_until_wired_to_service_registry(self):
        from backend.services.config_service import create_config_service

        with pytest.raises(NotImplementedError, match="ServiceRegistry"):
            create_config_service()
