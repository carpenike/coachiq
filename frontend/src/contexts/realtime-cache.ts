/**
 * Cache-patching helpers for SSE entity events.
 *
 * Kept out of realtime-provider.tsx so that file only exports components
 * (react-refresh) and so the cache logic is unit-testable without React.
 */

import type { QueryClient } from '@tanstack/react-query'

import type { EntityCollectionSchema, EntitySchema } from '@/api/types/domains'
import { entitiesQueryKeys } from '@/hooks/useEntities'

export interface IEntityUpdatePayload {
  entity_id: string
  entity_data: Record<string, unknown>
}

/**
 * Apply an entity_update to the query cache without network traffic.
 *
 * Invalidating collections here is not an option: pages mount several
 * collection queries at once (Climate has six), and entity updates arrive
 * continuously from the CAN bus, so per-event invalidation fans out into
 * enough GET /api/entities traffic to trip the backend rate limit (429s).
 * Instead, patch the entity into every cached collection that contains it.
 * Entities never enter or leave a collection on update — that only happens
 * on entity_created, which still invalidates.
 */
export function applyEntityUpdate(client: QueryClient, payload: IEntityUpdatePayload): void {
  const entity = payload.entity_data as EntitySchema
  client.setQueryData(entitiesQueryKeys.entity(payload.entity_id), entity)
  client.setQueriesData<EntityCollectionSchema>(
    { queryKey: entitiesQueryKeys.collections() },
    (collection) => {
      if (!collection?.entities.some((e) => e.entity_id === payload.entity_id)) return undefined
      return {
        ...collection,
        entities: collection.entities.map((e) => (e.entity_id === payload.entity_id ? entity : e)),
      }
    }
  )
}
