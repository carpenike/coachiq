# ADR-0015: Backend serves the built SPA

## Status

**Accepted**, 2026-07-02. Graduates HOF-056.

## Context

CoachIQ historically documented the production SPA as Caddy-owned: Caddy served
the built React files, carved out backend-owned prefixes, and proxied those
prefixes to FastAPI. The repository no longer matched that deployment story
cleanly. The NixOS module ran only `coachiq-daemon`, `pyproject.toml` already
included `frontend/dist/**/*`, `backend.core.config.Settings` already exposed a
`COACHIQ_STATIC_DIR` setting, and the Nix package already built a standalone
frontend derivation.

Keeping the proxy responsible for the SPA forces every deployment to duplicate
FastAPI's route split. The live backend route table has more root-owned families
than the obvious `/api` and `/ws` pair: MCP OAuth uses `/oauth` and
`/.well-known`, FastAPI owns `/docs`, `/redoc`, and `/openapi.json`, and
operational probes own `/health`, `/healthz`, `/readyz`, `/startupz`, and
`/metrics`. That list will drift if maintained as hand-written proxy rules.

Starlette's `StaticFiles(html=True)` does not provide SPA deep-link fallback by
itself. It serves `index.html` for directory requests and real files, but a
client-side route such as `/settings` still returns 404 unless the application
adds an explicit fallback.

## Decision

Serve the production React SPA from the FastAPI backend.

The backend resolves the SPA dist path from `Settings.static_dir`
(`COACHIQ_STATIC_DIR`). If the directory does not contain `index.html`, the SPA
route is not registered; this keeps development and tests on the existing Vite
dev-server flow by default.

When the dist is present, register the SPA/static fallback last, after all real
routers, FastAPI docs, health probes, and metrics. The fallback derives the
reserved backend-owned route families from the live app route table at startup
rather than using a hard-coded denylist. Existing static files under the dist are
served directly. Unmatched browser navigations (`GET`/`HEAD` with
`Accept: text/html`) outside backend-owned route families return `index.html` so
client-side routes work. Reserved route families and non-browser requests keep
normal backend 404 behavior, including the ADR-0005 JSON error envelope for API
requests.

The NixOS module defaults `COACHIQ_STATIC_DIR` to the built frontend derivation
output (`packages.frontend`) while still allowing an explicit
`services.coachiq.settings.COACHIQ_STATIC_DIR` override. Caddy becomes a single
pass-through reverse proxy for the unified backend origin, while still owning
edge duties such as TLS termination, proxy headers, compression, logging, and
security headers.

Authentication middleware must allow the same public SPA document navigations
that the fallback would serve. When the SPA is mounted, unauthenticated
`GET`/`HEAD` requests that accept `text/html` and whose root route family is not
backend-owned are allowed through to the SPA fallback. API, WebSocket, OAuth,
well-known, docs, health, readiness, startup, and metrics route families remain
outside this exemption and keep their normal authentication behavior. The
middleware reads the reserved route-family set derived by the SPA fallback at
startup so the two checks cannot drift.

## Consequences

### Becomes easier

- NixOS deployments get a self-contained UI by enabling one service.
- Reverse proxies no longer need to replicate CoachIQ's API/WebSocket/OAuth/docs
  route split.
- OIDC and MCP OAuth stay single-origin without proxy-specific static rules.
- SPA deep links work in production without frontend server configuration.

### Becomes harder

- FastAPI now has responsibility for serving production static assets.
- The fallback route must stay registered last; moving route registration around
  can change which paths are treated as SPA navigations.
- Authentication middleware must keep its SPA document-navigation exemption in
  sync with the fallback's derived reserved route-family set.
- Edge-layer rate limits need to be designed as optional proxy policy rather than
  as part of the canonical static/API split.

### Cannot do anymore

- Do not require production operators to hand-write a Caddy `file_server` plus
  backend prefix carve-out to use the built UI.
- Do not maintain a second hard-coded SPA reserved-prefix list in the proxy or
  backend fallback.
- Do not require authentication for public SPA document navigations while still
  requiring bearer tokens for backend-owned data routes.
- Do not rely on `StaticFiles(html=True)` alone for client-side route fallback.

## Alternatives considered

- **Keep Caddy serving the SPA**: rejected because it pushes backend route-table
  knowledge into every deployment and already diverged from the NixOS module.
- **Add a hard-coded backend denylist**: rejected because the review caught this
  exact drift. The fallback derives reserved route families from registered
  routes instead.
- **Always mount static files even when absent**: rejected because development and
  tests should keep working without a built frontend.

## See also

- `backend/main.py`
- `nix/module.nix`
- `config/Caddyfile.example`
- HOF-056 in the CoachIQ handoff channel.
