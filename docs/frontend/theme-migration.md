# Theme System Migration

## Overview

This project has been migrated from `next-themes` to a custom React Context-based theme provider that's specifically designed for Vite + React + Tailwind CSS + shadcn/ui projects.

## Why the Migration?

`next-themes` was designed specifically for Next.js applications and relies on Next.js-specific features:

- Server-side rendering (SSR) hydration handling
- Next.js environment variables and optimizations
- App directory structure assumptions

Using it in a Vite + React environment caused several issues:

- Unnecessary Next.js dependencies
- Potential compatibility problems with future updates
- Framework-specific optimizations that don't apply to Vite

## New Architecture

### Core Files

- **`src/contexts/theme-context.ts`** - Theme context definition and types
- **`src/hooks/use-theme.tsx`** - Main ThemeProvider component
- **`src/hooks/use-theme.ts`** - useTheme hook for consuming theme state
- **`src/components/theme-provider.tsx`** - Re-export for easier imports

### Features

✅ **Theme Persistence** - Saves user preference to localStorage
✅ **System Theme Detection** - Automatically detects OS dark/light preference
✅ **Flash Prevention** - Prevents theme flash on page load via inline script
✅ **Transition Control** - Optional transition disabling during theme changes
✅ **Full Compatibility** - Works seamlessly with Tailwind CSS v4 and shadcn/ui

### Usage

```tsx
import { ThemeProvider } from "@/components/theme-provider";
import { useTheme } from "@/hooks/use-theme";

// App setup
<ThemeProvider
  attribute="class"
  defaultTheme="system"
  enableSystem
  disableTransitionOnChange
>
  <App />
</ThemeProvider>;

// In components
function MyComponent() {
  const { theme, setTheme, resolvedTheme } = useTheme();

  return (
    <button onClick={() => setTheme("dark")}>
      Current theme: {resolvedTheme}
    </button>
  );
}
```

### API

The `useTheme` hook provides:

- **`theme`**: Current theme setting (`"light"`, `"dark"`, or `"system"`)
- **`setTheme(theme)`**: Function to change the theme
- **`systemTheme`**: The system's current preference (`"light"` or `"dark"`)
- **`resolvedTheme`**: The actual theme being applied (resolves `"system"` to light/dark)

### Flash Prevention

The theme flash prevention script in `index.html` ensures the correct theme is applied before React hydrates, eliminating the brief flash of incorrect theme that can occur on page load.

## Migration Benefits

1. **Reduced Bundle Size** - Removed unnecessary Next.js dependencies
2. **Better Performance** - Custom implementation optimized for Vite
3. **Future-Proof** - No reliance on Next.js-specific features
4. **Maintainability** - Full control over theme logic and behavior
5. **Type Safety** - Fully typed with TypeScript
