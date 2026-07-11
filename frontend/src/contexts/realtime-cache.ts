/**
 * Cache-patching helpers for SSE entity events.
 *
 * Kept out of realtime-provider.tsx so that file only exports components
 * (react-refresh) and so the cache logic is unit-testable without React.
 */

import type { QueryClient } from '@tanstack/react-query'

import type { EntityCollectionSchema, EntitySchema, LegacyEntity } from '@/api/types/domains'
import { reconcileEntityCommandLifecycle } from '@/hooks/entity-command-lifecycle'
import { entitiesQueryKeys } from '@/hooks/useEntities'

export interface IEntityUpdatePayload {
  entity_id: string
  entity_data: Record<string, unknown>
}

/**
 * Convert an SSE entity payload into the REST collection shape the UI reads.
 *
 * The SSE stream sends entities in the backend's internal ("legacy") shape:
 * the live field values live under `raw`, `state` is a device-status STRING
 * (e.g. "external_control"), and the timestamp is a unix float under
 * `timestamp`. The REST collection (EntitySchemaV2) instead exposes those field
 * values AS the `state` object and the time as an ISO `last_updated` — and every
 * page reads `entity.state.<field>`. Casting the raw SSE payload straight to
 * EntitySchema (the previous behaviour) made `state` the status string, so
 * `state.<field>` was undefined: values rendered on first load from REST, then
 * blanked on the first live update. Merge onto the previous entity so
 * REST-provided fields (name, protocol, available, area) survive when the SSE
 * payload omits them.
 */
type SseEntity = Partial<LegacyEntity> & {
  protocol?: string
  last_updated?: string | null
  last_seen_at?: string | null
  data_received_at?: string | null
  state_changed_at?: string | null
}

/** Build an EntitySchema from an SSE payload alone (no prior REST entity). */
function bootstrapEntity(legacy: SseEntity): EntitySchema {
  const id = String(legacy.entity_id ?? '')
  return {
    entity_id: id,
    name: legacy.friendly_name ?? id,
    device_type: legacy.device_type ?? 'unknown',
    protocol: legacy.protocol ?? 'unknown',
    area: legacy.suggested_area ?? null,
    state: {},
    last_updated: '',
    available: true,
  }
}

function toEntitySchema(data: Record<string, unknown>, prev?: EntitySchema): EntitySchema {
  const legacy = data as SseEntity
  const base = prev ?? bootstrapEntity(legacy)
  const lastUpdated =
    legacy.last_updated ??
    (typeof legacy.timestamp === 'number'
      ? new Date(legacy.timestamp * 1000).toISOString()
      : (base.last_updated ?? null))
  const lastSeenAt = legacy.last_seen_at ?? lastUpdated
  const dataReceivedAt = legacy.data_received_at ?? lastUpdated

  // Map the SSE `raw` field values onto `state` — the shape every page reads.
  return {
    ...base,
    state: legacy.raw ?? legacy.value ?? base.state ?? {},
    last_updated: lastUpdated,
    last_seen_at: lastSeenAt,
    data_received_at: dataReceivedAt,
    state_changed_at: legacy.state_changed_at ?? base.state_changed_at ?? null,
    available: true,
  }
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
  const previousEntity = client.getQueryData<EntitySchema>(
    entitiesQueryKeys.entity(payload.entity_id)
  )
  const updatedEntity = toEntitySchema(payload.entity_data, previousEntity)
  reconcileEntityCommandLifecycle(client, updatedEntity, 'sse')
  client.setQueryData<EntitySchema>(entitiesQueryKeys.entity(payload.entity_id), updatedEntity)
  client.setQueriesData<EntityCollectionSchema>(
    { queryKey: entitiesQueryKeys.collections() },
    (collection) => {
      if (!collection?.entities.some((e) => e.entity_id === payload.entity_id)) return undefined
      return {
        ...collection,
        entities: collection.entities.map((e) =>
          e.entity_id === payload.entity_id ? toEntitySchema(payload.entity_data, e) : e
        ),
      }
    }
  )
}
