"""Tests for dashboard preference persistence invariants."""

import asyncio
import hashlib

import pytest

from backend.repositories.dashboard_config_repository import DashboardConfigRepository


@pytest.mark.asyncio
async def test_first_preference_update_creates_user_without_deadlock(tmp_path) -> None:
    """The first synchronized save creates and persists a user configuration."""
    repository = DashboardConfigRepository(
        database_manager=None,
        performance_monitor=None,
        data_dir=tmp_path,
    )
    home = {
        "favoriteEntityIds": ["light-1"],
        "sectionOrder": ["zones", "alerts", "scenes", "power"],
        "hiddenSections": ["power"],
    }

    saved = await asyncio.wait_for(
        repository.update_preferences("user-123", {"home": home}),
        timeout=1.0,
    )
    reloaded = await repository.get_by_user_id("user-123")

    assert saved.preferences["home"] == home
    assert reloaded is saved
    digest = hashlib.sha256(b"user-123").hexdigest()
    assert (tmp_path / "dashboards" / f"{digest}.json").exists()


@pytest.mark.asyncio
async def test_identity_cannot_escape_dashboard_directory(tmp_path) -> None:
    """Authenticated identity text is never used as a filesystem path."""
    repository = DashboardConfigRepository(
        database_manager=None,
        performance_monitor=None,
        data_dir=tmp_path,
    )

    await repository.update_preferences("../../outside", {"home": {}})

    assert not (tmp_path / "outside.json").exists()
    assert len(list((tmp_path / "dashboards").glob("*.json"))) == 1
