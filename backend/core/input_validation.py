"""
Input Validation and Sanitization Helpers

Provides comprehensive input validation for safety-critical RV-C operations.
All validation follows defense-in-depth principles.

Note: "safety-critical" / "safety" naming in this file is historical and
refers to **API guardrail / command-validation** behavior, NOT vehicle safety.
The OEM Firefly MIRA panel owns the actual vehicle safety case. See
`docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`.
"""

import re
import string
import urllib.parse
from ipaddress import AddressValueError, ip_address, ip_network
from re import Pattern
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, validator

# Validation patterns
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")
SAFE_STRING_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-_.,!?()]+$")
ENTITY_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
CAN_ID_PATTERN = re.compile(r"^(0x)?[0-9A-Fa-f]{1,8}$")
PIN_PATTERN = re.compile(r"^\d{4,8}$")

# Safety limits
MAX_STRING_LENGTH = 1024
MAX_ARRAY_LENGTH = 100
MAX_NUMERIC_VALUE = 2**31 - 1
MIN_NUMERIC_VALUE = -(2**31)


class ValidationError(ValueError):
    """Custom validation error with details."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        self.field = field
        self.value = value
        super().__init__(message)


def sanitize_string(
    value: str,
    max_length: int = MAX_STRING_LENGTH,
    allowed_chars: str | None = None,
    strip_html: bool = True,
) -> str:
    """
    Sanitize string input for safe usage.

    Args:
        value: Input string to sanitize
        max_length: Maximum allowed length
        allowed_chars: Optional whitelist of allowed characters
        strip_html: Whether to strip HTML tags

    Returns:
        Sanitized string

    Raises:
        ValidationError: If string contains invalid content
    """
    if not isinstance(value, str):
        raise ValidationError("Value must be a string", value=value)

    # Truncate to max length
    value = value[:max_length]

    # Strip HTML if requested
    if strip_html:
        # Basic HTML stripping (in production use a proper library)
        value = re.sub(r"<[^>]+>", "", value)

    # Apply character whitelist if provided
    if allowed_chars:
        allowed_set = set(allowed_chars)
        value = "".join(c for c in value if c in allowed_set)

    # Remove null bytes and other dangerous characters
    value = value.replace("\x00", "")

    # Normalize whitespace
    value = " ".join(value.split())

    return value


def validate_email(email: str) -> str:
    """
    Validate and normalize email address.

    Args:
        email: Email address to validate

    Returns:
        Normalized email address

    Raises:
        ValidationError: If email is invalid
    """
    email = email.strip().lower()

    if not EMAIL_PATTERN.match(email):
        raise ValidationError("Invalid email format", field="email", value=email)

    if len(email) > 254:  # RFC 5321
        raise ValidationError("Email address too long", field="email", value=email)

    return email


def validate_username(username: str) -> str:
    """
    Validate username for authentication.

    Args:
        username: Username to validate

    Returns:
        Validated username

    Raises:
        ValidationError: If username is invalid
    """
    username = username.strip()

    if not USERNAME_PATTERN.match(username):
        raise ValidationError(
            "Username must be 3-32 characters, alphanumeric with _ and -",
            field="username",
            value=username,
        )

    return username


def validate_entity_id(entity_id: str) -> str:
    """
    Validate RV-C entity identifier.

    Args:
        entity_id: Entity ID to validate

    Returns:
        Validated entity ID

    Raises:
        ValidationError: If entity ID is invalid
    """
    if not ENTITY_ID_PATTERN.match(entity_id):
        raise ValidationError("Invalid entity ID format", field="entity_id", value=entity_id)

    return entity_id


def validate_can_id(can_id: str | int) -> int:
    """
    Validate and parse CAN identifier.

    Args:
        can_id: CAN ID as string or int

    Returns:
        Validated CAN ID as integer

    Raises:
        ValidationError: If CAN ID is invalid
    """
    if isinstance(can_id, int):
        if 0 <= can_id <= 0x1FFFFFFF:  # 29-bit extended CAN ID
            return can_id
        raise ValidationError("CAN ID out of range", field="can_id", value=can_id)

    if isinstance(can_id, str):
        if not CAN_ID_PATTERN.match(can_id):
            raise ValidationError("Invalid CAN ID format", field="can_id", value=can_id)

        # Parse hex or decimal
        try:
            if can_id.startswith("0x"):
                parsed = int(can_id, 16)
            else:
                parsed = int(can_id, 10)

            return validate_can_id(parsed)
        except ValueError:
            raise ValidationError("Invalid CAN ID value", field="can_id", value=can_id)

    raise ValidationError("CAN ID must be string or int", field="can_id", value=can_id)


def validate_pin(pin: str) -> str:
    """
    Validate PIN for safety operations.

    Args:
        pin: PIN to validate

    Returns:
        Validated PIN

    Raises:
        ValidationError: If PIN is invalid
    """
    if not PIN_PATTERN.match(pin):
        raise ValidationError("PIN must be 4-8 digits", field="pin")

    # Check for weak PINs
    if pin in {"0000", "1111", "1234", "4321", "9999"}:
        raise ValidationError("PIN is too weak", field="pin")

    return pin


def validate_ip_address(ip: str) -> str:
    """
    Validate IP address.

    Args:
        ip: IP address to validate

    Returns:
        Validated IP address

    Raises:
        ValidationError: If IP is invalid
    """
    try:
        ip_obj = ip_address(ip)

        # Reject private/local addresses for external APIs
        if ip_obj.is_private or ip_obj.is_loopback:
            raise ValidationError("Private IP addresses not allowed", field="ip_address", value=ip)

        return str(ip_obj)

    except (AddressValueError, ValueError) as e:
        raise ValidationError("Invalid IP address", field="ip_address", value=ip) from e


def validate_url(url: str, allowed_schemes: list[str] = ["http", "https"]) -> str:
    """
    Validate and sanitize URL.

    Args:
        url: URL to validate
        allowed_schemes: List of allowed URL schemes

    Returns:
        Validated URL

    Raises:
        ValidationError: If URL is invalid or dangerous
    """
    try:
        parsed = urllib.parse.urlparse(url)

        # Check scheme
        if parsed.scheme not in allowed_schemes:
            raise ValidationError(
                f"URL scheme must be one of {allowed_schemes}", field="url", value=url
            )

        # Check for empty host
        if not parsed.netloc:
            raise ValidationError("URL must have a valid host", field="url", value=url)

        hostname = (parsed.hostname or "").lower()

        # Block known local-resolving hostnames as a defense-in-depth SSRF measure.
        # Note: this does not perform DNS resolution; for full protection,
        # callers should also resolve and re-check the IP at request time.
        FORBIDDEN_HOSTS = {
            "localhost",
            "localhost.localdomain",
            "ip6-localhost",
            "ip6-loopback",
            "broadcasthost",
        }
        if hostname in FORBIDDEN_HOSTS or hostname.endswith(".localhost"):
            raise ValidationError(
                "URL points to a local hostname",
                field="url",
                value=url,
            )

        # Prevent SSRF by blocking local addresses (when host is a literal IP)
        try:
            host_ip = ip_address(hostname)
        except (AddressValueError, ValueError, TypeError):
            # Not an IP address (or hostname is None) — leave hostname-based
            # filtering to the FORBIDDEN_HOSTS check above.
            host_ip = None

        if host_ip is not None and (host_ip.is_private or host_ip.is_loopback):
            raise ValidationError(
                "URL points to private/local address",
                field="url",
                value=url,
            )

        # Reconstruct clean URL
        clean_url = urllib.parse.urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                "",  # Remove fragment
            )
        )

        return clean_url

    except Exception as e:
        raise ValidationError(f"Invalid URL: {e!s}", field="url", value=url)


def validate_numeric_range(
    value: int | float,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
    field_name: str = "value",
) -> int | float:
    """
    Validate numeric value is within allowed range.

    Args:
        value: Numeric value to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        field_name: Field name for error messages

    Returns:
        Validated value

    Raises:
        ValidationError: If value is out of range
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be numeric", field=field_name, value=value)

    if min_value is not None and value < min_value:
        raise ValidationError(f"{field_name} must be >= {min_value}", field=field_name, value=value)

    if max_value is not None and value > max_value:
        raise ValidationError(f"{field_name} must be <= {max_value}", field=field_name, value=value)

    return value


