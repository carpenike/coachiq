"""Regression tests for refresh-session persistence across backend restarts.

Historically ``SessionRepository`` stored refresh-token sessions only in an
in-memory dict, so every ``coachiq.service`` restart invalidated all refresh
tokens and bounced authenticated users back to /login. These tests pin the
fix: sessions are persisted to the ``user_sessions`` table and survive a
process restart (modelled here as a fresh ``SessionRepository`` on the same
SQLite file), while unpersistable sessions still fall back to in-memory.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.models.auth import Base, User
from backend.repositories.auth_repository import SessionRepository


class _FakeEngineSettings:
    def __init__(self, url: str) -> None:
        self._url = url

    def get_database_url(self) -> str:
        return self._url


class _FakeEngine:
    def __init__(self, url: str) -> None:
        self.settings = _FakeEngineSettings(url)


class _FakeDatabaseManager:
    """Minimal DatabaseManager surface used by AuthRepository."""

    def __init__(self, url: str, session_factory) -> None:
        self.engine = _FakeEngine(url)
        self._session_factory = session_factory

    @asynccontextmanager
    async def get_session(self):
        async with self._session_factory() as session:
            yield session


@pytest.fixture
def db_url(tmp_path):
    # A file-backed SQLite DB so data survives disposing the engine, modelling a
    # backend restart. (":memory:" would vanish per-connection.)
    return f"sqlite+aiosqlite:///{tmp_path / 'coachiq_test.db'}"


async def _make_db_manager(url: str) -> _FakeDatabaseManager:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _FakeDatabaseManager(url, factory)


async def _seed_user(manager: _FakeDatabaseManager, user_id: str) -> None:
    async with manager.get_session() as session:
        session.add(
            User(id=user_id, email=f"{user_id}@example.com", username=user_id, is_active=True)
        )
        await session.commit()


async def test_session_survives_restart(db_url):
    """A persisted session is found again by a fresh repository (post-restart)."""
    user_id = "user-persist-1"
    refresh_token = "refresh-token-persist-1"
    expires_at = datetime.now(UTC) + timedelta(days=7)

    manager = await _make_db_manager(db_url)
    await _seed_user(manager, user_id)

    repo = SessionRepository(manager, performance_monitor=None)
    session_id = await repo.create_user_session(user_id, refresh_token, {"ua": "test"}, expires_at)
    assert session_id

    # Simulate a restart: brand-new repository (empty in-memory maps) on the same
    # database file. Before the fix this returned None and forced re-login.
    restarted_manager = await _make_db_manager(db_url)
    restarted_repo = SessionRepository(restarted_manager, performance_monitor=None)

    found = await restarted_repo.get_user_session(refresh_token)
    assert found is not None
    assert found["user_id"] == user_id
    assert found["refresh_token"] == refresh_token
    assert found["is_active"] is True


async def test_revoked_session_not_returned_after_restart(db_url):
    """Revocation persists too — a revoked token stays dead across a restart."""
    user_id = "user-persist-2"
    refresh_token = "refresh-token-persist-2"
    expires_at = datetime.now(UTC) + timedelta(days=7)

    manager = await _make_db_manager(db_url)
    await _seed_user(manager, user_id)
    repo = SessionRepository(manager, performance_monitor=None)
    await repo.create_user_session(user_id, refresh_token, {}, expires_at)

    assert await repo.revoke_user_session(refresh_token) is True

    restarted_repo = SessionRepository(await _make_db_manager(db_url), performance_monitor=None)
    assert await restarted_repo.get_user_session(refresh_token) is None


async def test_expired_session_not_returned(db_url):
    """An expired persisted session is rejected."""
    user_id = "user-persist-3"
    refresh_token = "refresh-token-persist-3"
    expires_at = datetime.now(UTC) - timedelta(seconds=1)

    manager = await _make_db_manager(db_url)
    await _seed_user(manager, user_id)
    repo = SessionRepository(manager, performance_monitor=None)
    await repo.create_user_session(user_id, refresh_token, {}, expires_at)

    assert await repo.get_user_session(refresh_token) is None


async def test_unpersistable_user_falls_back_to_memory(db_url):
    """A user_id with no ``users`` row (FK) falls back to in-memory storage."""
    refresh_token = "refresh-token-fallback"
    expires_at = datetime.now(UTC) + timedelta(days=7)

    manager = await _make_db_manager(db_url)
    repo = SessionRepository(manager, performance_monitor=None)

    # No seeded user -> DB insert violates the FK -> in-memory fallback.
    session_id = await repo.create_user_session("ghost-user", refresh_token, {}, expires_at)
    assert session_id

    found = await repo.get_user_session(refresh_token)
    assert found is not None
    assert found["user_id"] == "ghost-user"
