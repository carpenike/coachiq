"""
Authentication Service - Clean Service Implementation

Service for managing authentication without Feature inheritance.
Uses repository injection pattern for all dependencies.
"""

import logging
from typing import Any

from backend.repositories.auth_repository import (
    AuthEventRepository,
    CredentialRepository,
    MfaRepository,
    SessionRepository,
)
from backend.services.auth_manager import AuthManager
from backend.services.auth_services import (
    LockoutService,
    MfaService,
    SessionService,
    TokenService,
)

logger = logging.getLogger(__name__)


class AuthService:
    """
    Service that manages authentication operations.

    This is a clean service implementation without Feature inheritance,
    using repository injection for all dependencies.
    """

    def __init__(
        self,
        credential_repository: CredentialRepository,
        session_repository: SessionRepository,
        auth_event_repository: AuthEventRepository,
        mfa_repository: MfaRepository | None = None,
        notification_service: Any | None = None,
        performance_monitor: Any | None = None,
        auth_repository: Any | None = None,  # Legacy AuthRepository for backward compatibility
        token_service: TokenService | None = None,
        session_service: SessionService | None = None,
        mfa_service: MfaService | None = None,
        lockout_service: LockoutService | None = None,
        auth_config: dict[str, Any] | None = None,
    ):
        """
        Initialize the authentication service with repository dependencies and sub-services.

        Args:
            credential_repository: Repository for credential management
            session_repository: Repository for session management
            auth_event_repository: Repository for auth event tracking
            mfa_repository: Optional repository for MFA management
            notification_service: Optional notification service for magic links
            performance_monitor: Optional performance monitor for service monitoring
            auth_repository: Legacy AuthRepository for backward compatibility with AuthManager
            token_service: Injected TokenService instance
            session_service: Injected SessionService instance
            mfa_service: Optional injected MfaService instance
            lockout_service: Injected LockoutService instance
            auth_config: Authentication configuration from SecurityConfigService
        """
        self._credential_repository = credential_repository
        self._session_repository = session_repository
        self._auth_event_repository = auth_event_repository
        self._mfa_repository = mfa_repository
        self._notification_service = notification_service
        self._performance_monitor = performance_monitor
        self._auth_repository = auth_repository  # Store legacy repository

        # Store injected sub-services
        self._token_service = token_service
        self._session_service = session_service
        self._mfa_service = mfa_service
        self._lockout_service = lockout_service
        self._auth_config = auth_config or {}

        self._running = False
        self._auth_manager: AuthManager | None = None

        logger.info("AuthService initialized with repositories and injected sub-services")

    async def start(self) -> None:
        """Start the authentication service with injected sub-services."""
        if self._running:
            return

        logger.info("Starting authentication service")

        try:
            # Validate that required sub-services are injected
            if not self._token_service or not self._session_service or not self._lockout_service:
                raise RuntimeError(
                    "AuthService requires TokenService, SessionService, and LockoutService to be injected"
                )

            # Initialize the auth manager facade with all services
            # Create auth settings from config with proper attributes
            auth_settings_dict = {
                "enabled": self._auth_config.get(
                    "enabled", False
                ),  # Use config value for auth enabled
                "secret_key": self._auth_config.get(
                    "jwt_secret", ""
                ),  # Map jwt_secret to secret_key
                "jwt_algorithm": self._auth_config.get("jwt_algorithm", "HS256"),
                "jwt_expire_minutes": self._auth_config.get("access_token_expire_minutes", 60),
                "magic_link_expire_minutes": self._auth_config.get("magic_link_expire_minutes", 15),
                "enable_magic_links": self._auth_config.get(
                    "enable_magic_links", False
                ),  # Default to False
                "enable_oauth": self._auth_config.get("enable_oauth", False),
                "enable_mfa": self._auth_config.get("enable_mfa", False),
                "enable_refresh_tokens": self._auth_config.get("enable_refresh_tokens", True),
                "enable_account_lockout": self._auth_config.get("enable_account_lockout", True),
                "admin_email": self._auth_config.get("admin_email"),  # Use config value
                "admin_username": self._auth_config.get("admin_username"),  # Add admin username
                "admin_password": self._auth_config.get("admin_password"),  # Add admin password
                "notification_from_email": "noreply@coachiq.local",
                "refresh_token_secret": self._auth_config.get(
                    "refresh_token_secret", self._auth_config.get("jwt_secret", "")
                ),
                **self._auth_config,  # Include any additional config
            }
            auth_settings = type("AuthSettings", (), auth_settings_dict)

            self._auth_manager = AuthManager(
                auth_settings=auth_settings,
                notification_manager=self._notification_service,
                auth_repository=self._auth_repository,  # Use injected legacy repository
                token_service=self._token_service,
                session_service=self._session_service,
                mfa_service=self._mfa_service,
                lockout_service=self._lockout_service,
                credential_repository=self._credential_repository,
            )

            # Add defensive logging as recommended by Zen
            if self._auth_repository:
                logger.info(
                    "AuthManager initialized with a valid AuthRepository for legacy operations."
                )
            else:
                logger.warning(
                    "AuthManager initialized without an AuthRepository. Legacy refresh token operations will fail."
                )

            await self._auth_manager.startup()

            self._running = True
            logger.info("Authentication service started successfully")

        except Exception as e:
            logger.error("Failed to start authentication service: %s", e)
            raise

    async def stop(self) -> None:
        """Stop the authentication service and clean up resources."""
        if not self._running:
            return

        logger.info("Stopping authentication service")

        if self._auth_manager:
            try:
                await self._auth_manager.shutdown()
            except Exception as e:
                logger.error("Error shutting down auth manager: %s", e)

        self._running = False
        logger.info("Authentication service stopped")

    def get_health_status(self) -> dict[str, Any]:
        """
        Get service health status.

        Returns:
            Health status information
        """
        if not self._auth_manager:
            return {
                "service": "AuthService",
                "healthy": False,
                "running": self._running,
                "error": "Auth manager not initialized",
            }

        try:
            # Get stats from auth manager synchronously
            # Note: In production, this should be made async
            stats = {}  # Placeholder - would call self._auth_manager.get_stats_sync()

            return {
                "service": "AuthService",
                "healthy": True,
                "running": self._running,
                "auth_mode": stats.get("auth_mode"),
                "jwt_available": stats.get("jwt_available"),
                "secret_key_configured": stats.get("secret_key_configured"),
                "notification_service_available": stats.get("notification_manager_available"),
                "mfa_enabled": self._mfa_service is not None,
            }
        except Exception as e:
            logger.error("Error getting auth service health: %s", e)
            return {
                "service": "AuthService",
                "healthy": False,
                "running": self._running,
                "error": str(e),
            }

    def get_auth_manager(self) -> AuthManager | None:
        """
        Get the authentication manager instance.

        Returns:
            The AuthManager instance or None if not initialized
        """
        return self._auth_manager

    async def get_service_info(self) -> dict[str, Any]:
        """
        Get service information and current status.

        Returns:
            Service information
        """
        info = {
            "name": "Authentication Service",
            "description": "JWT-based authentication with magic links and admin user management",
            "version": "2.0.0",
            "status": "running" if self._running else "stopped",
        }

        if self._auth_manager:
            try:
                stats = await self._auth_manager.get_stats()
                info["auth_mode"] = stats.get("auth_mode")
                info["dependencies_available"] = stats.get("jwt_available")
                info["configuration"] = {
                    "jwt_algorithm": self._auth_config.get("jwt_algorithm", "HS256"),
                    "jwt_expire_minutes": self._auth_config.get("access_token_expire_minutes", 60),
                    "magic_link_expire_minutes": self._auth_config.get(
                        "magic_link_expire_minutes", 15
                    ),
                    "enable_magic_links": self._auth_config.get("enable_magic_links", True),
                    "enable_oauth": self._auth_config.get("enable_oauth", False),
                    "enable_mfa": self._auth_config.get("enable_mfa", False),
                }
            except Exception as e:
                info["error"] = str(e)

        return info


def create_auth_service() -> AuthService:
    """
    Factory function for creating AuthService with dependencies.

    This would be registered with ServiceRegistry and automatically
    get the repositories injected.
    """
    msg = (
        "This factory should be registered with ServiceRegistry "
        "to get automatic dependency injection of repositories"
    )
    raise NotImplementedError(msg)
