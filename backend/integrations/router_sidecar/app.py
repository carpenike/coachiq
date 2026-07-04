"""Standalone plain-text ASGI app for the RouterOS sidecar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class RouterSidecarCallbacks:
    """Cached sidecar callback functions used by the standalone app."""

    location_state: Callable[[], str]
    starlink_verdict: Callable[[], str]
    starlink_raw: Callable[[], str]
    starlink_status: Callable[[], dict[str, Any]]
    starlink_history: Callable[[int | None], dict[str, Any]]
    starlink_diagnostics: Callable[[], dict[str, Any]]
    starlink_device_info: Callable[[], dict[str, Any]]
    nighthawk_status: Callable[[], dict[str, Any]]
    nighthawk_verdict: Callable[[], str]
    nighthawk_raw: Callable[[], str]


def _text_token(token: str) -> PlainTextResponse:
    """Return a RouterOS-friendly plain-text token response."""
    return PlainTextResponse(f"{token}\n", media_type="text/plain")


def _add_token_route(app: FastAPI, path: str, callback: Callable[[], str]) -> None:
    @app.get(path, response_class=PlainTextResponse)
    async def token_route() -> PlainTextResponse:
        return _text_token(callback())


def _add_json_route(app: FastAPI, path: str, callback: Callable[[], dict[str, Any]]) -> None:
    @app.get(path, response_class=JSONResponse)
    async def json_route() -> JSONResponse:
        return JSONResponse(callback())


def create_router_sidecar_app(callbacks: RouterSidecarCallbacks) -> FastAPI:
    """Create the sidecar app without auth, CSRF, SPA fallback, or OpenAPI docs."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    _add_token_route(app, "/healthz", lambda: "ok")
    _add_token_route(app, "/location-state", callbacks.location_state)
    _add_token_route(app, "/starlink/verdict", callbacks.starlink_verdict)
    _add_token_route(app, "/starlink/raw", callbacks.starlink_raw)
    _add_json_route(app, "/starlink/status", callbacks.starlink_status)

    @app.get("/starlink/history", response_class=JSONResponse)
    async def get_starlink_history(
        window: Annotated[int | None, Query(ge=1, le=900)] = None,
    ) -> JSONResponse:
        return JSONResponse(callbacks.starlink_history(window))

    _add_json_route(app, "/starlink/diagnostics", callbacks.starlink_diagnostics)
    _add_json_route(app, "/starlink/device-info", callbacks.starlink_device_info)
    _add_json_route(app, "/5g/status", callbacks.nighthawk_status)
    _add_token_route(app, "/5g/verdict", callbacks.nighthawk_verdict)
    _add_token_route(app, "/5g/raw", callbacks.nighthawk_raw)

    return app
