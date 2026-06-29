---
applyTo: "**/*.{ts,tsx,js,jsx}"
---

# TypeScript/JavaScript Code Style Guidelines

> **Note**: This file covers TypeScript/JavaScript coding standards and best practices.

## Linting & Code Quality

- **TypeScript**: Strict mode enabled with project references
- **ESLint**: Using the frontend flat config at `frontend/eslint.config.js`
- **Commands**:
  - Lint: `cd frontend && npm run lint`
  - Fix: `cd frontend && npm run lint:fix`
  - Style fixes: `cd frontend && npm run fix:style`
  - Interface fixes: `cd frontend && npm run fix:interfaces`
  - Type check: `cd frontend && npm run typecheck`
- **Line Length**: 100 characters
- **Formatting Rules**:
  - No trailing commas (comma-dangle: ["error", "never"])
  - Double quotes (quotes: ["error", "double"])
  - Always use semicolons (semi: ["error", "always"])
- **Line Endings**: LF (Unix style)
- **Indentation**: 2 spaces
- **TypeScript Interface Requirement**: Must have at least one import statement to avoid parsing errors

## Code Structure

- Use functional React components with hooks
- Component files should be named with PascalCase
- Utility/hook files should be named with camelCase
- One component per file (except for small related components)
- Extract complex logic to custom hooks
- Keep components focused on a single responsibility

## Import Structure

Organize imports in sections with a blank line between each:

```typescript
// React and hooks
import React, { useState, useEffect } from "react";

// Third-party libraries
import classNames from "classnames";

// Local components and hooks
import { Button } from "../components/Button";
import { useFetchData } from "../hooks/useFetchData";

// Types and interfaces
import type { Entity } from "../types/Entity";
```

## TypeScript Best Practices

- Use explicit types instead of `any` whenever possible
- Define interfaces or types for component props
- Use function type expressions for callbacks
- Prefer interfaces for public APIs and types for complex unions/intersections
- Use type guards to narrow types when needed
- Use generics to create reusable components

## React Best Practices

- Use React functional components and hooks
- Use composition over inheritance
- Implement proper cleanup in useEffect hooks
- Memoize expensive computations and callbacks when needed
- Use context for truly global state
- Extract reusable logic into custom hooks
- Use proper component composition to avoid prop drilling

## MCP Tools for TypeScript/React Code Style

### @context7 Use Cases - ALWAYS USE FIRST

Always use `@context7` first for any TypeScript or React questions to get current, accurate guidance:

- **TypeScript**: `@context7 TypeScript React prop types`, `@context7 React event types`
- **React Patterns**: `@context7 React custom hook pattern`, `@context7 React context with TypeScript`
- **Component Design**: `@context7 React component composition`, `@context7 React form validation`

### @perplexity Use Cases - FOR GENERAL CONCEPTS ONLY

Only use `@perplexity` for general concepts not related to specific library APIs:

- Research patterns: `@perplexity frontend architecture patterns`
- Investigate general concepts: `@perplexity React performance optimization`

> **Important**: For any React, TypeScript, or frontend library questions, always use `@context7` first to avoid outdated or hallucinated APIs.
