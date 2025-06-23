"""
User Invitation Service for CoachIQ Authentication

This service handles user invitation functionality for multi-user authentication mode,
including invitation creation, management, and magic link integration.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, EmailStr

from backend.core.config import get_settings
from backend.services.auth_manager import AuthManager
from backend.services.notification_manager import NotificationManager

logger = logging.getLogger(__name__)


class UserInvitation(BaseModel):
    """User invitation model."""

    id: str
    email: EmailStr
    invited_by_admin: str
    invitation_token: str
    expires_at: datetime
    used: bool = False
    used_at: datetime | None = None
    created_at: datetime


class UserInvitationRequest(BaseModel):
    """Request model for creating user invitations."""

    email: EmailStr
    role: str = "user"  # user, admin, readonly
    message: str | None = None


class UserInvitationResponse(BaseModel):
    """Response model for user invitation operations."""

    id: str
    email: str
    invitation_sent: bool
    expires_at: datetime
    invitation_link: str | None = None


class UserInvitationService:
    """
    Service for managing user invitations in multi-user authentication mode.

    Handles invitation creation, validation, and magic link integration for
    passwordless user onboarding.
    """

    def __init__(
        self, auth_manager: AuthManager, notification_manager: NotificationManager | None = None
    ):
        """
        Initialize the user invitation service.

        Args:
            auth_manager: Authentication manager instance
            notification_manager: Notification manager for sending invitation emails
        """
        self.auth_manager = auth_manager
        self.notification_manager = notification_manager
        self.settings = get_settings()
        self.logger = logging.getLogger(__name__)

        # In-memory storage for invitations (will be replaced with database in Phase 3)
        self._invitations: dict[str, UserInvitation] = {}
        self._invitations_by_email: dict[str, str] = {}  # email -> invitation_id mapping

    async def create_invitation(
        self,
        email: EmailStr,
        invited_by_admin: str,
        _role: str = "user",
        message: str | None = None,
        expires_hours: int = 72,
    ) -> UserInvitationResponse:
        """
        Create a new user invitation.

        Args:
            email: Email address to invite
            invited_by_admin: Admin user creating the invitation
            _role: User role (user, admin, readonly) - reserved for future implementation
            message: Optional personal message from the admin
            expires_hours: Invitation expiration time in hours

        Returns:
            UserInvitationResponse: Created invitation details

        Raises:
            ValueError: If invitation already exists or email is invalid
        """
        # Check if invitation already exists for this email
        if email in self._invitations_by_email:
            existing_id = self._invitations_by_email[email]
            existing = self._invitations.get(existing_id)
            if existing and not existing.used and existing.expires_at > datetime.now(UTC):
                msg = f"Active invitation already exists for {email}"
                raise ValueError(msg)

        # Generate unique invitation ID and token
        invitation_id = str(uuid.uuid4())
        invitation_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)

        # Create invitation record
        invitation = UserInvitation(
            id=invitation_id,
            email=email,
            invited_by_admin=invited_by_admin,
            invitation_token=invitation_token,
            expires_at=expires_at,
            created_at=datetime.now(UTC),
        )

        # Store invitation
        self._invitations[invitation_id] = invitation
        self._invitations_by_email[email] = invitation_id

        # Generate invitation link
        base_url = self.auth_manager.settings.base_url or "http://localhost:8000"
        invitation_link = f"{base_url}/api/auth/invitation/accept?token={invitation_token}"

        # Send invitation email if notification manager is available
        invitation_sent = False
        if self.notification_manager:
            try:
                invitation_sent = await self._send_invitation_email(
                    invitation, invitation_link, message
                )
            except Exception as e:
                self.logger.error(f"Failed to send invitation email to {email}: {e}")

        self.logger.info(
            f"User invitation created for {email} by {invited_by_admin}, "
            f"expires at {expires_at}, email sent: {invitation_sent}"
        )

        return UserInvitationResponse(
            id=invitation_id,
            email=email,
            invitation_sent=invitation_sent,
            expires_at=expires_at,
            invitation_link=invitation_link if not invitation_sent else None,
        )

    async def validate_invitation_token(self, token: str) -> UserInvitation | None:
        """
        Validate an invitation token.

        Args:
            token: Invitation token to validate

        Returns:
            UserInvitation: Valid invitation or None if invalid/expired
        """
        for invitation in self._invitations.values():
            if (
                invitation.invitation_token == token
                and not invitation.used
                and invitation.expires_at > datetime.now(UTC)
            ):
                return invitation
        return None

    async def accept_invitation(self, token: str) -> str | None:
        """
        Accept an invitation and generate a magic link token.

        Args:
            token: Invitation token

        Returns:
            str: Magic link token for authentication, or None if invalid
        """
        invitation = await self.validate_invitation_token(token)
        if not invitation:
            return None

        # Mark invitation as used
        invitation.used = True
        invitation.used_at = datetime.now(UTC)

        # Generate magic link token for immediate authentication
        try:
            magic_link = await self.auth_manager.generate_magic_link(
                invitation.email,
                expires_minutes=15,  # Short expiration for immediate use
            )

            if magic_link:
                # Extract token from magic link URL
                magic_token = magic_link.split("token=")[1]
                self.logger.info(f"Invitation accepted for {invitation.email}")
                return magic_token

        except Exception as e:
            self.logger.error(f"Failed to generate magic link for accepted invitation: {e}")

        return None

    async def list_invitations(
        self, include_expired: bool = False, include_used: bool = False
    ) -> list[UserInvitation]:
        """
        List all invitations with optional filtering.

        Args:
            include_expired: Include expired invitations
            include_used: Include used invitations

        Returns:
            List[UserInvitation]: List of invitations
        """
        now = datetime.now(UTC)
        invitations = []

        for invitation in self._invitations.values():
            # Filter based on parameters
            if not include_expired and invitation.expires_at <= now:
                continue
            if not include_used and invitation.used:
                continue

            invitations.append(invitation)

        # Sort by creation date, newest first
        return sorted(invitations, key=lambda x: x.created_at, reverse=True)

    async def revoke_invitation(self, invitation_id: str) -> bool:
        """
        Revoke an invitation (mark as used/expired).

        Args:
            invitation_id: ID of invitation to revoke

        Returns:
            bool: True if invitation was revoked, False if not found
        """
        invitation = self._invitations.get(invitation_id)
        if not invitation:
            return False

        invitation.used = True
        invitation.used_at = datetime.now(UTC)

        self.logger.info(f"Invitation {invitation_id} for {invitation.email} was revoked")
        return True

    async def cleanup_expired_invitations(self) -> int:
        """
        Clean up expired invitations from memory.

        Returns:
            int: Number of invitations cleaned up
        """
        now = datetime.now(UTC)
        expired_ids = []

        for invitation_id, invitation in self._invitations.items():
            if invitation.expires_at <= now:
                expired_ids.append(invitation_id)

        # Remove expired invitations
        for invitation_id in expired_ids:
            invitation = self._invitations.pop(invitation_id, None)
            if invitation:
                self._invitations_by_email.pop(invitation.email, None)

        if expired_ids:
            self.logger.info(f"Cleaned up {len(expired_ids)} expired invitations")

        return len(expired_ids)

    async def get_invitation_stats(self) -> dict[str, int]:
        """
        Get invitation statistics.

        Returns:
            Dict[str, int]: Invitation statistics
        """
        now = datetime.now(UTC)
        total = len(self._invitations)
        active = sum(
            1 for inv in self._invitations.values() if not inv.used and inv.expires_at > now
        )
        used = sum(1 for inv in self._invitations.values() if inv.used)
        expired = sum(
            1 for inv in self._invitations.values() if not inv.used and inv.expires_at <= now
        )

        return {"total": total, "active": active, "used": used, "expired": expired}

    async def _send_invitation_email(
        self, invitation: UserInvitation, invitation_link: str, message: str | None = None
    ) -> bool:
        """
        Send invitation email using the notification manager.

        Args:
            invitation: Invitation to send
            invitation_link: Generated invitation link
            message: Optional personal message

        Returns:
            bool: True if email was sent successfully
        """
        if not self.notification_manager:
            return False

        try:
            # Prepare email content
            subject = "You're invited to CoachIQ"

            # Create email body with invitation link
            body_parts = [
                "You've been invited to join CoachIQ by an administrator.",
                "",
                "Click the link below to accept your invitation:",
                f"{invitation_link}",
                "",
                f"This invitation will expire on {invitation.expires_at.strftime('%Y-%m-%d at %H:%M UTC')}.",
            ]

            if message:
                body_parts.insert(1, f"Personal message: {message}")
                body_parts.insert(2, "")

            body = "\n".join(body_parts)

            # Send email using notification manager
            success = await self.notification_manager.send_email(
                to_email=invitation.email, subject=subject, body=body, is_html=False
            )

            if success:
                self.logger.info(f"Invitation email sent successfully to {invitation.email}")
            else:
                self.logger.error(f"Failed to send invitation email to {invitation.email}")

            return success

        except Exception as e:
            self.logger.error(f"Exception sending invitation email to {invitation.email}: {e}")
            return False

    async def get_invitations_by_admin(self, admin_id: str) -> list[UserInvitation]:
        """
        Get all invitations created by a specific admin.

        Args:
            admin_id: Admin user ID

        Returns:
            List of invitations
        """
        return await self._repository.get_invitations_by_admin(admin_id)
