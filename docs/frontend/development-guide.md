# Frontend Development Guide

This guide explains how to work with the React frontend in the CoachIQ project.

## Architecture Overview

The CoachIQ project uses a modern web architecture:

- **Backend**: Python FastAPI server providing a RESTful API, an SSE event stream (`/api/events`), and diagnostic WebSocket endpoints
- **Frontend**: React-based Single Page Application (SPA) built with Vite
- **Deployment**: The FastAPI backend serves the built SPA from `COACHIQ_STATIC_DIR`, with Caddy as a pass-through reverse proxy (see [ADR-0015](../adr/ADR-0015-backend-serves-built-spa.md))

## Development Environment

### Using Nix (Recommended)

The project uses Nix flakes to provide a consistent development environment:

```bash
# Enter the development environment (from the repository root)
nix develop

# The environment automatically sets up Node.js
# Navigate to frontend directory
cd frontend

# Start the development server
npm run dev
```

### Manual Setup (Without Nix)

If you prefer not to use Nix, you can set up the environment manually:

```bash
# Ensure you have Node.js 22 installed (the Nix dev shell provides nodejs_22)
node --version

# Install dependencies
cd frontend
npm install

# Start the development server
npm run dev
```

## Building the Frontend

### Development Build

During development, Vite provides fast rebuilds:

```bash
cd frontend
npm run dev
```

This starts a development server at http://localhost:5173 with:

- API proxying to the backend (`/api` and `/ws`, see `vite.config.ts`)
- Source maps for debugging

Note: HMR and React Fast Refresh are deliberately disabled in `vite.config.ts`; reload the page to pick up changes.

### Production Build

For production builds, use either:

```bash
# Using Nix
nix run .#build-frontend

# Or manually
cd frontend
npm run build
```

The build output is placed in `frontend/dist/` and is served by the FastAPI backend in production.

## Project Structure

```
frontend/
├── public/           # Static assets copied as-is
├── src/
│   ├── api/          # API clients (REST client, SSE stream, domain APIs, generated types)
│   ├── components/   # Reusable React components
│   ├── contexts/     # Global providers (auth, realtime, coach connection, query, theme)
│   ├── hooks/        # Custom React hooks
│   ├── lib/          # Utilities and the route registry (routes.tsx)
│   ├── pages/        # Page components
│   └── main.tsx      # Application entry point
├── index.html        # HTML template
├── vite.config.ts    # Vite configuration
└── package.json      # Dependencies and scripts
```

## API Integration

The frontend communicates with the backend through:

### REST API

For data fetching and commands, use the typed client in `src/api/` (wrapped in TanStack Query hooks under `src/hooks/`):

```typescript
// Example API call
const response = await fetch('/api/entities');
const entities = await response.json();
```

### Realtime Updates (SSE)

Realtime entity updates arrive over a single Server-Sent Events stream at `/api/events`. `RealtimeProvider` (`src/contexts/realtime-provider.tsx`) owns one `CoachEventStream` (`src/api/sse.ts`) for the whole app and writes entity events directly into the TanStack Query cache — pages consume realtime state through the queries they already use, and components only need the connection status:

```typescript
import { useRealtime } from '@/contexts/realtime-context';

function ConnectionBadge() {
  const { status, reconnect } = useRealtime(); // 'connected' | 'connecting' | 'down'
  // ...
}
```

Do not open your own `EventSource` or WebSocket for entity data. WebSockets remain only for page-scoped diagnostic streams (log viewer and CAN tooling) via the hooks in `src/hooks/useWebSocket.ts` (`useLogWebSocket`, `useCANScanWebSocket`, `useCANRecorderWebSocket`, `useCANAnalyzerWebSocket`, `useCANFilterWebSocket`).

## Deployment

After building, the static files in `frontend/dist/` are served by the FastAPI backend (configured via `COACHIQ_STATIC_DIR`), with Caddy acting as a pass-through reverse proxy for TLS and headers.

See [React Deployment Guide](../react-deployment.md) for detailed deployment instructions.
