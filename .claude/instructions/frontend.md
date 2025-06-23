# React Frontend Instructions

## MCP Server Usage for Frontend Development

When developing frontend features, leverage MCP servers effectively:

1. **@playwright** - Primary tool for UI testing and verification during development
2. **@context7** - React patterns, hooks, TypeScript, and component libraries
3. **@zen analyze** - Component architecture and performance analysis
4. **@perplexity** - UI/UX best practices and accessibility standards

### Frontend Development MCP Workflow

```
# Building new components:
1. @context7 React component patterns with TypeScript
2. @context7 shadcn/ui component usage examples
3. @playwright browser_snapshot - Verify component rendering
4. @playwright browser_click/type - Test interactions

# Debugging UI issues:
1. @playwright browser_console_messages - Check for errors
2. @playwright browser_snapshot - See current DOM state
3. @context7 React debugging patterns
4. @zen analyze frontend/src/components - Review architecture
```

### Playwright Development Pattern

```bash
# Start dev server first
cd frontend && npm run dev

# Use Playwright to verify your work
1. browser_navigate(url="http://localhost:5173")
2. browser_snapshot() - Understand page structure
3. browser_click(element="Button", ref="button")
4. browser_type(element="Search", ref="input", text="test")
5. browser_take_screenshot() - Visual verification
```

## Technology Stack

- **React 19.1.0** with TypeScript strict mode
- **Vite** for development and production builds
- **TailwindCSS** for styling with shadcn/ui component library
- **React Query (@tanstack/react-query)** for server state management
- **React Router DOM** for client-side routing
- **WebSocket** for real-time data synchronization
- **Domain API v2** for enhanced API integration

## 🎯 IMPORTANT: Use Domain API v2 for New Development

**Domain API v2** provides enhanced frontend integration with:
- **Optimistic Updates**: Immediate UI feedback with automatic rollback on errors
- **Bulk Operations**: Efficient multi-entity operations with selection management
- **Type Safety**: Auto-generated TypeScript types from backend schemas
- **Better Performance**: Built-in caching and intelligent data fetching

### Domain API v2 Frontend Structure

```
frontend/src/
├── api/
│   ├── domains/             # Domain-specific API clients
│   │   ├── entities.ts     # Entity domain API client
│   │   └── index.ts        # Domain registration and migration helpers
│   ├── types/              # TypeScript types from backend schemas
│   │   └── domains.ts      # Domain API types
│   └── client.ts           # Base API client
├── hooks/
│   ├── domains/            # Domain-specific React hooks
│   │   ├── useEntitiesV2.ts # Entity management hooks
│   │   └── __tests__/      # Domain hook tests
│   └── useEntities.ts      # Legacy hooks (maintain only)
├── components/
│   ├── bulk-operations/    # Enhanced bulk operation components
│   │   ├── BulkOperationsModalV2.tsx
│   │   ├── EntitySelectorV2.tsx
│   │   └── index.ts
│   └── ui/                 # shadcn/ui base components
└── pages/                  # Route-level page components
```

## Project Structure

### Design System
- **Base Components**: shadcn/ui components in `components/ui/`
- **Theme System**: Dark/light mode with system preference detection
- **Responsive Design**: Mobile-first approach with Tailwind breakpoints
- **Accessibility**: WAI-ARIA compliant components

## Code Quality Requirements

### TypeScript Configuration
```bash
# Required before all commits
npm run typecheck
npm run lint
npm run lint:fix  # Auto-fix ESLint issues
```

### Standards
- **TypeScript**: Strict mode with project references
- **ESLint**: Flat config with React, TypeScript, and JSDoc plugins
- **Formatting Rules**:
  - No trailing commas: `comma-dangle: ["error", "never"]`
  - Double quotes: `quotes: ["error", "double"]`
  - Semicolons required: `semi: ["error", "always"]`
- **Import Aliases**: Use `@/` for `src/` imports

### Interface Requirements
```typescript
// All standalone interface files must have imports
import type { ReactNode } from "react";

export interface ComponentProps {
  children: ReactNode;
  className?: string;
}
```

## State Management Patterns

### ✅ Domain API v2 Patterns (PREFERRED)

#### Domain API Client
```typescript
// frontend/src/api/domains/entities.ts
import { apiGet, apiPost } from '../client';
import type { EntityCollectionSchema, ControlCommandSchema } from '../types/domains';

export async function fetchEntitiesV2(params?: {
  device_type?: string;
  area?: string;
  page?: number;
  page_size?: number;
}): Promise<EntityCollectionSchema> {
  const queryString = params ? buildQueryString(params) : '';
  const url = queryString ? `/api/v2/entities?${queryString}` : '/api/v2/entities';
  return apiGet<EntityCollectionSchema>(url);
}

export async function controlEntityV2(
  entityId: string,
  command: ControlCommandSchema
): Promise<OperationResultSchema> {
  return apiPost<OperationResultSchema>(`/api/v2/entities/${entityId}/control`, command);
}

export async function bulkControlEntitiesV2(
  request: BulkControlRequestSchema
): Promise<BulkOperationResultSchema> {
  return apiPost<BulkOperationResultSchema>('/api/v2/entities/bulk-control', request);
}
```

