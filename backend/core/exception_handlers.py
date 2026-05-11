"""
FastAPI Exception Handlers

Maps custom exceptions to appropriate HTTP responses with proper
error formatting and logging.
"""

import logging
import traceback
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.custom_exceptions import (
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
    CANBusOffError,
    CANError,
    CoachIQException,
    ConfigurationError,
    DatabaseConnectionError,
    DatabaseError,
    EmergencyStopError,
    EntityControlError,
    EntityNotFoundError,
    InputValidationError,
    InvalidCredentialsError,
    InvalidTokenError,
    RateLimitExceededError,
    SafetyException,
    SafetyViolationError,
    ServiceHealthCheckError,
    ServiceInitializationError,
    ServiceNotAvailableError,
    TokenExpiredError,
    WebSocketError,
)
from backend.core.custom_exceptions import (
    ValidationError as CustomValidationError,
)

logger = logging.getLogger(__name__)


def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Create standardized error response."""
    content = {
        "error": {
            "code": error_code,
            "message": message,
        }
    }

    if details:
        content["error"]["details"] = details

    if request_id:
        content["error"]["request_id"] = request_id

    return JSONResponse(status_code=status_code, content=content)


async def coachiq_exception_handler(request: Request, exc: CoachIQException) -> JSONResponse:
    """Handle all CoachIQ custom exceptions."""
    request_id = getattr(request.state, "request_id", None)

    # Log the exception with appropriate level
    if isinstance(exc, SafetyException):
        logger.error(
            f"Safety exception: {exc}",
            extra={
                "request_id": request_id,
                "safety_level": exc.safety_level,
                "error_code": exc.error_code,
                "details": exc.details,
            },
        )
    else:
        logger.warning(
            f"Application exception: {exc}",
            extra={
                "request_id": request_id,
                "error_code": exc.error_code,
                "details": exc.details,
            },
        )

    # Map exception types to HTTP status codes
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    if isinstance(exc, (InvalidCredentialsError, InvalidTokenError, TokenExpiredError)):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, AccountLockedError):
        status_code = status.HTTP_423_LOCKED
    elif isinstance(exc, AuthenticationError):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, AuthorizationError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, EntityNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (InputValidationError, CustomValidationError)):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, RateLimitExceededError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(exc, ServiceNotAvailableError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, ConfigurationError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    elif isinstance(exc, DatabaseConnectionError) or isinstance(exc, EmergencyStopError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return create_error_response(
        status_code=status_code,
        error_code=exc.error_code or "INTERNAL_ERROR",
        message=str(exc),
        details=exc.details,
        request_id=request_id,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        f"Validation error: {exc}",
        extra={"request_id": request_id, "errors": exc.errors()},
    )

    # Format validation errors
    errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        errors.append(
            {
                "field": field_path,
                "message": error["msg"],
                "type": error["type"],
            }
        )

    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": errors},
        request_id=request_id,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions."""
    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={"request_id": request_id},
    )

    return create_error_response(
        status_code=exc.status_code,
        error_code=f"HTTP_{exc.status_code}",
        message=exc.detail,
        request_id=request_id,
    )


async def database_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle SQLAlchemy database exceptions."""
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"Database exception: {exc}",
        extra={"request_id": request_id},
        exc_info=True,
    )

    if isinstance(exc, OperationalError):
        return create_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="DATABASE_UNAVAILABLE",
            message="Database service is temporarily unavailable",
            request_id=request_id,
        )
    if isinstance(exc, IntegrityError):
        return create_error_response(
            status_code=status.HTTP_409_CONFLICT,
            error_code="DATABASE_INTEGRITY_ERROR",
            message="Database integrity constraint violation",
            request_id=request_id,
        )

    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="DATABASE_ERROR",
        message="An error occurred while accessing the database",
        request_id=request_id,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle any unhandled exceptions."""
    request_id = getattr(request.state, "request_id", None)

    # Log full traceback for debugging
    logger.error(
        f"Unhandled exception: {exc}",
        extra={
            "request_id": request_id,
            "traceback": traceback.format_exc(),
        },
        exc_info=True,
    )

    # Don't expose internal details in production
    message = "An internal server error occurred"

    # Check debug mode from settings (avoiding app.state dependency)
    try:
        from backend.core.config import get_settings

        settings = get_settings()
        if settings.server.debug:
            message = str(exc)
    except Exception:
        # If we can't get settings, default to safe behavior (no debug info)
        pass

    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_SERVER_ERROR",
        message=message,
        request_id=request_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app."""

    # Custom exception handlers
    app.add_exception_handler(CoachIQException, coachiq_exception_handler)

    # Validation exception handlers
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)

    # HTTP exception handler
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Database exception handlers
    app.add_exception_handler(OperationalError, database_exception_handler)
    app.add_exception_handler(IntegrityError, database_exception_handler)

    # Generic exception handler (must be last)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Exception handlers registered")
