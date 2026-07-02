"""Standalone plain-text ASGI app for the RouterOS sidecar."""

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


def _text_token(token: str) -> PlainTextResponse:
    """Return a RouterOS-friendly plain-text token response."""
    return PlainTextResponse(f"{token}\n", media_type="text/plain")


def create_router_sidecar_app(
    *,
    location_state: Callable[[], str],
    starlink_verdict: Callable[[], str],
    starlink_raw: Callable[[], str],
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

    return app
