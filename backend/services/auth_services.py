"""Authentication Services

Core services for authentication management including:
- Token generation and validation
- Session management
- MFA operations
- Account lockout protection
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pyotp
from passlib.hash import bcrypt

from backend.core.performance import PerformanceMonitor
from backend.repositories.auth_repository import (
    AuthEventRepository,
    MfaRepository,
    SessionRepository,
)

logger = logging.getLogger(__name__)


class TokenService:
    """Service for JWT token operations (stateless)."""

    def __init__(
        self,
        jwt_secret: str,
        jwt_algorithm: str,
        access_token_expire_minutes: int,
        magic_link_expire_minutes: int,
    ):
        """Initialize the token service.

        Args:
            jwt_secret: Secret key for JWT signing
            jwt_algorithm: JWT algorithm to use
            access_token_expire_minutes: Access token expiration time
            magic_link_expire_minutes: Magic link token expiration time
        """
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        self._magic_link_expire_minutes = magic_link_expire_minutes

        logger.info("TokenService initialized")

    def generate_access_token(
        self,
        user_id: str,
        is_admin: bool = False,
        additional_claims: dict[str, Any] | None = None,
    ) -> str:
        """Generate a JWT access token.

        Args:
            user_id: User identifier
            is_admin: Whether user is admin
            additional_claims: Additional JWT claims

        Returns:
            JWT access token
        """
        expire = datetime.now(UTC) + timedelta(minutes=self._access_token_expire_minutes)

        claims = {
            "sub": user_id,
            "exp": expire,
            "iat": datetime.now(UTC),
            "type": "access",
            "admin": is_admin,
        }

        if additional_claims:
            claims.update(additional_claims)

        token = jwt.encode(claims, self._jwt_secret, algorithm=self._jwt_algorithm)

        logger.debug(f"Generated access token for user {user_id}")
        return token

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate and decode a JWT token.

        Args:
            token: JWT token to validate

        Returns:
            Decoded token claims or None if invalid
        """
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=[self._jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: {e}")
            return None

    def generate_magic_link_token(self, email: str, expires_minutes: int | None = None) -> str:
        """Generate a magic link token.

        Args:
            email: Email address for the magic link
            expires_minutes: Custom expiration time

        Returns:
            Magic link token
        """
        expire_minutes = expires_minutes or self._magic_link_expire_minutes
        expire = datetime.now(UTC) + timedelta(minutes=expire_minutes)

        claims = {"sub": email, "exp": expire, "iat": datetime.now(UTC), "type": "magic_link"}

        token = jwt.encode(claims, self._jwt_secret, algorithm=self._jwt_algorithm)

        logger.debug(f"Generated magic link token for {email}")
        return token

    def decode_magic_link_token(self, token: str) -> str | None:
        """Decode a magic link token.

        Args:
            token: Magic link token

        Returns:
            Email address or None if invalid
        """
        payload = self.validate_token(token)

        if payload and payload.get("type") == "magic_link":
            return payload.get("sub")

        return None

    def generate_refresh_token(self) -> str:
        """Generate a secure refresh token.

        Returns:
            Refresh token
        """
        return secrets.token_urlsafe(32)


class SessionService:
    """Service for session and refresh token management."""

    def __init__(
        self,
        token_service: TokenService,
        session_repository: SessionRepository,
        performance_monitor: PerformanceMonitor,
        refresh_token_expire_days: int = 30,
        max_sessions_per_user: int = 5,
    ):
        """Initialize the session service.

        Args:
            token_service: Token service for token operations
            session_repository: Repository for session data
            performance_monitor: Performance monitoring instance
            refresh_token_expire_days: Refresh token expiration
            max_sessions_per_user: Maximum concurrent sessions
        """
        self._token_service = token_service
        self._session_repo = session_repository
        self._monitor = performance_monitor
        self._refresh_expire_days = refresh_token_expire_days
        self._max_sessions = max_sessions_per_user

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("SessionService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.create_session = self._monitor.monitor_service_method(
            "SessionService", "create_session"
        )(self.create_session)

        self.refresh_access_token = self._monitor.monitor_service_method(
            "SessionService", "refresh_access_token"
        )(self.refresh_access_token)

    async def create_session(
        self, user_id: str, device_info: dict[str, Any] | None = None, request=None
    ) -> tuple[str, str]:
        """Create a new user session.

        Args:
            user_id: User identifier
            device_info: Device/client information
            request: Optional request object for fingerprint calculation

        Returns:
            Tuple of (access_token, refresh_token)
        """
        # Check session limit
        active_count = await self._session_repo.get_active_session_count(user_id)
        if active_count >= self._max_sessions:
            logger.warning(f"User {user_id} exceeded session limit")
            # Optionally revoke oldest session
            sessions = await self._session_repo.get_user_sessions(user_id)
            if sessions:
                oldest = min(sessions, key=lambda s: s["created_at"])
                await self._session_repo.revoke_user_session(oldest["refresh_token"])

        # Generate tokens
        access_token = self._token_service.generate_access_token(user_id)
        refresh_token = self._token_service.generate_refresh_token()

        # Enhance device_info with fingerprint if request is provided
        enhanced_device_info = device_info or {}
        if request:
            # Calculate fingerprint for session security
            import hashlib

            user_agent = (
                request.headers.get("User-Agent", "") if hasattr(request, "headers") else ""
            )
            client_ip = request.client.host if hasattr(request, "client") and request.client else ""

            # Use IP subnet for flexibility
            ip_parts = client_ip.split(".")
            ip_subnet = ".".join(ip_parts[:3]) if len(ip_parts) >= 3 else client_ip

            fingerprint_data = f"{user_agent}|{ip_subnet}"
            fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
            enhanced_device_info["fingerprint"] = fingerprint
            enhanced_device_info["user_agent"] = user_agent
            enhanced_device_info["ip_subnet"] = ip_subnet

        # Create session
        expires_at = datetime.now(UTC) + timedelta(days=self._refresh_expire_days)
        await self._session_repo.create_user_session(
            user_id, refresh_token, enhanced_device_info, expires_at
        )

        logger.info(f"Created session for user {user_id}")
        return access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> str | None:
        """Refresh an access token using refresh token.

        Args:
            refresh_token: Refresh token

        Returns:
            New access token or None if invalid
        """
        # Get session
        session = await self._session_repo.get_user_session(refresh_token)
        if not session:
            logger.warning("Refresh token not found or expired")
            return None

        # Generate new access token
        user_id = session["user_id"]
        access_token = self._token_service.generate_access_token(user_id)

        logger.debug(f"Refreshed access token for user {user_id}")
        return access_token

    async def revoke_session(self, refresh_token: str) -> bool:
        """Revoke a user session.

        Args:
            refresh_token: Refresh token to revoke

        Returns:
            True if revoked successfully
        """
        return await self._session_repo.revoke_user_session(refresh_token)

    async def revoke_all_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions revoked
        """
        return await self._session_repo.revoke_all_user_sessions(user_id)

    async def get_active_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Get active sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            List of active sessions
        """
        return await self._session_repo.get_user_sessions(user_id)

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions.

        Returns:
            Number of sessions cleaned
        """
        return await self._session_repo.cleanup_expired_sessions()


class MfaService:
    """Service for Multi-Factor Authentication operations."""

    def __init__(
        self,
        mfa_repository: MfaRepository,
        performance_monitor: PerformanceMonitor,
        issuer_name: str = "RV-C System",
        backup_codes_count: int = 8,
    ):
        """Initialize the MFA service.

        Args:
            mfa_repository: Repository for MFA data
            performance_monitor: Performance monitoring instance
            issuer_name: TOTP issuer name
            backup_codes_count: Number of backup codes to generate
        """
        self._mfa_repo = mfa_repository
        self._monitor = performance_monitor
        self._issuer_name = issuer_name
        self._backup_codes_count = backup_codes_count

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("MfaService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.generate_mfa_setup = self._monitor.monitor_service_method(
            "MfaService", "generate_mfa_setup"
        )(self.generate_mfa_setup)

        self.enable_mfa = self._monitor.monitor_service_method("MfaService", "enable_mfa")(
            self.enable_mfa
        )

        self.verify_mfa_code = self._monitor.monitor_service_method(
            "MfaService", "verify_mfa_code"
        )(self.verify_mfa_code)

    async def generate_mfa_setup(self, user_id: str, username: str) -> dict[str, Any]:
        """Generate MFA setup data.

        Args:
            user_id: User identifier
            username: Username for TOTP

        Returns:
            MFA setup data with secret and QR code
        """
        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Generate backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(self._backup_codes_count)]

        # Hash backup codes for storage
        backup_codes_hash = [bcrypt.hash(code) for code in backup_codes]

        # Create MFA config
        await self._mfa_repo.create_user_mfa(user_id, secret, backup_codes_hash)

        # Generate provisioning URI
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=username, issuer_name=self._issuer_name)

        logger.info(f"Generated MFA setup for user {user_id}")

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "backup_codes": backup_codes,
        }

    async def enable_mfa(self, user_id: str, code: str) -> bool:
        """Enable MFA after verifying initial code.

        Args:
            user_id: User identifier
            code: TOTP code to verify

        Returns:
            True if MFA enabled successfully
        """
        # Get MFA config
        config = await self._mfa_repo.get_user_mfa(user_id)
        if not config:
            logger.warning(f"MFA config not found for user {user_id}")
            return False

        # Verify code
        totp = pyotp.TOTP(config["secret"])
        if not totp.verify(code, valid_window=1):
            logger.warning(f"Invalid MFA code during enable for user {user_id}")
            return False

        # Enable MFA
        await self._mfa_repo.update_user_mfa(user_id, {"enabled": True})

        logger.info(f"MFA enabled for user {user_id}")
        return True

    async def verify_mfa_code(self, user_id: str, code: str) -> bool:
        """Verify an MFA code.

        Args:
            user_id: User identifier
            code: Code to verify (TOTP or backup)

        Returns:
            True if code is valid
        """
        # Get MFA config
        config = await self._mfa_repo.get_user_mfa(user_id)
        if not config or not config.get("enabled"):
            logger.warning(f"MFA not enabled for user {user_id}")
            return False

        # Try TOTP first
        totp = pyotp.TOTP(config["secret"])
        if totp.verify(code, valid_window=1):
            await self._mfa_repo.update_user_mfa(
                user_id, {"last_used": datetime.now(UTC).isoformat()}
            )
            logger.debug(f"Valid TOTP code for user {user_id}")
            return True

        # Try backup codes
        for code_hash in config.get("backup_codes_hash", []):
            if bcrypt.verify(code, code_hash):
                # Mark backup code as used
                if await self._mfa_repo.mark_backup_code_used(user_id, code_hash):
                    logger.info(f"Backup code used for user {user_id}")
                    return True

        logger.warning(f"Invalid MFA code for user {user_id}")
        return False

    async def disable_mfa(self, user_id: str) -> bool:
        """Disable MFA for a user.

        Args:
            user_id: User identifier

        Returns:
            True if disabled successfully
        """
        return await self._mfa_repo.delete_user_mfa(user_id)

    async def regenerate_backup_codes(self, user_id: str) -> list[str] | None:
        """Regenerate backup codes for a user.

        Args:
            user_id: User identifier

        Returns:
            New backup codes or None
        """
        # Get existing config
        config = await self._mfa_repo.get_user_mfa(user_id)
        if not config:
            return None

        # Generate new codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(self._backup_codes_count)]

        # Hash for storage
        backup_codes_hash = [bcrypt.hash(code) for code in backup_codes]

        # Create new config with same secret
        await self._mfa_repo.create_user_mfa(user_id, config["secret"], backup_codes_hash)

        # Re-enable if was enabled
        if config.get("enabled"):
            await self._mfa_repo.update_user_mfa(user_id, {"enabled": True})

        logger.info(f"Regenerated backup codes for user {user_id}")
        return backup_codes


class LockoutService:
    """Service for account lockout protection."""

    def __init__(
        self,
        auth_event_repository: AuthEventRepository,
        performance_monitor: PerformanceMonitor,
        max_failed_attempts: int,
        lockout_window_minutes: int,
        lockout_duration_minutes: int,
        attempt_tracker_service: Any | None = None,
    ):
        """Initialize the lockout service.

        Args:
            auth_event_repository: Repository for auth events
            performance_monitor: Performance monitoring instance
            max_failed_attempts: Maximum failed attempts before lockout
            lockout_window_minutes: Time window for counting attempts
            lockout_duration_minutes: How long to lock account
            attempt_tracker_service: Optional centralized attempt tracking service
        """
        self._auth_event_repo = auth_event_repository
        self._monitor = performance_monitor
        self._max_attempts = max_failed_attempts
        self._window_minutes = lockout_window_minutes
        self._lockout_minutes = lockout_duration_minutes
        self._attempt_tracker = attempt_tracker_service

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("LockoutService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.check_lockout = self._monitor.monitor_service_method(
            "LockoutService", "check_lockout"
        )(self.check_lockout)

        self.record_failed_attempt = self._monitor.monitor_service_method(
            "LockoutService", "record_failed_attempt"
        )(self.record_failed_attempt)

    async def check_lockout(self, username: str) -> tuple[bool, datetime | None]:
        """Check if user is locked out.

        Args:
            username: Username to check

        Returns:
            Tuple of (is_locked, unlock_time)
        """
        # Get recent failed attempts
        failed_count = await self._auth_event_repo.get_failed_attempts_count(
            username, self._window_minutes
        )

        if failed_count >= self._max_attempts:
            # Calculate unlock time
            events = await self._auth_event_repo.get_auth_events_for_user(
                username, datetime.now(UTC) - timedelta(minutes=self._window_minutes)
            )

            # Find the most recent failed attempt
            failed_events = [e for e in events if e["event_type"] == "login" and not e["success"]]

            if failed_events:
                latest_fail = max(failed_events, key=lambda e: e["timestamp"])
                fail_time = datetime.fromisoformat(latest_fail["timestamp"].replace("Z", "+00:00"))
                unlock_time = fail_time + timedelta(minutes=self._lockout_minutes)

                if unlock_time > datetime.now(UTC):
                    logger.warning(f"User {username} is locked out until {unlock_time}")
                    return True, unlock_time

        return False, None

    async def record_failed_attempt(
        self, username: str, metadata: dict[str, Any] | None = None
    ) -> int:
        """Record a failed login attempt.

        Args:
            username: Username that failed
            metadata: Additional event metadata

        Returns:
            Current failed attempt count
        """
        # Record the event
        await self._auth_event_repo.create_auth_event(username, "login", False, metadata)

        # Also track in centralized service if available
        if self._attempt_tracker:
            try:
                # Import here to avoid circular dependency
                from backend.services.attempt_tracker_service import (
                    AttemptStatus,
                    AttemptType,
                    SecurityAttempt,
                )

                attempt = SecurityAttempt(
                    attempt_type=AttemptType.LOGIN,
                    status=AttemptStatus.FAILED,
                    username=username,
                    ip_address=metadata.get("ip_address") if metadata else None,
                    user_agent=metadata.get("user_agent") if metadata else None,
                    metadata=metadata or {},
                )
                await self._attempt_tracker.track_attempt(attempt)
            except Exception as e:
                logger.error(f"Failed to track attempt in AttemptTrackerService: {e}")

        # Get current count
        failed_count = await self._auth_event_repo.get_failed_attempts_count(
            username, self._window_minutes
        )

        if failed_count >= self._max_attempts:
            logger.warning(f"User {username} reached max failed attempts ({failed_count})")

        return failed_count

    async def record_successful_login(
        self, username: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Record a successful login and clear failed attempts.

        Args:
            username: Username that succeeded
            metadata: Additional event metadata
        """
        # Record success
        await self._auth_event_repo.create_auth_event(username, "login", True, metadata)

        # Also track in centralized service if available
        if self._attempt_tracker:
            try:
                # Import here to avoid circular dependency
                from backend.services.attempt_tracker_service import (
                    AttemptStatus,
                    AttemptType,
                    SecurityAttempt,
                )

                attempt = SecurityAttempt(
                    attempt_type=AttemptType.LOGIN,
                    status=AttemptStatus.SUCCESS,
                    username=username,
                    ip_address=metadata.get("ip_address") if metadata else None,
                    user_agent=metadata.get("user_agent") if metadata else None,
                    metadata=metadata or {},
                )
                await self._attempt_tracker.track_attempt(attempt)
            except Exception as e:
                logger.error(f"Failed to track attempt in AttemptTrackerService: {e}")

        # Clear failed attempts
        await self._auth_event_repo.clear_failed_attempts(username)

        logger.info(f"Successful login recorded for {username}")

    async def get_lockout_info(self, username: str) -> dict[str, Any]:
        """Get detailed lockout information for a user.

        Args:
            username: Username to check

        Returns:
            Lockout status and details
        """
        is_locked, unlock_time = await self.check_lockout(username)
        failed_count = await self._auth_event_repo.get_failed_attempts_count(
            username, self._window_minutes
        )

        return {
            "is_locked": is_locked,
            "unlock_time": unlock_time.isoformat() if unlock_time else None,
            "failed_attempts": failed_count,
            "max_attempts": self._max_attempts,
            "attempts_remaining": max(0, self._max_attempts - failed_count),
        }
