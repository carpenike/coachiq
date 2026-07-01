"""Tests for MCP OAuth AS persistence helpers."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models.auth import User, UserRole
from backend.models.database import Base
from backend.models.mcp_oauth import (
    McpOAuthAccessToken,
    McpOAuthAuthorizationCode,
    McpOAuthClient,
)
from backend.services.auth.mcp_contract import MCP_TOKEN_PREFIX
from backend.services.auth.mcp_oauth_repository import McpOAuthRepository


class _RepositoryDatabaseSettings:
    """Minimal settings facade used by repository null-backend checks."""

    def get_database_url(self) -> str:
        """Return a non-null URL so repository operations run."""
        return "sqlite+aiosqlite:///:memory:"


class _RepositoryDatabaseEngine:
    """Minimal engine facade used by repository tests."""

    settings = _RepositoryDatabaseSettings()


class _RepositoryDatabase:
    """Minimal database manager facade for repository tests."""

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
    """Create an isolated MCP OAuth repository database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield _RepositoryDatabase(session_factory)
    finally:
        await engine.dispose()


async def _create_user(repository_database: _RepositoryDatabase) -> User:
    """Create a local user for token FK tests."""
    async with repository_database.get_session() as session:
        user = User(
            id="local-user",
            email="local@example.test",
            username="local",
            is_active=True,
            is_admin=False,
            role=UserRole.USER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_dcr_client_secret_is_hashed_and_constant_time_verified(
    repository_database: _RepositoryDatabase,
) -> None:
    """DCR clients store only hashed secrets while returning the plaintext once."""
    repository = McpOAuthRepository(repository_database)

    created = await repository.create_client(["https://claude.ai/callback"])

    assert created is not None
    client, client_secret = created
    assert client.client_secret_hash != client_secret
    assert repository.verify_client_secret(client, client_secret) is True
    assert repository.verify_client_secret(client, "wrong-secret") is False

    async with repository_database.get_session() as session:
        rows = (await session.execute(select(McpOAuthClient))).scalars().all()
    assert rows[0].client_secret_hash == client.client_secret_hash


@pytest.mark.asyncio
async def test_transaction_store_keeps_client_and_upstream_pkce_legs_distinct(
    repository_database: _RepositoryDatabase,
) -> None:
    """AS transaction state stores independent client and AS-to-PocketID PKCE data."""
    repository = McpOAuthRepository(repository_database)

    transaction = await repository.create_transaction(
        client_id="client-1",
        redirect_uri="https://claude.ai/callback",
        client_state="client-state",
        client_code_challenge="client-challenge",
        client_code_challenge_method="S256",
        upstream_code_verifier="as-pocketid-verifier",
        upstream_nonce="as-pocketid-nonce",
        ttl_seconds=300,
    )
    assert transaction is not None
    assert transaction.client_code_challenge != transaction.upstream_code_verifier

    consumed = await repository.consume_transaction(transaction.transaction_state)
    replay = await repository.consume_transaction(transaction.transaction_state)

    assert consumed is not None
    assert consumed.client_code_challenge == "client-challenge"
    assert consumed.upstream_code_verifier == "as-pocketid-verifier"
    assert replay is None


@pytest.mark.asyncio
async def test_authorization_code_is_hashed_and_single_use(
    repository_database: _RepositoryDatabase,
) -> None:
    """Authorization codes are stored hashed and consumed exactly once."""
    repository = McpOAuthRepository(repository_database)
    user = await _create_user(repository_database)

    code = await repository.create_authorization_code(
        user_id=user.id,
        client_id="client-1",
        redirect_uri="https://claude.ai/callback",
        code_challenge="client-challenge",
        code_challenge_method="S256",
        ttl_seconds=300,
    )
    assert code is not None

    async with repository_database.get_session() as session:
        stored_code = (await session.execute(select(McpOAuthAuthorizationCode))).scalar_one()
    assert stored_code.code_hash != code

    consumed = await repository.consume_authorization_code(code)
    replay = await repository.consume_authorization_code(code)

    assert consumed is not None
    assert consumed.client_id == "client-1"
    assert replay is None


@pytest.mark.asyncio
async def test_access_token_is_hashed_prefixed_and_revocable(
    repository_database: _RepositoryDatabase,
) -> None:
    """MCP access tokens are opaque, hashed at rest, and rejected after revocation."""
    repository = McpOAuthRepository(repository_database)
    user = await _create_user(repository_database)

    minted = await repository.mint_access_token(
        user_id=user.id,
        client_id="client-1",
        scope="openid email profile",
        ttl_days=90,
    )
    assert minted is not None
    access_token, token = minted
    assert token.startswith(MCP_TOKEN_PREFIX)

    async with repository_database.get_session() as session:
        stored_token = (await session.execute(select(McpOAuthAccessToken))).scalar_one()
    assert stored_token.token_hash == access_token.token_hash
    assert stored_token.token_hash != token

    validated = await repository.validate_access_token(token)
    assert validated is not None
    assert validated.user_id == user.id

    assert await repository.revoke_access_token(token) is True
    assert await repository.validate_access_token(token) is None
