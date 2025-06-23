"""
Sensitive Data Filter for Audit Logging

Provides utilities to filter out sensitive information from audit logs
to prevent exposure of passwords, tokens, and other confidential data.
"""

import re
from typing import Any, Dict, List, Set, Union


class SensitiveDataFilter:
    """Filter for removing sensitive data from logs and audit trails."""

    # Common patterns for sensitive field names
    SENSITIVE_PATTERNS = [
        r"password",
        r"passwd",
        r"pwd",
        r"secret",
        r"token",
        r"api_key",
        r"apikey",
        r"auth",
        r"authorization",
        r"credential",
        r"private_key",
        r"privatekey",
        r"access_key",
        r"accesskey",
        r"refresh_token",
        r"refreshtoken",
        r"session",
        r"cookie",
        r"csrf",
        r"pin",
        r"passcode",
        r"otp",
        r"mfa_code",
        r"verification_code",
        r"card_number",
        r"cardnumber",
        r"cvv",
        r"ssn",
        r"social_security",
        r"bank_account",
        r"routing_number",
    ]

    # Compiled regex for efficiency
    SENSITIVE_REGEX = re.compile("|".join(SENSITIVE_PATTERNS), re.IGNORECASE)

    # Values to mask specific patterns
    MASK_PATTERNS = {
        # Email addresses - show domain only
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}": lambda m: f"***@{m.group().split('@')[1]}",
        # JWT tokens - show header only
        r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+": lambda m: f"{m.group().split('.')[0]}.***",
        # Credit card numbers
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b": lambda m: f"****-****-****-{m.group()[-4:]}",
        # IP addresses - mask last octet
        r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b": lambda m: ".".join(m.group().split(".")[:-1])
        + ".***",
    }

    def __init__(self, additional_patterns: list[str] = None):
        """
        Initialize the filter with optional additional patterns.

        Args:
            additional_patterns: List of additional regex patterns to consider sensitive
        """
        self.additional_patterns = additional_patterns or []
        if self.additional_patterns:
            combined_patterns = self.SENSITIVE_PATTERNS + self.additional_patterns
            self.sensitive_regex = re.compile("|".join(combined_patterns), re.IGNORECASE)
        else:
            self.sensitive_regex = self.SENSITIVE_REGEX

    def is_sensitive_key(self, key: str) -> bool:
        """
        Check if a key name indicates sensitive data.

        Args:
            key: The key/field name to check

        Returns:
            True if the key appears to contain sensitive data
        """
        return bool(self.sensitive_regex.search(str(key)))

    def mask_value(self, value: Any) -> str:
        """
        Mask a sensitive value appropriately.

        Args:
            value: The value to mask

        Returns:
            Masked representation of the value
        """
        if value is None:
            return "null"

        value_str = str(value)

        # Apply specific masking patterns
        for pattern, mask_func in self.MASK_PATTERNS.items():
            value_str = re.sub(pattern, mask_func, value_str)

        # If no specific pattern matched, use generic masking
        if isinstance(value, str):
            if len(value) <= 4:
                return "***"
            # Show first and last character for longer strings
            return f"{value[0]}***{value[-1]}"
        if isinstance(value, (int, float)) or isinstance(value, bool):
            return "***"
        if isinstance(value, (list, tuple)):
            return f"[*** {len(value)} items ***]"
        if isinstance(value, dict):
            return f"{{*** {len(value)} fields ***}}"
        return "***"

    def _value_looks_sensitive(self, value: str) -> bool:
        """
        Check if a value looks like sensitive data based on its format.

        Args:
            value: The string value to check

        Returns:
            True if the value matches any sensitive data patterns
        """
        # Skip very short values (unlikely to be secrets)
        if len(value) < 8:
            return False

        # Check against all mask patterns
        for pattern in self.MASK_PATTERNS.keys():
            if re.search(pattern, value):
                return True

        # Check for common secret formats
        # Base64-like strings that could be API keys or tokens
        if re.match(r"^[A-Za-z0-9+/]{20,}={0,2}$", value):
            return True

        # Hex strings that could be keys or hashes
        if re.match(r"^[a-fA-F0-9]{32,}$", value):
            return True

        # UUID-like patterns
        if re.match(
            r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$", value
        ):
            return True

        return False

    def filter_dict(self, data: dict[str, Any], max_depth: int = 5) -> dict[str, Any]:
        """
        Filter sensitive data from a dictionary.

        Args:
            data: Dictionary to filter
            max_depth: Maximum depth to recurse

        Returns:
            Filtered dictionary with sensitive values masked
        """
        if max_depth <= 0:
            return {"_truncated": "max_depth_reached"}

        filtered = {}

        for key, value in data.items():
            # Check if key indicates sensitive data
            if self.is_sensitive_key(key):
                filtered[key] = self.mask_value(value)
            elif isinstance(value, dict):
                # Recurse for nested dictionaries
                filtered[key] = self.filter_dict(value, max_depth - 1)
            elif isinstance(value, (list, tuple)):
                # Handle lists/tuples
                if all(isinstance(item, dict) for item in value):
                    # List of dictionaries - filter each
                    filtered[key] = [self.filter_dict(item, max_depth - 1) for item in value]
                else:
                    # Regular list - check if key is sensitive
                    filtered[key] = value
            # Check if the value matches any sensitive patterns
            elif isinstance(value, str) and self._value_looks_sensitive(value):
                filtered[key] = self.mask_value(value)
            else:
                filtered[key] = value

        return filtered

    def filter_list(self, data: list[Any], max_depth: int = 5) -> list[Any]:
        """
        Filter sensitive data from a list.

        Args:
            data: List to filter
            max_depth: Maximum depth to recurse

        Returns:
            Filtered list with sensitive values masked
        """
        if max_depth <= 0:
            return ["_truncated: max_depth_reached"]

        filtered = []

        for item in data:
            if isinstance(item, dict):
                filtered.append(self.filter_dict(item, max_depth - 1))
            elif isinstance(item, (list, tuple)):
                filtered.append(self.filter_list(list(item), max_depth - 1))
            elif isinstance(item, str) and self._value_looks_sensitive(item):
                filtered.append(self.mask_value(item))
            else:
                filtered.append(item)

        return filtered

    def filter_args_kwargs(
        self, func_name: str, args: tuple, kwargs: dict, sensitive_params: set[str] = None
    ) -> dict[str, Any]:
        """
        Filter sensitive data from function arguments.

        Args:
            func_name: Name of the function (for context)
            args: Positional arguments
            kwargs: Keyword arguments
            sensitive_params: Set of parameter names to always mask

        Returns:
            Dictionary with filtered args and kwargs
        """
        filtered_args = []

        # Filter positional arguments
        for i, arg in enumerate(args):
            if isinstance(arg, dict):
                filtered_args.append(self.filter_dict(arg))
            elif isinstance(arg, (list, tuple)):
                filtered_args.append(self.filter_list(list(arg)))
            else:
                # Check if it looks like sensitive data
                arg_str = str(arg)
                if len(arg_str) > 10 and self.sensitive_regex.search(arg_str):
                    filtered_args.append(self.mask_value(arg))
                else:
                    filtered_args.append(arg)

        # Filter keyword arguments
        filtered_kwargs = self.filter_dict(kwargs)

        # Apply additional sensitive parameter filtering
        if sensitive_params:
            for param in sensitive_params:
                if param in filtered_kwargs:
                    filtered_kwargs[param] = self.mask_value(filtered_kwargs[param])

        return {
            "function": func_name,
            "args": filtered_args,
            "kwargs": filtered_kwargs,
        }


# Global instance for convenience
default_filter = SensitiveDataFilter()


def filter_sensitive_data(data: dict | list | Any) -> dict | list | Any:
    """
    Convenience function to filter sensitive data using the default filter.

    Args:
        data: Data to filter

    Returns:
        Filtered data with sensitive values masked
    """
    if isinstance(data, dict):
        return default_filter.filter_dict(data)
    if isinstance(data, (list, tuple)):
        return default_filter.filter_list(list(data))
    return data
