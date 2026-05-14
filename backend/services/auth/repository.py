"""
Authentication Repository

Repository pattern implementation for authentication data persistence.
Provides data access methods for all auth-related operations following
the established patterns in the CoachIQ codebase.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.auth import (
    AdminSettings,
    AuthEvent,
    MagicLinkToken,
    User,
    UserMFA,
    UserMFABackupCode,
    UserSession,
)
from backend.services.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class AuthRepository:
    """
    Repository for authentication data persistence.

    Provides async data access methods for all authentication-related
    operations including users, sessions, admin settings, and auth events.
    """

    def __init__(self, database_manager: DatabaseManager):
        """
        Initialize the auth repository.

        Args:
            database_manager: Database manager instance
        """
        self.db_manager = database_manager
        self.logger = logging.getLogger(__name__)

    async def _handle_null_backend(self, operation: str) -> Any:
        """Handle operations when persistence is disabled."""
        self.logger.debug(f"Auth repository {operation} called but persistence is disabled")
        return None

    async def _execute_with_session(self, operation, *args, **kwargs):
        """Execute a database operation with proper session management."""
        # Check for null backend
        database_url = self.db_manager.engine.settings.get_database_url()
        if database_url == "null://memory":
            return await self._handle_null_backend(operation.__name__)

        try:
            async with self.db_manager.get_session() as session:
                return await operation(session, *args, **kwargs)
        except Exception as e:
            self.logger.error(f"Database operation {operation.__name__} failed: {e}")
            return None

    async def _execute_bool_operation(self, operation, *args, **kwargs) -> bool:
        """Execute a database operation that returns bool."""
        database_url = self.db_manager.engine.settings.get_database_url()
        if database_url == "null://memory":
            self.logger.debug(
                f"Auth repository {operation.__name__} called but persistence is disabled"
            )
            return False

        try:
            async with self.db_manager.get_session() as session:
                result = await operation(session, *args, **kwargs)
                return result if isinstance(result, bool) else False
        except Exception as e:
            self.logger.error(f"Database operation {operation.__name__} failed: {e}")
            return False

    async def _execute_int_operation(self, operation, *args, **kwargs) -> int:
        """Execute a database operation that returns int."""
        database_url = self.db_manager.engine.settings.get_database_url()
        if database_url == "null://memory":
            self.logger.debug(
                f"Auth repository {operation.__name__} called but persistence is disabled"
            )
            return 0

        try:
            async with self.db_manager.get_session() as session:
                result = await operation(session, *args, **kwargs)
                return result if isinstance(result, int) else 0
        except Exception as e:
            self.logger.error(f"Database operation {operation.__name__} failed: {e}")
            return 0

    async def _execute_list_operation(self, operation, *args, **kwargs) -> list:
        """Execute a database operation that returns list."""
        database_url = self.db_manager.engine.settings.get_database_url()
        if database_url == "null://memory":
            self.logger.debug(
                f"Auth repository {operation.__name__} called but persistence is disabled"
            )
            return []

        try:
            async with self.db_manager.get_session() as session:
                result = await operation(session, *args, **kwargs)
                return result if isinstance(result, list) else []
        except Exception as e:
            self.logger.error(f"Database operation {operation.__name__} failed: {e}")
            return []

    # Admin Settings Operations

    async def get_admin_setting(self, key: str) -> str | None:
        """Get an admin setting value."""

        async def _get_setting(session: AsyncSession, setting_key: str) -> str | None:
            result = await session.execute(
                select(AdminSettings.setting_value).where(AdminSettings.setting_key == setting_key)
            )
            row = result.first()
            return row[0] if row else None

        return await self._execute_with_session(_get_setting, key)

    async def set_admin_setting(
        self,
        key: str,
        value: str,
        setting_type: str = "string",
        description: str | None = None,
        is_secret: bool = False,
    ) -> bool:
        """Set an admin setting value."""

        async def _set_setting(
            session: AsyncSession,
            setting_key: str,
            setting_value: str,
            setting_type: str,
            description: str | None,
            is_secret: bool,
        ) -> bool:
            try:
                # Check if setting exists
                result = await session.execute(
                    select(AdminSettings.id).where(AdminSettings.setting_key == setting_key)
                )
                existing = result.first()

                if existing:
                    # Update existing setting
                    await session.execute(
                        update(AdminSettings)
                        .where(AdminSettings.setting_key == setting_key)
                        .values(
                            setting_value=setting_value,
                            setting_type=setting_type,
                            description=description,
                            is_secret=is_secret,
                            updated_at=datetime.now(UTC),
                        )
                    )
                else:
                    # Create new setting
                    setting = AdminSettings(
                        id=str(uuid4()),
                        setting_key=setting_key,
                        setting_value=setting_value,
                        setting_type=setting_type,
                        description=description,
                        is_secret=is_secret,
                    )
                    session.add(setting)

                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to set admin setting {setting_key}: {e}")
                return False

        return await self._execute_bool_operation(
            _set_setting, key, value, setting_type, description, is_secret
        )

    async def delete_admin_setting(self, key: str) -> bool:
        """Delete an admin setting."""

        async def _delete_setting(session: AsyncSession, setting_key: str) -> bool:
            try:
                result = await session.execute(
                    delete(AdminSettings).where(AdminSettings.setting_key == setting_key)
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to delete admin setting {setting_key}: {e}")
                return False

        return await self._execute_bool_operation(_delete_setting, key)

    # Admin Credentials Operations

    async def get_admin_credentials(self) -> dict[str, Any] | None:
        """Get admin credentials from database."""

        async def _get_credentials(session: AsyncSession) -> dict[str, Any] | None:
            try:
                # Get all admin-related settings
                result = await session.execute(
                    select(
                        AdminSettings.setting_key,
                        AdminSettings.setting_value,
                        AdminSettings.setting_type,
                    ).where(AdminSettings.setting_key.like("admin_%"))
                )
                rows = result.fetchall()

                if not rows:
                    return None

                # Convert to dict with proper field mapping
                credentials = {}
                for row in rows:
                    key, value, setting_type = row
                    if setting_type == "boolean":
                        credentials[key] = value.lower() == "true"
                    elif setting_type == "datetime":
                        credentials[key] = datetime.fromisoformat(value) if value else None
                    else:
                        credentials[key] = value

                # Check if we have the essential fields and remap to expected format
                if "admin_username" in credentials and "admin_password_hash" in credentials:
                    # Remap fields to match AuthManager expectations
                    return {
                        "username": credentials["admin_username"],
                        "password_hash": credentials["admin_password_hash"],
                        "created_at": credentials.get("admin_created_at"),
                        "password_auto_generated": credentials.get(
                            "admin_password_auto_generated", False
                        ),
                    }

                return None
            except Exception as e:
                self.logger.error(f"Failed to get admin credentials: {e}")
                return None

        return await self._execute_with_session(_get_credentials)

    async def set_admin_credentials(
        self,
        username: str,
        password_hash: str,
        auto_generated: bool = False,
    ) -> bool:
        """Set admin credentials in database."""

        async def _set_credentials(
            session: AsyncSession,
            admin_username: str,
            admin_password_hash: str,
            admin_auto_generated: bool,
        ) -> bool:
            try:
                now = datetime.now(UTC)

                # Store admin credentials as multiple settings
                settings = [
                    ("admin_username", admin_username, "string", "Admin username"),
                    (
                        "admin_password_hash",
                        admin_password_hash,
                        "string",
                        "Admin password hash",
                        True,
                    ),
                    ("admin_created_at", now.isoformat(), "datetime", "Admin creation timestamp"),
                    (
                        "admin_password_auto_generated",
                        str(admin_auto_generated),
                        "boolean",
                        "Whether password was auto-generated",
                    ),
                ]

                for key, value, setting_type, description, *is_secret in settings:
                    secret = bool(is_secret)

                    # Check if setting exists
                    result = await session.execute(
                        select(AdminSettings.id).where(AdminSettings.setting_key == key)
                    )
                    existing = result.first()

                    if existing:
                        # Update existing setting
                        await session.execute(
                            update(AdminSettings)
                            .where(AdminSettings.setting_key == key)
                            .values(
                                setting_value=value,
                                setting_type=setting_type,
                                description=description,
                                is_secret=secret,
                                updated_at=now,
                            )
                        )
                    else:
                        # Create new setting
                        setting = AdminSettings(
                            id=str(uuid4()),
                            setting_key=key,
                            setting_value=value,
                            setting_type=setting_type,
                            description=description,
                            is_secret=secret,
                        )
                        session.add(setting)

                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to set admin credentials: {e}")
                return False

        return await self._execute_bool_operation(
            _set_credentials, username, password_hash, auto_generated
        )

    # User Operations

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Get a user by ID."""

        async def _get_user(session: AsyncSession, uid: str) -> User | None:
            result = await session.execute(select(User).where(User.id == uid))
            return result.scalar_one_or_none()

        return await self._execute_with_session(_get_user, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email."""

        async def _get_user(session: AsyncSession, user_email: str) -> User | None:
            result = await session.execute(select(User).where(User.email == user_email))
            return result.scalar_one_or_none()

        return await self._execute_with_session(_get_user, email)

    async def create_user(
        self,
        email: str,
        username: str | None = None,
        display_name: str | None = None,
        is_admin: bool = False,
        preferences: dict | None = None,
    ) -> User | None:
        """Create a new user."""

        async def _create_user(
            session: AsyncSession,
            user_email: str,
            user_username: str | None,
            user_display_name: str | None,
            user_is_admin: bool,
            user_preferences: dict | None,
        ) -> User | None:
            try:
                user = User(
                    id=str(uuid4()),
                    email=user_email,
                    username=user_username,
                    display_name=user_display_name,
                    is_admin=user_is_admin,
                    preferences=user_preferences,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user
            except IntegrityError as e:
                await session.rollback()
                self.logger.error(f"User with email {user_email} already exists: {e}")
                return None
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to create user {user_email}: {e}")
                return None

        return await self._execute_with_session(
            _create_user, email, username, display_name, is_admin, preferences
        )

    # User Session Operations

    async def create_user_session(
        self,
        user_id: str,
        session_token: str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_info: dict | None = None,
    ) -> UserSession | None:
        """Create a new user session."""

        async def _create_session(
            session: AsyncSession,
            uid: str,
            token: str,
            expires: datetime,
            ip: str | None,
            agent: str | None,
            device: dict | None,
        ) -> UserSession | None:
            try:
                user_session = UserSession(
                    id=str(uuid4()),
                    user_id=uid,
                    session_token=token,
                    expires_at=expires,
                    ip_address=ip,
                    user_agent=agent,
                    device_info=device,
                )
                session.add(user_session)
                await session.commit()
                await session.refresh(user_session)
                return user_session
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to create user session: {e}")
                return None

        return await self._execute_with_session(
            _create_session, user_id, session_token, expires_at, ip_address, user_agent, device_info
        )

    async def get_user_session(self, session_token: str) -> UserSession | None:
        """Get a user session by token."""

        async def _get_session(session: AsyncSession, token: str) -> UserSession | None:
            result = await session.execute(
                select(UserSession).where(UserSession.session_token == token)
            )
            return result.scalar_one_or_none()

        return await self._execute_with_session(_get_session, session_token)

    async def update_session_last_accessed(self, session_token: str) -> bool:
        """Update the last accessed time for a session."""

        async def _update_session(session: AsyncSession, token: str) -> bool:
            try:
                result = await session.execute(
                    update(UserSession)
                    .where(UserSession.session_token == token)
                    .values(last_accessed_at=datetime.now(UTC))
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to update session last accessed: {e}")
                return False

        return await self._execute_bool_operation(_update_session, session_token)

    async def revoke_user_session(self, session_token: str) -> bool:
        """Revoke a user session."""

        async def _revoke_session(session: AsyncSession, token: str) -> bool:
            try:
                result = await session.execute(
                    update(UserSession)
                    .where(UserSession.session_token == token)
                    .values(is_active=False)
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to revoke session: {e}")
                return False

        return await self._execute_bool_operation(_revoke_session, session_token)

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user."""

        async def _revoke_all_sessions(session: AsyncSession, uid: str) -> int:
            try:
                result = await session.execute(
                    update(UserSession).where(UserSession.user_id == uid).values(is_active=False)
                )
                await session.commit()
                return result.rowcount
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to revoke all sessions for user {uid}: {e}")
                return 0

        return await self._execute_int_operation(_revoke_all_sessions, user_id)

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""

        async def _cleanup_sessions(session: AsyncSession) -> int:
            try:
                now = datetime.now(UTC)
                result = await session.execute(
                    delete(UserSession).where(UserSession.expires_at < now)
                )
                await session.commit()
                return result.rowcount
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to cleanup expired sessions: {e}")
                return 0

        return await self._execute_int_operation(_cleanup_sessions)

    # Auth Event Operations

    async def create_auth_event(
        self,
        user_id: str | None,
        event_type: str,
        success: bool,
        provider: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        email: str | None = None,
        details: dict | None = None,
        error_message: str | None = None,
    ) -> AuthEvent | None:
        """Create an authentication event."""

        async def _create_event(
            session: AsyncSession,
            uid: str | None,
            evt_type: str,
            evt_success: bool,
            evt_provider: str | None,
            evt_ip: str | None,
            evt_agent: str | None,
            evt_email: str | None,
            evt_details: dict | None,
            evt_error: str | None,
        ) -> AuthEvent | None:
            try:
                auth_event = AuthEvent(
                    id=str(uuid4()),
                    user_id=uid,
                    event_type=evt_type,
                    success=evt_success,
                    provider=evt_provider,
                    ip_address=evt_ip,
                    user_agent=evt_agent,
                    email=evt_email,
                    details=evt_details,
                    error_message=evt_error,
                )
                session.add(auth_event)
                await session.commit()
                await session.refresh(auth_event)
                return auth_event
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to create auth event: {e}")
                return None

        return await self._execute_with_session(
            _create_event,
            user_id,
            event_type,
            success,
            provider,
            ip_address,
            user_agent,
            email,
            details,
            error_message,
        )

    async def get_auth_events_for_user(
        self,
        user_id: str | None = None,
        email: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[AuthEvent]:
        """Get authentication events for a user."""

        async def _get_events(
            session: AsyncSession,
            uid: str | None,
            user_email: str | None,
            evt_type: str | None,
            evt_limit: int,
            evt_since: datetime | None,
        ) -> list[AuthEvent]:
            try:
                query = select(AuthEvent)

                # Build where conditions
                conditions = []
                if uid:
                    conditions.append(AuthEvent.user_id == uid)
                if user_email:
                    conditions.append(AuthEvent.email == user_email)
                if evt_type:
                    conditions.append(AuthEvent.event_type == evt_type)
                if evt_since:
                    conditions.append(AuthEvent.created_at >= evt_since)

                if conditions:
                    query = query.where(and_(*conditions))

                query = query.order_by(AuthEvent.created_at.desc()).limit(evt_limit)

                result = await session.execute(query)
                return list(result.scalars().all())
            except Exception as e:
                self.logger.error(f"Failed to get auth events: {e}")
                return []

        return await self._execute_list_operation(
            _get_events, user_id, email, event_type, limit, since
        )

    async def get_failed_attempts_count(
        self,
        user_id: str | None = None,
        email: str | None = None,
        since: datetime | None = None,
    ) -> int:
        """Get count of failed authentication attempts."""

        async def _count_failed_attempts(
            session: AsyncSession,
            uid: str | None,
            user_email: str | None,
            evt_since: datetime | None,
        ) -> int:
            try:
                query = select(func.count(AuthEvent.id)).where(
                    and_(
                        not AuthEvent.success,
                        AuthEvent.event_type.in_(["login", "token_refresh", "admin_login"]),
                    )
                )

                # Add user/email filter
                if uid:
                    query = query.where(AuthEvent.user_id == uid)
                elif user_email:
                    query = query.where(AuthEvent.email == user_email)

                # Add time filter
                if evt_since:
                    query = query.where(AuthEvent.created_at >= evt_since)

                result = await session.execute(query)
                return result.scalar() or 0
            except Exception as e:
                self.logger.error(f"Failed to count failed attempts: {e}")
                return 0

        return await self._execute_int_operation(_count_failed_attempts, user_id, email, since)

    # Magic Link Token Operations

    async def create_magic_link_token(
        self,
        email: str,
        token_hash: str,
        expires_at: datetime,
        redirect_url: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> MagicLinkToken | None:
        """Create a magic link token."""

        async def _create_token(
            session: AsyncSession,
            token_email: str,
            token_hash: str,
            token_expires: datetime,
            token_redirect: str | None,
            token_ip: str | None,
            token_agent: str | None,
        ) -> MagicLinkToken | None:
            try:
                magic_token = MagicLinkToken(
                    id=str(uuid4()),
                    email=token_email,
                    token_hash=token_hash,
                    expires_at=token_expires,
                    redirect_url=token_redirect,
                    ip_address=token_ip,
                    user_agent=token_agent,
                )
                session.add(magic_token)
                await session.commit()
                await session.refresh(magic_token)
                return magic_token
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to create magic link token: {e}")
                return None

        return await self._execute_with_session(
            _create_token, email, token_hash, expires_at, redirect_url, ip_address, user_agent
        )

    async def get_magic_link_token(self, token_hash: str) -> MagicLinkToken | None:
        """Get a magic link token by hash."""

        async def _get_token(session: AsyncSession, hash_value: str) -> MagicLinkToken | None:
            result = await session.execute(
                select(MagicLinkToken).where(MagicLinkToken.token_hash == hash_value)
            )
            return result.scalar_one_or_none()

        return await self._execute_with_session(_get_token, token_hash)

    async def use_magic_link_token(self, token_hash: str) -> bool:
        """Mark a magic link token as used."""

        async def _use_token(session: AsyncSession, hash_value: str) -> bool:
            try:
                result = await session.execute(
                    update(MagicLinkToken)
                    .where(MagicLinkToken.token_hash == hash_value)
                    .values(used=True, used_at=datetime.now(UTC))
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to use magic link token: {e}")
                return False

        return await self._execute_bool_operation(_use_token, token_hash)

    async def cleanup_expired_magic_links(self) -> int:
        """Clean up expired magic link tokens."""

        async def _cleanup_tokens(session: AsyncSession) -> int:
            try:
                now = datetime.now(UTC)
                result = await session.execute(
                    delete(MagicLinkToken).where(MagicLinkToken.expires_at < now)
                )
                await session.commit()
                return result.rowcount
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to cleanup expired magic link tokens: {e}")
                return 0

        return await self._execute_int_operation(_cleanup_tokens)

    # MFA Operations

    async def get_user_mfa(self, user_id: str) -> UserMFA | None:
        """Get MFA settings for a user."""

        async def _get_mfa(session: AsyncSession, uid: str) -> UserMFA | None:
            result = await session.execute(select(UserMFA).where(UserMFA.user_id == uid))
            return result.scalar_one_or_none()

        return await self._execute_with_session(_get_mfa, user_id)

    async def create_user_mfa(
        self,
        user_id: str,
        totp_secret: str,
        backup_codes: list[str] | None = None,
        recovery_codes: list[str] | None = None,
    ) -> UserMFA | None:
        """Create MFA settings for a user."""

        async def _create_mfa(
            session: AsyncSession,
            uid: str,
            secret: str,
            backup_codes_list: list[str] | None,
            recovery_codes_list: list[str] | None,
        ) -> UserMFA | None:
            try:
                user_mfa = UserMFA(
                    id=str(uuid4()),
                    user_id=uid,
                    totp_secret=secret,
                    totp_enabled=False,
                    is_enabled=False,
                    backup_codes_generated=bool(backup_codes_list),
                    recovery_codes=recovery_codes_list or [],
                )
                session.add(user_mfa)
                await session.flush()  # Get the ID

                # Create backup codes if provided
                if backup_codes_list:
                    for code in backup_codes_list:
                        # Hash the backup code for storage
                        import hashlib

                        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()

                        backup_code = UserMFABackupCode(
                            id=str(uuid4()),
                            user_mfa_id=user_mfa.id,
                            code_hash=code_hash,
                            is_used=False,
                        )
                        session.add(backup_code)

                await session.commit()
                await session.refresh(user_mfa)
                return user_mfa
            except IntegrityError as e:
                await session.rollback()
                self.logger.error(f"MFA already exists for user {uid}: {e}")
                return None
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to create MFA for user {uid}: {e}")
                return None

        return await self._execute_with_session(
            _create_mfa, user_id, totp_secret, backup_codes, recovery_codes
        )

    async def update_user_mfa(
        self,
        user_id: str,
        is_enabled: bool | None = None,
        totp_enabled: bool | None = None,
        last_used_at: datetime | None = None,
        recovery_codes: list[str] | None = None,
    ) -> bool:
        """Update MFA settings for a user."""

        async def _update_mfa(
            session: AsyncSession,
            uid: str,
            enabled: bool | None,
            totp_enabled_val: bool | None,
            last_used: datetime | None,
            recovery_codes_list: list[str] | None,
        ) -> bool:
            try:
                # Build update values
                update_values = {"updated_at": datetime.now(UTC)}

                if enabled is not None:
                    update_values["is_enabled"] = enabled
                if totp_enabled_val is not None:
                    update_values["totp_enabled"] = totp_enabled_val
                if last_used is not None:
                    update_values["last_used_at"] = last_used
                if recovery_codes_list is not None:
                    update_values["recovery_codes"] = recovery_codes_list

                result = await session.execute(
                    update(UserMFA).where(UserMFA.user_id == uid).values(**update_values)
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to update MFA for user {uid}: {e}")
                return False

        return await self._execute_bool_operation(
            _update_mfa, user_id, is_enabled, totp_enabled, last_used_at, recovery_codes
        )

    async def delete_user_mfa(self, user_id: str) -> bool:
        """Delete MFA settings for a user."""

        async def _delete_mfa(session: AsyncSession, uid: str) -> bool:
            try:
                result = await session.execute(delete(UserMFA).where(UserMFA.user_id == uid))
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to delete MFA for user {uid}: {e}")
                return False

        return await self._execute_bool_operation(_delete_mfa, user_id)

    async def get_user_backup_codes(self, user_id: str) -> list[UserMFABackupCode]:
        """Get backup codes for a user."""

        async def _get_backup_codes(session: AsyncSession, uid: str) -> list[UserMFABackupCode]:
            try:
                result = await session.execute(
                    select(UserMFABackupCode)
                    .join(UserMFA)
                    .where(UserMFA.user_id == uid)
                    .order_by(UserMFABackupCode.created_at)
                )
                return list(result.scalars().all())
            except Exception as e:
                self.logger.error(f"Failed to get backup codes for user {uid}: {e}")
                return []

        return await self._execute_list_operation(_get_backup_codes, user_id)

    async def use_backup_code(self, user_id: str, code: str) -> bool:
        """Mark a backup code as used."""

        async def _use_backup_code(session: AsyncSession, uid: str, backup_code: str) -> bool:
            try:
                # Hash the code to match stored hash
                import hashlib

                code_hash = hashlib.sha256(backup_code.upper().encode()).hexdigest()

                # Find and update the backup code
                result = await session.execute(
                    update(UserMFABackupCode)
                    .where(
                        and_(
                            UserMFABackupCode.user_mfa_id.in_(
                                select(UserMFA.id).where(UserMFA.user_id == uid)
                            ),
                            UserMFABackupCode.code_hash == code_hash,
                            UserMFABackupCode.is_used == False,  # noqa: E712
                        )
                    )
                    .values(is_used=True, used_at=datetime.now(UTC))
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to use backup code for user {uid}: {e}")
                return False

        return await self._execute_bool_operation(_use_backup_code, user_id, code)

    async def regenerate_backup_codes(self, user_id: str, new_backup_codes: list[str]) -> bool:
        """Replace all backup codes for a user with new ones."""

        async def _regenerate_codes(session: AsyncSession, uid: str, codes: list[str]) -> bool:
            try:
                # Get the UserMFA record
                mfa_result = await session.execute(select(UserMFA.id).where(UserMFA.user_id == uid))
                mfa_record = mfa_result.first()
                if not mfa_record:
                    return False

                mfa_id = mfa_record[0]

                # Delete existing backup codes
                await session.execute(
                    delete(UserMFABackupCode).where(UserMFABackupCode.user_mfa_id == mfa_id)
                )

                # Create new backup codes
                import hashlib

                for code in codes:
                    code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
                    backup_code = UserMFABackupCode(
                        id=str(uuid4()),
                        user_mfa_id=mfa_id,
                        code_hash=code_hash,
                        is_used=False,
                    )
                    session.add(backup_code)

                # Update MFA record
                await session.execute(
                    update(UserMFA)
                    .where(UserMFA.id == mfa_id)
                    .values(backup_codes_generated=True, updated_at=datetime.now(UTC))
                )

                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to regenerate backup codes for user {uid}: {e}")
                return False

        return await self._execute_bool_operation(_regenerate_codes, user_id, new_backup_codes)

    async def verify_backup_code(self, user_id: str, code: str) -> bool:
        """Verify if a backup code is valid and unused."""

        async def _verify_code(session: AsyncSession, uid: str, backup_code: str) -> bool:
            try:
                import hashlib

                code_hash = hashlib.sha256(backup_code.upper().encode()).hexdigest()

                result = await session.execute(
                    select(UserMFABackupCode.id)
                    .join(UserMFA)
                    .where(
                        and_(
                            UserMFA.user_id == uid,
                            UserMFABackupCode.code_hash == code_hash,
                            UserMFABackupCode.is_used == False,  # noqa: E712
                        )
                    )
                )
                return result.first() is not None
            except Exception as e:
                self.logger.error(f"Failed to verify backup code for user {uid}: {e}")
                return False

        return await self._execute_bool_operation(_verify_code, user_id, code)

    async def count_unused_backup_codes(self, user_id: str) -> int:
        """Count unused backup codes for a user."""

        async def _count_codes(session: AsyncSession, uid: str) -> int:
            try:
                result = await session.execute(
                    select(func.count(UserMFABackupCode.id))
                    .join(UserMFA)
                    .where(
                        and_(
                            UserMFA.user_id == uid,
                            UserMFABackupCode.is_used == False,  # noqa: E712
                        )
                    )
                )
                return result.scalar() or 0
            except Exception as e:
                self.logger.error(f"Failed to count backup codes for user {uid}: {e}")
                return 0

        return await self._execute_int_operation(_count_codes, user_id)

    async def get_all_user_mfa(self) -> list[UserMFA]:
        """Get all MFA settings for all users."""

        async def _get_all_mfa(session: AsyncSession) -> list[UserMFA]:
            try:
                result = await session.execute(select(UserMFA).order_by(UserMFA.created_at))
                return list(result.scalars().all())
            except Exception as e:
                self.logger.error(f"Failed to get all MFA settings: {e}")
                return []

        return await self._execute_list_operation(_get_all_mfa)

    # Utility Methods

    async def health_check(self) -> bool:
        """Perform a health check on the auth repository."""
        # Check for null backend
        database_url = self.db_manager.engine.settings.get_database_url()
        if database_url == "null://memory":
            return True  # Null backend is considered healthy

        try:
            async with self.db_manager.get_session() as session:
                # Simple query to verify database connectivity
                await session.execute(select(func.count()).select_from(AdminSettings))
                return True
        except Exception as e:
            self.logger.error(f"Auth repository health check failed: {e}")
            return False
