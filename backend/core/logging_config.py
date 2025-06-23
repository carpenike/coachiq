"""
Logging configuration module for the coachiq backend.

This module provides comprehensive logging configuration that matches the functionality
of the old core_daemon system, including coloredlogs integration and WebSocket log handler support.
"""

import json
import logging
import os
import time
from typing import TYPE_CHECKING

try:
    import coloredlogs

    HAS_COLOREDLOGS = True
except ImportError:
    HAS_COLOREDLOGS = False

from backend.core.config import LoggingSettings

if TYPE_CHECKING:
    from backend.websocket.handlers import WebSocketManager

logger = logging.getLogger(__name__)


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
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime(record.created)),
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


def configure_logging(
    settings: LoggingSettings | None = None,
    websocket_manager: "WebSocketManager | None" = None,
) -> logging.Logger:
    """
    Configure comprehensive logging for the backend application.

    This function sets up logging similar to the old core_daemon system with:
    - Proper log level configuration from environment variables
    - JSON structured logging for production/journald compatibility
    - Coloredlogs integration for development console output (if available)
    - Optional WebSocket log handler for real-time log streaming
    - Proper handler management to avoid duplicates

    Args:
        settings (LoggingSettings | None): Logging configuration settings.
                                         If None, defaults will be used.
        websocket_manager (WebSocketManager | None): WebSocket manager for log streaming.
                                                    If provided, adds WebSocket log handler.

    Returns:
        logging.Logger: The configured root logger
    """
    root_logger = logging.getLogger()

    # Get configuration from environment or settings
    if settings:
        log_level_str = settings.level
        log_format = settings.format
        use_json_format = getattr(settings, "json_format", False)
    else:
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        # Use JSON format in production environments
        use_json_format = os.getenv("LOG_FORMAT", "").lower() == "json" or os.getenv(
            "ENVIRONMENT", "development"
        ).lower() in ("production", "staging")

    # Convert log level string to integer
    log_level_int = getattr(logging, log_level_str, None)
    if not isinstance(log_level_int, int):
        logger.warning(f"Invalid LOG_LEVEL '{log_level_str}'. Defaulting to INFO.")
        log_level_int = logging.INFO

    # Set the root logger's level to DEBUG to allow all messages through
    # Individual handlers will filter based on their own levels
    root_logger.setLevel(logging.DEBUG)

    # Remove any existing handlers to prevent duplicates
    # Important: iterate over a copy of the list for safe removal
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Configure console logging
    if use_json_format:
        # Use JSON formatter for production/journald compatibility
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level_int)
        json_formatter = JsonFormatter()
        console_handler.setFormatter(json_formatter)
        root_logger.addHandler(console_handler)
        logger.info("JSON structured logging configured for production/journald compatibility")
    elif HAS_COLOREDLOGS:
        # Use coloredlogs for enhanced console output in development
        coloredlogs.install(
            level=log_level_int,
            fmt=log_format,
            datefmt="%Y-%m-%d %H:%M:%S",  # Consistent date format without milliseconds
            logger=root_logger,
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
        logger.info("Coloredlogs configured for enhanced console output")
    else:
        # Fallback to basic console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level_int)
        # Use consistent date format without milliseconds
        formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        logger.info("Basic console logging configured (coloredlogs not available)")

    # Add WebSocket log handler if websocket_manager is provided
    if websocket_manager:
        try:
            import asyncio

            from backend.services.websocket_service import WebSocketLogHandler

            # Get the current event loop or create a new one
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            ws_handler = WebSocketLogHandler(websocket_service, loop)
            # Always set WebSocket handler to DEBUG to send all logs
            # Let frontend handle filtering based on client preferences
            ws_handler.setLevel(logging.DEBUG)

            # Always use JSON formatter for WebSocket logs to ensure consistent
            # structured data for frontend parsing
            ws_formatter = JsonFormatter()

            ws_handler.setFormatter(ws_formatter)
            root_logger.addHandler(ws_handler)
            logger.info("WebSocket log handler configured for real-time log streaming")
        except Exception as e:
            logger.warning(f"Failed to configure WebSocket log handler: {e}")

    # Add file logging if configured
    if settings and settings.log_to_file and settings.log_file:
        try:
            # Ensure log directory exists
            settings.log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(settings.log_file)
            file_handler.setLevel(log_level_int)

            # Use JSON formatter for file logs if configured
            file_formatter = (
                JsonFormatter()
                if use_json_format
                else logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")
            )

            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            logger.info(f"File logging configured: {settings.log_file}")
        except Exception as e:
            logger.warning(f"Failed to configure file logging: {e}")

    logger.info(f"Logging configured with level: {log_level_str}")

    # Ensure at least one handler is attached to the root logger
    if not root_logger.handlers:
        fallback_handler = logging.StreamHandler()
        fallback_handler.setLevel(log_level_int)
        fallback_handler.setFormatter(logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S"))
        root_logger.addHandler(fallback_handler)
        logger.warning(
            "No log handlers were attached after configuration; added fallback StreamHandler."
        )

    return root_logger


def setup_early_logging() -> None:
    """
    Set up basic logging early in the application startup process.

    This function provides minimal logging configuration before the full
    application configuration is loaded. It's useful for logging during
    the initial startup phase. It applies coloredlogs if available for
    consistent colored output from the very beginning.
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level_int = getattr(logging, log_level_str, logging.INFO)

    # Check if we should use JSON format (production/staging environment)
    use_json_format = os.getenv("ENVIRONMENT", "development").lower() in (
        "production",
        "staging",
    )

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
    from backend.services.websocket_service import WebSocketLogHandler

    has_ws_handler = any(
        isinstance(handler, WebSocketLogHandler) for handler in root_logger.handlers
    )

    if not has_ws_handler:
        try:
            import asyncio

            from backend.services.websocket_service import WebSocketLogHandler

            # Get the current event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("No event loop available for WebSocket logging")
                return

            ws_handler = WebSocketLogHandler(websocket_service, loop)
            # Always set WebSocket handler to DEBUG to send all logs
            # Let frontend handle filtering based on client preferences
            ws_handler.setLevel(logging.DEBUG)

            # Use the same formatter as existing handlers if available
            if root_logger.handlers and root_logger.handlers[0].formatter:
                ws_handler.setFormatter(root_logger.handlers[0].formatter)
            else:
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
                ws_handler.setFormatter(formatter)

            root_logger.addHandler(ws_handler)
            logger.info("WebSocket log handler added to existing logging configuration")
        except Exception as e:
            logger.warning(f"Failed to add WebSocket log handler: {e}")


def create_unified_log_config(
    settings: LoggingSettings | None = None,
) -> dict:
    """
    Create a unified logging configuration dictionary for both application and Uvicorn loggers.

    This function generates a logging configuration that applies the custom JsonFormatter
    to all loggers (root, uvicorn, uvicorn.error, uvicorn.access) ensuring consistent
    formatting across both application logs and Uvicorn service logs.

    Args:
        settings (LoggingSettings | None): Logging configuration settings.
                                         If None, defaults will be used.

    Returns:
        dict: Logging configuration dictionary compatible with logging.config.dictConfig
              and uvicorn's log_config parameter.
    """
    # Get configuration from environment or settings
    if settings:
        log_level_str = settings.level
        use_json_format = getattr(settings, "json_format", False)
    else:
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        # Use JSON format in production environments
        use_json_format = os.getenv("LOG_FORMAT", "").lower() == "json" or os.getenv(
            "ENVIRONMENT", "development"
        ).lower() in ("production", "staging")

    # Convert log level string to integer
    log_level_int = getattr(logging, log_level_str, None)
    if not isinstance(log_level_int, int):
        logger.warning(f"Invalid LOG_LEVEL '{log_level_str}'. Defaulting to INFO.")
        log_level_str = "INFO"

    # Create the base logging configuration
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {},
        "handlers": {},
        "loggers": {},
    }

    if use_json_format:
        # Use JsonFormatter for all logs
        log_config["formatters"]["json"] = {
            "()": "backend.core.logging_config_new.JsonFormatter",
            "service_name": "coachiq",
        }

        log_config["handlers"]["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        }
    elif HAS_COLOREDLOGS:
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

        log_config["handlers"]["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "colored",
            "stream": "ext://sys.stdout",
        }
    else:
        # Fallback to basic console handler
        log_config["formatters"]["standard"] = {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",  # Consistent date format without milliseconds
        }

        log_config["handlers"]["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        }

    # Configure all loggers to use the same formatter
    log_config["loggers"] = {
        "": {  # Root logger
            "handlers": ["console"],
            "level": log_level_str,
        },
        "uvicorn": {
            "handlers": ["console"],
            "level": log_level_str,
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": log_level_str,
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": log_level_str,
            "propagate": False,
        },
    }

    return log_config


def configure_unified_logging(
    settings: LoggingSettings | None = None,
    websocket_manager: "WebSocketManager | None" = None,
) -> tuple[dict, logging.Logger]:
    """
    Configure unified logging for both application and Uvicorn with optional WebSocket support.

    This function creates a logging configuration that can be used with uvicorn.run(log_config=...)
    and also sets up additional WebSocket logging if a websocket_manager is provided.

    Args:
        settings (LoggingSettings | None): Logging configuration settings.
        websocket_manager (WebSocketManager | None): WebSocket manager for log streaming.

    Returns:
        tuple[dict, logging.Logger]: The log configuration dict and configured root logger.
    """
    # Create the unified log configuration
    log_config = create_unified_log_config(settings)

    # Apply the configuration
    import logging.config

    logging.config.dictConfig(log_config)

    root_logger = logging.getLogger()

    # Add WebSocket log handler if websocket_manager is provided
    if websocket_manager:
        try:
            import asyncio

            from backend.services.websocket_service import WebSocketLogHandler

            # Get the current event loop or create a new one
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            ws_handler = WebSocketLogHandler(websocket_service, loop)
            # Always set WebSocket handler to DEBUG to send all logs
            ws_handler.setLevel(logging.DEBUG)

            # Use the same formatter as the console handler
            if root_logger.handlers and root_logger.handlers[0].formatter:
                ws_handler.setFormatter(root_logger.handlers[0].formatter)

            root_logger.addHandler(ws_handler)
            logger.info("WebSocket log handler added to unified logging configuration")
        except Exception as e:
            logger.warning(f"Failed to add WebSocket log handler: {e}")

    return log_config, root_logger
