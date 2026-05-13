"""
Test the new persistence fixtures to ensure they work correctly.

This test module validates that the updated test configuration provides
real SQLite database files for more realistic testing scenarios.
"""

from pathlib import Path

import pytest

from backend.services.database_engine import DatabaseSettings
from backend.services.database_manager import DatabaseManager


def test_database_path_fixture(test_database_path: Path) -> None:
    """Test that database path fixture creates a valid temporary path."""
    assert isinstance(test_database_path, Path)
    assert test_database_path.name == "test_coachiq.db"
    assert "coachiq_test_" in str(test_database_path.parent)


def test_database_settings_fixture(test_database_settings: DatabaseSettings) -> None:
    """Test that database settings fixture is configured correctly."""
    assert isinstance(test_database_settings, DatabaseSettings)
    assert test_database_settings.backend.value == "sqlite"
    # Test timeout is configured for testing environment
    assert test_database_settings.sqlite_timeout == 10  # noqa: PLR2004
    assert test_database_settings.pool_size == 1
    assert test_database_settings.max_overflow == 0
    assert "test_coachiq.db" in test_database_settings.sqlite_path


@pytest.mark.asyncio
async def test_database_manager_fixture(test_database_manager: DatabaseManager) -> None:
    """Test that database manager fixture creates a working database."""
    assert isinstance(test_database_manager, DatabaseManager)
    assert test_database_manager.backend == "sqlite"

    # Test that the database is actually initialized and working
    health_check = await test_database_manager.health_check()
    assert health_check is True

    # Test that we can get a session and execute a query
    async with test_database_manager.get_session() as session:
        assert session is not None
        # Simple test query to verify the database is working
        from sqlalchemy import text

        result = await session.execute(text("SELECT 1 as test_value"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1


@pytest.mark.skip(
    reason=(
        "test_persistence_feature fixture in tests/conftest.py:127 returns "
        "None now -- the persistence-feature concept was retired (persistence "
        "is now default; see commented-out body of the fixture). The "
        "fixture itself should arguably be removed in a follow-up cleanup, "
        "along with this test and the client_with_persistence fixture wiring "
        "below. Skipping rather than rewriting because the feature pattern "
        "is gone, not just the test contract -- this is Pattern A."
    )
)
@pytest.mark.asyncio
async def test_persistence_feature_fixture(test_persistence_feature: object) -> None:
    """Test that persistence feature fixture is properly initialized."""
    # Verify the persistence feature is available
    assert test_persistence_feature is not None

    # Verify it has the expected database manager
    assert hasattr(test_persistence_feature, "_database_manager")
    assert test_persistence_feature._database_manager is not None  # noqa: SLF001

    # Test that the database manager is working through the feature
    db_manager = test_persistence_feature._database_manager  # noqa: SLF001
    health_check = await db_manager.health_check()
    assert health_check is True


def test_client_with_persistence_fixture_exists() -> None:
    """Test that client with persistence fixture is available."""
    # Just test that the fixture exists in conftest.py
    # This avoids complex app startup issues during testing
    from tests.conftest import client_with_persistence

    assert client_with_persistence is not None


def test_fixture_isolation(test_database_path: Path) -> None:
    """Test that each test gets its own isolated database."""
    # This test ensures that the database path is unique per test
    # The temporary directory should be unique for this test instance
    assert test_database_path.exists() is False  # File shouldn't exist yet

    # Create the file to verify it's writable
    test_database_path.touch()
    assert test_database_path.exists() is True

    # The cleanup should happen automatically when the fixture scope ends