#### Domain React Hooks with Optimistic Updates
```typescript
// frontend/src/hooks/domains/useEntitiesV2.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchEntitiesV2, controlEntityV2, bulkControlEntitiesV2 } from '../../api/domains/entities';

export const entitiesV2QueryKeys = {
  all: ['entities-v2'] as const,
  collections: () => [...entitiesV2QueryKeys.all, 'collections'] as const,
  collection: (params: any) => [...entitiesV2QueryKeys.collections(), params] as const,
};

// Enhanced entity listing with filtering
export function useEntitiesV2(params?: EntityQueryParams) {
  return useQuery({
    queryKey: entitiesV2QueryKeys.collection(params || {}),
    queryFn: () => fetchEntitiesV2(params),
    staleTime: 30000,
  });
}

// Entity control with optimistic updates
export function useControlEntityV2() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ entityId, command }: { entityId: string; command: ControlCommandSchema }) =>
      controlEntityV2(entityId, command),
    onMutate: async ({ entityId, command }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: entitiesV2QueryKeys.all });

      // Snapshot previous value
      const previousCollections = queryClient.getQueriesData({ queryKey: entitiesV2QueryKeys.collections() });

      // Optimistically update entity state
      queryClient.setQueriesData(
        { queryKey: entitiesV2QueryKeys.collections() },
        (old: EntityCollectionSchema | undefined) => {
          if (!old) return old;

          return {
            ...old,
            entities: old.entities.map(entity =>
              entity.entity_id === entityId
                ? { ...entity, state: { ...entity.state, ...getOptimisticState(command) } }
                : entity
            ),
          };
        }
      );

      return { previousCollections };
    },
    onError: (err, variables, context) => {
      // Rollback optimistic update on error
      if (context?.previousCollections) {
        context.previousCollections.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      // Always refetch after error or success
      queryClient.invalidateQueries({ queryKey: entitiesV2QueryKeys.all });
    },
  });
}

// Bulk operations with selection management
export function useEntitySelection() {
  const [selectedEntityIds, setSelectedEntityIds] = useState<string[]>([]);
  const queryClient = useQueryClient();

  const bulkControlMutation = useMutation({
    mutationFn: bulkControlEntitiesV2,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: entitiesV2QueryKeys.all });
      setSelectedEntityIds([]); // Clear selection after successful operation
    },
  });

  const executeBulkOperation = async (command: ControlCommandSchema, options?: {
    ignoreErrors?: boolean;
    timeout?: number;
  }) => {
    if (selectedEntityIds.length === 0) {
      throw new Error('No entities selected for bulk operation');
    }

    return bulkControlMutation.mutateAsync({
      entity_ids: selectedEntityIds,
      command,
      ignore_errors: options?.ignoreErrors ?? true,
      timeout_seconds: options?.timeout,
    });
  };

  return {
    selectedEntityIds,
    selectedCount: selectedEntityIds.length,
    selectEntity: (entityId: string) => {
      setSelectedEntityIds(prev => [...prev, entityId]);
    },
    deselectEntity: (entityId: string) => {
      setSelectedEntityIds(prev => prev.filter(id => id !== entityId));
    },
    toggleEntitySelection: (entityId: string) => {
      setSelectedEntityIds(prev =>
        prev.includes(entityId)
          ? prev.filter(id => id !== entityId)
          : [...prev, entityId]
      );
    },
    selectAll: (entityIds: string[]) => {
      setSelectedEntityIds(entityIds);
    },
    deselectAll: () => {
      setSelectedEntityIds([]);
    },
    executeBulkOperation,
    bulkOperationState: {
      isLoading: bulkControlMutation.isPending,
      error: bulkControlMutation.error,
      data: bulkControlMutation.data,
    },
  };
}
```

### ❌ Legacy API Patterns (Maintain Only)

#### Legacy React Query Pattern
```typescript
// frontend/src/hooks/useEntities.ts (Legacy - maintain only)
export function useEntities() {
  return useQuery({
    queryKey: ["entities"],
    queryFn: () => apiClient.getEntities(),
    staleTime: 30000
  });
}

// Legacy mutation pattern
export function useControlEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: apiClient.controlEntity,
    onMutate: async (variables) => {
      // Basic optimistic update logic
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["entities"] });
    }
  });
}
```

