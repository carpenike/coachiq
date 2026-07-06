# Frontend Development Setup

## API and Realtime Configuration

### Development Mode

In development, the frontend uses different strategies for REST, realtime (SSE), and diagnostic WebSocket connections:

1. **API Requests**: Use the Vite proxy
   - All requests to `/api/*` are proxied to `http://localhost:8000`
   - No CORS issues because requests appear to come from the same origin
   - Configuration: `vite.config.ts` proxy settings

2. **Realtime Updates (SSE)**: Same origin as the API
   - The app's realtime channel is a Server-Sent Events stream at `/api/events`
     (`src/api/sse.ts`, `CoachEventStream`), consumed by `RealtimeProvider`
     (`src/contexts/realtime-provider.tsx`)
   - It uses `fetch` + `ReadableStream` (not native `EventSource`) so it can send
     the `Authorization` header from `localStorage`
   - Because it lives under `/api`, it goes through the same Vite proxy — no
     extra configuration is needed
   - Entity events land directly in the TanStack Query cache; pages consume
     realtime state through the queries they already use

3. **Diagnostic WebSocket Streams**: Direct connection to backend
   - WebSockets survive only as page-scoped diagnostic streams (log viewer,
     CAN scanner/recorder/analyzer/filter — see `src/hooks/useWebSocket.ts`)
   - They connect directly to `ws://localhost:8000` in development
   - Configured via `VITE_BACKEND_WS_URL` in `.env.development`
     (`VITE_WS_URL` is the legacy fallback; see `WS_BASE` in `src/api/client.ts`)

### Environment Variables

The `.env.development` file should contain:

```bash
# API requests (including the /api/events SSE stream) use the Vite proxy (leave empty)
VITE_API_URL=

# Diagnostic WebSocket streams connect directly to the backend
VITE_BACKEND_WS_URL=ws://localhost:8000
```

Optional:

```bash
# Verbose WebSocket debug logging in the browser console (dev only)
VITE_DEBUG_WS=true
```

### Production Mode

In production:

- The FastAPI backend serves the built SPA, REST API, SSE stream, and WebSocket
  endpoints from one origin (see [ADR-0015](../adr/ADR-0015-backend-serves-built-spa.md))
- Caddy is a pass-through reverse proxy in front of that single origin
- No environment variables needed (the frontend uses relative paths, and
  WebSocket URLs are auto-detected from the page origin)

## Troubleshooting

If you see CORS errors in development:

1. Check that the Vite dev server is running (`npm run dev`)
2. Verify the backend is running on `http://localhost:8000`
3. Ensure `.env.development` has the correct settings
4. Make sure you're not setting `VITE_API_URL` to a full URL
