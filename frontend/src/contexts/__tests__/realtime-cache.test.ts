/**
 * Tests for applyEntityUpdate — SSE entity updates must patch the query
 * cache in place instead of invalidating collections, so a chatty CAN bus
 * doesn't fan out into refetch storms that trip the backend rate limit.
 *
 * The SSE stream sends the backend's internal ("legacy") entity shape: live
 * field values under `raw`, `state` as a device-status STRING, and a unix-float
 * `timestamp`. The UI reads the REST shape (EntitySchemaV2), where those field
 * values ARE `state` and the time is an ISO `last_updated`. These tests pin the
 * conversion: without it, a live update overwrote `state` with the status
 * string, so values rendered on first load then blanked on the first update.
 */

import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it } from 'vitest'

import type { EntityCollectionSchema, EntitySchema } from '@/api/types/domains'
import { applyEntityUpdate } from '../realtime-cache'
import { entitiesQueryKeys } from '@/hooks/useEntities'

/** A REST-shaped entity (EntitySchemaV2) as it lands from GET /api/v1/entities. */
function makeRestEntity(id: string, overrides: Partial<EntitySchema> = {}): EntitySchema {
  return {
    entity_id: id,
    name: id,
    device_type: 'climate',
    protocol: 'rvc',
    state: {},
    area: null,
    last_updated: '2026-07-08T00:00:00Z',
    available: true,
    ...overrides,
  } as EntitySchema
}

/**
 * An SSE `entity_update` payload's `entity_data`, in the backend's actual
 * on-the-wire (legacy) shape: field values live under `raw`/`value`, `state` is
 * a device-status string, and `timestamp` is unix-float seconds.
 */
function makeSsePayload(
  id: string,
  raw: Record<string, unknown>,
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    entity_id: id,
    friendly_name: `Friendly ${id}`,
    device_type: 'climate',
    protocol: 'rvc',
    suggested_area: 'main',
    state: 'external_control',
    raw,
    value: raw,
    timestamp: 1783536790,
    capabilities: [],
    groups: ['climate'],
    ...overrides,
  }
}

function makeCollection(entities: EntitySchema[]): EntityCollectionSchema {
  return {
    entities,
    total_count: entities.length,
    page: 1,
    page_size: 100,
    has_next: false,
  } as EntityCollectionSchema
}

describe('applyEntityUpdate', () => {
  let client: QueryClient

  beforeEach(() => {
    client = new QueryClient()
  })

  it('exposes SSE raw field values as `state` (the shape the UI reads)', () => {
    applyEntityUpdate(client, {
      entity_id: 'thermostat_1',
      entity_data: makeSsePayload('thermostat_1', { temp: 72 }),
    })

    const cached = client.getQueryData<EntitySchema>(entitiesQueryKeys.entity('thermostat_1'))
    // The regression: state must be the field dict, NOT the "external_control" string.
    expect(cached?.state).toEqual({ temp: 72 })
    expect(cached?.last_updated).toBe(new Date(1783536790 * 1000).toISOString())
    expect(cached?.available).toBe(true)
  })

  it('patches raw values into cached collections while preserving REST fields', () => {
    const stale = makeRestEntity('thermostat_1', { name: 'Bedroom', state: { temp: 68 } })
    const other = makeRestEntity('thermostat_2')
    const keyA = entitiesQueryKeys.collection({ device_type: 'climate' })
    const keyB = entitiesQueryKeys.collection({ device_type: 'climate', page_size: 100 })
    client.setQueryData(keyA, makeCollection([stale, other]))
    client.setQueryData(keyB, makeCollection([stale]))

    applyEntityUpdate(client, {
      entity_id: 'thermostat_1',
      entity_data: makeSsePayload('thermostat_1', { temp: 72 }),
    })

    const collectionA = client.getQueryData<EntityCollectionSchema>(keyA)
    const patchedA = collectionA?.entities.find((e) => e.entity_id === 'thermostat_1')
    expect(patchedA?.state).toEqual({ temp: 72 }) // live value shows, not blanked
    expect(patchedA?.name).toBe('Bedroom') // REST-provided field survives the merge
    expect(collectionA?.entities.find((e) => e.entity_id === 'thermostat_2')).toBe(other)

    const collectionB = client.getQueryData<EntityCollectionSchema>(keyB)
    expect(collectionB?.entities[0]?.state).toEqual({ temp: 72 })
  })

  it('leaves collections that do not contain the entity untouched', () => {
    const tanks = makeCollection([makeRestEntity('fresh_tank', { device_type: 'tank' })])
    const key = entitiesQueryKeys.collection({ device_type: 'tank' })
    client.setQueryData(key, tanks)
    const before = client.getQueryState(key)?.dataUpdatedAt

    applyEntityUpdate(client, {
      entity_id: 'thermostat_1',
      entity_data: makeSsePayload('thermostat_1', { temp: 72 }),
    })

    expect(client.getQueryData(key)).toBe(tanks)
    expect(client.getQueryState(key)?.dataUpdatedAt).toBe(before)
  })

  it('does not mark any collection query as invalidated', () => {
    const key = entitiesQueryKeys.collection({ device_type: 'climate' })
    client.setQueryData(key, makeCollection([makeRestEntity('thermostat_1')]))

    applyEntityUpdate(client, {
      entity_id: 'thermostat_1',
      entity_data: makeSsePayload('thermostat_1', { temp: 75 }),
    })

    expect(client.getQueryState(key)?.isInvalidated).toBe(false)
  })
})