### WebSocket Integration
```typescript
import { useContext, useEffect } from "react";
import { WebSocketContext } from "@/contexts/websocket-context";

export function useWebSocketData() {
  const { socket, isConnected } = useContext(WebSocketContext);

  useEffect(() => {
    if (!socket) return;

    const handleMessage = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      // Handle real-time updates
    };

    socket.addEventListener("message", handleMessage);
    return () => socket.removeEventListener("message", handleMessage);
  }, [socket]);

  return { isConnected };
}
```

### React Context for UI State
```typescript
import { createContext, useContext, ReactNode } from "react";

interface ThemeContextType {
  theme: "light" | "dark" | "system";
  setTheme: (theme: "light" | "dark" | "system") => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
```

## API Integration Patterns

### REST API Client
```typescript
// Centralized API client
class ApiClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_URL || "";
  }

  async getEntities(): Promise<Entity[]> {
    const response = await fetch(`${this.baseUrl}/api/entities`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async controlEntity(id: string, command: EntityCommand): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/entities/${id}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command)
    });

    if (!response.ok) {
      throw new Error(`Control failed: ${response.status}`);
    }
  }
}

export const apiClient = new ApiClient();
```

### WebSocket Connection
```typescript
export function createWebSocketConnection() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/entities`;

  const socket = new WebSocket(wsUrl);

  socket.onopen = () => console.log("WebSocket connected");
  socket.onclose = () => {
    console.log("WebSocket disconnected, reconnecting...");
    setTimeout(() => createWebSocketConnection(), 3000);
  };
  socket.onerror = (error) => console.error("WebSocket error:", error);

  return socket;
}
```

## Component Patterns

### shadcn/ui Component Usage
```typescript
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

export function EntityCard({ entity }: { entity: Entity }) {
  const controlMutation = useControlEntity();

  const handleToggle = () => {
    controlMutation.mutate({
      entityId: entity.id,
      command: { command: "toggle" }
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{entity.name}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center space-x-2">
          <Switch
            checked={entity.state === "on"}
            onCheckedChange={handleToggle}
            disabled={controlMutation.isPending}
          />
          <span>{entity.state}</span>
        </div>
      </CardContent>
    </Card>
  );
}
```

### Performance Optimization
```typescript
import { memo, useMemo } from "react";
import { VirtualizedTable } from "@/components/virtualized-table";

// Memoize expensive components
export const EntityList = memo(function EntityList({ entities }: Props) {
  const sortedEntities = useMemo(
    () => entities.sort((a, b) => a.name.localeCompare(b.name)),
    [entities]
  );

  return <VirtualizedTable data={sortedEntities} />;
});
```

## Testing Patterns

### Vitest Configuration
```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Test wrapper with providers
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } }
  });

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

describe("EntityCard", () => {
  it("toggles entity state on switch click", async () => {
    const mockEntity = { id: "1", name: "Light", state: "off" };

    render(<EntityCard entity={mockEntity} />, { wrapper: TestWrapper });

    const toggle = screen.getByRole("switch");
    fireEvent.click(toggle);

    expect(mockControlEntity).toHaveBeenCalledWith({
      entityId: "1",
      command: { command: "toggle" }
    });
  });
});
```

## Build and Development

### Development Server
```bash
cd frontend
npm run dev          # Start development server on :5173
npm run build        # Production build to dist/
npm run preview      # Preview production build
```

### Environment Configuration
```typescript
// Use environment variables with Vite
const config = {
  apiUrl: import.meta.env.VITE_API_URL || "http://localhost:8000",
  wsUrl: import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws",
  isDevelopment: import.meta.env.DEV
};
```

## MCP Tools for Frontend Development

### Always Use @context7 First
- **React Patterns**: `@context7 React useState with TypeScript generics`
- **Component Design**: `@context7 React functional component TypeScript props`
- **Hooks**: `@context7 React useEffect cleanup pattern`
- **State Management**: `@context7 React Query optimistic updates`

### Project Context
- **Find Components**: `@context7 existing component patterns`
- **API Integration**: `@context7 WebSocket message handling`
- **Styling**: `@context7 Tailwind responsive design patterns`

## Critical Requirements

- **Unified API**: Use `/api/entities` endpoints only, never separate patterns like `/api/lights`
- **Entity Commands**: Use standardized command structure for all entity control
- **Type Safety**: All API responses must have proper TypeScript types
- **Real-time Updates**: Implement optimistic updates with WebSocket synchronization
- **Accessibility**: Ensure all interactive elements are keyboard accessible
- **Performance**: Use virtualization for large data sets and proper memoization
