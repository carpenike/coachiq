"""
Logging configuration module for the coachiq backend.

Provides the unified dictConfig used by both the application and uvicorn
(``create_unified_log_config`` / ``configure_unified_logging``), an idempotent
early-startup configurator (``setup_early_logging``), a JSON formatter for
journald/log-aggregation environments, and the hook that attaches the
WebSocket log handler for live log streaming (``update_websocket_logging``).
"""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

try:
    import coloredlogs

    HAS_COLOREDLOGS = True
except ImportError:
    HAS_COLOREDLOGS = False

from backend.core.config import LoggingSettings
from backend.core.sensitive_data_filter import SensitiveDataLogFilter

logger = logging.getLogger(__name__)


def _get_environment() -> str:
    """Return the deployment environment name in lowercase.

    Reads ``COACHIQ_ENVIRONMENT`` first (set by the production systemd unit),
    falling back to ``ENVIRONMENT``, then ``"development"``.
    """
    return (os.getenv("COACHIQ_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "development").lower()


def _should_use_json(settings: LoggingSettings | None = None) -> bool:
    """Decide whether JSON log output should be used.

    An explicit ``settings.json_format`` wins; otherwise JSON is auto-detected
    from ``LOG_FORMAT=json`` or a production/staging environment.

    Args:
        settings: Optional logging settings carrying an explicit override.

    Returns:
        True if JSON log output should be used.
    """
    if settings is not None and settings.json_format is not None:
        return settings.json_format
    return os.getenv("LOG_FORMAT", "").lower() == "json" or _get_environment() in (
        "production",
        "staging",
    )


class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging compatible with journald and WebSocket streaming.

    Formats log records as JSON with contextual fields for modern log aggregation
    and analysis tools.
    """

    def __init__(self, service_name: str = "coachiq") -> None:
        """
        Initialize the JSON formatter.

        Args:
            service_name (str): Name of the service for log identification
        """
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as JSON.

        Args:
            record (logging.LogRecord): The log record to format

        Returns:
            str: JSON-formatted log entry
        """
        # Create base log entry with standard fields
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "service": self.service_name,
            "thread": record.thread,
            "thread_name": record.threadName,
        }

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add any extra fields from the log record
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "exc_info",
                "exc_text",
                "stack_info",
            }:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def setup_early_logging() -> None:
    """
    Set up basic logging early in the application startup process.

    This function provides minimal logging configuration before the full
    application configuration is loaded. It's useful for logging during
    the initial startup phase. It applies coloredlogs if available for
    consistent colored output from the very beginning.

    Idempotent: if the root logger already has handlers (e.g. uvicorn already
    applied the unified dictConfig before backend.main was imported), this
    function returns immediately without reconfiguring.
    """
    if logging.getLogger().handlers:
        return

    log_level_str = (
        os.getenv("COACHIQ_LOGGING__LEVEL") or os.getenv("LOG_LEVEL") or "INFO"
    ).upper()
    log_level_int = getattr(logging, log_level_str, logging.INFO)

    # Check if we should use JSON format (production/staging environment)
    use_json_format = _get_environment() in ("production", "staging")

    if use_json_format:
        # Use basic configuration with JSON-like format for production
        logging.basicConfig(
            level=log_level_int,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",  # Consistent date format without milliseconds
            force=True,  # Override any existing configuration
        )
        logger.info(f"Early JSON-compatible logging configured with level: {log_level_str}")
    elif HAS_COLOREDLOGS:
        # Apply coloredlogs for enhanced early startup output
        coloredlogs.install(
            level=log_level_int,
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",  # Consistent date format without milliseconds
            reconfigure=True,
            field_styles={
                "asctime": {"color": "cyan"},  # Subtle color for timestamp
                "name": {"color": "blue"},
                "levelname": {"bold": True},  # Bold levelname, inherits level color
                # "message": {"color": "white"},  # Default terminal color for messages
            },
            level_styles={
                "debug": {"color": "green"},  # Green for debug (less severe)
                "info": {"color": "white"},  # Default/neutral for info
                "warning": {"color": "yellow"},
                "error": {"color": "red"},
                "critical": {"color": "red", "bold": True},
            },
        )
        logger.info(f"Early coloredlogs configured with level: {log_level_str}")
    else:
        # Fallback to basic configuration
        logging.basicConfig(
            level=log_level_int,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",  # Consistent date format without milliseconds
            force=True,  # Override any existing configuration
        )
        logger.info(f"Early basic logging configured with level: {log_level_str}")


def update_websocket_logging(websocket_service) -> None:
    """
    Add or update WebSocket logging to an already configured logger.

    This function is useful when the WebSocket manager becomes available
    after the initial logging configuration.

    Args:
        websocket_service: WebSocket service for log streaming
    """
    root_logger = logging.getLogger()

    # Check if WebSocket handler already exists
    from backend.services.system.websocket_service import WebSocketLogHandler

    has_ws_handler = any(
        isinstance(handler, WebSocketLogHandler) for handler in root_logger.handlers
    )

    if not has_ws_handler:
        try:
            import asyncio

            from backend.services.system.websocket_service import WebSocketLogHandler

            # Get the current event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("No event loop available for WebSocket logging")
                return

            ws_handler = WebSocketLogHandler(websocket_service, loop)
            # Always set WebSocket handler to DEBUG to send all logs
            # (the root logger is configured at DEBUG; the console handler
            # filters at the configured level). Let the frontend handle
            # filtering based on client preferences.
            ws_handler.setLevel(logging.DEBUG)

            # Always use a plain formatter: copying the console formatter would
            # stream coloredlogs' ANSI escape codes to WebSocket clients in dev.
            ws_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )

            # Redact secrets before they leave the process over the WebSocket.
            ws_handler.addFilter(SensitiveDataLogFilter())

            root_logger.addHandler(ws_handler)
            logger.info("WebSocket log handler added to existing logging configuration")
        except Exception as e:
            logger.warning(f"Failed to add WebSocket log handler: {e}")


