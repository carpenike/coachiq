"""
Tests for ``backend.core.logging_config`` and ``backend.core.sensitive_data_filter``.

Covers the unified dictConfig factory (``create_unified_log_config``), the
``JsonFormatter`` timestamp fix, JSON auto-detection from the environment,
rotating file handler wiring, the conservative ``SensitiveDataLogFilter``,
and the idempotency of ``setup_early_logging``.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import datetime
from unittest.mock import patch

import pytest

from backend.core.config import LoggingSettings
from backend.core.logging_config import (
    JsonFormatter,
    create_unified_log_config,
    setup_early_logging,
)
from backend.core.sensitive_data_filter import SensitiveDataLogFilter
from tests._helpers.settings import isolated_env

UVICORN_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture
def restore_logging():
    """Snapshot and restore root/uvicorn logger state around dictConfig calls."""
    root = logging.getLogger()
    saved_root_handlers = list(root.handlers)
    saved_root_level = root.level
    saved_uvicorn = {}
    for name in UVICORN_LOGGER_NAMES:
        uv_logger = logging.getLogger(name)
        saved_uvicorn[name] = (
            list(uv_logger.handlers),
            uv_logger.level,
            uv_logger.propagate,
        )

    yield

    root.handlers[:] = saved_root_handlers
    root.setLevel(saved_root_level)
    for name, (handlers, level, propagate) in saved_uvicorn.items():
        uv_logger = logging.getLogger(name)
        uv_logger.handlers[:] = handlers
        uv_logger.setLevel(level)
        uv_logger.propagate = propagate


def make_record(msg: str, args: tuple | None = None) -> logging.LogRecord:
    """Build a minimal log record for formatter/filter tests."""
    return logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg=msg,
        args=args,
        exc_info=None,
    )


@pytest.mark.unit
class TestCreateUnifiedLogConfig:
    """Test suite for create_unified_log_config."""

    def test_json_formatter_factory_path_and_dictconfig_applies(self, restore_logging):
        """Regression test: the JSON formatter factory must reference a real module.

        The previous factory string pointed at ``backend.core.logging_config_new``,
        which does not exist, so ``dictConfig`` crashed on every production start.
        """
        cfg = create_unified_log_config(LoggingSettings(json_format=True))

        assert cfg["formatters"]["json"]["()"] == "backend.core.logging_config.JsonFormatter"
        assert cfg["handlers"]["console"]["formatter"] == "json"

        # Must apply cleanly (this raised ImportError before the fix).
        logging.config.dictConfig(cfg)

    def test_auto_detect_json_in_production(self):
        """json_format=None auto-detects JSON when COACHIQ_ENVIRONMENT=production."""
        env = isolated_env({"COACHIQ_ENVIRONMENT": "production"})
        env.pop("LOG_FORMAT", None)
        env.pop("ENVIRONMENT", None)
        with patch.dict(os.environ, env, clear=True):
            cfg = create_unified_log_config(LoggingSettings())

        assert cfg["handlers"]["console"]["formatter"] == "json"
        assert "json" in cfg["formatters"]

    def test_auto_detect_no_json_in_development(self):
        """json_format=None does not select JSON in development."""
        env = isolated_env({"COACHIQ_ENVIRONMENT": "development"})
        env.pop("LOG_FORMAT", None)
        env.pop("ENVIRONMENT", None)
        with patch.dict(os.environ, env, clear=True):
            cfg = create_unified_log_config(LoggingSettings())

        assert cfg["handlers"]["console"]["formatter"] != "json"
        assert "json" not in cfg["formatters"]

    def test_explicit_json_format_overrides_environment(self):
        """An explicit json_format=False wins over a production environment."""
        env = isolated_env({"COACHIQ_ENVIRONMENT": "production"})
        env.pop("LOG_FORMAT", None)
        env.pop("ENVIRONMENT", None)
        with patch.dict(os.environ, env, clear=True):
            cfg = create_unified_log_config(LoggingSettings(json_format=False))

        assert cfg["handlers"]["console"]["formatter"] != "json"

    def test_file_handler_configuration(self, tmp_path):
        """log_to_file wires a RotatingFileHandler with the configured limits."""
        settings = LoggingSettings(
            log_to_file=True,
            log_file=tmp_path / "logs" / "x.log",
            json_format=False,
            colorize=False,
            max_bytes=12345,
            backup_count=3,
        )
        cfg = create_unified_log_config(settings)

        file_handler = cfg["handlers"]["file"]
        assert file_handler["class"] == "logging.handlers.RotatingFileHandler"
        assert file_handler["filename"] == str(tmp_path / "logs" / "x.log")
        assert file_handler["maxBytes"] == 12345
        assert file_handler["backupCount"] == 3
        assert file_handler["encoding"] == "utf-8"
        # Plain formatter for files (never colored - no ANSI codes in files).
        assert file_handler["formatter"] == "standard"
        assert "file" in cfg["loggers"][""]["handlers"]
        # Parent directory is created eagerly.
        assert (tmp_path / "logs").is_dir()

    def test_root_logger_debug_console_carries_configured_level(self):
        """Root logger is DEBUG; the console handler filters at the configured level."""
        cfg = create_unified_log_config(LoggingSettings(level="WARNING", json_format=True))

        assert cfg["loggers"][""]["level"] == "DEBUG"
        assert cfg["handlers"]["console"]["level"] == "WARNING"
        for name in UVICORN_LOGGER_NAMES:
            assert cfg["loggers"][name]["level"] == "WARNING"
            assert cfg["loggers"][name]["propagate"] is False

    def test_sensitive_filter_attached_to_console(self):
        """The redaction filter is registered and attached to the console handler."""
        cfg = create_unified_log_config(LoggingSettings(json_format=True))

        assert (
            cfg["filters"]["redact_sensitive"]["()"]
            == "backend.core.sensitive_data_filter.SensitiveDataLogFilter"
        )
        assert "redact_sensitive" in cfg["handlers"]["console"]["filters"]


@pytest.mark.unit
class TestJsonFormatter:
    """Test suite for JsonFormatter."""

    def test_timestamp_is_valid_iso8601(self):
        """The timestamp parses as ISO-8601 and contains no literal '%f'."""
        record = make_record("hello world")
        entry = json.loads(JsonFormatter().format(record))

        assert "%f" not in entry["timestamp"]
        parsed = datetime.fromisoformat(entry["timestamp"])
        assert parsed.tzinfo is not None

    def test_extra_fields_pass_through(self):
        """Extra fields set on the record appear in the JSON output."""
        record = make_record("payload")
        record.correlation_id = "abc-123"
        entry = json.loads(JsonFormatter().format(record))

        assert entry["message"] == "payload"
        assert entry["correlation_id"] == "abc-123"
        assert entry["service"] == "coachiq"


@pytest.mark.unit
class TestSensitiveDataLogFilter:
    """Test suite for the conservative logging redaction filter."""

    def test_jwt_token_redacted(self):
        record = make_record(
            "Received eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcDEF123-_x from client"
        )
        assert SensitiveDataLogFilter().filter(record) is True

        message = record.getMessage()
        assert "eyJhbGciOiJIUzI1NiJ9.***" in message
        assert "eyJzdWIiOiIxMjM0In0" not in message
        assert "abcDEF123-_x" not in message

    def test_password_key_value_redacted(self):
        record = make_record("login attempt with password=hunter22 failed")
        SensitiveDataLogFilter().filter(record)

        message = record.getMessage()
        assert "hunter22" not in message
        assert "password=***" in message

    def test_ordinary_ip_and_email_untouched(self):
        """IPs and emails stay readable - this filter is narrower than SensitiveDataFilter."""
        original = "client 192.168.1.10 connected as user@example.com"
        record = make_record(original)
        SensitiveDataLogFilter().filter(record)

        assert record.getMessage() == original

    def test_percent_style_args_still_render_when_nothing_matches(self):
        record = make_record("value is %s", args=("ok",))
        assert SensitiveDataLogFilter().filter(record) is True

        assert record.getMessage() == "value is ok"
        assert record.args == ("ok",)

    def test_credit_card_redacted(self):
        record = make_record("charged card 4111-1111-1111-1234 successfully")
        SensitiveDataLogFilter().filter(record)

        message = record.getMessage()
        assert "4111-1111-1111-1234" not in message
        assert "****-****-****-1234" in message


@pytest.mark.unit
class TestSetupEarlyLogging:
    """Test suite for setup_early_logging idempotency."""

    def test_noop_when_root_already_has_handlers(self, restore_logging):
        """A pre-configured root logger (e.g. via uvicorn dictConfig) is left alone."""
        root = logging.getLogger()
        dummy = logging.NullHandler()
        root.handlers[:] = [dummy]

        setup_early_logging()

        assert root.handlers == [dummy]
