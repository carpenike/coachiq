"""Behavior tests for authentication guardrail services."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.config import AuthenticationSettings
from backend.core.custom_exceptions import AuthenticationError, InvalidTokenError
from backend.services.auth.manager import AuthManager, AuthMode
from backend.services.auth.service import AuthService, create_auth_service

pytestmark = [pytest.mark.unit, pytest.mark.auth]


class FakeAuthEvent:
    """Minimal auth event object for lockout calculations."""

    def __init__(self, success: bool, created_at: datetime) -> None:
        self.success = success
        self.created_at = created_at


def auth_settings(**overrides: object) -> AuthenticationSettings:
    """Create authentication settings with a real secret by default."""
    defaults: dict[str, object] = {
        "enabled": True,
        "secret_key": "test-secret-key-that-is-long-enough",
        "enable_magic_links": False,
        "enable_oauth": False,
        "admin_email": "",
        "admin_username": "",
        "admin_password": "",
        "enable_mfa": False,
    }
    defaults.update(overrides)
    return AuthenticationSettings(**defaults)


def auth_manager(**settings_overrides: object) -> AuthManager:
    """Create a legacy-mode AuthManager for focused unit tests."""
    return AuthManager(auth_settings=auth_settings(**settings_overrides))


def test_auth_mode_detection_none_single_and_multi() -> None:
    """Auth mode follows the configured auth features."""
    assert (
        AuthManager(auth_settings=AuthenticationSettings(enabled=False)).auth_mode == AuthMode.NONE
    )
    assert auth_manager(admin_username="admin").auth_mode == AuthMode.SINGLE_USER
    assert auth_manager(admin_email="admin@example.com").auth_mode == AuthMode.MULTI_USER


def test_generate_and_validate_legacy_jwt_token() -> None:
    """Legacy token generation and validation round-trip expected claims."""
    manager = auth_manager()

    token = manager.generate_token("user-1", username="ryan", additional_claims={"role": "admin"})
    payload = manager.validate_token(token)

    assert payload["sub"] == "user-1"
    assert payload["username"] == "ryan"
    assert payload["role"] == "admin"
    assert payload["iss"] == "coachiq"


def test_invalid_or_unavailable_tokens_are_rejected() -> None:
    """Invalid tokens and disabled auth dependencies fail closed."""
    manager = auth_manager()

    with pytest.raises(InvalidTokenError):
        manager.validate_token("not-a-token")

    missing_secret = AuthManager(auth_settings=AuthenticationSettings(enabled=False))
    missing_secret.settings.secret_key = ""
    with pytest.raises(AuthenticationError):
        missing_secret.generate_token("user-1")


def test_is_authenticated_request_respects_mode_and_token_validity() -> None:
    """Authentication request checks allow NONE mode and reject bad tokens otherwise."""
    no_auth = AuthManager(auth_settings=AuthenticationSettings(enabled=False))
    assert no_auth.is_authenticated_request(None) is True

    manager = auth_manager(admin_username="admin")
    token = manager.generate_token("user-1")
    assert manager.is_authenticated_request(token) is True
    assert manager.is_authenticated_request(None) is False
    assert manager.is_authenticated_request("bad") is False


@pytest.mark.asyncio
async def test_service_mode_delegates_token_generation_and_validation() -> None:
    """Service-mode AuthManager delegates token operations to injected services."""
    token_service = Mock()
    token_service.generate_access_token.return_value = "delegated-token"
    token_service.validate_token.return_value = {"sub": "admin-user", "role": "admin"}

    manager = AuthManager(
        auth_settings=auth_settings(enable_mfa=True),
        token_service=token_service,
        session_service=Mock(),
        mfa_service=Mock(),
        lockout_service=Mock(),
    )

    token = manager.generate_token("admin-user", username="admin")
    payload = manager.validate_token(token)

    assert token == token_service.generate_access_token.return_value
    assert payload["sub"] == "admin-user"
    token_service.generate_access_token.assert_called_once()


def test_mfa_availability_and_backup_code_generation() -> None:
    """MFA helper decisions depend on settings and generate configured backup codes."""
    manager = auth_manager(enable_mfa=True, mfa_backup_codes_count=5, mfa_backup_code_length=6)

    assert manager.is_mfa_available() is True
    codes = manager._generate_backup_codes()
    assert len(codes) == 5
    assert all(len(code) == 6 for code in codes)


@pytest.mark.asyncio
async def test_lockout_detection_and_status_uses_failed_events() -> None:
    """Lockout decisions count recent failed login events and report details."""
    manager = auth_manager(max_failed_attempts=3, lockout_duration_minutes=30)
    now = datetime.now(UTC)
    failed_events = [FakeAuthEvent(False, now - timedelta(minutes=offset)) for offset in (3, 2, 1)]
    repo = AsyncMock()
    repo.get_auth_events_for_user.return_value = failed_events
    manager.auth_repository = repo

    locked, lockout_until = await manager.is_account_locked("Admin")
    status = await manager.get_lockout_status("Admin")

    assert locked is True
    assert lockout_until is not None
    assert status["is_locked"] is True
    assert status["failed_attempts"] == 3
    assert status["username"] == "Admin"


@pytest.mark.asyncio
async def test_record_failed_and_successful_login_create_audit_events() -> None:
    """Failed and successful login recording use the repository event stream."""
    manager = auth_manager(max_failed_attempts=10)
    repo = AsyncMock()
    repo.get_auth_events_for_user.return_value = [
        FakeAuthEvent(False, datetime.now(UTC) - timedelta(minutes=1))
    ]
    manager.auth_repository = repo

    await manager.record_failed_attempt("admin")
    await manager.record_successful_login("admin")

    assert repo.create_auth_event.await_count == 2
    first_call = repo.create_auth_event.await_args_list[0].kwargs
    second_call = repo.create_auth_event.await_args_list[1].kwargs
    assert first_call["success"] is False
    assert first_call["email"] == "admin"
    assert second_call["success"] is True
    assert second_call["user_id"] == "admin"


@pytest.mark.asyncio
async def test_mfa_setup_and_verification_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """MFA setup stores secrets and successful verification enables MFA."""
    manager = auth_manager(enable_mfa=True)
    repo = AsyncMock()
    repo.create_user_mfa.return_value = True
    repo.get_user_mfa.return_value = SimpleNamespace(
        totp_secret="SECRET", is_enabled=True, created_at=datetime.now(UTC), last_used_at=None
    )
    repo.update_user_mfa.return_value = True
    repo.verify_backup_code.return_value = False
    repo.count_unused_backup_codes.return_value = 5
    repo.get_user_backup_codes.return_value = ["x"] * 5
    manager.auth_repository = repo
    monkeypatch.setattr(manager, "_generate_qr_code", lambda uri: f"qr:{uri}")
    monkeypatch.setattr(manager, "_verify_totp_code", lambda secret, code: code == "123456")

    generated = await manager.generate_mfa_secret("user-1")
    verified = await manager.verify_mfa_setup("user-1", "123456")
    code_valid = await manager.verify_mfa_code("user-1", "123456")
    status = await manager.get_mfa_status("user-1")

    assert generated["secret"]
    assert generated["qr_code"].startswith("qr:")
    assert verified is True
    assert code_valid is True
    assert status["mfa_enabled"] is True
    repo.create_user_mfa.assert_awaited_once()


@pytest.fixture
def auth_service_dependencies() -> dict[str, object]:
    """Create AuthService dependency mocks."""
    return {
        "credential_repository": AsyncMock(),
        "session_repository": AsyncMock(),
        "auth_event_repository": AsyncMock(),
        "auth_repository": AsyncMock(),
        "token_service": Mock(),
        "session_service": Mock(),
        "mfa_service": Mock(),
        "lockout_service": Mock(),
        "auth_settings": auth_settings(
            enabled=True,
            secret_key="test-secret-key-that-is-long-enough",
            admin_username="admin",
            admin_password="password",
            enable_magic_links=False,
            enable_mfa=True,
        ),
    }


def test_auth_service_health_before_start(auth_service_dependencies: dict[str, object]) -> None:
    """AuthService reports unhealthy until its manager is initialized."""
    service = AuthService(**auth_service_dependencies)

    health = service.get_health_status()

    assert health["healthy"] is False
    assert health["error"] == "Auth manager not initialized"
    assert service.get_auth_manager() is None


@pytest.mark.asyncio
async def test_auth_service_start_requires_core_subservices(
    auth_service_dependencies: dict[str, object],
) -> None:
    """AuthService fails fast when required sub-services are not injected."""
    auth_service_dependencies["token_service"] = None
    service = AuthService(**auth_service_dependencies)

    with pytest.raises(RuntimeError, match="requires TokenService"):
        await service.start()


@pytest.mark.asyncio
async def test_auth_service_start_stop_and_service_info(
    auth_service_dependencies: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AuthService starts an AuthManager facade, exposes info, and shuts it down."""
    fake_manager = AsyncMock()
    fake_manager.startup = AsyncMock()
    fake_manager.shutdown = AsyncMock()
    fake_manager.get_stats = AsyncMock(return_value={"auth_mode": "single", "jwt_available": True})

    class FakeAuthManager:
        def __new__(cls, *_args: object, **_kwargs: object) -> AsyncMock:
            return fake_manager

    monkeypatch.setattr("backend.services.auth.service.AuthManager", FakeAuthManager)
    service = AuthService(**auth_service_dependencies)

    await service.start()
    info = await service.get_service_info()
    health = service.get_health_status()
    await service.stop()

    fake_manager.startup.assert_awaited_once()
    fake_manager.shutdown.assert_awaited_once()
    assert info["auth_mode"] == "single"
    assert health["healthy"] is True
    assert service.get_auth_manager() is fake_manager


