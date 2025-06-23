"""User Invitation Repository

Handles data access for user invitation management including:
- Invitation storage and retrieval
- Token validation
- Expiration tracking
- Usage statistics
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from backend.repositories.base import MonitoredRepository

logger = logging.getLogger(__name__)


class UserInvitationRepository(MonitoredRepository):
    """Repository for user invitation data management."""

    def __init__(self, database_manager, performance_monitor):
        """Initialize the repository.

        Args:
            database_manager: Database manager for persistence
            performance_monitor: Performance monitoring instance
        """
        super().__init__(database_manager, performance_monitor)

        # In-memory storage (would be database tables in production)
        self._invitations: dict[str, Any] = {}  # id -> UserInvitation
        self._invitations_by_email: dict[str, str] = {}  # email -> invitation_id
        self._invitations_by_token: dict[str, str] = {}  # token -> invitation_id

    @MonitoredRepository._monitored_operation("store_invitation")
    async def store_invitation(self, invitation: Any) -> bool:  # invitation: UserInvitation
        """Store a new invitation.

        Args:
            invitation: User invitation to store

        Returns:
            True if stored successfully
        """
        try:
            # Store by ID
            self._invitations[invitation.id] = invitation

            # Update email index
            self._invitations_by_email[invitation.email] = invitation.id

            # Update token index
            self._invitations_by_token[invitation.invitation_token] = invitation.id

            logger.info(f"Stored invitation {invitation.id} for {invitation.email}")
            return True

        except Exception as e:
            logger.error(f"Error storing invitation: {e}")
            return False

    @MonitoredRepository._monitored_operation("get_invitation_by_id")
    async def get_invitation_by_id(
        self, invitation_id: str
    ) -> Any | None:  # Optional[UserInvitation]
        """Get invitation by ID.

        Args:
            invitation_id: Invitation identifier

        Returns:
            Invitation if found
        """
        return self._invitations.get(invitation_id)

    @MonitoredRepository._monitored_operation("get_invitation_by_email")
    async def get_invitation_by_email(self, email: str) -> Any | None:  # Optional[UserInvitation]
        """Get invitation by email.

        Args:
            email: Email address

        Returns:
            Invitation if found
        """
        invitation_id = self._invitations_by_email.get(email)
        if invitation_id:
            return self._invitations.get(invitation_id)
        return None

    @MonitoredRepository._monitored_operation("get_invitation_by_token")
    async def get_invitation_by_token(self, token: str) -> Any | None:  # Optional[UserInvitation]
        """Get invitation by token.

        Args:
            token: Invitation token

        Returns:
            Invitation if found
        """
        invitation_id = self._invitations_by_token.get(token)
        if invitation_id:
            return self._invitations.get(invitation_id)
        return None

    @MonitoredRepository._monitored_operation("update_invitation")
    async def update_invitation(self, invitation: Any) -> bool:  # invitation: UserInvitation
        """Update an existing invitation.

        Args:
            invitation: Updated invitation

        Returns:
            True if updated successfully
        """
        if invitation.id not in self._invitations:
            logger.error(f"Invitation {invitation.id} not found for update")
            return False

        self._invitations[invitation.id] = invitation
        return True

    @MonitoredRepository._monitored_operation("list_invitations")
    async def list_invitations(
        self, include_expired: bool = False, include_used: bool = False
    ) -> list[Any]:  # List[UserInvitation]
        """List invitations with optional filtering.

        Args:
            include_expired: Include expired invitations
            include_used: Include used invitations

        Returns:
            List of invitations
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

    @MonitoredRepository._monitored_operation("delete_invitation")
    async def delete_invitation(self, invitation_id: str) -> bool:
        """Delete an invitation.

        Args:
            invitation_id: Invitation to delete

        Returns:
            True if deleted successfully
        """
        invitation = self._invitations.get(invitation_id)
        if not invitation:
            return False

        # Remove from all indexes
        self._invitations.pop(invitation_id, None)
        self._invitations_by_email.pop(invitation.email, None)
        self._invitations_by_token.pop(invitation.invitation_token, None)

        logger.info(f"Deleted invitation {invitation_id}")
        return True

    @MonitoredRepository._monitored_operation("cleanup_expired")
    async def cleanup_expired(self) -> int:
        """Clean up expired invitations.

        Returns:
            Number of invitations cleaned up
        """
        now = datetime.now(UTC)
        expired_ids = []

        for invitation_id, invitation in self._invitations.items():
            if invitation.expires_at <= now:
                expired_ids.append(invitation_id)

        # Remove expired invitations
        for invitation_id in expired_ids:
            await self.delete_invitation(invitation_id)

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired invitations")

        return len(expired_ids)

    @MonitoredRepository._monitored_operation("get_statistics")
    async def get_statistics(self) -> dict[str, int]:
        """Get invitation statistics.

        Returns:
            Statistics dictionary
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

    @MonitoredRepository._monitored_operation("check_email_has_active")
    async def check_email_has_active(self, email: str) -> bool:
        """Check if email has an active invitation.

        Args:
            email: Email to check

        Returns:
            True if active invitation exists
        """
        invitation = await self.get_invitation_by_email(email)
        if invitation:
            now = datetime.now(UTC)
            return not invitation.used and invitation.expires_at > now
        return False

    @MonitoredRepository._monitored_operation("mark_as_used")
    async def mark_as_used(self, invitation_id: str) -> bool:
        """Mark invitation as used.

        Args:
            invitation_id: Invitation to mark

        Returns:
            True if marked successfully
        """
        invitation = self._invitations.get(invitation_id)
        if not invitation:
            return False

        invitation.used = True
        invitation.used_at = datetime.now(UTC)

        logger.info(f"Marked invitation {invitation_id} as used")
        return True

    @MonitoredRepository._monitored_operation("get_invitations_by_admin")
    async def get_invitations_by_admin(self, admin_id: str) -> list[Any]:  # List[UserInvitation]
        """Get all invitations created by a specific admin.

        Args:
            admin_id: Admin user ID

        Returns:
            List of invitations
        """
        invitations = [
            inv for inv in self._invitations.values() if inv.invited_by_admin == admin_id
        ]

        # Sort by creation date, newest first
        return sorted(invitations, key=lambda x: x.created_at, reverse=True)
