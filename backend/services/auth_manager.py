"""
Authentication Manager for CoachIQ

This module provides a centralized authentication service that handles:
- Authentication mode detection (none, single-user, multi-user)
- JWT token generation and validation
- Admin user management
- Session management
- Magic link generation for passwordless authentication
- Integration with notification system for magic links

The AuthManager follows the existing service patterns in the codebase and
integrates with the feature management system.

Example:
    >>> auth_manager = AuthManager(auth_settings, notification_manager)
    >>> admin_token = await auth_manager.authenticate_admin(username, password)
    >>> magic_link = await auth_manager.generate_magic_link("user@example.com")
    >>> user = await auth_manager.validate_token(token)
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

try:
    import jwt
    import pyotp
    from passlib.context import CryptContext

    JWT_AVAILABLE = True
    BCRYPT_AVAILABLE = True
    TOTP_AVAILABLE = True
except ImportError as e:
    JWT_AVAILABLE = False
    BCRYPT_AVAILABLE = False
    TOTP_AVAILABLE = False

    logging.error(f"Authentication dependencies missing: {e}. Please install with: poetry install")

from backend.core.config import AuthenticationSettings

if TYPE_CHECKING:
    from backend.services.auth_repository import AuthRepository


class AuthMode(str, Enum):
    """Authentication modes supported by the system."""

    NONE = "none"  # No authentication required
    SINGLE_USER = "single"  # Single admin user with username/password
    MULTI_USER = "multi"  # Multiple users with magic links and OAuth


class AuthenticationError(Exception):
    """Base exception for authentication errors."""


class InvalidTokenError(AuthenticationError):
    """Raised when a token is invalid or expired."""


class UserNotFoundError(AuthenticationError):
    """Raised when a user cannot be found."""


class AccountLockedError(AuthenticationError):
    """Raised when an account is locked due to too many failed attempts."""

    def __init__(self, message: str, lockout_until: datetime, attempts: int):
        super().__init__(message)
        self.lockout_until = lockout_until
        self.attempts = attempts


class AuthManager:
    """
    Centralized authentication manager for CoachIQ.

    Provides authentication services including JWT token management,
    admin user authentication, magic link generation, and mode detection.

    Now operates as a facade over specialized services for better separation of concerns.
    """

    def __init__(
        self,
        auth_settings: AuthenticationSettings,
        notification_manager: Any | None = None,
        auth_repository: "AuthRepository | None" = None,
        token_service: Any | None = None,
        session_service: Any | None = None,
        mfa_service: Any | None = None,
        lockout_service: Any | None = None,
        credential_repository: Any | None = None,
    ):
        """
        Initialize the authentication manager.

        Args:
            auth_settings: Authentication configuration settings
            notification_manager: NotificationManager instance for magic links
            auth_repository: AuthRepository instance for database persistence (optional)
            token_service: Optional pre-configured token service
            session_service: Optional pre-configured session service
            mfa_service: Optional pre-configured MFA service
            lockout_service: Optional pre-configured lockout service
            credential_repository: Optional pre-configured credential repository
        """
        self.logger = logging.getLogger(__name__)

        # Ensure we have the correct settings type
        # Check if this looks like the full Settings object (has multiple subsections)
        if hasattr(auth_settings, "server") or hasattr(auth_settings, "database"):
            # We were passed the full Settings object, extract AuthenticationSettings
            if hasattr(auth_settings, "auth"):
                self.settings = auth_settings.auth  # type: ignore[attr-defined]
                self.logger.warning(
                    "AuthManager received full Settings object instead of AuthenticationSettings, extracting auth settings"
                )
            else:
                # This shouldn't happen, but handle gracefully
                self.logger.error("AuthManager received Settings object without auth section")
                raise ValueError("Invalid settings object provided to AuthManager")
        else:
            # We have the correct AuthenticationSettings object
            self.settings = auth_settings

        self.notification_manager = notification_manager
        self.auth_repository = auth_repository

        # Initialize services if provided
        self._token_service = token_service
        self._session_service = session_service
        self._mfa_service = mfa_service
        self._lockout_service = lockout_service
        self._credential_repo = credential_repository

        # Determine if we're in service mode or legacy mode
        self._service_mode = bool(
            token_service and session_service and mfa_service and lockout_service
        )

        # Initialize password hashing context
        if JWT_AVAILABLE and BCRYPT_AVAILABLE:
            self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        else:
            self.pwd_context = None
            if not JWT_AVAILABLE:
                self.logger.error("JWT dependencies not available - authentication disabled")
            if not BCRYPT_AVAILABLE:
                self.logger.error("bcrypt not available - password hashing will fail")
            msg = "Authentication dependencies missing. Please install with: poetry install"
            raise RuntimeError(msg)

        # Determine authentication mode
        self.auth_mode = self._detect_auth_mode()
        self.logger.info(f"Authentication mode detected: {self.auth_mode}")

        # Store auto-generated password temporarily for one-time display
        self._generated_password = None

        # Note: Single user admin initialization is now done in startup() method
        # to support async database operations

    def _validate_persistence_available(self) -> None:
        """
        Validate that persistence (auth repository) is available.

        Raises:
            AuthenticationError: If auth repository is not available
        """
        if not self.auth_repository:
            msg = (
                "Authentication persistence is required but not available. "
                "Ensure the database is accessible."
            )
            raise AuthenticationError(msg)

    @property
    def repository(self) -> "AuthRepository":
        """
        Get auth repository with guaranteed non-None type.

        This property should only be used after calling _validate_persistence_available().
        """
        if not self.auth_repository:
            msg = (
                "Authentication persistence is required but not available. "
                "Ensure the database is accessible."
            )
            raise AuthenticationError(msg)
        return self.auth_repository

    async def startup(self) -> None:
        """Initialize the authentication manager on startup."""
        self.logger.info("Authentication manager started")

        if self.auth_mode == AuthMode.NONE:
            self.logger.warning("Authentication is DISABLED - all requests will be allowed")
        elif self.auth_mode == AuthMode.SINGLE_USER:
            self.logger.info("Single-user authentication mode enabled")
            await self._initialize_single_user_admin()
            if self.settings.admin_username and self.settings.admin_password:
                self.logger.info("Admin credentials configured via environment variables")
            else:
                self.logger.warning("Admin credentials auto-generated - check logs for details")
        elif self.auth_mode == AuthMode.MULTI_USER:
            self.logger.info("Multi-user authentication mode enabled")
            if self.settings.admin_email:
                self.logger.info(f"Admin email configured: {self.settings.admin_email}")
            else:
                self.logger.warning("No admin email configured - will need to be set manually")

    async def shutdown(self) -> None:
        """Cleanup authentication manager on shutdown."""
        self.logger.info("Authentication manager stopped")

    def _detect_auth_mode(self) -> AuthMode:
        """
        Detect the authentication mode based on configuration.

        Returns:
            AuthMode: The detected authentication mode
        """
        # Check if authentication is explicitly disabled
        if not self.settings.enabled:
            return AuthMode.NONE

        # Check for multi-user indicators
        if (
            self.settings.enable_oauth
            or self.settings.enable_magic_links
            or self.settings.admin_email
        ):
            return AuthMode.MULTI_USER

        # Check for single-user indicators
        if self.settings.admin_username or self.settings.admin_password:
            return AuthMode.SINGLE_USER

        # Default to no authentication if nothing is configured
        return AuthMode.NONE

    async def _initialize_single_user_admin(self) -> None:
        """Initialize admin credentials for single-user mode."""
        # Validate persistence is available first
        self._validate_persistence_available()

        username = self.settings.admin_username or "admin"
        password = self.settings.admin_password

        # Check if admin credentials already exist in database
        existing_credentials = await self.repository.get_admin_credentials()
        if existing_credentials:
            self.logger.info("Admin credentials already exist in database")
            return

        if not password:
            # Generate a random password
            password = secrets.token_urlsafe(16)
            # Store the generated password temporarily for one-time display via API
            self._generated_password = password
            self.logger.critical(f"Auto-generated admin credentials for username: {username}")
            self.logger.critical(
                "IMPORTANT: Use the /api/auth/admin/credentials endpoint to retrieve the password. "
                "It will only be displayed once for security reasons."
            )

        # Hash the password using bcrypt (dependencies are guaranteed to be available)
        if not self.pwd_context:
            msg = "Password context not available"
            raise RuntimeError(msg)
        password_hash = self.pwd_context.hash(password)
        auto_generated = not bool(self.settings.admin_password)

        # Store in repository (fail-fast if this fails)
        success = await self.repository.set_admin_credentials(
            username=username,
            password_hash=password_hash,
            auto_generated=auto_generated,
        )
        if not success:
            msg = (
                f"Failed to store admin credentials in database for user {username}. "
                "Check database connectivity and permissions."
            )
            raise AuthenticationError(msg)

        self.logger.info("Admin credentials stored in database")

    def generate_token(
        self,
        user_id: str,
        username: str = "",
        expires_delta: timedelta | None = None,
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate a JWT token for a user.

        Args:
            user_id: Unique identifier for the user
            username: Username for the user (optional)
            expires_delta: Token expiration time (defaults to configured value)
            additional_claims: Additional claims to include in the token

        Returns:
            str: The encoded JWT token

        Raises:
            AuthenticationError: If JWT is not available
        """
        if self._service_mode and self._token_service:
            # Service mode - delegate to token service
            try:
                # Add username to additional claims
                claims = additional_claims or {}
                claims["username"] = username
                # Note: TokenService doesn't support custom expiration, uses configured value
                return self._token_service.generate_access_token(
                    user_id,
                    is_admin="admin" in user_id.lower(),  # Simple admin check
                    additional_claims=claims,
                )
            except Exception as e:
                self.logger.error(f"Failed to generate JWT token: {e}")
                msg = "Token generation failed"
                raise AuthenticationError(msg) from e
        else:
            # Legacy mode
            if not JWT_AVAILABLE or not self.settings.secret_key:
                msg = "JWT token generation not available"
                raise AuthenticationError(msg)

            if expires_delta is None:
                expires_delta = timedelta(minutes=self.settings.jwt_expire_minutes)

            expire = datetime.now(UTC) + expires_delta

            to_encode = {
                "sub": str(user_id),
                "username": username,
                "exp": expire,
                "iat": datetime.now(UTC),
                "iss": "coachiq",
                "aud": "coachiq-api",
            }

            if additional_claims:
                to_encode.update(additional_claims)

            try:
                return jwt.encode(
                    to_encode,
                    self.settings.secret_key,
                    algorithm=self.settings.jwt_algorithm,
                )
            except Exception as e:
                self.logger.error(f"Failed to generate JWT token: {e}")
                msg = "Token generation failed"
                raise AuthenticationError(msg) from e

    def validate_token(self, token: str) -> dict[str, Any]:
        """
        Validate and decode a JWT token.

        Args:
            token: The JWT token to validate

        Returns:
            Dict[str, Any]: The decoded token payload

        Raises:
            InvalidTokenError: If the token is invalid or expired
        """
        if self._service_mode and self._token_service:
            # Service mode - delegate to token service
            payload = self._token_service.validate_token(token)
            if payload is None:
                msg = "Invalid or expired token"
                raise InvalidTokenError(msg)
            return payload
        # Legacy mode
        if not JWT_AVAILABLE or not self.settings.secret_key:
            msg = "JWT validation not available"
            raise InvalidTokenError(msg)

        try:
            return jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=[self.settings.jwt_algorithm],
                audience="coachiq-api",
                issuer="coachiq",
            )
        except jwt.ExpiredSignatureError as e:
            msg = "Token has expired"
            raise InvalidTokenError(msg) from e
        except jwt.InvalidTokenError as e:
            msg = f"Invalid token: {e}"
            raise InvalidTokenError(msg) from e

    async def generate_refresh_token(
        self,
        user_id: str,
        username: str = "",
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate a refresh token for a user.

        Args:
            user_id: Unique identifier for the user
            username: Username for the user (optional)
            additional_claims: Additional claims to include in the token

        Returns:
            str: The encoded refresh token

        Raises:
            AuthenticationError: If JWT is not available or refresh tokens disabled
        """
        if not self.settings.enable_refresh_tokens:
            msg = "Refresh tokens are disabled"
            raise AuthenticationError(msg)

        if self._service_mode and self._session_service:
            # Service mode - delegate to session service
            try:
                # Session service handles token generation internally
                access_token, refresh_token = await self._session_service.create_session(
                    user_id, {"username": username, **(additional_claims or {})}
                )
                # Return only the refresh token
                return refresh_token
            except Exception as e:
                self.logger.error(f"Failed to generate refresh token: {e}")
                msg = "Refresh token generation failed"
                raise AuthenticationError(msg) from e
        # Legacy mode
        elif not JWT_AVAILABLE or not self.settings.refresh_token_secret:
            msg = "Refresh token generation not available"
            raise AuthenticationError(msg)

        # Generate unique token ID for tracking
        import secrets

        token_id = secrets.token_urlsafe(16)

        expires_delta = timedelta(days=self.settings.refresh_token_expire_days)
        expire = datetime.now(UTC) + expires_delta

        to_encode = {
            "sub": str(user_id),
            "username": username,
            "exp": expire,
            "iat": datetime.now(UTC),
            "iss": "coachiq",
            "aud": "coachiq-refresh",
            "jti": token_id,  # JWT ID for tracking
            "token_type": "refresh",
        }

        if additional_claims:
            to_encode.update(additional_claims)

        try:
            encoded_jwt = jwt.encode(
                to_encode,
                self.settings.refresh_token_secret,
                algorithm=self.settings.jwt_algorithm,
            )

            # Store refresh token in repository (fail-fast if this fails)
            self._validate_persistence_available()
            session_created = await self.repository.create_user_session(
                user_id=str(user_id),
                session_token=token_id,  # Use token_id as session identifier
                expires_at=expire,
            )
            if not session_created:
                msg = (
                    f"Failed to store refresh token in database for user {user_id}. "
                    "Check database connectivity and permissions."
                )
                raise AuthenticationError(msg)

            return encoded_jwt
        except Exception as e:
            self.logger.error(f"Failed to generate refresh token: {e}")
            msg = "Refresh token generation failed"
            raise AuthenticationError(msg) from e

    async def validate_refresh_token(self, token: str) -> dict[str, Any]:
        """
        Validate and decode a refresh token.

        Args:
            token: The refresh token to validate

        Returns:
            dict[str, Any]: The decoded token payload

        Raises:
            InvalidTokenError: If the token is invalid, expired, or revoked
        """
        if not self.settings.enable_refresh_tokens:
            msg = "Refresh tokens are disabled"
            raise InvalidTokenError(msg)

        if not JWT_AVAILABLE or not self.settings.refresh_token_secret:
            msg = "Refresh token validation not available"
            raise InvalidTokenError(msg)

        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        try:
            payload = jwt.decode(
                token,
                self.settings.refresh_token_secret,
                algorithms=[self.settings.jwt_algorithm],
                audience="coachiq-refresh",
                issuer="coachiq",
            )

            # Check if token is revoked in repository (fail-fast if this fails)
            token_id = payload.get("jti")
            if token_id:
                session = await self.repository.get_user_session(token_id)
                if session and not session.is_active:
                    msg = "Refresh token has been revoked"
                    raise InvalidTokenError(msg)

            return payload
        except jwt.ExpiredSignatureError as e:
            # Clean up expired token from storage
            token_id = jwt.decode(token, options={"verify_signature": False}).get("jti")
            if token_id:
                await self.repository.revoke_user_session(token_id)
            msg = "Refresh token has expired"
            raise InvalidTokenError(msg) from e
        except jwt.InvalidTokenError as e:
            msg = f"Invalid refresh token: {e}"
            raise InvalidTokenError(msg) from e

    async def revoke_refresh_token(self, token: str) -> bool:
        """
        Revoke a refresh token.

        Args:
            token: The refresh token to revoke

        Returns:
            bool: True if token was revoked, False if not found
        """
        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        try:
            # Use same verification as validate_refresh_token to ensure consistency
            payload = jwt.decode(
                token,
                self.settings.refresh_token_secret,
                algorithms=[self.settings.jwt_algorithm],
                audience="coachiq-refresh",
                issuer="coachiq",
            )
            token_id = payload.get("jti")

            if token_id:
                # Revoke in repository (fail-fast if this fails)
                revoked = await self.repository.revoke_user_session(token_id)

                if revoked:
                    self.logger.info(f"Refresh token revoked: {token_id}")

                return revoked

            return False
        except Exception as e:
            self.logger.warning(f"Failed to revoke refresh token: {e}")
            return False

    async def revoke_all_user_refresh_tokens(self, user_id: str) -> int:
        """
        Revoke all refresh tokens for a specific user.

        Args:
            user_id: User ID whose tokens should be revoked

        Returns:
            int: Number of tokens revoked
        """
        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        # Revoke from repository (fail-fast if this fails)
        revoked_count = await self.repository.revoke_all_user_sessions(str(user_id))

        if revoked_count > 0:
            self.logger.info(f"Revoked {revoked_count} refresh tokens for user {user_id}")

        return revoked_count

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, str]:
        """
        Generate a new access token using a valid refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            tuple[str, str]: New access token and new refresh token

        Raises:
            InvalidTokenError: If refresh token is invalid
            AuthenticationError: If token generation fails
        """
        if self._service_mode and self._session_service:
            # Service mode - delegate to session service
            new_access_token = await self._session_service.refresh_access_token(refresh_token)
            if not new_access_token:
                msg = "Failed to refresh access token"
                raise InvalidTokenError(msg)
            # In service mode, we don't rotate refresh tokens by default
            return new_access_token, refresh_token
        # Legacy mode
        # Validate the refresh token
        payload = await self.validate_refresh_token(refresh_token)

        user_id = payload.get("sub")
        username = payload.get("username", "")

        if not user_id:
            msg = "Invalid refresh token payload"
            raise InvalidTokenError(msg)

        # Generate new access token
        access_token = self.generate_token(
            user_id=user_id,
            username=username,
            additional_claims={
                "email": payload.get("email"),
                "role": payload.get("role", "user"),
                "mode": payload.get("mode", self.auth_mode.value),
            },
        )

        # Generate new refresh token (token rotation for security)
        new_refresh_token = await self.generate_refresh_token(
            user_id=user_id,
            username=username,
            additional_claims={
                "email": payload.get("email"),
                "role": payload.get("role", "user"),
                "mode": payload.get("mode", self.auth_mode.value),
            },
        )

        # Revoke the old refresh token
        await self.revoke_refresh_token(refresh_token)

        return access_token, new_refresh_token

    async def cleanup_expired_refresh_tokens(self) -> int:
        """
        Clean up expired refresh tokens from storage.

        Returns:
            int: Number of tokens cleaned up
        """
        # Validate persistence is available first
        self._validate_persistence_available()

        # Clean up from repository (fail-fast if this fails)
        cleaned_count = await self.repository.cleanup_expired_sessions()

        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} expired refresh tokens")

        return cleaned_count

    async def authenticate_admin_with_refresh(
        self, username: str, password: str
    ) -> tuple[str, str] | None:
        """
        Authenticate admin user and return both access and refresh tokens.

        Args:
            username: Admin username
            password: Admin password

        Returns:
            Optional[tuple[str, str]]: (access_token, refresh_token) if successful, None otherwise

        Raises:
            AccountLockedError: If the account is locked due to failed attempts
        """
        if self.auth_mode != AuthMode.SINGLE_USER:
            self.logger.warning(f"Admin authentication called in {self.auth_mode} mode")
            return None

        # Validate persistence is available first
        self._validate_persistence_available()

        # Get admin credentials from repository (fail-fast if this fails)
        admin_credentials = await self.repository.get_admin_credentials()

        if not admin_credentials:
            self.logger.error("No admin credentials configured")
            return None

        # Check if account is locked
        is_locked, lockout_until = await self.is_account_locked(username)
        if is_locked:
            # Get failed attempts count from auth events
            window_start = datetime.now(UTC) - timedelta(
                hours=self.settings.max_lockout_duration_hours
            )
            failed_count = await self.repository.get_failed_attempts_count(
                email=username.lower(), since=window_start
            )

            msg = (
                f"Account locked until {lockout_until.isoformat() if lockout_until else 'unknown'}"
            )
            raise AccountLockedError(
                msg,
                lockout_until,
                failed_count,
            )

        # Verify username
        if username != admin_credentials["username"]:
            self.logger.warning(f"Invalid admin username: {username}")
            await self.record_failed_attempt(username)
            return None

        # Verify password using bcrypt
        if not self.pwd_context or not self.pwd_context.verify(
            password, admin_credentials["password_hash"]
        ):
            self.logger.warning("Invalid admin password")
            await self.record_failed_attempt(username)
            return None

        # Generate both tokens
        try:
            additional_claims = {"role": "admin", "mode": "single-user"}

            access_token = self.generate_token(
                user_id="admin",
                username=username,
                additional_claims=additional_claims,
            )

            refresh_token = ""
            if self.settings.enable_refresh_tokens:
                refresh_token = await self.generate_refresh_token(
                    user_id="admin",
                    username=username,
                    additional_claims=additional_claims,
                )

            # Record successful login for lockout tracking
            await self.record_successful_login(username)

            self.logger.info(f"Admin user authenticated with refresh: {username}")
            return access_token, refresh_token
        except AuthenticationError as e:
            self.logger.error(f"Failed to generate admin tokens: {e}")
            return None

    async def authenticate_admin(self, username: str, password: str) -> str | None:
        """
        Authenticate admin user in single-user mode.

        Args:
            username: Admin username
            password: Admin password

        Returns:
            Optional[str]: JWT token if authentication successful, None otherwise

        Raises:
            AccountLockedError: If the account is locked due to failed attempts
        """
        if self.auth_mode != AuthMode.SINGLE_USER:
            self.logger.warning(f"Admin authentication called in {self.auth_mode} mode")
            return None

        if self._service_mode and self._credential_repo and self._lockout_service:
            # Service mode - use repositories and services
            # Check if account is locked
            is_locked, lockout_until = await self._lockout_service.check_lockout(username)
            if is_locked:
                # Get lockout info for error details
                lockout_info = await self._lockout_service.get_lockout_info(username)
                msg = f"Account locked until {lockout_until.isoformat() if lockout_until else 'unknown'}"
                raise AccountLockedError(
                    msg,
                    lockout_until,
                    lockout_info.get("failed_attempts", 0),
                )

            # Get admin credentials
            admin_creds = await self._credential_repo.get_admin_credentials()
            if not admin_creds:
                self.logger.error("No admin credentials configured")
                return None

            # Verify credentials
            if username != admin_creds["username"]:
                self.logger.warning(f"Invalid admin username: {username}")
                await self._lockout_service.record_failed_attempt(username)
                return None

            # Verify password
            is_valid = await self._credential_repo.verify_password(
                admin_creds["username"], password
            )
            if not is_valid:
                self.logger.warning("Invalid admin password")
                await self._lockout_service.record_failed_attempt(username)
                return None

            # Generate token
            additional_claims = {"role": "admin", "mode": "single-user"}
            access_token = self.generate_token(
                user_id="admin",
                username=username,
                additional_claims=additional_claims,
            )

            # Record successful login
            await self._lockout_service.record_successful_login(username)
            self.logger.info(f"Admin user authenticated: {username}")
            return access_token
        # Legacy mode
        # Validate persistence is available first
        self._validate_persistence_available()

        # Get admin credentials from repository (fail-fast if this fails)
        admin_credentials = await self.repository.get_admin_credentials()

        if not admin_credentials:
            self.logger.error("No admin credentials configured")
            return None

        # Check if account is locked
        is_locked, lockout_until = await self.is_account_locked(username)
        if is_locked:
            # Get failed attempts count from auth events
            window_start = datetime.now(UTC) - timedelta(
                hours=self.settings.max_lockout_duration_hours
            )
            failed_count = await self.repository.get_failed_attempts_count(
                email=username.lower(), since=window_start
            )

            msg = (
                f"Account locked until {lockout_until.isoformat() if lockout_until else 'unknown'}"
            )
            raise AccountLockedError(
                msg,
                lockout_until,
                failed_count,
            )

        # Verify username
        if username != admin_credentials["username"]:
            self.logger.warning(f"Invalid admin username: {username}")
            await self.record_failed_attempt(username)
            return None

        # Verify password using bcrypt
        if not self.pwd_context or not self.pwd_context.verify(
            password, admin_credentials["password_hash"]
        ):
            self.logger.warning("Invalid admin password")
            await self.record_failed_attempt(username)
            return None

        # Generate token
        try:
            token = self.generate_token(
                user_id="admin",
                username=username,
                additional_claims={"role": "admin", "mode": "single-user"},
            )

            # Record successful login for lockout tracking
            await self.record_successful_login(username)

            self.logger.info(f"Admin user authenticated: {username}")
            return token
        except AuthenticationError as e:
            self.logger.error(f"Failed to generate admin token: {e}")
            return None

    async def generate_magic_link(
        self, email: str, expires_minutes: int = 15, redirect_url: str | None = None
    ) -> str | None:
        """
        Generate a magic link for passwordless authentication.

        Args:
            email: Email address for the magic link
            expires_minutes: Link expiration time in minutes
            redirect_url: URL to redirect to after authentication

        Returns:
            Optional[str]: The magic link URL if successful
        """
        if self.auth_mode == AuthMode.NONE:
            self.logger.warning("Magic link requested but authentication is disabled")
            return None

        try:
            # Generate a secure token
            expires_delta = timedelta(minutes=expires_minutes)
            token = self.generate_token(
                user_id=email,
                username=email,
                expires_delta=expires_delta,
                additional_claims={
                    "type": "magic_link",
                    "email": email,
                    "redirect_url": redirect_url,
                },
            )

            # Construct the magic link URL
            base_url = self.settings.base_url or "http://localhost:8000"
            magic_link = f"{base_url}/api/auth/magic?token={token}"

            self.logger.info(f"Generated magic link for {email}")
            return magic_link

        except AuthenticationError as e:
            self.logger.error(f"Failed to generate magic link for {email}: {e}")
            return None

    async def send_magic_link_email(
        self, email: str, expires_minutes: int = 15, redirect_url: str | None = None
    ) -> bool:
        """
        Send a magic link via email using the notification manager.

        Args:
            email: Email address to send the magic link to
            expires_minutes: Link expiration time in minutes
            redirect_url: URL to redirect to after authentication

        Returns:
            bool: True if email was sent successfully
        """
        if not self.notification_manager:
            self.logger.error("No notification manager available for magic link emails")
            return False

        magic_link = await self.generate_magic_link(email, expires_minutes, redirect_url)
        if not magic_link:
            return False

        try:
            success = await self.notification_manager.send_magic_link_email(
                to_email=email, magic_link=magic_link, expires_minutes=expires_minutes
            )

            if success:
                self.logger.info(f"Magic link email sent to {email}")
            else:
                self.logger.error(f"Failed to send magic link email to {email}")

            return success

        except Exception as e:
            self.logger.error(f"Error sending magic link email to {email}: {e}")
            return False

    async def validate_magic_link(self, token: str) -> dict[str, Any] | None:
        """
        Validate a magic link token.

        Args:
            token: The magic link token to validate

        Returns:
            Optional[Dict[str, Any]]: User info if valid, None otherwise
        """
        try:
            payload = self.validate_token(token)

            # Verify this is a magic link token
            if payload.get("type") != "magic_link":
                self.logger.warning("Token is not a magic link token")
                return None

            email = payload.get("email")
            if not email:
                self.logger.warning("Magic link token missing email")
                return None

            self.logger.info(f"Valid magic link token for {email}")
            return {
                "email": email,
                "user_id": payload.get("sub"),
                "redirect_url": payload.get("redirect_url"),
            }

        except InvalidTokenError as e:
            self.logger.warning(f"Invalid magic link token: {e}")
            return None

    def is_authenticated_request(self, token: str | None) -> bool:
        """
        Check if a request is authenticated based on the current mode.

        Args:
            token: Authorization token from the request

        Returns:
            bool: True if the request should be allowed
        """
        if self.auth_mode == AuthMode.NONE:
            # No authentication required
            return True

        if not token:
            return False

        try:
            self.validate_token(token)
            return True
        except InvalidTokenError:
            return False

    async def get_generated_credentials(self) -> dict[str, str] | None:
        """
        Get auto-generated admin credentials (one-time display only).

        This method returns the credentials only once for security reasons.
        After calling this method, the credentials are cleared from memory.

        Returns:
            Optional[Dict[str, str]]: Admin credentials if available, None otherwise
        """
        if self.auth_mode != AuthMode.SINGLE_USER or not self._generated_password:
            return None

        # Get admin credentials from repository (fail-fast if not available)
        self._validate_persistence_available()
        admin_credentials = await self.repository.get_admin_credentials()

        if not admin_credentials:
            return None

        # Return credentials once
        credentials = {
            "username": admin_credentials["username"],
            "password": self._generated_password,
            "created_at": admin_credentials["created_at"].isoformat(),
            "warning": "Save these credentials immediately! They will not be displayed again.",
        }

        # Clear the generated password from memory for security
        self._generated_password = None

        self.logger.info("Auto-generated admin credentials retrieved via API")
        return credentials

    async def has_generated_credentials(self) -> bool:
        """
        Check if there are auto-generated credentials available for retrieval.

        Returns:
            bool: True if credentials are available for one-time display
        """
        if self.auth_mode != AuthMode.SINGLE_USER or not self._generated_password:
            return False

        # Check if password was auto-generated from repository (fail-fast if not available)
        self._validate_persistence_available()
        admin_credentials = await self.repository.get_admin_credentials()
        if admin_credentials:
            return admin_credentials.get("password_auto_generated", False)

        return False

    async def get_stats(self) -> dict[str, Any]:
        """
        Get authentication manager statistics.

        Returns:
            Dict[str, Any]: Statistics about the authentication system
        """
        # Get admin credentials for stats
        admin_credentials = None
        if self.auth_mode == AuthMode.SINGLE_USER:
            # Use repository (fail-fast if not available)
            self._validate_persistence_available()
            admin_credentials = await self.repository.get_admin_credentials()

        stats = {
            "auth_mode": self.auth_mode.value,
            "jwt_available": JWT_AVAILABLE,
            "bcrypt_available": BCRYPT_AVAILABLE,
            "secret_key_configured": bool(self.settings.secret_key),
            "notification_manager_available": self.notification_manager is not None,
            "admin_configured": (
                bool(admin_credentials) if self.auth_mode == AuthMode.SINGLE_USER else None
            ),
            "has_generated_credentials": await self.has_generated_credentials(),
        }

        if self.auth_mode == AuthMode.SINGLE_USER and admin_credentials:
            stats["admin_username"] = admin_credentials.get("username")
            stats["admin_created_at"] = admin_credentials.get("created_at")
            stats["password_auto_generated"] = admin_credentials.get(
                "password_auto_generated", False
            )

        return stats

    # Multi-Factor Authentication (MFA) methods

    def is_mfa_available(self) -> bool:
        """Check if MFA dependencies are available."""
        return TOTP_AVAILABLE and getattr(self.settings, "enable_mfa", False)

    async def generate_mfa_secret(self, user_id: str) -> dict[str, Any]:
        """
        Generate a new TOTP secret for a user.

        Args:
            user_id: User ID to generate secret for

        Returns:
            dict[str, Any]: Secret and QR code information

        Raises:
            AuthenticationError: If MFA is not available
        """
        if not self.is_mfa_available():
            msg = "MFA not available - missing dependencies or disabled"
            raise AuthenticationError(msg)

        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Get MFA settings from feature flags
        issuer = getattr(self.settings, "mfa_totp_issuer", "CoachIQ")
        digits = getattr(self.settings, "mfa_totp_digits", 6)

        # Create TOTP instance
        totp = pyotp.TOTP(secret, digits=digits)

        # Generate provisioning URI for QR code
        provisioning_uri = totp.provisioning_uri(name=user_id, issuer_name=issuer)

        # Generate QR code image
        qr_code_data = self._generate_qr_code(provisioning_uri)

        # Generate backup codes
        backup_codes = self._generate_backup_codes()

        # Store secret (but don't enable MFA yet) - use repository (fail-fast if this fails)
        self._validate_persistence_available()
        user_mfa = await self.repository.create_user_mfa(
            user_id=user_id,
            totp_secret=secret,
            backup_codes=backup_codes,
            recovery_codes=[],
        )
        if not user_mfa:
            msg = (
                f"Failed to store MFA secret in database for user {user_id}. "
                "Check database connectivity and permissions."
            )
            raise AuthenticationError(msg)

        self.logger.info(f"Generated MFA secret for user {user_id}")

        return {
            "secret": secret,
            "qr_code": qr_code_data,
            "provisioning_uri": provisioning_uri,
            "backup_codes": backup_codes,
            "issuer": issuer,
        }

    def _generate_qr_code(self, provisioning_uri: str) -> str:
        """Generate base64-encoded QR code image."""
        import base64
        import io

        import qrcode

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        img_buffer = io.BytesIO()
        img.save(img_buffer, "PNG")
        img_str = base64.b64encode(img_buffer.getvalue()).decode()

        return f"data:image/png;base64,{img_str}"

    def _generate_backup_codes(self) -> list[str]:
        """Generate backup codes for MFA recovery."""
        backup_codes_count = getattr(self.settings, "mfa_backup_codes_count", 10)
        backup_code_length = getattr(self.settings, "mfa_backup_code_length", 8)

        backup_codes = []
        for _ in range(backup_codes_count):
            # Generate alphanumeric backup codes
            code = secrets.token_hex(backup_code_length // 2).upper()
            backup_codes.append(code)

        return backup_codes

    async def verify_mfa_setup(self, user_id: str, totp_code: str) -> bool:
        """
        Verify TOTP code during MFA setup and enable MFA.

        Args:
            user_id: User ID
            totp_code: TOTP code from authenticator app

        Returns:
            bool: True if verification successful and MFA enabled

        Raises:
            AuthenticationError: If MFA not available or user not found
        """
        if not self.is_mfa_available():
            msg = "MFA not available"
            raise AuthenticationError(msg)

        # Get MFA secret from repository (fail-fast if this fails)
        self._validate_persistence_available()
        user_mfa = await self.repository.get_user_mfa(user_id)
        if not user_mfa:
            msg = "MFA setup not initiated for user"
            raise AuthenticationError(msg)
        secret = user_mfa.totp_secret

        # Verify TOTP code
        if self._verify_totp_code(secret, totp_code):
            # Enable MFA for the user (fail-fast if this fails)
            now = datetime.now(UTC)
            success = await self.repository.update_user_mfa(
                user_id=user_id, is_enabled=True, totp_enabled=True, last_used_at=now
            )
            if not success:
                msg = (
                    f"Failed to enable MFA in database for user {user_id}. "
                    "Check database connectivity and permissions."
                )
                raise AuthenticationError(msg)

            self.logger.info(f"MFA enabled for user {user_id}")
            return True

        return False

    async def verify_mfa_code(self, user_id: str, code: str) -> bool:
        """
        Verify MFA code (TOTP or backup code).

        Args:
            user_id: User ID
            code: TOTP code or backup code

        Returns:
            bool: True if code is valid

        Raises:
            AuthenticationError: If MFA not available or not enabled for user
        """
        if not self.is_mfa_available():
            msg = "MFA not available"
            raise AuthenticationError(msg)

        # Get MFA data from repository (fail-fast if this fails)
        self._validate_persistence_available()
        user_mfa = await self.repository.get_user_mfa(user_id)
        if not user_mfa:
            msg = "MFA not set up for user"
            raise AuthenticationError(msg)

        secret = user_mfa.totp_secret
        enabled = user_mfa.is_enabled

        if not enabled:
            msg = "MFA not enabled for user"
            raise AuthenticationError(msg)

        now = datetime.now(UTC)

        # Try TOTP first
        if self._verify_totp_code(secret, code):
            # Update last used timestamp
            await self.repository.update_user_mfa(user_id=user_id, last_used_at=now)
            return True

        # Try backup codes
        if await self._verify_backup_code(user_id, code):
            # Update last used timestamp
            await self.repository.update_user_mfa(user_id=user_id, last_used_at=now)
            return True

        return False

    def _verify_totp_code(self, secret: str, code: str) -> bool:
        """Verify TOTP code against secret."""
        digits = getattr(self.settings, "mfa_totp_digits", 6)
        window = getattr(self.settings, "mfa_totp_window", 1)

        totp = pyotp.TOTP(secret, digits=digits)
        return totp.verify(code, valid_window=window)

    async def _verify_backup_code(self, user_id: str, code: str) -> bool:
        """Verify backup code and mark as used."""
        # Use repository (fail-fast if this fails)
        # Check if backup code is valid and unused in database
        is_valid = await self.repository.verify_backup_code(user_id, code)
        if is_valid:
            # Mark as used in database
            used = await self.repository.use_backup_code(user_id, code)
            if used:
                self.logger.info(f"Backup code used for user {user_id}")

                # Check if we need to regenerate backup codes
                unused_count = await self.repository.count_unused_backup_codes(user_id)
                regeneration_threshold = getattr(
                    self.settings, "mfa_backup_code_regeneration_threshold", 3
                )

                if unused_count <= regeneration_threshold:
                    await self._regenerate_backup_codes(user_id)

                return True
            self.logger.warning(f"Failed to mark backup code as used for user {user_id}")
        return False

    async def _regenerate_backup_codes(self, user_id: str) -> list[str]:
        """Regenerate backup codes for a user."""
        new_backup_codes = self._generate_backup_codes()

        # Use repository (fail-fast if this fails)
        success = await self.repository.regenerate_backup_codes(user_id, new_backup_codes)
        if not success:
            msg = (
                f"Failed to regenerate backup codes in database for user {user_id}. "
                "Check database connectivity and permissions."
            )
            raise AuthenticationError(msg)

        self.logger.info(f"Regenerated backup codes for user {user_id}")
        return new_backup_codes

    async def disable_mfa(self, user_id: str, admin_user: str = "system") -> bool:
        """
        Disable MFA for a user (admin function).

        Args:
            user_id: User ID to disable MFA for
            admin_user: Admin performing the action

        Returns:
            bool: True if MFA was disabled, False if not enabled
        """
        was_enabled = False

        # Use repository (fail-fast if this fails)
        self._validate_persistence_available()

        # Check if user has MFA enabled
        user_mfa = await self.repository.get_user_mfa(user_id)
        if not user_mfa:
            return False

        was_enabled = user_mfa.is_enabled
        # Delete MFA data from database
        success = await self.repository.delete_user_mfa(user_id)
        if not success:
            msg = (
                f"Failed to delete MFA in database for user {user_id}. "
                "Check database connectivity and permissions."
            )
            raise AuthenticationError(msg)

        if was_enabled:
            self.logger.info(f"MFA disabled for user {user_id} by admin {admin_user}")
            return True

        return False

    async def get_mfa_status(self, user_id: str) -> dict[str, Any]:
        """
        Get MFA status for a user.

        Args:
            user_id: User ID to check

        Returns:
            dict[str, Any]: MFA status information
        """
        # Use repository (fail-fast if this fails)
        self._validate_persistence_available()

        user_mfa = await self.repository.get_user_mfa(user_id)
        if not user_mfa:
            return {
                "user_id": user_id,
                "mfa_enabled": False,
                "setup_initiated": False,
                "available": self.is_mfa_available(),
            }

        # Get backup code counts from database
        unused_backup_codes = await self.repository.count_unused_backup_codes(user_id)
        backup_codes_list = await self.repository.get_user_backup_codes(user_id)
        total_backup_codes = len(backup_codes_list)

        return {
            "user_id": user_id,
            "mfa_enabled": user_mfa.is_enabled,
            "setup_initiated": True,
            "created_at": user_mfa.created_at.isoformat() if user_mfa.created_at else None,
            "last_used": user_mfa.last_used_at.isoformat() if user_mfa.last_used_at else None,
            "backup_codes_remaining": unused_backup_codes,
            "backup_codes_total": total_backup_codes,
            "available": self.is_mfa_available(),
        }

    async def get_backup_codes(self, user_id: str) -> list[str] | None:
        """
        Get backup codes for a user (one-time display).

        Args:
            user_id: User ID

        Returns:
            list[str] | None: Backup codes if available
        """
        # Use repository (fail-fast if this fails)
        self._validate_persistence_available()

        user_mfa = await self.repository.get_user_mfa(user_id)
        if not user_mfa:
            return None

        # Note: This returns the original backup codes, not the hashed versions
        # This is only called for one-time display during setup
        # The actual backup codes are stored hashed in the database
        # This method should only be used immediately after generation
        backup_codes_list = await self.repository.get_user_backup_codes(user_id)
        if backup_codes_list:
            msg = "get_backup_codes called but codes are hashed in database - returning empty list"
            self.logger.warning(msg)
            return []  # Cannot return hashed codes
        return None

    async def regenerate_backup_codes(self, user_id: str) -> list[str] | None:
        """
        Regenerate backup codes for a user.

        Args:
            user_id: User ID

        Returns:
            list[str] | None: New backup codes if successful
        """
        # Use repository (fail-fast if this fails)
        self._validate_persistence_available()

        user_mfa = await self.repository.get_user_mfa(user_id)
        if not user_mfa:
            return None

        return await self._regenerate_backup_codes(user_id)

    async def get_all_mfa_status(self) -> list[dict[str, Any]]:
        """
        Get MFA status for all users.

        Returns:
            list[dict[str, Any]]: List of MFA status for all users
        """
        all_users = set()

        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        # Get all users with MFA from repository
        all_user_mfa = await self.repository.get_all_user_mfa()
        for user_mfa in all_user_mfa:
            all_users.add(user_mfa.user_id)

        # Also include admin user if in single-user mode and admin exists
        if self.auth_mode == AuthMode.SINGLE_USER:
            admin_credentials = await self.repository.get_admin_credentials()
            if admin_credentials:
                all_users.add("admin")

        # Get MFA status for each user (now async)
        results = []
        for user_id in sorted(all_users):
            status = await self.get_mfa_status(user_id)
            results.append(status)

        return results

    # Account lockout management methods

    async def is_account_locked(self, username: str) -> tuple[bool, datetime | None]:
        """
        Check if an account is currently locked.

        Args:
            username: Username to check

        Returns:
            tuple[bool, datetime | None]: (is_locked, lockout_expires)
        """
        if not self.settings.enable_account_lockout:
            return False, None

        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        # Calculate time window for recent failed attempts
        window_start = datetime.now(UTC) - timedelta(hours=self.settings.max_lockout_duration_hours)

        # Get recent failed login attempts from repository
        failed_events = await self.repository.get_auth_events_for_user(
            email=username.lower(), event_type="login", since=window_start
        )

        # Filter for failed attempts only
        failed_attempts = [event for event in failed_events if not event.success]

        if len(failed_attempts) >= self.settings.max_failed_attempts:
            # Get the latest failed attempt to calculate lockout
            latest_attempt = max(failed_attempts, key=lambda x: x.created_at)

            # Calculate lockout duration with exponential backoff
            # Count consecutive failed attempts for escalation
            consecutive_failures = 0
            for event in sorted(failed_attempts, key=lambda x: x.created_at, reverse=True):
                if not event.success:
                    consecutive_failures += 1
                else:
                    break

            escalation_level = max(
                0, (consecutive_failures // self.settings.max_failed_attempts) - 1
            )
            base_duration = self.settings.lockout_duration_minutes
            escalated_duration = base_duration * (
                self.settings.lockout_escalation_factor**escalation_level
            )

            # Cap at maximum duration
            max_duration = self.settings.max_lockout_duration_hours * 60
            lockout_minutes = min(escalated_duration, max_duration)

            lockout_until = latest_attempt.created_at + timedelta(minutes=lockout_minutes)

            now = datetime.now(UTC)
            if now < lockout_until:
                return True, lockout_until
            return False, None

        return False, None

    async def record_failed_attempt(self, username: str) -> None:
        """
        Record a failed login attempt and apply lockout if necessary.

        Args:
            username: Username that failed authentication
        """
        if not self.settings.enable_account_lockout:
            return

        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        # Create AuthEvent for failed login attempt
        await self.repository.create_auth_event(
            user_id=None,  # No user_id for failed attempts
            event_type="login",
            success=False,
            email=username.lower(),
            details={"lockout_check": True},
        )

        # Check current lockout status to log appropriately
        is_locked, lockout_until = await self.is_account_locked(username)
        if is_locked:
            lockout_time = lockout_until.isoformat() if lockout_until else "unknown"
            self.logger.error(f"Account locked for user {username} until {lockout_time}")
        else:
            # Count recent failed attempts for logging
            window_start = datetime.now(UTC) - timedelta(
                hours=self.settings.max_lockout_duration_hours
            )
            failed_events = await self.repository.get_auth_events_for_user(
                email=username.lower(), event_type="login", since=window_start
            )
            failed_count = len([event for event in failed_events if not event.success])
            self.logger.warning(f"Failed login attempt {failed_count} for user: {username}")

    async def record_successful_login(self, username: str) -> None:
        """
        Record a successful login and potentially reset lockout escalation.

        Args:
            username: Username that successfully authenticated
        """
        if not self.settings.enable_account_lockout:
            return

        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        # Create AuthEvent for successful login
        await self.repository.create_auth_event(
            user_id="admin" if username == "admin" else None,  # Set user_id for admin
            event_type="login",
            success=True,
            email=username.lower(),
            details={"lockout_reset": True},
        )

        self.logger.info(f"Successful login recorded for user {username}")

    async def get_lockout_status(self, username: str) -> dict[str, Any]:
        """
        Get detailed lockout status for a user.

        Args:
            username: Username to check

        Returns:
            dict[str, Any]: Lockout status information
        """
        is_locked, lockout_until = await self.is_account_locked(username)

        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        # Get recent auth events to calculate stats
        window_start = datetime.now(UTC) - timedelta(hours=self.settings.max_lockout_duration_hours)
        auth_events = await self.repository.get_auth_events_for_user(
            email=username.lower(), event_type="login", since=window_start
        )

        failed_attempts = [event for event in auth_events if not event.success]

        failed_count = len(failed_attempts)
        last_attempt = (
            max(auth_events, key=lambda x: x.created_at).created_at if auth_events else None
        )

        # Count consecutive successful logins since last failure
        consecutive_successes = 0
        for event in sorted(auth_events, key=lambda x: x.created_at, reverse=True):
            if event.success:
                consecutive_successes += 1
            else:
                break

        # Calculate escalation level based on failed attempts
        escalation_level = max(0, (failed_count // self.settings.max_failed_attempts))

        return {
            "username": username,
            "is_locked": is_locked,
            "lockout_until": lockout_until.isoformat() if lockout_until else None,
            "failed_attempts": failed_count,
            "escalation_level": escalation_level,
            "last_attempt": last_attempt.isoformat() if last_attempt else None,
            "consecutive_successful_logins": consecutive_successes,
            "lockout_enabled": self.settings.enable_account_lockout,
            "max_failed_attempts": self.settings.max_failed_attempts,
            "lockout_duration_minutes": self.settings.lockout_duration_minutes,
        }

    async def unlock_account(self, username: str, admin_user: str = "system") -> bool:
        """
        Manually unlock an account (admin function).

        Args:
            username: Username to unlock
            admin_user: Admin performing the unlock

        Returns:
            bool: True if account was unlocked, False if not locked
        """
        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        # Check if account is currently locked
        is_locked, lockout_until = await self.is_account_locked(username)

        if not is_locked:
            return False

        # Clear lockout by creating a successful login event that resets the lockout state
        # This approach uses the existing AuthEvent system to manage lockout state
        await self.repository.create_auth_event(
            user_id="admin" if username == "admin" else None,
            event_type="admin_unlock",
            success=True,
            email=username.lower(),
            details={"unlocked_by": admin_user, "manual_unlock": True},
        )

        self.logger.info(f"Account unlocked for user {username} by admin {admin_user}")
        return True

    async def get_all_lockout_status(self) -> list[dict[str, Any]]:
        """
        Get lockout status for all tracked users.

        Returns:
            list[dict[str, Any]]: List of lockout status for all users
        """
        # Use repository (fail-fast if not available)
        self._validate_persistence_available()

        all_users = set()

        # Get all users with auth events from the repository
        window_start = datetime.now(UTC) - timedelta(hours=self.settings.max_lockout_duration_hours)
        all_auth_events = await self.repository.get_auth_events_for_user(
            event_type="login", since=window_start
        )

        # Collect unique usernames from auth events
        for event in all_auth_events:
            if event.email:
                all_users.add(event.email)

        # Also include admin user if in single-user mode
        if self.auth_mode == AuthMode.SINGLE_USER:
            admin_credentials = await self.repository.get_admin_credentials()
            if admin_credentials:
                all_users.add(admin_credentials["username"])

        # Get status for each user async
        results = []
        for username in sorted(all_users):
            status = await self.get_lockout_status(username)
            results.append(status)

        return results
