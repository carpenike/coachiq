/**
 * Tests for applyEntityUpdate — SSE entity updates must patch the query
 * cache in place instead of invalidating collections, so a chatty CAN bus
 * doesn't fan out into refetch storms that trip the backend rate limit.
 */

import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it } from 'vitest'

import type { EntityCollectionSchema, EntitySchema } from '@/api/types/domains'
import { applyEntityUpdate } from '../realtime-cache'
import { entitiesQueryKeys } from '@/hooks/useEntities'

function makeEntity(id: string, overrides: Partial<EntitySchema> = {}): EntitySchema {
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

  it('writes the entity into its individual-entity cache entry', () => {
    const updated = makeEntity('thermostat_1', { state: { temp: 72 } })
    applyEntityUpdate(client, { entity_id: 'thermostat_1', entity_data: updated })

    expect(client.getQueryData(entitiesQueryKeys.entity('thermostat_1'))).toEqual(updated)
  })

  it('patches the entity into every cached collection containing it', () => {
    const stale = makeEntity('thermostat_1', { state: { temp: 68 } })
    const other = makeEntity('thermostat_2')
    const keyA = entitiesQueryKeys.collection({ device_type: 'climate' })
    const keyB = entitiesQueryKeys.collection({ device_type: 'climate', page_size: 100 })
    client.setQueryData(keyA, makeCollection([stale, other]))
    client.setQueryData(keyB, makeCollection([stale]))

    const updated = makeEntity('thermostat_1', { state: { temp: 72 } })
    applyEntityUpdate(client, { entity_id: 'thermostat_1', entity_data: updated })

    const collectionA = client.getQueryData<EntityCollectionSchema>(keyA)
    expect(collectionA?.entities).toEqual([updated, other])
    const collectionB = client.getQueryData<EntityCollectionSchema>(keyB)
    expect(collectionB?.entities).toEqual([updated])
  })

  it('leaves collections that do not contain the entity untouched', () => {
    const tanks = makeCollection([makeEntity('fresh_tank', { device_type: 'tank' })])
    const key = entitiesQueryKeys.collection({ device_type: 'tank' })
    client.setQueryData(key, tanks)
    const before = client.getQueryState(key)?.dataUpdatedAt

    applyEntityUpdate(client, {
      entity_id: 'thermostat_1',
      entity_data: makeEntity('thermostat_1'),
    })

    expect(client.getQueryData(key)).toBe(tanks)
    expect(client.getQueryState(key)?.dataUpdatedAt).toBe(before)
  })

  it('does not mark any collection query as invalidated', () => {
    const key = entitiesQueryKeys.collection({ device_type: 'climate' })
    client.setQueryData(key, makeCollection([makeEntity('thermostat_1')]))

    applyEntityUpdate(client, {
      entity_id: 'thermostat_1',
      entity_data: makeEntity('thermostat_1', { state: { temp: 75 } }),
    })

    expect(client.getQueryState(key)?.isInvalidated).toBe(false)
  })
})
