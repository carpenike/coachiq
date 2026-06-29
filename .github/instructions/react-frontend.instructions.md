---
applyTo: "**/frontend/**"
---

# React Frontend Architecture

## Technology Stack

- React 19.1.0 with TypeScript strict mode
- Vite for development and building
- TailwindCSS with shadcn/ui component library
- React Query (@tanstack/react-query) for server state management
- WebSocket for real-time data synchronization
- React Router DOM for client-side routing

## Linting & Code Quality

- TypeScript: Strict mode enabled with project references (tsconfig.json → tsconfig.app.json)
- ESLint: Using flat config system with both eslint.config.js and eslint.config.mjs
- Plugins: react-hooks, react-refresh, jsdoc
- Type Checking: Run with `npm run typecheck` (required for all PRs)
- Format: Follow ESLint configuration rules
- Formatting Rules:
  - No trailing commas (comma-dangle: ["error", "never"])
  - Double quotes (quotes: ["error", "double"])
  - Always use semicolons (semi: ["error", "always"])
- Line Endings: LF (Unix style)
- Indentation: 2 spaces
- TypeScript Interfaces: Must have at least one import statement to avoid parsing errors
- Verification: All code must pass linting, type checking, and formatting checks
- Fix Scripts: Use `npm run fix:style` to fix common ESLint issues

## Directory Structure

- `frontend/src/components/`: Reusable UI components
- `frontend/src/pages/`: Top-level page components
- `frontend/src/hooks/`: Custom React hooks
- `frontend/src/utils/`: Utility functions and helpers
- `frontend/src/api.ts`: Backend API interaction

## Features

- Modern React-based UI with real-time data via WebSocket connection
- Dashboard view with system status
- Device management interface
- Light control interface
- CAN message analyzer
- Network topology visualization

## Design Principles

- Modern UI with curved lines and contemporary themes
- Responsive design that works on all device sizes
- Consistent color scheme and typography
- Accessible interface following WAI-ARIA guidelines

## MCP Tools for React Development

### @context7 Use Cases - ALWAYS USE FIRST

Always use `@context7` first for any React or library-related questions to get current, accurate API information:

- **React Hooks**: `@context7 React useState with TypeScript generics`, `@context7 useReducer complex state`
- **Component Patterns**: `@context7 React functional component with TypeScript props`, `@context7 children prop types`
- **React Events**: `@context7 React form events TypeScript`, `@context7 React synthetic event types`
- **React Testing**: `@context7 React Testing Library component with state`

- **Project-specific**:
  - Get WebSocket message formats: `@context7 WebSocket message format entities`
  - Find API endpoint schemas: `@context7 /api/v2/entities schema`
  - Review component implementations: `@context7 Lights.tsx component`
  - Find backend state models: `@context7 entity state model`

### @perplexity Use Cases - FOR GENERAL CONCEPTS ONLY

Only use `@perplexity` for general concepts not related to specific library APIs:

- Research general architecture patterns: `@perplexity frontend state management patterns`
- Investigate general concepts: `@perplexity WebSocket security best practices`
- Explore UI design principles: `@perplexity dashboard UI/UX principles`

> **Important**: For any React, TypeScript, Vite, or Tailwind questions, always use `@context7` first to avoid outdated or hallucinated APIs.

## API Integration

### REST API Example

```typescript
// Fetch entities from the API
const fetchEntities = async () => {
  try {
    const response = await fetch("/api/v2/entities");
    if (!response.ok) throw new Error("Network response was not ok");
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error fetching entities:", error);
    throw error;
  }
};
```

### WebSocket Example

```typescript
// Connect to entities WebSocket
const connectWebSocket = () => {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/entities`;

  const socket = new WebSocket(wsUrl);

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // Handle incoming data
  };

  socket.onclose = () => {
    // Implement reconnection logic
    setTimeout(() => connectWebSocket(), 3000);
  };

  return socket;
};
```

## Development Process

1. Run backend: `poetry run python run_server.py`
2. Run frontend: `cd frontend && npm run dev`
3. Access development server at http://localhost:5173

## Building for Production

```bash
cd frontend
npm run build
# Output in frontend/dist/
```

## Deployment

The built files from `frontend/dist/` should be deployed to `/var/lib/coachiq-web-ui/dist/`
on the target system where Caddy is configured to serve them.