@pytest.mark.asyncio
async def test_auth_service_passes_typed_settings_to_auth_manager(
    auth_service_dependencies: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AuthService passes canonical typed auth settings to the runtime AuthManager."""
    typed_settings = auth_settings(
        enabled=True,
        secret_key="typed-secret-key-that-is-long-enough",
        admin_username="typed-admin",
        admin_password="typed-password",
        enable_magic_links=True,
        jwt_expire_minutes=23,
        refresh_token_expire_days=11,
    )
    auth_service_dependencies["auth_settings"] = typed_settings
    captured: dict[str, object] = {}

    class FakeAuthManager:
        def __new__(cls, **kwargs: object) -> AsyncMock:
            captured["auth_settings"] = kwargs["auth_settings"]
            fake_manager = AsyncMock()
            fake_manager.startup = AsyncMock()
            return fake_manager

    monkeypatch.setattr("backend.services.auth.service.AuthManager", FakeAuthManager)
    service = AuthService(**auth_service_dependencies)

    await service.start()

    assert captured["auth_settings"] is typed_settings
    assert typed_settings.enabled is True
    assert typed_settings.admin_username == "typed-admin"
    assert typed_settings.admin_password == "typed-password"  # noqa: S105
    assert typed_settings.enable_magic_links is True
    assert typed_settings.jwt_expire_minutes == 23
    assert typed_settings.refresh_token_expire_days == 11


def test_create_auth_service_factory_is_registry_only() -> None:
    """The standalone factory documents ServiceRegistry-only creation."""
    with pytest.raises(NotImplementedError):
        create_auth_service()
