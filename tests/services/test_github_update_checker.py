"""
Test suite for GitHubUpdateChecker.

Tests the GitHub update checker service, including:
- Background update checking
- Release information caching
- GitHub API interaction
- Error handling and rate limiting
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from backend.services.github_update_checker import (
    GitHubUpdateChecker,
    build_github_api_url,
    get_github_repo,
)

# ================================
# Test Fixtures
# ================================


@pytest.fixture
def update_checker():
    """Create GitHubUpdateChecker instance for testing."""
    return GitHubUpdateChecker()


@pytest.fixture
def mock_httpx_response():
    """Create a mock httpx response for testing."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tag_name": "v1.2.3",
        "name": "Release 1.2.3",
        "published_at": "2023-01-01T00:00:00Z",
        "html_url": "https://github.com/owner/repo/releases/tag/v1.2.3",
        "body": "Release notes here",
        "prerelease": False,
        "draft": False,
    }
    mock_response.raise_for_status = Mock()
    return mock_response


# ================================
# Utility Function Tests
# ================================


class TestUtilityFunctions:
    """Test utility functions."""

    @patch.dict("os.environ", {"GITHUB_OWNER": "testowner", "GITHUB_REPO": "testrepo"})
    def test_get_github_repo_from_env(self):
        """Test getting GitHub repo from environment variables."""
        owner, repo = get_github_repo()
        assert owner == "testowner"
        assert repo == "testrepo"

    @patch.dict("os.environ", {}, clear=True)
    def test_get_github_repo_defaults(self):
        """Test getting GitHub repo with default values."""
        owner, repo = get_github_repo()
        assert owner == "carpenike"
        assert repo == "coachiq"

    def test_build_github_api_url(self):
        """Test building GitHub API URL."""
        url = build_github_api_url("owner", "repo")
        expected = "https://api.github.com/repos/owner/repo/releases/latest"
        assert url == expected


# ================================
# Core Functionality Tests
# ================================


class TestGitHubUpdateCheckerInitialization:
    """Test GitHubUpdateChecker initialization."""

    def test_init_default_state(self, update_checker):
        """Test initial state of update checker."""
        assert update_checker.latest_version is None
        assert update_checker.last_checked == 0
        assert update_checker.last_success == 0
        assert update_checker.error is None
        assert update_checker.latest_release_info is None
        assert update_checker._task is None


# ================================
# Service Lifecycle Tests
# ================================


class TestServiceLifecycle:
    """Test service start/stop lifecycle."""

    async def test_start_service(self, update_checker):
        """Test starting the update checker service."""
        assert update_checker._task is None

        await update_checker.start()

        assert update_checker._task is not None
        assert isinstance(update_checker._task, asyncio.Task)

        # Clean up
        await update_checker.stop()

    async def test_start_service_already_running(self, update_checker):
        """Test starting service when already running."""
        await update_checker.start()
        task1 = update_checker._task

        # Starting again should not create new task
        await update_checker.start()
        task2 = update_checker._task

        assert task1 is task2

        # Clean up
        await update_checker.stop()

    async def test_stop_service(self, update_checker):
        """Test stopping the update checker service."""
        await update_checker.start()
        assert update_checker._task is not None

        await update_checker.stop()

        assert update_checker._task is None

    async def test_stop_service_not_running(self, update_checker):
        """Test stopping service when not running."""
        assert update_checker._task is None

        # Should not raise an error
        await update_checker.stop()

        assert update_checker._task is None

    async def test_service_lifecycle_multiple_cycles(self, update_checker):
        """Test multiple start/stop cycles."""
        # First cycle
        await update_checker.start()
        assert update_checker._task is not None
        await update_checker.stop()
        assert update_checker._task is None

        # Second cycle
        await update_checker.start()
        assert update_checker._task is not None
        await update_checker.stop()
        assert update_checker._task is None


# ================================
# Update Checking Tests
# ================================


class TestUpdateChecking:
    """Test update checking functionality."""

    @patch("backend.services.github_update_checker.httpx.AsyncClient")
    async def test_check_now_success(self, mock_client_class, update_checker, mock_httpx_response):
        """Test successful update check."""
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_httpx_response

        await update_checker.check_now()

        assert update_checker.latest_version == "1.2.3"  # Tag stripped of 'v'
        assert update_checker.error is None
        assert update_checker.last_success > 0
        assert update_checker.latest_release_info is not None

    @patch("backend.services.github_update_checker.httpx.AsyncClient")
    async def test_check_now_http_error(self, mock_client_class, update_checker):
        """Test update check with HTTP error."""
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=Mock()
        )

        await update_checker.check_now()

        assert update_checker.latest_version is None
        assert update_checker.error is not None
        assert update_checker.last_success == 0

    async def test_force_check_delegates_to_check_now(self, update_checker):
        """Test that force_check delegates to check_now."""
        with patch.object(update_checker, "check_now") as mock_check:
            await update_checker.force_check()
            mock_check.assert_called_once()