def validate_array_length(
    array: list[Any], max_length: int = MAX_ARRAY_LENGTH, field_name: str = "array"
) -> list[Any]:
    """
    Validate array length to prevent resource exhaustion.

    Args:
        array: Array to validate
        max_length: Maximum allowed length
        field_name: Field name for error messages

    Returns:
        Validated array

    Raises:
        ValidationError: If array is too long
    """
    if not isinstance(array, list):
        raise ValidationError(f"{field_name} must be a list", field=field_name, value=array)

    if len(array) > max_length:
        raise ValidationError(
            f"{field_name} exceeds maximum length of {max_length}",
            field=field_name,
            value=f"[{len(array)} items]",
        )

    return array


# Pydantic models for complex validation


class SafetyOperationRequest(BaseModel):
    """Validated safety operation request."""

    entity_id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    operation: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    pin: str | None = Field(None, pattern=r"^\d{4,8}$")
    parameters: dict = Field(default_factory=dict)

    @validator("parameters")
    def validate_parameters(cls, v):
        """Ensure parameters dict is safe."""
        if len(v) > 20:
            raise ValueError("Too many parameters")

        for key, value in v.items():
            if not isinstance(key, str) or len(key) > 64:
                raise ValueError(f"Invalid parameter key: {key}")

            if isinstance(value, str) and len(value) > 256:
                raise ValueError(f"Parameter value too long: {key}")

        return v


class BulkOperationRequest(BaseModel):
    """Validated bulk operation request."""

    entity_ids: list[str] = Field(..., max_length=50)
    operation: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    pin: str | None = Field(None, pattern=r"^\d{4,8}$")
    parameters: dict = Field(default_factory=dict)

    @validator("entity_ids")
    def validate_entity_ids(cls, v):
        """Validate each entity ID."""
        for entity_id in v:
            validate_entity_id(entity_id)
        return v
