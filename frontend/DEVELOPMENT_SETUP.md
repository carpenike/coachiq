# Frontend Development Setup

## API and WebSocket Configuration

### Development Mode

In development, the frontend uses different strategies for API and WebSocket connections:

1. **API Requests**: Use the Vite proxy
   - All requests to `/api/*` are proxied to `http://localhost:8000`
   - No CORS issues because requests appear to come from the same origin
   - Configuration: `vite.config.ts` proxy settings

2. **WebSocket Connections**: Direct connection to backend
   - WebSockets connect directly to `ws://localhost:8000`
   - Configured via `VITE_BACKEND_WS_URL` in `.env.development`
   - Direct connection is more reliable than proxying WebSockets

### Environment Variables

The `.env.development` file should contain:
```bash
# API requests use Vite proxy (leave empty)
VITE_API_URL=

# WebSocket connects directly to backend
VITE_BACKEND_WS_URL=ws://localhost:8000

# Auto-connect WebSockets in development
VITE_AUTO_CONNECT_WS=true
```

### Production Mode

In production:
- Both API and WebSocket requests go through the reverse proxy (Caddy)
- CORS is handled by Caddy, not the application
- No environment variables needed (uses relative paths)

## Troubleshooting

If you see CORS errors in development:
1. Check that the Vite dev server is running (`npm run dev`)
2. Verify the backend is running on `http://localhost:8000`
3. Ensure `.env.development` has the correct settings
4. Make sure you're not setting `VITE_API_URL` to a full URL