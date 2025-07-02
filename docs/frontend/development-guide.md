# Frontend Development Guide

This guide explains how to work with the React frontend in the rvc2api project.

## Architecture Overview

The rvc2api project uses a modern web architecture:

- **Backend**: Python FastAPI server providing RESTful API and WebSocket endpoints
- **Frontend**: React-based Single Page Application (SPA) built with Vite
- **Deployment**: Caddy webserver serving static assets with API proxying

## Development Environment

### Using Nix (Recommended)

The project uses Nix flakes to provide a consistent development environment:

```bash
# Enter the development environment
cd /Users/ryan/src/rvc2api
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
# Ensure you have Node.js 20+ installed
node --version

# Install dependencies
cd /Users/ryan/src/rvc2api/frontend
npm install

# Start the development server
npm run dev
```

## Building the Frontend

### Development Build

During development, Vite provides fast rebuilds and HMR (Hot Module Replacement):

```bash
cd frontend
npm run dev
```

This starts a development server at http://localhost:5173 with:
- Hot Module Replacement for instant UI updates
- API proxying to the backend
- Source maps for debugging

### Production Build

For production builds, use either:

```bash
# Using Nix
nix run .#build-frontend

# Or manually
cd frontend
npm run build
```

The build output is placed in `frontend/dist/` and is ready to be served by Caddy.

## Project Structure

```
frontend/
├── public/           # Static assets copied as-is
├── src/
│   ├── components/   # Reusable React components
│   ├── pages/        # Page components
│   ├── hooks/        # Custom React hooks
│   ├── api.ts        # API client functions
│   └── main.tsx      # Application entry point
├── index.html        # HTML template
├── vite.config.ts    # Vite configuration
└── package.json      # Dependencies and scripts
```

## API Integration

The frontend communicates with the backend through:

### REST API

For data fetching and commands:

```typescript
// Example API call
const response = await fetch('/api/entities');
const entities = await response.json();
```

### WebSocket

For real-time updates:

```typescript
// Example WebSocket connection
const ws = new WebSocket(`ws://${window.location.host}/ws/entities`);

ws.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  // Handle real-time update
});
```

## Deployment

After building, the static files in `frontend/dist/` should be deployed to a webserver. The project uses Caddy for serving these files and proxying API requests to the backend.

See [React Deployment Guide](react-deployment.md) for detailed deployment instructions.
