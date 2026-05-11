"""
Role-based authorization decorators for FastAPI endpoints.

This module provides decorators for enforcing role-based access control
on API endpoints, ensuring that only users with appropriate permissions
can access protected resources.
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Type variable for generic callable
F = TypeVar("F", bound=Callable[..., Any])


def _get_current_user_from_kwargs(kwargs: dict[str, Any]) -> dict[str, Any] | None:
    """Extract current user from kwargs."""
    for value in kwargs.values():
        if isinstance(value, dict) and "user_id" in value:
            return value
    return None


def _check_user_role(current_user: dict[str, Any] | None, allowed_roles: tuple[str, ...]) -> None:
    """
    Check if user has required role. Raises HTTPException if not.

    This is a helper to reduce complexity in role checking decorators.
    """
    if not current_user:
        logger.error(
            "No authenticated user found in endpoint arguments. "
            "Ensure AuthenticatedUser dependency is included."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_role = current_user.get("role")
    if not user_role:
        logger.warning(
            "User %s has no role assigned",
            current_user.get("user_id", "unknown"),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no assigned role",
        )

    if user_role not in allowed_roles:
        logger.warning(
            "Access denied for user %s with role %s. Required roles: %s",
            current_user.get("user_id", "unknown"),
            user_role,
            allowed_roles,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {', '.join(allowed_roles)}",
        )

    logger.debug(
        "Access granted for user %s with role %s",
        current_user.get("user_id", "unknown"),
        user_role,
    )


def require_role(*allowed_roles: str) -> Callable[[F], F]:
    """
    Decorator that enforces role-based authorization on endpoints.

    This decorator checks that the authenticated user has one of the
    allowed roles before executing the endpoint function.

    Args:
        allowed_roles: One or more role names that are allowed access

    Returns:
        Decorated function that enforces role checking

    Example:
        @require_role("admin", "moderator")
        async def delete_user(user_id: str, current_user: AuthenticatedUser):
            # Only admins and moderators can execute this
            pass
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = _get_current_user_from_kwargs(kwargs)
            _check_user_role(current_user, allowed_roles)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = _get_current_user_from_kwargs(kwargs)
            _check_user_role(current_user, allowed_roles)
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast("F", async_wrapper)
        return cast("F", sync_wrapper)

    return decorator


def require_admin[T: Callable[..., Any]](func: T) -> T:
    """
    Decorator that requires admin role for endpoint access.

    This is a convenience decorator equivalent to @require_role("admin").

    Args:
        func: The endpoint function to protect

    Returns:
        Decorated function that enforces admin access

    Example:
        @require_admin
        async def system_config(current_user: AuthenticatedUser):
            # Only admins can access this
            pass
    """
    return require_role("admin")(func)


def _check_authenticated(current_user: dict[str, Any] | None) -> None:
    """
    Check if user is authenticated. Raises HTTPException if not.

    This is a helper to reduce complexity in authentication checking decorators.
    """
    if not current_user:
        logger.error(
            "No authenticated user found in endpoint arguments. "
            "Ensure AuthenticatedUser dependency is included."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    logger.debug(
        "Authenticated access for user %s",
        current_user.get("user_id", "unknown"),
    )


def require_authenticated[T: Callable[..., Any]](func: T) -> T:
    """
    Decorator that only requires authentication, not specific roles.

    This ensures the user is authenticated but doesn't check roles.
    Useful for endpoints that should be accessible to all authenticated users.

    Args:
        func: The endpoint function to protect

    Returns:
        Decorated function that enforces authentication

    Example:
        @require_authenticated
        async def get_profile(current_user: AuthenticatedUser):
            # Any authenticated user can access their profile
            pass
    """

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        current_user = _get_current_user_from_kwargs(kwargs)
        _check_authenticated(current_user)
        return await func(*args, **kwargs)

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        current_user = _get_current_user_from_kwargs(kwargs)
        _check_authenticated(current_user)
        return func(*args, **kwargs)

    # Return appropriate wrapper based on function type
    if asyncio.iscoroutinefunction(func):
        return cast("T", async_wrapper)
    return cast("T", sync_wrapper)


def _check_permission(current_user: dict[str, Any] | None, permission: str) -> None:
    """
    Check if user has required permission. Raises HTTPException if not.

    This is a helper to reduce complexity in permission checking decorators.
    """
    if not current_user:
        logger.error(
            "No authenticated user found in endpoint arguments. "
            "Ensure AuthenticatedUser dependency is included."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_permissions = current_user.get("permissions", [])
    if permission not in user_permissions:
        logger.warning(
            "Permission denied for user %s. Required permission: %s",
            current_user.get("user_id", "unknown"),
            permission,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {permission}",
        )

    logger.debug(
        "Permission granted for user %s: %s",
        current_user.get("user_id", "unknown"),
        permission,
    )


def require_permission(permission: str) -> Callable[[F], F]:
    """
    Decorator that requires specific permission for endpoint access.

    This decorator checks that the authenticated user has the required
    permission in their permissions list.

    Args:
        permission: The permission name required for access

    Returns:
        Decorated function that enforces permission checking

    Example:
        @require_permission("can_delete_users")
        async def delete_user(user_id: str, current_user: AuthenticatedUser):
            # Only users with can_delete_users permission can execute
            pass
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = _get_current_user_from_kwargs(kwargs)
            _check_permission(current_user, permission)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = _get_current_user_from_kwargs(kwargs)
            _check_permission(current_user, permission)
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast("F", async_wrapper)
        return cast("F", sync_wrapper)

    return decorator
