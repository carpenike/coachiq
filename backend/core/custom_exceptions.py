"""
Custom Exceptions for RV-C Control System

Comprehensive exception hierarchy for proper error handling throughout
the application, following safety-critical system best practices.
"""

from typing import Any, Dict, Optional


# Base Exceptions
class CoachIQException(Exception):
    """Base exception for all CoachIQ custom exceptions."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class SafetyException(CoachIQException):
    """Base exception for safety-critical operations."""

    def __init__(
        self,
        message: str,
        safety_level: str = "HIGH",
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, error_code, details)
        self.safety_level = safety_level


# Authentication & Authorization Exceptions
class AuthenticationError(CoachIQException):
    """Base exception for authentication failures."""


class InvalidCredentialsError(AuthenticationError):
    """Raised when provided credentials are invalid."""

    def __init__(self, username: str | None = None):
        message = "Invalid username or password"
        details = {"username": username} if username else {}
        super().__init__(message, "AUTH_INVALID_CREDENTIALS", details)


class TokenExpiredError(AuthenticationError):
    """Raised when JWT token has expired."""

    def __init__(self, token_type: str = "access"):
        message = f"{token_type.capitalize()} token has expired"
        super().__init__(message, "AUTH_TOKEN_EXPIRED", {"token_type": token_type})


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid or malformed."""

    def __init__(self, reason: str = "Invalid token"):
        super().__init__(reason, "AUTH_TOKEN_INVALID")


class AccountLockedError(AuthenticationError):
    """Raised when account is locked due to security reasons."""

    def __init__(
        self,
        message: str | None = None,
        lockout_until: Any | None = None,
        attempts: int | None = None,
        username: str | None = None,
        locked_until: str | None = None,
    ):
        # Support both old and new signatures
        if message and lockout_until is not None and attempts is not None:
            # New signature from auth_manager
            self.lockout_until = lockout_until
            self.attempts = attempts
            details = {
                "lockout_until": str(lockout_until) if lockout_until else None,
                "attempts": attempts,
            }
            super().__init__(message, "AUTH_ACCOUNT_LOCKED", details)
        else:
            # Original signature
            username = username or "unknown"
            message = message or f"Account '{username}' is locked"
            details = {"username": username}
            if locked_until:
                details["locked_until"] = locked_until
            self.lockout_until = None
            self.attempts = None
            super().__init__(message, "AUTH_ACCOUNT_LOCKED", details)


class MFARequiredError(AuthenticationError):
    """Raised when MFA is required but not provided."""

    def __init__(self, mfa_type: str = "TOTP"):
        message = "Multi-factor authentication required"
        super().__init__(message, "AUTH_MFA_REQUIRED", {"mfa_type": mfa_type})


class AuthorizationError(CoachIQException):
    """Base exception for authorization failures."""


class InsufficientPermissionsError(AuthorizationError):
    """Raised when user lacks required permissions."""

    def __init__(
        self,
        required_permission: str,
        user_permissions: list[str] | None = None,
    ):
        message = f"Insufficient permissions. Required: {required_permission}"
        details = {
            "required_permission": required_permission,
            "user_permissions": user_permissions or [],
        }
        super().__init__(message, "AUTH_INSUFFICIENT_PERMISSIONS", details)


class RoleRequiredError(AuthorizationError):
    """Raised when user lacks required role."""

    def __init__(self, required_roles: list[str], user_roles: list[str] | None = None):
        message = f"Required role(s): {', '.join(required_roles)}"
        details = {
            "required_roles": required_roles,
            "user_roles": user_roles or [],
        }
        super().__init__(message, "AUTH_ROLE_REQUIRED", details)


# Entity & Control Exceptions
class EntityError(CoachIQException):
    """Base exception for entity-related errors."""


class EntityNotFoundError(EntityError):
    """Raised when requested entity does not exist."""

    def __init__(self, entity_id: str):
        message = f"Entity '{entity_id}' not found"
        super().__init__(message, "ENTITY_NOT_FOUND", {"entity_id": entity_id})


class EntityAlreadyExistsError(EntityError):
    """Raised when attempting to create duplicate entity."""

    def __init__(self, entity_id: str):
        message = f"Entity '{entity_id}' already exists"
        super().__init__(message, "ENTITY_ALREADY_EXISTS", {"entity_id": entity_id})


class EntityControlError(SafetyException):
    """Raised when entity control operation fails."""

    def __init__(
        self,
        entity_id: str,
        command: str,
        reason: str,
        safety_level: str = "MEDIUM",
    ):
        message = f"Failed to control entity '{entity_id}': {reason}"
        details = {"entity_id": entity_id, "command": command, "reason": reason}
        super().__init__(message, safety_level, "ENTITY_CONTROL_FAILED", details)


