import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import {
  defaultShouldDehydrateQuery,
  type DehydrateOptions,
  type Query,
  type QueryClient
} from "@tanstack/react-query";
import type { Persister } from "@tanstack/react-query-persist-client";

import type { IEntityCommandLifecycle } from "@/hooks/entity-command-lifecycle";

export const OFFLINE_ENTITY_CACHE_MAX_AGE_MS = 1000 * 60 * 60 * 24 * 7;
export const OFFLINE_ENTITY_CACHE_BUSTER = "coachiq-entity-cache-v1";
const OFFLINE_ENTITY_CACHE_KEY = "coachiq:last-known-entities";
const ENTITY_COMMAND_LIFECYCLE_KEY = ["entities", "command-lifecycle"] as const;

export function shouldPersistEntityQuery(query: Query): boolean {
  const [, scope] = query.queryKey;
  return (
    defaultShouldDehydrateQuery(query) &&
    query.queryKey[0] === "entities" &&
    (scope === "collections" || scope === "entity")
  );
}

export const entityCacheDehydrateOptions: DehydrateOptions = {
  shouldDehydrateMutation: () => false,
  shouldDehydrateQuery: shouldPersistEntityQuery
};

export function hasUnconfirmedEntityCommand(queryClient: QueryClient): boolean {
  return queryClient
    .getQueriesData<IEntityCommandLifecycle>({ queryKey: ENTITY_COMMAND_LIFECYCLE_KEY })
    .some(([, lifecycle]) =>
      lifecycle ? lifecycle.phase === "pending" || lifecycle.phase === "accepted" : false
    );
}

export function guardAuthoritativeEntityPersister(
  queryClient: QueryClient,
  persister: Persister
): Persister {
  return {
    persistClient: (persistedClient) => {
      if (hasUnconfirmedEntityCommand(queryClient)) return;
      return persister.persistClient(persistedClient);
    },
    restoreClient: persister.restoreClient,
    removeClient: persister.removeClient
  };
}

function getBrowserStorage(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

export function createEntityCachePersister(queryClient: QueryClient): Persister {
  const storagePersister = createAsyncStoragePersister({
    storage: getBrowserStorage(),
    key: OFFLINE_ENTITY_CACHE_KEY,
    throttleTime: 1000
  });
  return guardAuthoritativeEntityPersister(queryClient, storagePersister);
}
