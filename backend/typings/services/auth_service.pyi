"""
Type stubs for AuthService
"""

from typing import Any, Dict, Optional

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

class AuthService:
    """
    Service that manages authentication operations.
    
    This is a clean service implementation without Feature inheritance,
    using repository injection for all dependencies.
    """

    _credential_repository: CredentialRepository
    _session_repository: SessionRepository
    _auth_event_repository: AuthEventRepository
    _mfa_repository: MfaRepository | None
    _notification_service: Any | None
    _performance_monitor: Any | None
    _auth_repository: Any | None
    _token_service: TokenService | None
    _session_service: SessionService | None
    _mfa_service: MfaService | None
    _lockout_service: LockoutService | None
    _auth_config: dict[str, Any]
    _running: bool
    _auth_manager: AuthManager | None

    def __init__(
        self,
        credential_repository: CredentialRepository,
        session_repository: SessionRepository,
        auth_event_repository: AuthEventRepository,
        mfa_repository: MfaRepository | None = None,
        notification_service: Any | None = None,
        performance_monitor: Any | None = None,
        auth_repository: Any | None = None,
        token_service: TokenService | None = None,
        session_service: SessionService | None = None,
        mfa_service: MfaService | None = None,
        lockout_service: LockoutService | None = None,
        auth_config: dict[str, Any] | None = None,
    ) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def get_auth_manager(self) -> AuthManager | None: ...

    async def health_check(self) -> dict[str, Any]: ...

    async def validate_session(self, token: str) -> dict[str, Any] | None: ...

    async def invalidate_session(self, token: str) -> bool: ...

    async def cleanup_expired_sessions(self) -> int: ...

    async def get_user_sessions(self, user_id: str) -> list[dict[str, Any]]: ...
