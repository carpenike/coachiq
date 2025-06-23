"""
Integration tests for the user invitation system.

Tests cover:
- User invitation creation and management
- Magic link integration with invitations
- Admin invitation workflows
- Email notification integration
- Invitation expiration and cleanup
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from backend.core.config import AuthenticationSettings
from backend.services.auth_manager import AuthManager
from backend.services.user_invitation_service import UserInvitationService


class TestUserInvitationService:
    """Test user invitation service functionality."""

    @pytest.fixture
    def auth_manager(self):
        """Create auth manager for invitation testing."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            enable_magic_links=True,
            secret_key="test-secret-key-for-invitations",
            base_url="http://localhost:8000",
        )
        return AuthManager(auth_settings)

    @pytest.fixture
    def notification_manager(self):
        """Create mock notification manager."""
        manager = MagicMock()

        # Make send_email return a coroutine
        async def mock_send_email(*args, **kwargs):
            return True

        manager.send_email = mock_send_email
        return manager

    @pytest.fixture
    def invitation_service(self, auth_manager, notification_manager):
        """Create user invitation service instance."""
        return UserInvitationService(auth_manager, notification_manager)

    @pytest.mark.asyncio
    async def test_create_invitation_success(self, invitation_service):
        """Test successful invitation creation."""
        response = await invitation_service.create_invitation(
            email="user@example.com",
            invited_by_admin="admin",
            role="user",
            message="Welcome to CoachIQ!",
        )

        assert response.email == "user@example.com"
        assert response.invitation_sent is True
        assert response.expires_at > datetime.now(UTC)
        assert response.invitation_link is None  # Not returned when email sent

        # Verify invitation is stored
        stats = await invitation_service.get_invitation_stats()
        assert stats["total"] == 1
        assert stats["active"] == 1

    @pytest.mark.asyncio
    async def test_create_invitation_duplicate_email(self, invitation_service):
        """Test creating invitation for email that already has active invitation."""
        # Create first invitation
        await invitation_service.create_invitation(
            email="user@example.com", invited_by_admin="admin"
        )

        # Try to create second invitation for same email
        with pytest.raises(ValueError, match="Active invitation already exists"):
            await invitation_service.create_invitation(
                email="user@example.com", invited_by_admin="admin"
            )

    @pytest.mark.asyncio
    async def test_create_invitation_without_notification_manager(self, auth_manager):
        """Test invitation creation without notification manager."""
        invitation_service = UserInvitationService(auth_manager, None)

        response = await invitation_service.create_invitation(
            email="user@example.com", invited_by_admin="admin"
        )

        assert response.email == "user@example.com"
        assert response.invitation_sent is False
        assert response.invitation_link is not None  # Link provided when email not sent
        assert response.invitation_link.startswith(
            "http://localhost:8000/api/auth/invitation/accept?token="
        )

    @pytest.mark.asyncio
    async def test_validate_invitation_token(self, invitation_service):
        """Test invitation token validation."""
        # Create invitation
        await invitation_service.create_invitation(
            email="user@example.com", invited_by_admin="admin"
        )

        # Get the token from the service's internal storage
        invitations = await invitation_service.list_invitations()
        assert len(invitations) == 1
        token = invitations[0].invitation_token

        # Validate token
        invitation = await invitation_service.validate_invitation_token(token)
        assert invitation is not None
        assert invitation.email == "user@example.com"
        assert not invitation.used

        # Test invalid token
        invalid_invitation = await invitation_service.validate_invitation_token("invalid-token")
        assert invalid_invitation is None

    @pytest.mark.asyncio
    async def test_accept_invitation(self, invitation_service):
        """Test accepting an invitation."""
        # Create invitation
        await invitation_service.create_invitation(
            email="user@example.com", invited_by_admin="admin"
        )

        # Get invitation token
        invitations = await invitation_service.list_invitations()
        token = invitations[0].invitation_token

        # Accept invitation
        magic_token = await invitation_service.accept_invitation(token)

        assert magic_token is not None
        assert isinstance(magic_token, str)

        # Verify invitation is marked as used
        invitation = await invitation_service.validate_invitation_token(token)
        assert invitation is None  # Should be None since it's used

        # Check that invitation is marked as used in stats
        stats = await invitation_service.get_invitation_stats()
        assert stats["used"] == 1
        assert stats["active"] == 0

    @pytest.mark.asyncio
    async def test_accept_invalid_invitation(self, invitation_service):
        """Test accepting invalid invitation."""
        magic_token = await invitation_service.accept_invitation("invalid-token")
        assert magic_token is None

    @pytest.mark.asyncio
    async def test_list_invitations(self, invitation_service):
        """Test listing invitations with filtering."""
        # Create multiple invitations
        await invitation_service.create_invitation(
            email="user1@example.com", invited_by_admin="admin"
        )
        await invitation_service.create_invitation(
            email="user2@example.com", invited_by_admin="admin"
        )

        # List all invitations
        all_invitations = await invitation_service.list_invitations(
            include_expired=True, include_used=True
        )
        assert len(all_invitations) == 2

        # Accept one invitation
        invitations = await invitation_service.list_invitations()
        token = invitations[0].invitation_token
        await invitation_service.accept_invitation(token)

        # List active invitations only
        active_invitations = await invitation_service.list_invitations(
            include_expired=False, include_used=False
        )
        assert len(active_invitations) == 1

        # List including used invitations
        all_invitations = await invitation_service.list_invitations(
            include_expired=False, include_used=True
        )
        assert len(all_invitations) == 2

    @pytest.mark.asyncio
    async def test_revoke_invitation(self, invitation_service):
        """Test revoking an invitation."""
        # Create invitation
        await invitation_service.create_invitation(
            email="user@example.com", invited_by_admin="admin"
        )

        # Get invitation ID
        invitations = await invitation_service.list_invitations()
        invitation_id = invitations[0].id

        # Revoke invitation
        success = await invitation_service.revoke_invitation(invitation_id)
        assert success is True

        # Verify invitation is marked as used
        stats = await invitation_service.get_invitation_stats()
        assert stats["used"] == 1
        assert stats["active"] == 0

        # Test revoking non-existent invitation
        success = await invitation_service.revoke_invitation("non-existent-id")
        assert success is False

    @pytest.mark.asyncio
    async def test_cleanup_expired_invitations(self, invitation_service):
        """Test cleaning up expired invitations."""
        # Create invitation with short expiration
        await invitation_service.create_invitation(
            email="user@example.com",
            invited_by_admin="admin",
            expires_hours=0,  # Expires immediately
        )

        # Verify invitation exists
        stats = await invitation_service.get_invitation_stats()
        assert stats["total"] == 1

        # Clean up expired invitations
        cleaned_count = await invitation_service.cleanup_expired_invitations()
        assert cleaned_count == 1

        # Verify invitation is removed
        stats = await invitation_service.get_invitation_stats()
        assert stats["total"] == 0

    @pytest.mark.asyncio
    async def test_invitation_statistics(self, invitation_service):
        """Test invitation statistics collection."""
        # Initial stats should be empty
        stats = await invitation_service.get_invitation_stats()
        assert stats["total"] == 0
        assert stats["active"] == 0
        assert stats["used"] == 0
        assert stats["expired"] == 0

        # Create active invitation
        await invitation_service.create_invitation(
            email="active@example.com", invited_by_admin="admin"
        )

        # Create and accept invitation
        await invitation_service.create_invitation(
            email="used@example.com", invited_by_admin="admin"
        )
        invitations = await invitation_service.list_invitations()
        used_token = next(
            inv.invitation_token for inv in invitations if inv.email == "used@example.com"
        )
        await invitation_service.accept_invitation(used_token)

        # Create expired invitation
        await invitation_service.create_invitation(
            email="expired@example.com", invited_by_admin="admin", expires_hours=0
        )

        # Check final stats
        stats = await invitation_service.get_invitation_stats()
        assert stats["total"] == 3
        assert stats["active"] == 1
        assert stats["used"] == 1
        assert stats["expired"] == 1


