# CoachIQ Frontend

Modern React frontend for the CoachIQ system built with Vite, TypeScript, and Shadcn/UI.

## Tech Stack

- **React 19** - Modern React with concurrent features
- **TypeScript 5.8** - Type-safe development
- **Vite 6** - Fast build tool and dev server
- **Shadcn/UI** - Modern, accessible component library (Radix UI primitives)
- **TailwindCSS v4** - Utility-first CSS framework
- **TanStack Query (React Query v5)** - Data fetching and state management
- **React Router v6** - Client-side routing
- **Server-Sent Events (SSE)** - Realtime entity updates over `/api/events` (see `src/api/sse.ts`); WebSockets remain only for page-scoped diagnostic streams
- **Leaflet / react-leaflet** - Location page breadcrumb map
- **Recharts** - Charts and visualizations
- **react-window** - Virtualized tables and lists
- **react-hook-form + zod** - Forms and validation

## Development

### Prerequisites

- Node.js 22 (the Nix dev shell provides `nodejs_22`)
- npm

### Setup

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Run tests
npm run test

# Run type checking
npm run typecheck

# Run linting
npm run lint
```

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run test` - Run tests with Vitest
- `npm run test:ui` - Run tests with UI
- `npm run test:coverage` - Run tests with coverage
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix ESLint errors
- `npm run typecheck` - Run TypeScript checks
- `npm run gen:api` - Regenerate API types from the backend OpenAPI schema
- `npm run check:api-types` - Verify generated API types are up to date

## Project Structure

```
src/
├── api/              # API clients (REST client, SSE stream, domain APIs, generated types)
├── assets/           # Static assets imported by components
├── components/       # Reusable components
│   ├── ui/          # Shadcn/UI components
│   └── ...
├── contexts/        # Global providers (auth, realtime, coach connection, query, theme)
├── hooks/           # Custom React hooks
├── lib/             # Utility libraries (incl. route registry in routes.tsx)
├── pages/           # Page components
├── test/            # Test setup and utilities
├── types/           # TypeScript type definitions
└── utils/           # Miscellaneous helpers
```

## Component Guidelines

### Using Shadcn/UI Components

Always prefer Shadcn/UI components over custom implementations:

```tsx
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Good
<Button variant="primary">Click me</Button>;

// Avoid custom button implementations
```

### Layout Consistency

All pages should use the `AppLayout` wrapper:

```tsx
import { AppLayout } from "@/components/app-layout";

export function MyPage() {
  return <AppLayout pageTitle="My Page">{/* Page content */}</AppLayout>;
}
```

### Accessibility

- Use semantic HTML elements
- Include proper ARIA attributes
- Test with keyboard navigation
- Ensure proper color contrast

## Testing

Tests are written with Vitest and React Testing Library:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

describe("MyComponent", () => {
  it("renders correctly", () => {
    render(<MyComponent />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});
```

## Performance

### Code Splitting

- Vendor libraries are automatically split into separate chunks
- Routes are lazy-loaded where appropriate
- Icon libraries use tree-shaking

### Build Optimization

- TypeScript compilation with strict mode
- ESLint with accessibility rules
- Vite optimizations for production builds

## Contributing

1. Follow the established patterns
2. Write tests for new components
3. Ensure accessibility compliance
4. Run linting and type checking before committing
