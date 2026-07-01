"""Persistence helpers for the embedded MCP OAuth Authorization Server."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.mcp_oauth import (
    McpOAuthAccessToken,
    McpOAuthAuthorizationCode,
    McpOAuthClient,
    McpOAuthTransaction,
)
from backend.services.auth.mcp_contract import MCP_TOKEN_PREFIX
from backend.services.database.database_manager import DatabaseManager


class McpOAuthRepository:
    """Repository for MCP OAuth clients, transaction state, auth codes, and tokens."""

    def __init__(self, database_manager: DatabaseManager):
        """Initialize the repository."""
        self._database_manager = database_manager

    async def create_client(self, redirect_uris: list[str]) -> tuple[McpOAuthClient, str] | None:
        """Create a dynamically registered OAuth client with a hashed secret."""
        client_id = f"ciqclient_{secrets.token_urlsafe(24)}"
        client_secret = f"ciqsecret_{secrets.token_urlsafe(32)}"

        async def _create(session: AsyncSession) -> tuple[McpOAuthClient, str]:
            client = McpOAuthClient(
                id=str(uuid4()),
                client_id=client_id,
                client_secret_hash=self.hash_secret(client_secret),
                redirect_uris=redirect_uris,
            )
            session.add(client)
            await session.commit()
            await session.refresh(client)
            return client, client_secret

        return await self._execute(_create)

    async def get_client(self, client_id: str) -> McpOAuthClient | None:
        """Return a DCR client by client_id."""

        async def _get(session: AsyncSession) -> McpOAuthClient | None:
            result = await session.execute(
                select(McpOAuthClient).where(McpOAuthClient.client_id == client_id)
            )
            return result.scalar_one_or_none()

        return await self._execute(_get)

    def verify_client_secret(self, client: McpOAuthClient, presented_secret: str | None) -> bool:
        """Compare a presented client secret to the stored hash in constant time."""
        if presented_secret is None:
            return False
        return hmac.compare_digest(client.client_secret_hash, self.hash_secret(presented_secret))

    async def create_transaction(  # noqa: PLR0913
        self,
        *,
        client_id: str,
        redirect_uri: str,
        client_state: str | None,
        client_code_challenge: str,
        client_code_challenge_method: str,
        upstream_code_verifier: str,
        upstream_nonce: str,
        ttl_seconds: int,
    ) -> McpOAuthTransaction | None:
        """Create short-lived AS transaction state for the two PKCE legs."""
        transaction_state = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        async def _create(session: AsyncSession) -> McpOAuthTransaction:
            transaction = McpOAuthTransaction(
                id=str(uuid4()),
                transaction_state=transaction_state,
                client_id=client_id,
                redirect_uri=redirect_uri,
                client_state=client_state,
                client_code_challenge=client_code_challenge,
                client_code_challenge_method=client_code_challenge_method,
                upstream_code_verifier=upstream_code_verifier,
                upstream_nonce=upstream_nonce,
                expires_at=expires_at,
            )
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            return transaction

        return await self._execute(_create)

    async def consume_transaction(self, transaction_state: str) -> McpOAuthTransaction | None:
        """Consume AS transaction state exactly once."""

        async def _consume(session: AsyncSession) -> McpOAuthTransaction | None:
            now = datetime.now(UTC)
            result = await session.execute(
                update(McpOAuthTransaction)
                .where(
                    McpOAuthTransaction.transaction_state == transaction_state,
                    McpOAuthTransaction.consumed_at.is_(None),
                    McpOAuthTransaction.expires_at > now,
                )
                .values(consumed_at=now)
                .returning(McpOAuthTransaction.id)
            )
            transaction_id = result.scalar_one_or_none()
            if transaction_id is None:
                return None
            transaction = await session.get(McpOAuthTransaction, transaction_id)
            if transaction is None:
                return None
            await session.commit()
            return transaction

        return await self._execute(_consume)

    async def create_authorization_code(  # noqa: PLR0913
        self,
        *,
        user_id: str,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        ttl_seconds: int,
    ) -> str | None:
        """Create a single-use authorization code and store only its hash."""
        code = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        async def _create(session: AsyncSession) -> str:
            auth_code = McpOAuthAuthorizationCode(
                id=str(uuid4()),
                code_hash=self.hash_secret(code),
                client_id=client_id,
                user_id=user_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                expires_at=expires_at,
            )
            session.add(auth_code)
            await session.commit()
            return code

        return await self._execute(_create)

    async def consume_authorization_code(self, code: str) -> McpOAuthAuthorizationCode | None:
        """Consume an authorization code exactly once."""

        async def _consume(session: AsyncSession) -> McpOAuthAuthorizationCode | None:
            now = datetime.now(UTC)
            result = await session.execute(
                update(McpOAuthAuthorizationCode)
                .where(
                    McpOAuthAuthorizationCode.code_hash == self.hash_secret(code),
                    McpOAuthAuthorizationCode.consumed_at.is_(None),
                    McpOAuthAuthorizationCode.expires_at > now,
                )
                .values(consumed_at=now)
                .returning(McpOAuthAuthorizationCode.id)
            )
            auth_code_id = result.scalar_one_or_none()
            if auth_code_id is None:
                return None
            auth_code = await session.get(McpOAuthAuthorizationCode, auth_code_id)
            if auth_code is None:
                return None
            await session.commit()
            return auth_code

        return await self._execute(_consume)

    async def mint_access_token(
        self,
        *,
        user_id: str,
        client_id: str,
        scope: str,
        ttl_days: int,
    ) -> tuple[McpOAuthAccessToken, str] | None:
        """Mint an opaque MCP-only access token and store only its hash."""
        token = f"{MCP_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(UTC) + timedelta(days=ttl_days)

        async def _mint(session: AsyncSession) -> tuple[McpOAuthAccessToken, str]:
            access_token = McpOAuthAccessToken(
                id=str(uuid4()),
                token_hash=self.hash_secret(token),
                user_id=user_id,
                client_id=client_id,
                scope=scope,
                expires_at=expires_at,
            )
            session.add(access_token)
            await session.commit()
            await session.refresh(access_token)
            return access_token, token

        return await self._execute(_mint)

    async def validate_access_token(self, token: str) -> McpOAuthAccessToken | None:
        """Validate an opaque MCP access token by hashed handle lookup."""
        if not token.startswith(MCP_TOKEN_PREFIX):
            return None

        async def _validate(session: AsyncSession) -> McpOAuthAccessToken | None:
            result = await session.execute(
                select(McpOAuthAccessToken).where(
                    McpOAuthAccessToken.token_hash == self.hash_secret(token)
                )
            )
            access_token = result.scalar_one_or_none()
            if (
                not access_token
                or access_token.revoked_at is not None
                or _is_expired(access_token.expires_at)
            ):
                return None
            access_token.last_used_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(access_token)
            return access_token

        return await self._execute(_validate)

    async def revoke_access_token(self, token: str) -> bool:
        """Soft-revoke an opaque MCP access token."""

        async def _revoke(session: AsyncSession) -> bool:
            result = await session.execute(
                select(McpOAuthAccessToken).where(
                    McpOAuthAccessToken.token_hash == self.hash_secret(token)
                )
            )
            access_token = result.scalar_one_or_none()
            if not access_token:
                return False
            access_token.revoked_at = datetime.now(UTC)
            await session.commit()
            return True

        return bool(await self._execute(_revoke))

    @staticmethod
    def hash_secret(secret: str) -> str:
        """Return a SHA-256 hash for stored secrets and token handles."""
        return hashlib.sha256(secret.encode()).hexdigest()

    async def _execute(self, operation):
        """Run a repository operation in an async DB session."""
        database_url = self._database_manager.engine.settings.get_database_url()
        if database_url == "null://memory":
            return None
        async with self._database_manager.get_session() as session:
            return await operation(session)


def _is_expired(value: datetime) -> bool:
    """Return whether a database datetime is in the past."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)
