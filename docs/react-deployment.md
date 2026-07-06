# React Deployment

This document describes the production deployment of the CoachIQ React frontend. The backend serves the built SPA directly; see [ADR-0015](adr/ADR-0015-backend-serves-built-spa.md) for the rationale.

For information on developing the frontend, see the [Frontend Development Guide](frontend/development-guide.md).

## Architecture

The architecture consists of:

1. **FastAPI Backend**: A single origin serving the REST API (`/api/*`), the SSE realtime stream (`/api/events`), diagnostic WebSocket endpoints (`/ws/*`), OAuth discovery, health probes, metrics, API docs, and the built React SPA
2. **React Frontend**: Built with Vite (`npm run build`) and served by the backend from `COACHIQ_STATIC_DIR`
3. **Caddy** (optional edge): A pass-through reverse proxy that forwards every request to the backend and owns TLS termination, proxy headers, compression, logging, and security headers — it does not maintain an API-vs-static route split

```
  +---------+                +-------+                 +---------------------+
  | Browser | <---HTTPS----> | Caddy | <---HTTP/WS---> | FastAPI             |
  +---------+                +-------+                 |  - API / SSE / WS   |
                          (pass-through)               |  - built React SPA  |
                                                       +---------------------+
```

## Backend SPA Serving

The backend resolves the SPA dist path from the `COACHIQ_STATIC_DIR` setting (`Settings.static_dir`, see `backend/main.py`):

- If the directory contains an `index.html`, the SPA fallback route is registered last, after all real routers, docs, health probes, and metrics
- Static files under the dist are served directly
- Unmatched browser navigations (`GET`/`HEAD` with `Accept: text/html`) outside backend-owned route families return `index.html`, so client-side routes (deep links) work without any proxy configuration
- Backend-owned route families (`/api`, `/ws`, `/oauth`, `/.well-known`, `/docs`, `/redoc`, `/openapi.json`, `/health`, `/healthz`, `/readyz`, `/startupz`, `/metrics`) are derived from the live route table at startup, not hard-coded
- If `index.html` is not present, the SPA route is not registered — development and tests keep using the Vite dev server

On NixOS, the module (`nix/module.nix`) defaults `COACHIQ_STATIC_DIR` to the built frontend derivation (`packages.frontend`), so enabling the service yields a self-contained UI. An explicit `services.coachiq.settings.COACHIQ_STATIC_DIR` override is still supported.

## Caddy Configuration

An example configuration lives at `config/Caddyfile.example`. Key points:

- `reverse_proxy localhost:8000` for the whole site — no `file_server`, no per-prefix carve-outs
- Health-checked upstream (`health_uri /health`)
- Sets `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Request-ID` headers
- Adds security headers (HSTS, `X-Frame-Options`, etc.), gzip compression, and JSON access logs
- Redirects HTTP to HTTPS

## Deployment Process

### NixOS (recommended)

Enable the CoachIQ service; the module builds the frontend and points `COACHIQ_STATIC_DIR` at it automatically.

### Manual

1. Build the React frontend:

   ```
   cd frontend
   npm install
   npm run build
   ```

2. Deploy `frontend/dist/` to the server and point the backend at it:

   ```
   COACHIQ_STATIC_DIR=/path/to/frontend/dist
   ```

3. Run the backend (it serves the SPA and all API traffic on one port):

   ```
   poetry run python run_server.py
   ```

4. (Optional) Put Caddy in front for TLS, using `config/Caddyfile.example` as a starting point, and check it is running:

   ```
   systemctl status caddy
   ```

## Development Workflow

During development the built SPA is not used; the Vite dev server serves the frontend:

1. Run the FastAPI backend:

   ```
   poetry run python run_server.py
   ```

2. Run the React dev server:

   ```
   cd frontend
   npm run dev
   ```

The Vite dev server (see `frontend/vite.config.ts`) proxies `/api/*` — including the `/api/events` SSE stream — to `http://localhost:8000`, and proxies `/ws/*` for the page-scoped diagnostic WebSocket streams (in practice the diagnostic WebSocket hooks connect directly to `ws://localhost:8000` via `VITE_BACKEND_WS_URL`; see [Frontend Development Setup](frontend/development-setup.md)).
