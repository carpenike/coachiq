"""
Test suite for authentication system.

Verifies that the authentication properly validates JWT tokens
and rejects invalid/missing authentication.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, status

from backend.core.dependencies import get_authenticated_admin, get_authenticated_user


@pytest.mark.asyncio
async def test_get_authenticated_user_no_header():
    """Test that missing authorization header raises 401."""
    mock_auth_manager = Mock()

    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_user(mock_auth_manager, None)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authorization header missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_authenticated_user_invalid_scheme():
    """Test that non-Bearer scheme raises 401."""
    mock_auth_manager = Mock()

    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_user(mock_auth_manager, "Basic sometoken")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid authentication scheme" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_authenticated_user_valid_token():
    """Test that valid token returns user data."""
    mock_auth_manager = Mock()
    mock_auth_manager.validate_token = AsyncMock(
        return_value={"user_id": "test123", "email": "test@example.com", "role": "user"}
    )

    user = await get_authenticated_user(mock_auth_manager, "Bearer valid_token")

    assert user["user_id"] == "test123"
    assert user["email"] == "test@example.com"
    assert user["role"] == "user"
    mock_auth_manager.validate_token.assert_called_once_with("valid_token")


@pytest.mark.asyncio
async def test_get_authenticated_user_invalid_token():
    """Test that invalid token raises 401."""
    mock_auth_manager = Mock()
    mock_auth_manager.validate_token = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_user(mock_auth_manager, "Bearer invalid_token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid or expired token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_authenticated_user_token_validation_error():
    """Test that token validation errors raise 401."""
    mock_auth_manager = Mock()
    mock_auth_manager.validate_token = AsyncMock(side_effect=Exception("Token decode error"))

    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_user(mock_auth_manager, "Bearer error_token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_authenticated_admin_with_admin_user():
    """Test that admin user passes admin check."""
    admin_user = {"user_id": "admin123", "email": "admin@example.com", "role": "admin"}

    result = await get_authenticated_admin(admin_user)
    assert result == admin_user


@pytest.mark.asyncio
async def test_get_authenticated_admin_with_regular_user():
    """Test that non-admin user raises 403."""
    regular_user = {"user_id": "user123", "email": "user@example.com", "role": "user"}

    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_admin(regular_user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Admin access required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_authenticated_admin_with_missing_role():
    """Test that user without role field raises 403."""
    user_no_role = {"user_id": "user123", "email": "user@example.com"}

    with pytest.raises(HTTPException) as exc_info:
        await get_authenticated_admin(user_no_role)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Admin access required" in exc_info.value.detail
