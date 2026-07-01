"""Tests for federated authentication provider bindings."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.auth import AuthProvider, UserAuthProvider, UserRole
from backend.models.database import Base
from backend.services.auth.repository import AuthRepository


class _RepositoryDatabaseSettings:
    """Minimal settings facade used by AuthRepository null-backend checks."""

    def get_database_url(self) -> str:
        """Return a non-null URL so repository operations run."""
        return "sqlite+aiosqlite:///:memory:"


class _RepositoryDatabaseEngine:
    """Minimal engine facade used by AuthRepository."""

    settings = _RepositoryDatabaseSettings()


class _RepositoryDatabase:
    """Minimal database manager facade for AuthRepository tests."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.engine = _RepositoryDatabaseEngine()
        self._session_factory = session_factory

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an isolated async SQLAlchemy session."""
        async with self._session_factory() as session:
            yield session


@pytest.fixture
async def repository_database() -> AsyncGenerator[_RepositoryDatabase, None]:
    """Create an isolated auth repository database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield _RepositoryDatabase(session_factory)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_federated_user_uses_provider_subject_as_stable_key(
    repository_database: _RepositoryDatabase,
) -> None:
    """PocketID re-login updates mutable user data while preserving the bound subject."""
    repository = AuthRepository(repository_database)

    first_login = await repository.upsert_federated_user(
        provider=AuthProvider.POCKETID,
        provider_user_id="pocketid-sub-123",
        email="old@example.test",
        username="oldname",
        display_name="Old Name",
        role=UserRole.USER,
        email_verified=True,
        provider_data={"groups": ["coachiq-users"]},
    )
    assert first_login is not None

    second_login = await repository.upsert_federated_user(
        provider=AuthProvider.POCKETID,
        provider_user_id="pocketid-sub-123",
        email="new@example.test",
        username="newname",
        display_name="New Name",
        role=UserRole.ADMIN,
        email_verified=True,
        provider_data={"groups": ["coachiq-admins"]},
    )
    assert second_login is not None
    assert second_login.id == first_login.id
    assert second_login.email == "new@example.test"
    assert second_login.username == "newname"
    assert second_login.display_name == "New Name"
    assert second_login.is_admin is True

    bound_user = await repository.get_user_by_auth_provider(
        AuthProvider.POCKETID, "pocketid-sub-123"
    )
    assert bound_user is not None
    assert bound_user.id == first_login.id
    assert bound_user.email == "new@example.test"


@pytest.mark.asyncio
async def test_verified_email_first_login_links_existing_local_user(
    repository_database: _RepositoryDatabase,
) -> None:
    """Verified PocketID email may adopt an existing matching local account."""
    repository = AuthRepository(repository_database)
    local_user = await repository.create_user(
        email="local@example.test",
        username="local",
        display_name="Local User",
    )
    assert local_user is not None

    linked_user = await repository.upsert_federated_user(
        provider=AuthProvider.POCKETID,
        provider_user_id="verified-sub",
        email="local@example.test",
        username="pocketid-local",
        display_name="PocketID Local",
        role=UserRole.ADMIN,
        email_verified=True,
        provider_data={"email_verified": True},
    )

    assert linked_user is not None
    assert linked_user.id == local_user.id
    assert linked_user.email == "local@example.test"
    assert linked_user.role == UserRole.ADMIN
    bound_user = await repository.get_user_by_auth_provider(AuthProvider.POCKETID, "verified-sub")
    assert bound_user is not None
    assert bound_user.id == local_user.id


@pytest.mark.asyncio
async def test_unverified_email_first_login_does_not_link_existing_local_user(
    repository_database: _RepositoryDatabase,
) -> None:
    """Unverified PocketID email creates a fresh sub-keyed account on email collision."""
    repository = AuthRepository(repository_database)
    local_user = await repository.create_user(
        email="admin@example.test",
        username="local-admin",
        display_name="Local Admin",
        is_admin=True,
    )
    assert local_user is not None

    federated_user = await repository.upsert_federated_user(
        provider=AuthProvider.POCKETID,
        provider_user_id="unverified-sub",
        email="admin@example.test",
        username="pocketid-admin",
        display_name="Unverified PocketID User",
        role=UserRole.USER,
        email_verified=False,
        provider_data={"email_verified": False},
    )

    assert federated_user is not None
    assert federated_user.id != local_user.id
    assert federated_user.email != local_user.email
    assert federated_user.email.endswith("@federated.coachiq.local")
    assert federated_user.role == UserRole.USER
    bound_user = await repository.get_user_by_auth_provider(
        AuthProvider.POCKETID, "unverified-sub"
    )
    assert bound_user is not None
    assert bound_user.id == federated_user.id


@pytest.mark.asyncio
async def test_provider_subject_binding_is_unique(
    repository_database: _RepositoryDatabase,
) -> None:
    """A provider subject can only bind to one local user."""
    repository = AuthRepository(repository_database)

    existing_user = await repository.upsert_federated_user(
        provider=AuthProvider.POCKETID,
        provider_user_id="pocketid-sub-456",
        email="first@example.test",
        username="first",
        display_name="First User",
    )
    other_user = await repository.create_user(
        email="second@example.test",
        username="second",
        display_name="Second User",
    )
    assert existing_user is not None
    assert other_user is not None

    async with repository_database.get_session() as session:
        session.add(
            UserAuthProvider(
                id=str(uuid4()),
                user_id=other_user.id,
                provider=AuthProvider.POCKETID,
                provider_user_id="pocketid-sub-456",
                is_verified=True,
                is_primary=False,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