def create_unified_log_config(
    settings: LoggingSettings | None = None,
) -> dict:
    """
    Create a unified logging configuration dictionary for both application and Uvicorn loggers.

    This function generates a logging configuration that applies consistent
    formatting to all loggers (root, uvicorn, uvicorn.error, uvicorn.access).
    The root logger is set to DEBUG while the console/file handlers carry the
    configured level, so the WebSocket log handler (attached later at DEBUG via
    update_websocket_logging) receives debug records while console output stays
    filtered at the configured level.

    Args:
        settings (LoggingSettings | None): Logging configuration settings.
                                         If None, defaults will be used.

    Returns:
        dict: Logging configuration dictionary compatible with logging.config.dictConfig
              and uvicorn's log_config parameter.
    """
    # Get configuration from environment or settings
    log_level_str = settings.level if settings else os.getenv("LOG_LEVEL", "INFO").upper()

    use_json_format = _should_use_json(settings)

    # Convert log level string to integer
    log_level_int = getattr(logging, log_level_str, None)
    if not isinstance(log_level_int, int):
        logger.warning(f"Invalid LOG_LEVEL '{log_level_str}'. Defaulting to INFO.")
        log_level_str = "INFO"

    # Create the base logging configuration
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            # Plain formatter, always available (used for file output in
            # non-JSON mode so ANSI codes never end up in files).
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",  # Consistent date format without milliseconds
            },
        },
        "filters": {
            "redact_sensitive": {
                "()": "backend.core.sensitive_data_filter.SensitiveDataLogFilter",
            },
        },
        "handlers": {},
        "loggers": {},
    }

    use_colored = (
        not use_json_format and HAS_COLOREDLOGS and (settings is None or settings.colorize)
    )

    if use_json_format:
        # Use JsonFormatter for all logs
        log_config["formatters"]["json"] = {
            "()": "backend.core.logging_config.JsonFormatter",
            "service_name": "coachiq",
        }
        console_formatter = "json"
    elif use_colored:
        # For development with coloredlogs, use ColoredFormatter directly
        # to ensure consistent styling across all loggers including uvicorn
        log_config["formatters"]["colored"] = {
            "()": "coloredlogs.ColoredFormatter",
            "fmt": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",  # Consistent date format without milliseconds
            "level_styles": {
                "debug": {"color": "green"},  # Green for debug (less severe)
                "info": {"color": "white"},  # Default/neutral for info
                "warning": {"color": "yellow"},
                "error": {"color": "red"},
                "critical": {"color": "red", "bold": True},
            },
            "field_styles": {
                "asctime": {"color": "cyan"},  # Subtle color for timestamp
                "name": {"color": "blue"},
                "levelname": {"bold": True},  # Bold levelname, inherits level color
                # "message": {"color": "white"},  # Default terminal color for messages
            },
        }
        console_formatter = "colored"
    else:
        # Fallback to the plain formatter
        console_formatter = "standard"

    # Console output is filtered at the configured level; the root logger stays
    # at DEBUG so handlers attached later (WebSocket streaming) can see debug records.
    log_config["handlers"]["console"] = {
        "class": "logging.StreamHandler",
        "formatter": console_formatter,
        "stream": "ext://sys.stdout",
        "level": log_level_str,
        "filters": ["redact_sensitive"],
    }

    handler_names = ["console"]

    # Optional rotating file handler (honors settings.log_to_file).
    log_file = settings.log_file or settings.file if settings else None
    if settings and settings.log_to_file and log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_config["handlers"]["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_path),
                "maxBytes": settings.max_bytes,
                "backupCount": settings.backup_count,
                "encoding": "utf-8",
                "level": log_level_str,
                # Never the colored formatter: no ANSI codes in files.
                "formatter": "json" if use_json_format else "standard",
                "filters": ["redact_sensitive"],
            }
            handler_names.append("file")
        except Exception as e:
            logger.warning("Failed to configure file logging for %s: %s", log_file, e)

    # Configure all loggers to use the same handlers. The root logger is DEBUG
    # (handlers filter per-level); uvicorn loggers stay at the configured level.
    log_config["loggers"] = {
        "": {  # Root logger
            "handlers": list(handler_names),
            "level": "DEBUG",
        },
        "uvicorn": {
            "handlers": list(handler_names),
            "level": log_level_str,
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": list(handler_names),
            "level": log_level_str,
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": list(handler_names),
            "level": log_level_str,
            "propagate": False,
        },
    }

    return log_config


def configure_unified_logging(
    settings: LoggingSettings | None = None,
) -> tuple[dict, logging.Logger]:
    """
    Configure unified logging for both application and Uvicorn.

    This function creates a logging configuration that can be used with
    uvicorn.run(log_config=...). The WebSocket log handler for /ws/logs is
    attached separately at startup via update_websocket_logging().

    Args:
        settings (LoggingSettings | None): Logging configuration settings.

    Returns:
        tuple[dict, logging.Logger]: The log configuration dict and configured root logger.
    """
    # Create the unified log configuration
    log_config = create_unified_log_config(settings)

    # Apply the configuration
    import logging.config

    logging.config.dictConfig(log_config)

    root_logger = logging.getLogger()

    return log_config, root_logger