class InvalidCommandError(EntityError):
    """Raised when command is invalid for entity type."""

    def __init__(self, entity_id: str, command: str, valid_commands: list[str]):
        message = f"Invalid command '{command}' for entity '{entity_id}'"
        details = {
            "entity_id": entity_id,
            "command": command,
            "valid_commands": valid_commands,
        }
        super().__init__(message, "ENTITY_INVALID_COMMAND", details)


# CAN Bus Exceptions
class CANError(SafetyException):
    """Base exception for CAN bus errors."""


class CANInterfaceError(CANError):
    """Raised when CAN interface operation fails."""

    def __init__(self, interface: str, operation: str, reason: str):
        message = f"CAN interface '{interface}' {operation} failed: {reason}"
        details = {"interface": interface, "operation": operation}
        super().__init__(message, "HIGH", "CAN_INTERFACE_ERROR", details)


class CANMessageError(CANError):
    """Raised when CAN message is invalid or cannot be processed."""

    def __init__(self, can_id: int, reason: str):
        message = f"Invalid CAN message (ID: 0x{can_id:X}): {reason}"
        details = {"can_id": can_id, "can_id_hex": f"0x{can_id:X}"}
        super().__init__(message, "MEDIUM", "CAN_MESSAGE_ERROR", details)


class CANBusOffError(CANError):
    """Raised when CAN bus enters bus-off state."""

    def __init__(self, interface: str):
        message = f"CAN interface '{interface}' is in bus-off state"
        super().__init__(message, "CRITICAL", "CAN_BUS_OFF", {"interface": interface})


# Database Exceptions
class DatabaseError(CoachIQException):
    """Base exception for database-related errors."""


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""

    def __init__(self, reason: str):
        message = f"Database connection failed: {reason}"
        super().__init__(message, "DB_CONNECTION_FAILED")


class DatabaseMigrationError(DatabaseError):
    """Raised when database migration fails."""

    def __init__(self, migration_name: str, reason: str):
        message = f"Migration '{migration_name}' failed: {reason}"
        details = {"migration": migration_name}
        super().__init__(message, "DB_MIGRATION_FAILED", details)


class DataIntegrityError(DatabaseError):
    """Raised when data integrity violation occurs."""

    def __init__(self, table: str, constraint: str):
        message = f"Data integrity violation in table '{table}': {constraint}"
        details = {"table": table, "constraint": constraint}
        super().__init__(message, "DB_INTEGRITY_ERROR", details)


# Configuration Exceptions
class ConfigurationError(CoachIQException):
    """Base exception for configuration errors."""


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, config_key: str, reason: str):
        message = f"Invalid configuration for '{config_key}': {reason}"
        details = {"config_key": config_key}
        super().__init__(message, "CONFIG_INVALID", details)


class ConfigurationLoadError(ConfigurationError):
    """Raised when configuration file cannot be loaded."""

    def __init__(self, file_path: str, reason: str):
        message = f"Failed to load configuration from '{file_path}': {reason}"
        details = {"file_path": file_path}
        super().__init__(message, "CONFIG_LOAD_FAILED", details)


# RV-C Protocol Exceptions
class RVCError(CoachIQException):
    """Base exception for RV-C protocol errors."""


class UnknownPGNError(RVCError):
    """Raised when PGN is not recognized."""

    def __init__(self, pgn: int):
        message = f"Unknown PGN: {pgn} (0x{pgn:X})"
        details = {"pgn": pgn, "pgn_hex": f"0x{pgn:X}"}
        super().__init__(message, "RVC_UNKNOWN_PGN", details)


class InvalidDGNError(RVCError):
    """Raised when DGN is invalid."""

    def __init__(self, dgn: int, reason: str):
        message = f"Invalid DGN {dgn}: {reason}"
        details = {"dgn": dgn}
        super().__init__(message, "RVC_INVALID_DGN", details)


# Safety System Exceptions
class EmergencyStopError(SafetyException):
    """Raised when emergency stop is triggered."""

    def __init__(self, trigger_source: str, reason: str):
        message = f"EMERGENCY STOP triggered by {trigger_source}: {reason}"
        details = {"trigger_source": trigger_source, "reason": reason}
        super().__init__(message, "CRITICAL", "SAFETY_EMERGENCY_STOP", details)


class SafetyViolationError(SafetyException):
    """Raised when safety constraint is violated."""

    def __init__(self, constraint: str, current_value: Any, limit_value: Any):
        message = f"Safety constraint violated: {constraint}"
        details = {
            "constraint": constraint,
            "current_value": current_value,
            "limit_value": limit_value,
        }
        super().__init__(message, "HIGH", "SAFETY_VIOLATION", details)


class SafetyPINRequiredError(SafetyException):
    """Raised when safety PIN is required but not provided."""

    def __init__(self, operation: str):
        message = f"Safety PIN required for operation: {operation}"
        details = {"operation": operation}
        super().__init__(message, "HIGH", "SAFETY_PIN_REQUIRED", details)


