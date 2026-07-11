/**
 * React Query Client Configuration
 *
 * Configures TanStack Query with appropriate defaults for the RVC API.
 * Provides optimized settings for real-time data, error handling, and caching.
 */

import { QueryClient } from '@tanstack/react-query';
import { APIClientError } from '../api';
import { OFFLINE_ENTITY_CACHE_MAX_AGE_MS } from './offline-query-persistence';

/**
 * Default stale time for different types of data
 */
export const STALE_TIMES = {
  // Real-time data should be refreshed frequently
  ENTITIES: 1000 * 10, // 10 seconds
  CAN_STATISTICS: 1000 * 5, // 5 seconds

  // Semi-static data can be cached longer
  ENTITY_METADATA: 1000 * 60 * 5, // 5 minutes
  FEATURE_STATUS: 1000 * 60 * 2, // 2 minutes
  CAN_INTERFACES: 1000 * 60 * 10, // 10 minutes

  // Static configuration data
  HEALTH_STATUS: 1000 * 30, // 30 seconds
  UNKNOWN_PGNS: 1000 * 60 * 5, // 5 minutes
  UNMAPPED_ENTRIES: 1000 * 60 * 5, // 5 minutes
} as const;

/**
 * Creates a configured QueryClient for the RVC application
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Default stale time for all queries
        staleTime: STALE_TIMES.ENTITIES,

        // Keep restored last-known entity data available throughout offline use.
        gcTime: OFFLINE_ENTITY_CACHE_MAX_AGE_MS,

        // Retry configuration
        retry: (failureCount, error) => {
          // Don't retry 4xx errors (client errors)
          if (error instanceof APIClientError && error.status >= 400 && error.status < 500) {
            return false;
          }

          // Retry up to 3 times for other errors
          return failureCount < 3;
        },

        // Retry delay with exponential backoff
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),

        // Refetch on window focus for real-time data
        refetchOnWindowFocus: true,

        // Refetch on reconnect
        refetchOnReconnect: true,

        // Don't refetch on mount if data is fresh
        refetchOnMount: false,
      },

      mutations: {
        // Run immediately so offline controls fail instead of pausing until reconnect.
        networkMode: 'always',

        // Retry mutations once for network errors
        retry: (failureCount, error) => {
          if (error instanceof APIClientError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 1;
        },

        // Shorter retry delay for mutations
        retryDelay: 1000,
      },
    },
  });
}

/**
 * Query keys factory for consistent key management
 */
export const queryKeys = {
  // Entity-related queries
  entities: {
    all: ['entities'] as const,
    lists: () => [...queryKeys.entities.all, 'list'] as const,
    list: (filters?: Record<string, unknown>) => [...queryKeys.entities.lists(), filters] as const,
    details: () => [...queryKeys.entities.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.entities.details(), id] as const,
    metadata: (id: string) => [...queryKeys.entities.detail(id), 'metadata'] as const,
    history: (id: string, params?: Record<string, unknown>) =>
      [...queryKeys.entities.detail(id), 'history', params] as const,
  },

  // Convenience entity type queries
  lights: {
    all: ['entities', 'lights'] as const,
    list: () => [...queryKeys.lights.all, 'list'] as const,
  },

  locks: {
    all: ['entities', 'locks'] as const,
    list: () => [...queryKeys.locks.all, 'list'] as const,
  },

  tankSensors: {
    all: ['entities', 'tank-sensors'] as const,
    list: () => [...queryKeys.tankSensors.all, 'list'] as const,
  },

  temperatureSensors: {
    all: ['entities', 'temperature-sensors'] as const,
    list: () => [...queryKeys.temperatureSensors.all, 'list'] as const,
  },

  // CAN bus queries
  can: {
    all: ['can'] as const,
    interfaces: () => [...queryKeys.can.all, 'interfaces'] as const,
    statistics: () => [...queryKeys.can.all, 'statistics'] as const,
    messages: (limit?: number) => [...queryKeys.can.all, 'messages', limit] as const,
    metrics: () => [...queryKeys.can.all, 'metrics'] as const,
    unknownPgns: () => [...queryKeys.can.all, 'unknown-pgns'] as const,
    unmappedEntries: () => [...queryKeys.can.all, 'unmapped-entries'] as const,
  },

  // System configuration queries
  system: {
    all: ['system'] as const,
    health: () => [...queryKeys.system.all, 'health'] as const,
    features: () => [...queryKeys.system.all, 'features'] as const,
    queueStatus: () => [...queryKeys.system.all, 'queue-status'] as const,
  },

  // Authentication queries
  auth: {
    all: ['auth'] as const,
    user: () => [...queryKeys.auth.all, 'user'] as const,
    status: () => [...queryKeys.auth.all, 'status'] as const,
    credentials: () => [...queryKeys.auth.all, 'credentials'] as const,
  },
} as const;

/**
 * Type helper for query keys
 */
export type QueryKeys = typeof queryKeys;
