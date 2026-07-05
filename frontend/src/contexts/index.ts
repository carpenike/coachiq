/**
 * Centralized exports for application contexts
 *
 * This file provides a single import point for all global contexts and providers.
 * Use this for cleaner imports throughout the application.
 */

// Theme Context
export { ThemeProvider } from '../hooks/use-theme.tsx';
export { useTheme } from '../hooks/use-theme.ts';

// Realtime (SSE) Context
export { useRealtime, RealtimeContext, type IRealtimeContext, type RealtimeHealth } from './realtime-context';
export { RealtimeProvider } from './realtime-provider';

// Query Provider
export { QueryProvider } from './query-provider';

// Authentication Context
export { AuthProvider, useAuth, useHasRole, useAuthMode } from './auth-context';
