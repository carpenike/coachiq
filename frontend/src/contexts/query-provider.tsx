/**
 * Query Provider Component
 *
 * Provides React Query context to the application.
 * Includes development tools integration and global configuration.
 */

import { createQueryClient } from '@/lib/query-client';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import type { ReactNode } from 'react';

import {
  createEntityCachePersister,
  entityCacheDehydrateOptions,
  OFFLINE_ENTITY_CACHE_BUSTER,
  OFFLINE_ENTITY_CACHE_MAX_AGE_MS
} from '@/lib/offline-query-persistence';

interface QueryProviderProps {
  children: ReactNode;
}

// Create a singleton query client instance
const queryClient = createQueryClient();
const entityCachePersister = createEntityCachePersister(queryClient);

/**
 * Provides React Query context to the application
 */
export function QueryProvider({ children }: QueryProviderProps) {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: entityCachePersister,
        maxAge: OFFLINE_ENTITY_CACHE_MAX_AGE_MS,
        buster: OFFLINE_ENTITY_CACHE_BUSTER,
        dehydrateOptions: entityCacheDehydrateOptions
      }}
    >
      {children}
      {/* Only show devtools in development */}
      {import.meta.env.DEV && (
        <ReactQueryDevtools
          initialIsOpen={false}
          buttonPosition="bottom-right"
        />
      )}
    </PersistQueryClientProvider>
  );
}
