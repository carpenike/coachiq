"""Tests for ``backend.services.logging.log_history`` (journalctl subprocess path).

All subprocess interaction is mocked: this container has no populated journal,
and the tests must pin down argv construction (level->priority mapping, unit
scoping, since/until, cursor) and the --reverse + --cursor pagination
semantics (inclusive cursor entry skipped so pages are strictly older).
"""

from __future__ import annotations

import datetime
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services.logging import log_history


def journal_line(
    cursor: str,
    message: str = "plain text line",
    priority: str = "6",
    timestamp_us: int = 1_750_000_000_000_000,
    identifier: str = "coachiq",
) -> str:
    """Build one journalctl -o json output line."""
    return json.dumps(
        {
            "__CURSOR": cursor,
            "__REALTIME_TIMESTAMP": str(timestamp_us),
            "MESSAGE": message,
            "PRIORITY": priority,
            "SYSLOG_IDENTIFIER": identifier,
        }
    )


def structured_message(message: str, logger: str = "backend.foo", level: str = "ERROR") -> str:
    """Build a MESSAGE payload shaped like our JsonFormatter output."""
    return json.dumps(
        {
            "timestamp": "2026-07-08T12:00:00+00:00",
            "level": level,
            "message": message,
            "logger": logger,
            "service": "coachiq",
        }
    )


def fake_run(stdout: str, returncode: int = 0, stderr: str = ""):
    """Return a subprocess.run replacement yielding a canned result."""

    def _run(cmd, **kwargs):
        _run.last_cmd = cmd
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    _run.last_cmd = None
    return _run


@pytest.fixture(autouse=True)
def journald_forced_available(monkeypatch):
    """Force the availability probe on and reset its cache around each test."""
    log_history._probe_journald.cache_clear()
    monkeypatch.setattr(log_history, "is_journald_available", lambda: True)
    yield
    log_history._probe_journald.cache_clear()


@pytest.fixture(autouse=True)
def default_unit(monkeypatch):
    """Pin the configured journald unit so tests don't depend on env settings."""
    monkeypatch.setattr(log_history, "_get_journald_unit", lambda: "coachiq")


@pytest.mark.unit
class TestCommandConstruction:
    """journalctl argv construction."""

    def test_base_command_shape(self):
        run = fake_run("")
        with patch.object(log_history.subprocess, "run", run):
            log_history.query_journald_logs(limit=100)

        cmd = run.last_cmd
        assert cmd[0] == "journalctl"
        for flag in ("-o", "--no-pager", "--quiet", "--reverse"):
            assert flag in cmd
        assert cmd[cmd.index("-o") + 1] == "json"
        # limit + 1 rows to detect has_more (no cursor)
        assert cmd[cmd.index("-n") + 1] == "101"
        assert cmd[cmd.index("-u") + 1] == "coachiq"

    @pytest.mark.parametrize(
        ("level", "priority"),
        [("CRITICAL", "2"), ("ERROR", "3"), ("warning", "4"), ("info", "6"), ("DEBUG", "7")],
    )
    def test_level_maps_to_syslog_priority(self, level, priority):
        run = fake_run("")
        with patch.object(log_history.subprocess, "run", run):
            log_history.query_journald_logs(level=level)

        cmd = run.last_cmd
        assert cmd[cmd.index("-p") + 1] == priority

    def test_unknown_level_omits_priority_flag(self):
        run = fake_run("")
        with patch.object(log_history.subprocess, "run", run):
            log_history.query_journald_logs(level="bogus")

        assert "-p" not in run.last_cmd

    def test_since_until_cursor_args(self):
        run = fake_run("")
        since = datetime.datetime(2026, 7, 1, 10, 0, 0, tzinfo=datetime.UTC)
        until = datetime.datetime(2026, 7, 2, 10, 0, 0, tzinfo=datetime.UTC)
        with patch.object(log_history.subprocess, "run", run):
            log_history.query_journald_logs(since=since, until=until, cursor="cur-1", limit=50)

        cmd = run.last_cmd
        assert cmd[cmd.index("--since") + 1] == since.isoformat()
        assert cmd[cmd.index("--until") + 1] == until.isoformat()
        assert "--cursor=cur-1" in cmd
        # limit + 2 when a cursor is passed (inclusive cursor row gets skipped)
        assert cmd[cmd.index("-n") + 1] == "52"

    def test_no_unit_flag_when_unit_unset(self, monkeypatch):
        monkeypatch.setattr(log_history, "_get_journald_unit", lambda: None)
        run = fake_run("")
        with patch.object(log_history.subprocess, "run", run):
            log_history.query_journald_logs()

        assert "-u" not in run.last_cmd


