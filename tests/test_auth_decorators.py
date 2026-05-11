"""
Test suite for authorization decorators.

Verifies that role-based access control decorators properly
enforce permissions and handle various edge cases.
"""

import pytest
from fastapi import HTTPException, status

from backend.core.auth_decorators import (
    require_admin,
    require_authenticated,
    require_permission,
    require_role,
)


class TestRequireRole:
    """Test cases for require_role decorator."""

    @pytest.mark.asyncio
    async def test_require_role_allows_matching_role(self):
        """Test that users with allowed roles can access the endpoint."""

        @require_role("admin", "moderator")
        async def protected_endpoint(current_user: dict) -> str:
            return "success"

        # Admin should have access
        admin_user = {"user_id": "admin123", "role": "admin"}
        result = await protected_endpoint(current_user=admin_user)
        assert result == "success"

        # Moderator should also have access
        mod_user = {"user_id": "mod123", "role": "moderator"}
        result = await protected_endpoint(current_user=mod_user)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_require_role_denies_non_matching_role(self):
        """Test that users without allowed roles are denied access."""

        @require_role("admin")
        async def admin_only_endpoint(current_user: dict) -> str:
            return "admin data"

        regular_user = {"user_id": "user123", "role": "user"}

        with pytest.raises(HTTPException) as exc_info:
            await admin_only_endpoint(current_user=regular_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Insufficient permissions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_role_no_user(self):
        """Test that missing user raises 401."""

        @require_role("admin")
        async def protected_endpoint() -> str:
            return "should not reach here"

        with pytest.raises(HTTPException) as exc_info:
            await protected_endpoint()

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_role_no_role_field(self):
        """Test that user without role field raises 403."""

        @require_role("admin")
        async def protected_endpoint(current_user: dict) -> str:
            return "should not reach here"

        user_no_role = {"user_id": "user123", "email": "user@example.com"}

        with pytest.raises(HTTPException) as exc_info:
            await protected_endpoint(current_user=user_no_role)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "User has no assigned role" in exc_info.value.detail

    def test_require_role_sync_function(self):
        """Test that decorator works with synchronous functions."""

        @require_role("admin")
        def sync_endpoint(current_user: dict) -> str:
            return "sync success"

        admin_user = {"user_id": "admin123", "role": "admin"}
        result = sync_endpoint(current_user=admin_user)
        assert result == "sync success"

        regular_user = {"user_id": "user123", "role": "user"}
        with pytest.raises(HTTPException) as exc_info:
            sync_endpoint(current_user=regular_user)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestRequireAdmin:
    """Test cases for require_admin decorator."""

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin(self):
        """Test that admin users can access admin-only endpoints."""

        @require_admin
        async def admin_endpoint(current_user: dict) -> str:
            return "admin access granted"

        admin_user = {"user_id": "admin123", "role": "admin"}
        result = await admin_endpoint(current_user=admin_user)
        assert result == "admin access granted"

    @pytest.mark.asyncio
    async def test_require_admin_denies_non_admin(self):
        """Test that non-admin users are denied access."""

        @require_admin
        async def admin_endpoint(current_user: dict) -> str:
            return "should not reach here"

        regular_user = {"user_id": "user123", "role": "user"}

        with pytest.raises(HTTPException) as exc_info:
            await admin_endpoint(current_user=regular_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "admin" in exc_info.value.detail


class TestRequireAuthenticated:
    """Test cases for require_authenticated decorator."""

    @pytest.mark.asyncio
    async def test_require_authenticated_allows_any_user(self):
        """Test that any authenticated user can access the endpoint."""

        @require_authenticated
        async def user_endpoint(current_user: dict) -> str:
            return f"Hello {current_user['user_id']}"

        # Regular user should have access
        regular_user = {"user_id": "user123", "role": "user"}
        result = await user_endpoint(current_user=regular_user)
        assert result == "Hello user123"

        # Admin should also have access
        admin_user = {"user_id": "admin123", "role": "admin"}
        result = await user_endpoint(current_user=admin_user)
        assert result == "Hello admin123"

        # User without role should still have access
        user_no_role = {"user_id": "norole123"}
        result = await user_endpoint(current_user=user_no_role)
        assert result == "Hello norole123"

    @pytest.mark.asyncio
    async def test_require_authenticated_denies_unauthenticated(self):
        """Test that unauthenticated requests are denied."""

        @require_authenticated
        async def user_endpoint() -> str:
            return "should not reach here"

        with pytest.raises(HTTPException) as exc_info:
            await user_endpoint()

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in exc_info.value.detail


class TestRequirePermission:
    """Test cases for require_permission decorator."""

    @pytest.mark.asyncio
    async def test_require_permission_allows_with_permission(self):
        """Test that users with required permission can access."""

        @require_permission("can_delete_users")
        async def delete_endpoint(current_user: dict) -> str:
            return "deletion allowed"

        user_with_perm = {
            "user_id": "user123",
            "role": "moderator",
            "permissions": ["can_view_users", "can_delete_users"],
        }
        result = await delete_endpoint(current_user=user_with_perm)
        assert result == "deletion allowed"

    @pytest.mark.asyncio
    async def test_require_permission_denies_without_permission(self):
        """Test that users without required permission are denied."""

        @require_permission("can_delete_users")
        async def delete_endpoint(current_user: dict) -> str:
            return "should not reach here"

        user_without_perm = {
            "user_id": "user123",
            "role": "user",
            "permissions": ["can_view_users"],
        }

        with pytest.raises(HTTPException) as exc_info:
            await delete_endpoint(current_user=user_without_perm)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "can_delete_users" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_permission_empty_permissions(self):
        """Test that users with no permissions list are denied."""

        @require_permission("any_permission")
        async def protected_endpoint(current_user: dict) -> str:
            return "should not reach here"

        user_no_perms = {"user_id": "user123", "role": "user"}

        with pytest.raises(HTTPException) as exc_info:
            await protected_endpoint(current_user=user_no_perms)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestDecoratorIntegration:
    """Test decorator integration scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_decorators(self):
        """Test that multiple decorators can be stacked."""

        @require_authenticated
        @require_role("admin", "moderator")
        @require_permission("can_manage_system")
        async def super_protected_endpoint(current_user: dict) -> str:
            return "all checks passed"

        # User with all requirements should pass
        super_user = {
            "user_id": "super123",
            "role": "admin",
            "permissions": ["can_manage_system", "can_view_all"],
        }
        result = await super_protected_endpoint(current_user=super_user)
        assert result == "all checks passed"

        # User missing permission should fail
        admin_no_perm = {
            "user_id": "admin123",
            "role": "admin",
            "permissions": ["can_view_all"],
        }
        with pytest.raises(HTTPException) as exc_info:
            await super_protected_endpoint(current_user=admin_no_perm)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self):
        """Test that decorators preserve original function metadata."""

        @require_admin
        async def documented_endpoint(current_user: dict) -> str:
            """This endpoint does important admin stuff."""
            return "admin stuff done"

        # Check that docstring is preserved
        assert documented_endpoint.__doc__ == "This endpoint does important admin stuff."
        assert documented_endpoint.__name__ == "documented_endpoint"
