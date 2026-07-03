"""Standalone plain-text ASGI app for the RouterOS sidecar."""

from collections.abc import Callable
from typing import Annotated
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, PlainTextResponse


def _text_token(token: str) -> PlainTextResponse:
    """Return a RouterOS-friendly plain-text token response."""
    return PlainTextResponse(f"{token}\n", media_type="text/plain")


def create_router_sidecar_app(
    *,
    location_state: Callable[[], str],
    starlink_verdict: Callable[[], str],
    starlink_raw: Callable[[], str],
    starlink_status: Callable[[], dict[str, Any]],
    starlink_history: Callable[[int | None], dict[str, Any]],
    starlink_diagnostics: Callable[[], dict[str, Any]],
    starlink_device_info: Callable[[], dict[str, Any]],
) -> FastAPI:
    """Create the sidecar app without auth, CSRF, SPA fallback, or OpenAPI docs."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> PlainTextResponse:
        return _text_token("ok")

    @app.get("/location-state", response_class=PlainTextResponse)
    async def get_location_state() -> PlainTextResponse:
        return _text_token(location_state())

    @app.get("/starlink/verdict", response_class=PlainTextResponse)
    async def get_starlink_verdict() -> PlainTextResponse:
        return _text_token(starlink_verdict())

    @app.get("/starlink/raw", response_class=PlainTextResponse)
    async def get_starlink_raw() -> PlainTextResponse:
        return _text_token(starlink_raw())

    @app.get("/starlink/status", response_class=JSONResponse)
    async def get_starlink_status() -> JSONResponse:
        return JSONResponse(starlink_status())

    @app.get("/starlink/history", response_class=JSONResponse)
    async def get_starlink_history(
        window: Annotated[int | None, Query(ge=1, le=900)] = None,
    ) -> JSONResponse:
        return JSONResponse(starlink_history(window))

    @app.get("/starlink/diagnostics", response_class=JSONResponse)
    async def get_starlink_diagnostics() -> JSONResponse:
        return JSONResponse(starlink_diagnostics())

    @app.get("/starlink/device-info", response_class=JSONResponse)
    async def get_starlink_device_info() -> JSONResponse:
        return JSONResponse(starlink_device_info())

    return app
