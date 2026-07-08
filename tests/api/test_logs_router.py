"""Tests for ``backend/api/routers/logs.py`` (/api/logs/history + /api/logs/stream).

Uses a minimal FastAPI app with only the logs router mounted, overriding the
auth dependencies (Pattern B, like tests/unit/test_database_management_api.py):
admin acceptance and 401/403 rejection are exercised through
``app.dependency_overrides`` rather than a full auth stack. The journald path
is covered by tests/services/test_log_history.py; here journald is forced
unavailable so /history exercises the ring-buffer memory fallback.

The /stream SSE tests drive the endpoint's generator directly (same pattern
as tests/websocket/test_event_stream.py): the stream never ends on its own,
and both TestClient and httpx's ASGITransport buffer/deadlock on infinite
streaming responses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.api.routers.logs import router, stream_logs
from backend.core.dependencies import (
    get_auth_manager,
    get_authenticated_admin,
    get_authenticated_user,
)
from backend.services.auth.manager import AuthMode
from backend.services.logging import log_history
from backend.services.logging.log_stream import LogStreamHandler

ADMIN_USER = {"user_id": "test-admin", "username": "test-admin", "role": "admin"}


def _make_request() -> Request:
    """Bare Starlette request for calling the endpoint function directly."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/logs/stream",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 4242),
    }
    return Request(scope)


def make_record(msg: str, level: int = logging.INFO, name: str = "backend.test"):
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


@pytest.fixture
def app() -> FastAPI:
    """Minimal app with only the logs router mounted."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def stream_handler(monkeypatch) -> LogStreamHandler:
    """Fresh (non-singleton) handler injected into the router module."""
    handler = LogStreamHandler(buffer_size=500)
    monkeypatch.setattr("backend.api.routers.logs.get_log_stream_handler", lambda: handler)
    return handler


@pytest.fixture
def no_journald(monkeypatch) -> None:
    monkeypatch.setattr(log_history, "is_journald_available", lambda: False)


@pytest.fixture
def admin_client(app: FastAPI, stream_handler, no_journald) -> Generator[TestClient, None, None]:
    """TestClient with the admin gate overridden to always succeed."""
    app.dependency_overrides[get_authenticated_admin] = lambda: ADMIN_USER
    with TestClient(app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.api
class TestAuth:
    """Both endpoints are admin-only."""

    @pytest.mark.parametrize("path", ["/api/logs/history", "/api/logs/stream"])
    def test_unauthenticated_request_is_401(self, app: FastAPI, path: str) -> None:
        # Auth manager present and NOT in AuthMode.NONE; no Authorization header.
        app.dependency_overrides[get_auth_manager] = lambda: Mock(auth_mode=AuthMode.SINGLE_USER)
        try:
            with TestClient(app, base_url="http://test") as client:
                response = client.get(path)
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.parametrize("path", ["/api/logs/history", "/api/logs/stream"])
    def test_non_admin_user_is_403(self, app: FastAPI, path: str) -> None:
        app.dependency_overrides[get_authenticated_user] = lambda: {
            "username": "user",
            "role": "user",
        }
        try:
            with TestClient(app, base_url="http://test") as client:
                response = client.get(path)
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


@pytest.mark.api
class TestHistoryMemoryFallback:
    """/history served from the ring buffer when journald is unavailable."""

    def test_returns_memory_source_not_501(
        self, admin_client: TestClient, stream_handler: LogStreamHandler
    ) -> None:
        stream_handler.handle(make_record("warn line", logging.WARNING, "backend.can"))
        stream_handler.handle(make_record("info line", logging.INFO, "backend.core"))

        response = admin_client.get("/api/logs/history")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "memory"
        assert data["has_more"] is False
        # Newest first
        assert [e["message"] for e in data["entries"]] == ["info line", "warn line"]
        # Levels mapped to syslog priorities
        assert data["entries"][0]["level"] == 6  # INFO
        assert data["entries"][1]["level"] == 4  # WARNING
        assert data["entries"][0]["module"] == "backend.core"

    def test_cursor_pagination_returns_strictly_older(
        self, admin_client: TestClient, stream_handler: LogStreamHandler
    ) -> None:
        for i in range(10):
            stream_handler.handle(make_record(f"msg {i}"))

        page1 = admin_client.get("/api/logs/history", params={"limit": 4}).json()
        assert [e["message"] for e in page1["entries"]] == ["msg 9", "msg 8", "msg 7", "msg 6"]
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = admin_client.get(
            "/api/logs/history", params={"limit": 4, "cursor": page1["next_cursor"]}
        ).json()
        assert [e["message"] for e in page2["entries"]] == ["msg 5", "msg 4", "msg 3", "msg 2"]
        assert all(int(e["cursor"]) < int(page1["next_cursor"]) for e in page2["entries"])

    def test_level_and_module_filters(
        self, admin_client: TestClient, stream_handler: LogStreamHandler
    ) -> None:
        stream_handler.handle(make_record("debug can", logging.DEBUG, "backend.can"))
        stream_handler.handle(make_record("error can", logging.ERROR, "backend.can"))
        stream_handler.handle(make_record("error core", logging.ERROR, "backend.core"))

        response = admin_client.get(
            "/api/logs/history", params={"level": "warning", "module": "backend.can"}
        )

        assert response.status_code == 200
        assert [e["message"] for e in response.json()["entries"]] == ["error can"]


@pytest.mark.api
class TestStream:
    """/stream SSE contract: retry hint, initial batch, live batches, cleanup."""

    async def test_stream_yields_retry_hint_and_initial_batch_then_live_event(
        self, stream_handler: LogStreamHandler
    ) -> None:
        stream_handler.set_loop(asyncio.get_running_loop())
        stream_handler.handle(make_record("historic entry"))

        response = await stream_logs(_make_request(), ADMIN_USER, level="debug", modules=None)

        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"

        iterator = response.body_iterator
        try:
            assert await anext(iterator) == "retry: 3000\n\n"

            # Initial batch: one `logs` event replaying the ring buffer.
            initial = await asyncio.wait_for(anext(iterator), timeout=5.0)
            assert initial.startswith("event: logs\ndata: [")
            assert initial.endswith("\n\n")
            assert "historic entry" in initial

            # A live entry arrives as a subsequent batch, flushed after the
            # 0.5s batch interval.
            stream_handler.handle(make_record("live entry"))
            live = await asyncio.wait_for(anext(iterator), timeout=5.0)
            assert live.startswith("event: logs\ndata: [")
            assert "live entry" in live
        finally:
            # Client disconnect == generator close; cleanup must unsubscribe.
            await iterator.aclose()

        assert stream_handler.subscriber_count == 0

    async def test_stream_filters_by_level_and_modules(
        self, stream_handler: LogStreamHandler
    ) -> None:
        stream_handler.handle(make_record("dropped debug", logging.DEBUG, "backend.can"))
        stream_handler.handle(make_record("dropped module", logging.ERROR, "backend.core"))
        stream_handler.handle(make_record("kept", logging.ERROR, "backend.can.bus"))

        response = await stream_logs(
            _make_request(), ADMIN_USER, level="INFO", modules="backend.can"
        )
        iterator = response.body_iterator
        try:
            assert await anext(iterator) == "retry: 3000\n\n"
            initial = await asyncio.wait_for(anext(iterator), timeout=5.0)

            assert "kept" in initial
            assert "dropped debug" not in initial
            assert "dropped module" not in initial
        finally:
            await iterator.aclose()
