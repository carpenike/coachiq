"""Regression tests for cwd-independent runtime write paths."""

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.core.config import Settings
from backend.integrations.can.can_bus_recorder import CANBusRecorder
from backend.services.notifications.notification_queue import NotificationQueue
from backend.services.notifications.notification_reporting_service import (
    NotificationReportingService,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_WRITE_NAMES = (
    Path("recordings"),
    Path("reports"),
    Path("templates") / "reports",
    Path("data") / "notifications.db",
)


def _snapshot_cwd_targets(working_directory: Path) -> dict[Path, bool]:
    """Capture whether legacy cwd-relative runtime write targets already exist."""
    return {
        working_directory / runtime_write_name: (working_directory / runtime_write_name).exists()
        for runtime_write_name in RUNTIME_WRITE_NAMES
    }


def _assert_no_new_cwd_targets(snapshot: dict[Path, bool]) -> None:
    """Verify the exercised code paths did not create cwd-relative runtime files."""
    for runtime_path, existed_before in snapshot.items():
        assert runtime_path.exists() is existed_before


@pytest.mark.asyncio
async def test_runtime_write_paths_self_anchor_across_process_cwd(tmp_path, monkeypatch):
    """Runtime write consumers resolve the same absolute paths from any process cwd."""
    data_dir = (tmp_path / "coachiq-data").resolve()
    observed_paths: list[tuple[Path, Path, Path]] = []

    for working_directory in (REPO_ROOT, REPO_ROOT / "backend", Path("/")):
        cwd_snapshot = _snapshot_cwd_targets(working_directory)
        monkeypatch.chdir(working_directory)

        settings = Settings(persistence={"data_dir": data_dir})
        settings.persistence.ensure_directories()

        recorder = CANBusRecorder(storage_path=settings.get_can_recorder_storage_path())
        reporting_service = NotificationReportingService(
            MagicMock(), MagicMock(), settings.persistence.get_reports_dir()
        )
        notification_queue = NotificationQueue(settings.notifications.queue_db_path)
        await notification_queue.initialize()
        await notification_queue.close()

        recorder_path = recorder.storage_path
        reports_path = reporting_service.reports_dir
        queue_path = notification_queue.db_path

        assert recorder_path == data_dir / "recordings"
        assert reports_path == data_dir / "reports"
        assert queue_path == data_dir / "databases" / "notifications.db"
        assert recorder_path.is_absolute()
        assert reports_path.is_absolute()
        assert queue_path.is_absolute()
        assert recorder_path.is_dir()
        assert reports_path.is_dir()
        assert queue_path.is_file()

        observed_paths.append((recorder_path, reports_path, queue_path))
        _assert_no_new_cwd_targets(cwd_snapshot)

    assert len(set(observed_paths)) == 1


@pytest.mark.asyncio
async def test_reporting_html_fallback_is_cwd_independent(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    """HTML reports use the resolved optional-template path and built-in fallback."""
    working_directory = tmp_path / "cwd"
    working_directory.mkdir()
    reports_dir = tmp_path / "coachiq-data" / "reports"
    cwd_snapshot = _snapshot_cwd_targets(working_directory)
    monkeypatch.chdir(working_directory)

    reporting_service = NotificationReportingService(MagicMock(), MagicMock(), reports_dir)

    caplog.set_level(logging.INFO)
    file_path, file_size = await reporting_service._generate_html_report(
        report_id="fallback-report",
        data={"report_type": "daily_digest", "summary": {"total_sent": 0}},
        template_name="daily_digest",
    )

    assert reporting_service.report_templates_dir == REPO_ROOT / "templates" / "reports"
    assert file_path == reports_dir / "fallback-report.html"
    assert file_path.is_file()
    assert file_size > 0
    assert "Daily Digest" in file_path.read_text(encoding="utf-8")
    assert "using built-in HTML fallback" in caplog.text
    _assert_no_new_cwd_targets(cwd_snapshot)


def test_runtime_path_settings_preserve_explicit_overrides(tmp_path):
    """Explicit absolute and in-memory paths are not re-anchored under data_dir."""
    data_dir = (tmp_path / "coachiq-data").resolve()
    explicit_recorder_dir = (tmp_path / "external-recordings").resolve()
    explicit_queue_db = (tmp_path / "external-notifications.db").resolve()

    settings = Settings(
        persistence={"data_dir": data_dir},
        can_recorder={"storage_path": explicit_recorder_dir},
        notifications={"queue_db_path": str(explicit_queue_db)},
    )
    memory_settings = Settings(
        persistence={"data_dir": data_dir}, notifications={"queue_db_path": ":memory:"}
    )

    assert settings.get_can_recorder_storage_path() == explicit_recorder_dir
    assert settings.notifications.queue_db_path == str(explicit_queue_db)
    assert memory_settings.notifications.queue_db_path == ":memory:"
    assert NotificationQueue(":memory:").db_path == ":memory:"