@pytest.mark.unit
class TestParsing:
    """JSON-line parsing: structured MESSAGE extraction and plain fallback."""

    def test_structured_message_extracted(self):
        line = journal_line(
            "c1", message=structured_message("boom happened", "backend.can.bus", "ERROR")
        )
        run = fake_run(line + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(limit=10)

        (entry,) = result["entries"]
        assert entry["message"] == "boom happened"
        assert entry["module"] == "backend.can.bus"
        assert entry["level"] == 3  # ERROR -> syslog 3
        assert entry["cursor"] == "c1"

    def test_plain_message_fallback_uses_priority(self):
        line = journal_line("c2", message="Started CoachIQ.", priority="5", identifier="systemd")
        run = fake_run(line + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(limit=10)

        (entry,) = result["entries"]
        assert entry["message"] == "Started CoachIQ."
        assert entry["module"] == "systemd"
        assert entry["level"] == 5

    def test_timestamp_from_realtime_microseconds(self):
        ts_us = 1_750_000_000_123_456
        line = journal_line("c3", timestamp_us=ts_us)
        run = fake_run(line + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(limit=10)

        (entry,) = result["entries"]
        expected = datetime.datetime.fromtimestamp(ts_us / 1_000_000, tz=datetime.UTC)
        assert entry["timestamp"] == expected.isoformat()

    def test_module_filter_is_prefix_match_post_parse(self):
        lines = "\n".join(
            [
                journal_line("c1", message=structured_message("a", "backend.can.bus")),
                journal_line("c2", message=structured_message("b", "backend.core.config")),
                journal_line("c3", message=structured_message("c", "backend.can.interface")),
            ]
        )
        run = fake_run(lines + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(module="backend.can", limit=10)

        assert [e["message"] for e in result["entries"]] == ["a", "c"]
        # next_cursor still tracks the raw page (pre-module-filter) tail
        assert result["next_cursor"] == "c3"

    def test_malformed_lines_are_skipped(self):
        lines = "not json at all\n" + journal_line("c1", message="ok") + "\n"
        run = fake_run(lines)
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(limit=10)

        assert [e["message"] for e in result["entries"]] == ["ok"]


@pytest.mark.unit
class TestPagination:
    """--reverse + --cursor pagination semantics."""

    def test_single_page_no_more(self):
        lines = "\n".join(journal_line(f"c{i}", message=f"m{i}") for i in range(3))
        run = fake_run(lines + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(limit=10)

        assert len(result["entries"]) == 3
        assert result["has_more"] is False
        assert result["next_cursor"] == "c2"

    def test_full_page_sets_has_more_and_next_cursor(self):
        # limit=2 -> fetches 3 rows; 3 rows returned means another page exists.
        lines = "\n".join(journal_line(f"c{i}", message=f"m{i}") for i in range(3))
        run = fake_run(lines + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(limit=2)

        assert [e["message"] for e in result["entries"]] == ["m0", "m1"]
        assert result["has_more"] is True
        assert result["next_cursor"] == "c1"

    def test_cursor_continuation_skips_inclusive_cursor_row(self):
        # journalctl --reverse --cursor=c1 returns the c1 row first (inclusive),
        # then strictly older rows.
        lines = "\n".join(
            [
                journal_line("c1", message="m1"),
                journal_line("c2", message="m2"),
                journal_line("c3", message="m3"),
            ]
        )
        run = fake_run(lines + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(cursor="c1", limit=2)

        assert [e["message"] for e in result["entries"]] == ["m2", "m3"]
        assert result["next_cursor"] == "c3"
        assert result["has_more"] is False

    def test_cursor_row_not_first_is_not_skipped(self):
        # Defensive: if journalctl starts elsewhere (rotation), nothing is lost.
        lines = "\n".join([journal_line("other", message="m0"), journal_line("c9", message="m9")])
        run = fake_run(lines + "\n")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(cursor="c1", limit=5)

        assert [e["message"] for e in result["entries"]] == ["m0", "m9"]

    def test_empty_result(self):
        run = fake_run("")
        with patch.object(log_history.subprocess, "run", run):
            result = log_history.query_journald_logs(limit=10)

        assert result == {"entries": [], "next_cursor": None, "has_more": False}


@pytest.mark.unit
class TestFailureModes:
    """Timeouts, bad exit codes, and the availability probe."""

    def test_timeout_raises_runtime_error(self):
        def _run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

        with (
            patch.object(log_history.subprocess, "run", _run),
            pytest.raises(RuntimeError, match="timed out"),
        ):
            log_history.query_journald_logs()

    def test_bad_exit_code_raises_runtime_error(self):
        run = fake_run("", returncode=2, stderr="Failed to open journal")
        with (
            patch.object(log_history.subprocess, "run", run),
            pytest.raises(RuntimeError, match="Failed to open journal"),
        ):
            log_history.query_journald_logs()

    def test_probe_false_when_journalctl_missing(self, monkeypatch):
        log_history._probe_journald.cache_clear()
        monkeypatch.setattr(log_history.shutil, "which", lambda _: None)
        assert log_history._probe_journald() is False

    def test_probe_true_on_rc_zero(self, monkeypatch):
        log_history._probe_journald.cache_clear()
        monkeypatch.setattr(log_history.shutil, "which", lambda _: "/usr/bin/journalctl")
        with patch.object(log_history.subprocess, "run", fake_run("", returncode=0)):
            assert log_history._probe_journald() is True

    def test_probe_true_on_rc_one_without_stderr(self, monkeypatch):
        log_history._probe_journald.cache_clear()
        monkeypatch.setattr(log_history.shutil, "which", lambda _: "/usr/bin/journalctl")
        with patch.object(log_history.subprocess, "run", fake_run("", returncode=1)):
            assert log_history._probe_journald() is True

    def test_probe_false_on_rc_one_with_stderr(self, monkeypatch):
        log_history._probe_journald.cache_clear()
        monkeypatch.setattr(log_history.shutil, "which", lambda _: "/usr/bin/journalctl")
        with patch.object(
            log_history.subprocess, "run", fake_run("", returncode=1, stderr="permission denied")
        ):
            assert log_history._probe_journald() is False