class InvalidSafetyPINError(SafetyException):
    """Raised when provided safety PIN is invalid."""

    def __init__(self, attempts_remaining: int | None = None):
        message = "Invalid safety PIN"
        details = {}
        if attempts_remaining is not None:
            details["attempts_remaining"] = attempts_remaining
        super().__init__(message, "HIGH", "SAFETY_PIN_INVALID", details)


# WebSocket Exceptions
class WebSocketError(CoachIQException):
    """Base exception for WebSocket errors."""


class WebSocketAuthenticationError(WebSocketError):
    """Raised when WebSocket authentication fails."""

    def __init__(self, reason: str = "Authentication required"):
        super().__init__(reason, "WS_AUTH_FAILED")


class WebSocketRateLimitError(WebSocketError):
    """Raised when WebSocket client exceeds rate limit."""

    def __init__(self, limit: int, window: int):
        message = f"Rate limit exceeded: {limit} messages per {window} seconds"
        details = {"limit": limit, "window": window}
        super().__init__(message, "WS_RATE_LIMIT", details)


# Validation Exceptions
class ValidationError(CoachIQException):
    """Base exception for validation errors."""


class InputValidationError(ValidationError):
    """Raised when input validation fails."""

    def __init__(self, field: str, value: Any, constraint: str):
        message = f"Validation failed for field '{field}': {constraint}"
        details = {"field": field, "value": str(value), "constraint": constraint}
        super().__init__(message, "VALIDATION_FAILED", details)


class RangeValidationError(ValidationError):
    """Raised when value is outside allowed range."""

    def __init__(
        self,
        field: str,
        value: Any,
        min_value: Any | None = None,
        max_value: Any | None = None,
    ):
        if min_value is not None and max_value is not None:
            message = f"Value for '{field}' must be between {min_value} and {max_value}"
        elif min_value is not None:
            message = f"Value for '{field}' must be >= {min_value}"
        else:
            message = f"Value for '{field}' must be <= {max_value}"

        details = {"field": field, "value": value}
        if min_value is not None:
            details["min_value"] = min_value
        if max_value is not None:
            details["max_value"] = max_value

        super().__init__(message, "VALIDATION_RANGE", details)


# Service Exceptions (extending existing ones)
class ServiceHealthCheckError(CoachIQException):
    """Raised when service health check fails."""

    def __init__(self, service_name: str, checks_failed: list[str]):
        message = f"Service '{service_name}' health check failed"
        details = {"service_name": service_name, "checks_failed": checks_failed}
        super().__init__(message, "SERVICE_UNHEALTHY", details)


class ServiceDependencyError(CoachIQException):
    """Raised when service dependency is not met."""

    def __init__(self, service_name: str, missing_dependencies: list[str]):
        message = f"Service '{service_name}' missing dependencies: {', '.join(missing_dependencies)}"
        details = {
            "service_name": service_name,
            "missing_dependencies": missing_dependencies,
        }
        super().__init__(message, "SERVICE_DEPENDENCY_ERROR", details)


class ServiceInitializationError(CoachIQException):
    """Raised when service fails to initialize."""

    def __init__(self, service_name: str, reason: str):
        message = f"Service '{service_name}' failed to initialize: {reason}"
        details = {"service_name": service_name, "reason": reason}
        super().__init__(message, "SERVICE_INITIALIZATION_ERROR", details)


class ServiceNotAvailableError(CoachIQException):
    """Raised when service is not available."""

    def __init__(self, service_name: str, reason: str = "Service not available"):
        message = f"Service '{service_name}' is not available: {reason}"
        details = {"service_name": service_name, "reason": reason}
        super().__init__(message, "SERVICE_NOT_AVAILABLE", details)


# Rate Limiting Exceptions
class RateLimitExceededError(CoachIQException):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        limit: int,
        window: int,
        retry_after: int | None = None,
    ):
        message = f"Rate limit exceeded: {limit} requests per {window} seconds"
        details = {"limit": limit, "window": window}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(message, "RATE_LIMIT_EXCEEDED", details)


# External Service Exceptions
class ExternalServiceError(CoachIQException):
    """Base exception for external service failures."""


class EmailServiceError(ExternalServiceError):
    """Raised when email service fails."""

    def __init__(self, operation: str, reason: str):
        message = f"Email service {operation} failed: {reason}"
        details = {"operation": operation}
        super().__init__(message, "EMAIL_SERVICE_ERROR", details)


class VectorSearchError(ExternalServiceError):
    """Raised when vector search service fails."""

    def __init__(self, operation: str, reason: str):
        message = f"Vector search {operation} failed: {reason}"
        details = {"operation": operation}
        super().__init__(message, "VECTOR_SEARCH_ERROR", details)
