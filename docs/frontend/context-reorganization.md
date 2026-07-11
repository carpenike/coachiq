# React Folder Structure - Reorganization Summary

> **Historical note (2026-07):** This document describes a past migration. The
> deleted feature-WebSocket context was replaced by the SSE-based `RealtimeProvider`
> (`realtime-provider.tsx` / `realtime-context.ts`) in commit `3bebabb`. The
> current global contexts in `src/contexts/` are auth (`auth-context.tsx`),
> realtime (`realtime-provider.tsx` + `realtime-context.ts`), coach connection
> (`coach-connection.tsx` + `coach-connection-context.ts`), query
> (`query-provider.tsx`), and theme (`theme-context.ts`). The
> centralized-vs-co-located principles below still apply.

Based on 2024/2025 React best practices research, here's how your project contexts have been reorganized:

## ✅ Final Context Organization (at the time of this migration)

### Centralized Global Contexts (`src/contexts/`)

These contexts were used throughout the application:

- `theme-context.ts` - Theme state (dark/light mode)
- `realtime-context.ts` - Global SSE connection state
- `realtime-provider.tsx` - Global SSE event provider
- `query-provider.tsx` - React Query provider
- `index.ts` - Centralized exports for clean imports

### Component-Specific Contexts (Co-located)

These contexts remain with their specific components:

- `components/log-viewer/log-viewer-context.tsx` - ✅ **CORRECTLY PLACED**
- `components/ui/sidebar.tsx` - Sidebar-specific context
- `components/ui/form.tsx` - Form field contexts
- `components/ui/chart.tsx` - Chart-specific context

## 📋 Best Practices Applied

### 1. **Centralized vs Co-located Decision Matrix**

| Context Type                                 | Location              | Reasoning                            |
| -------------------------------------------- | --------------------- | ------------------------------------ |
| **Global App State** (Auth, Theme, Realtime) | `src/contexts/`       | Used throughout the application      |
| **Feature-Specific** (Log Viewer)            | Within feature folder | Only relevant to specific components |
| **UI Component** (Sidebar, Form)             | Within component      | Tightly coupled to component         |

### 2. **Import Pattern**

Feature-specific contexts remain co-located:

```tsx
import { LogViewerContext } from "./log-viewer-context";
```

### 3. **Folder Structure Comparison**

**Old Structure:**

```
src/
  contexts/
    theme-context.ts
  components/
    providers/           # Mixed global/local concerns
      query-provider.tsx
    log-viewer/
      log-viewer-context.tsx
```

**New Structure:**

```
src/
  contexts/              # ✅ All global contexts
    index.ts            # Clean export point
    theme-context.ts
    realtime-context.ts
    realtime-provider.tsx
    query-provider.tsx
  components/
    log-viewer/          # Feature-specific context co-located
      log-viewer-context.tsx
      LogViewer.tsx
      LogList.tsx
      ...
```

## 🎯 Key Benefits

1. **Clear Separation**: Global vs feature-specific contexts are clearly separated
2. **Easier Refactoring**: Feature contexts can be moved/removed with their components
3. **Better Code Splitting**: Feature-specific code bundles together naturally
4. **Reduced Cognitive Load**: Developers know where to find contexts based on scope
5. **Industry Standard**: Follows 2024/2025 React best practices

## 🔄 Migration Completed

- Moved `QueryProvider` to the centralized context location
- Replaced global feature WebSockets with the SSE-based realtime context
- Updated imports throughout the codebase
- Kept `log-viewer-context.tsx` co-located with its feature

Your log-viewer context was already correctly placed according to modern React patterns!