# ================================
# Data Access Tests
# ================================


class TestDataAccess:
    """Test data access methods."""

    def test_get_status_no_data(self, update_checker):
        """Test getting status when no data is available."""
        result = update_checker.get_status()

        assert result["latest_version"] is None
        assert result["last_checked"] == 0
        assert result["last_success"] == 0
        assert result["error"] is None
        assert result["latest_release_info"] is None
        assert "repo" in result
        assert "api_url" in result

    def test_get_status_with_data(self, update_checker):
        """Test getting status with data."""
        # Set some test data
        update_checker.latest_version = "1.2.3"
        update_checker.last_checked = time.time()
        update_checker.last_success = time.time()
        update_checker.error = None
        update_checker.latest_release_info = {"name": "Test Release"}

        result = update_checker.get_status()

        assert result["latest_version"] == "1.2.3"
        assert result["last_checked"] > 0
        assert result["last_success"] > 0
        assert result["error"] is None
        assert result["latest_release_info"] == {"name": "Test Release"}

    def test_get_status_with_error(self, update_checker):
        """Test getting status when there's an error."""
        update_checker.error = "Connection failed"
        update_checker.last_checked = time.time()

        result = update_checker.get_status()

        assert result["error"] == "Connection failed"
        assert result["latest_version"] is None


# ================================
# Integration Tests
# ================================


class TestServiceIntegration:
    """Test service integration scenarios."""

    async def test_complete_update_workflow(self, update_checker):
        """Test complete update checking workflow."""
        with patch("backend.services.github_update_checker.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            mock_response.json.return_value = {
                "tag_name": "v2.0.0",
                "name": "Major Release",
                "published_at": "2023-06-01T00:00:00Z",
            }
            mock_client.get.return_value = mock_response

            # Start service
            await update_checker.start()

            # Force a check
            await update_checker.force_check()

            # Verify data is available
            assert update_checker.latest_version == "2.0.0"

            status = update_checker.get_status()
            assert status["latest_version"] == "2.0.0"

            # Stop service
            await update_checker.stop()

    async def test_service_resilience(self, update_checker):
        """Test service resilience to various failure modes.

        Updated 2026-05-13: ``check_now()`` is the resilience boundary --
        production wraps the entire HTTP-fetch body in ``try/except
        Exception`` (see ``backend/services/github_update_checker.py:79+``)
        and writes the error to ``self.error`` instead of propagating.
        ``force_check()`` is a thin wrapper that just calls ``check_now()``
        and does NOT have its own try/except.

        The previous test mocked ``check_now`` directly to raise, which
        bypasses the production try/except entirely and forces
        ``force_check`` to propagate. To exercise the actual resilience
        contract, we instead mock the underlying ``httpx.AsyncClient``
        so the production try/except in ``check_now`` fires.
        """
        # Start service
        await update_checker.start()

        # Patch the AsyncClient so check_now's internal try/except
        # actually exercises (vs. mocking check_now itself, which
        # bypasses the resilience layer).
        with patch("backend.services.github_update_checker.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            # Network failure: HTTPStatusError from the GET
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "Network down", request=Mock(), response=Mock()
            )
            await update_checker.force_check()
            # Production should record the error rather than propagate.
            assert update_checker.error is not None, (
                "check_now should record the network error in self.error"
            )

            # Generic exception
            mock_client.get.side_effect = Exception("Unknown error")
            await update_checker.force_check()
            assert update_checker.error is not None

            # Recovery: a well-formed response should clear the error.
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_response.json.return_value = {
                "tag_name": "v1.0.0",
                "name": "Recovery Release",
                "published_at": "2024-01-01T00:00:00Z",
                "body": "Recovered",
                "html_url": "https://example.com",
                "discussion_url": None,
            }
            mock_client.get.side_effect = None
            mock_client.get.return_value = mock_response
            await update_checker.force_check()

        # Service should still be running
        assert update_checker._task is not None

        await update_checker.stop()

    async def test_concurrent_operations(self, update_checker):
        """Test concurrent service operations."""
        # Start service
        await update_checker.start()

        # Run multiple concurrent operations
        tasks = [
            asyncio.create_task(update_checker.force_check()),
            asyncio.create_task(update_checker.force_check()),
        ]

        # Should complete without issues
        await asyncio.gather(*tasks, return_exceptions=True)

        await update_checker.stop()