class TestUserInvitationEmailIntegration:
    """Test user invitation email functionality."""

    @pytest.fixture
    def auth_manager(self):
        """Create auth manager for email testing."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            enable_magic_links=True,
            secret_key="test-secret-key",
            base_url="https://coachiq.example.com",
        )
        return AuthManager(auth_settings)

    @pytest.mark.asyncio
    async def test_email_content_generation(self, auth_manager):
        """Test invitation email content generation."""
        notification_manager = MagicMock()

        # Capture email arguments
        sent_emails = []

        async def capture_send_email(**kwargs):
            sent_emails.append(kwargs)
            return True

        notification_manager.send_email = capture_send_email

        invitation_service = UserInvitationService(auth_manager, notification_manager)

        # Create invitation with personal message
        await invitation_service.create_invitation(
            email="user@example.com",
            invited_by_admin="admin",
            message="Welcome to our team!",
            role="user",
        )

        # Verify email was sent with correct content
        assert len(sent_emails) == 1
        email = sent_emails[0]

        assert email["to_email"] == "user@example.com"
        assert email["subject"] == "You're invited to CoachIQ"
        assert "Welcome to our team!" in email["body"]
        assert "https://coachiq.example.com/api/auth/invitation/accept?token=" in email["body"]
        assert email["is_html"] is False

    @pytest.mark.asyncio
    async def test_email_sending_failure(self, auth_manager):
        """Test handling of email sending failures."""
        notification_manager = MagicMock()

        # Make email sending fail
        async def failing_send_email(**kwargs):
            return False

        notification_manager.send_email = failing_send_email

        invitation_service = UserInvitationService(auth_manager, notification_manager)

        # Create invitation - should not raise exception
        response = await invitation_service.create_invitation(
            email="user@example.com", invited_by_admin="admin"
        )

        # Should indicate email was not sent
        assert response.invitation_sent is False
        # Should provide fallback invitation link
        assert response.invitation_link is not None

    @pytest.mark.asyncio
    async def test_email_sending_exception(self, auth_manager):
        """Test handling of email sending exceptions."""
        notification_manager = MagicMock()

        # Make email sending raise exception
        async def exception_send_email(**kwargs):
            raise Exception("SMTP server unavailable")

        notification_manager.send_email = exception_send_email

        invitation_service = UserInvitationService(auth_manager, notification_manager)

        # Create invitation - should not raise exception
        response = await invitation_service.create_invitation(
            email="user@example.com", invited_by_admin="admin"
        )

        # Should indicate email was not sent
        assert response.invitation_sent is False
        # Should provide fallback invitation link
        assert response.invitation_link is not None


class TestInvitationMagicLinkIntegration:
    """Test integration between invitations and magic link authentication."""

    @pytest.fixture
    def auth_manager(self):
        """Create auth manager with magic link support."""
        auth_settings = AuthenticationSettings(
            enabled=True,
            enable_magic_links=True,
            secret_key="test-secret-key-for-magic-links",
            base_url="http://localhost:8000",
        )
        return AuthManager(auth_settings)

    @pytest.mark.asyncio
    async def test_invitation_to_magic_link_flow(self, auth_manager):
        """Test complete flow from invitation to magic link authentication."""
        invitation_service = UserInvitationService(auth_manager, None)

        # Step 1: Admin creates invitation
        await invitation_service.create_invitation(
            email="newuser@example.com", invited_by_admin="admin@example.com"
        )

        # Step 2: User clicks invitation link and accepts
        invitations = await invitation_service.list_invitations()
        invitation_token = invitations[0].invitation_token

        magic_token = await invitation_service.accept_invitation(invitation_token)
        assert magic_token is not None

        # Step 3: Validate magic link token
        user_info = await auth_manager.validate_magic_link(magic_token)
        assert user_info is not None
        assert user_info["email"] == "newuser@example.com"
        assert user_info["user_id"] == "newuser@example.com"

        # Step 4: Generate final access token
        access_token = auth_manager.generate_token(
            user_id=user_info["user_id"],
            username=user_info["email"],
            additional_claims={"email": user_info["email"], "role": "user", "mode": "multi-user"},
        )

        assert access_token is not None

        # Step 5: Validate final access token
        payload = auth_manager.validate_token(access_token)
        assert payload["sub"] == "newuser@example.com"
        assert payload["email"] == "newuser@example.com"
        assert payload["role"] == "user"
        assert payload["mode"] == "multi-user"


# Pytest configuration for invitation tests
@pytest.fixture(autouse=True)
def reset_invitation_state():
    """Reset invitation state between tests."""
    # This fixture ensures each test starts with a clean state
    return
    # Any cleanup code would go here


# Mark all tests in this module as invitation tests
pytestmark = pytest.mark.auth
