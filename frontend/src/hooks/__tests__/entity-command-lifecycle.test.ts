import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";

import type { EntityCollectionSchema, EntitySchema } from "@/api/types/domains";
import {
  acceptEntityCommandLifecycle,
  beginEntityCommandLifecycle,
  entityCommandQueryKeys,
  failEntityCommandLifecycle,
  getEntityCommandOperation,
} from "@/hooks/entity-command-lifecycle";
import { entitiesQueryKeys } from "@/hooks/useEntities";
import { applyEntityUpdate } from "@/contexts/realtime-cache";

function makeEntity(id: string, state: Record<string, unknown>): EntitySchema {
  return {
    entity_id: id,
    name: id,
    device_type: "light",
    protocol: "rvc",
    state,
    area: null,
    last_updated: "2026-07-11T00:00:00Z",
    available: true
  };
}

function makeCollection(entities: EntitySchema[]): EntityCollectionSchema {
  return {
    entities,
    total_count: entities.length,
    page: 1,
    page_size: 100,
    has_next: false
  };
}

describe("entity command lifecycle", () => {
  let client: QueryClient;

  beforeEach(() => {
    client = new QueryClient();
  });

  it("patches every matching collection and detail while leaving acceptance unconfirmed", async () => {
    const entity = makeEntity("light_1", { state: "off", brightness: 0 });
    const collectionA = entitiesQueryKeys.collection({ device_type: "light" });
    const collectionB = entitiesQueryKeys.collection({ area: "salon" });
    const detail = entitiesQueryKeys.entity(entity.entity_id);
    const validatedDetail = [...detail, "validated"] as const;
    client.setQueryData(collectionA, makeCollection([entity]));
    client.setQueryData(collectionB, makeCollection([entity]));
    client.setQueryData(detail, entity);
    client.setQueryData(validatedDetail, entity);

    const command = { command: "set" as const, state: true };
    const transaction = await beginEntityCommandLifecycle(
      client,
      [entity.entity_id],
      command
    );
    expect(
      client.getQueryData<EntityCollectionSchema>(collectionA)?.entities[0]?.state?.state
    ).toBe("on");
    expect(
      client.getQueryData<EntityCollectionSchema>(collectionB)?.entities[0]?.state?.state
    ).toBe("on");
    expect(client.getQueryData<EntitySchema>(detail)?.state?.state).toBe("on");
    expect(client.getQueryData<EntitySchema>(validatedDetail)?.state?.state).toBe("on");

    acceptEntityCommandLifecycle(client, transaction, entity.entity_id, "operation-1");
    const operation = getEntityCommandOperation(command);
    expect(
      client.getQueryData(entityCommandQueryKeys.operation(entity.entity_id, operation))
    ).toMatchObject({ phase: "accepted", operationId: "operation-1" });

    applyEntityUpdate(client, {
      entity_id: entity.entity_id,
      entity_data: {
        entity_id: entity.entity_id,
        device_type: "light",
        raw: { state: "on", brightness: 0 },
        timestamp: 1783792800
      }
    });
    expect(
      client.getQueryData(entityCommandQueryKeys.operation(entity.entity_id, operation))
    ).toMatchObject({ phase: "confirmed", confirmationSource: "sse" });
  });

  it("rolls every collection and detail variant back on rejection", async () => {
    const entity = makeEntity("light_1", { state: "off", brightness: 0 });
    const collectionA = entitiesQueryKeys.collection({ device_type: "light" });
    const collectionB = entitiesQueryKeys.collection({ area: "salon" });
    const detail = entitiesQueryKeys.entity(entity.entity_id);
    const validatedDetail = [...detail, "validated"] as const;
    client.setQueryData(collectionA, makeCollection([entity]));
    client.setQueryData(collectionB, makeCollection([entity]));
    client.setQueryData(detail, entity);
    client.setQueryData(validatedDetail, entity);

    const transaction = await beginEntityCommandLifecycle(
      client,
      [entity.entity_id],
      { command: "set", state: true }
    );
    failEntityCommandLifecycle(
      client,
      transaction,
      [entity.entity_id],
      "rejected",
      "Device rejected the command."
    );

    expect(
      client.getQueryData<EntityCollectionSchema>(collectionA)?.entities[0]?.state?.state
    ).toBe("off");
    expect(
      client.getQueryData<EntityCollectionSchema>(collectionB)?.entities[0]?.state?.state
    ).toBe("off");
    expect(client.getQueryData<EntitySchema>(detail)?.state?.state).toBe("off");
    expect(client.getQueryData<EntitySchema>(validatedDetail)?.state?.state).toBe("off");
    expect(
      client.getQueryData(entityCommandQueryKeys.operation(entity.entity_id, "power"))
    ).toMatchObject({ phase: "rejected", error: "Device rejected the command." });
  });

  it("holds optimistic off through stale on SSE until zero status confirms", async () => {
    const entity = makeEntity("light_1", { operating_status: 200 });
    const collectionKey = entitiesQueryKeys.collection({ device_type: "light" });
    const detailKey = entitiesQueryKeys.entity(entity.entity_id);
    client.setQueryData(collectionKey, makeCollection([entity]));
    client.setQueryData(detailKey, entity);

    await beginEntityCommandLifecycle(
      client,
      [entity.entity_id],
      { command: "set", state: false }
    );

    applyEntityUpdate(client, {
      entity_id: entity.entity_id,
      entity_data: {
        entity_id: entity.entity_id,
        device_type: "light",
        raw: { operating_status: 200 },
        timestamp: 1783792800
      }
    });

    expect(client.getQueryData<EntitySchema>(detailKey)?.state).toMatchObject({ state: "off" });
    expect(
      client.getQueryData<EntityCollectionSchema>(collectionKey)?.entities[0]?.state
    ).toMatchObject({ state: "off" });
    expect(
      client.getQueryData(entityCommandQueryKeys.operation(entity.entity_id, "power"))
    ).toMatchObject({ phase: "pending" });

    applyEntityUpdate(client, {
      entity_id: entity.entity_id,
      entity_data: {
        entity_id: entity.entity_id,
        device_type: "light",
        raw: { operating_status: 0 },
        timestamp: 1783792801
      }
    });

    expect(client.getQueryData<EntitySchema>(detailKey)?.state).toEqual({ operating_status: 0 });
    expect(
      client.getQueryData(entityCommandQueryKeys.operation(entity.entity_id, "power"))
    ).toMatchObject({ phase: "confirmed", confirmationSource: "sse" });
  });

  it("rolls back only failed entities in a partial bulk result", async () => {
    const accepted = makeEntity("light_1", { state: "off" });
    const rejected = makeEntity("light_2", { state: "off" });
    const collectionKey = entitiesQueryKeys.collection({ device_type: "light" });
    client.setQueryData(collectionKey, makeCollection([accepted, rejected]));
    client.setQueryData(entitiesQueryKeys.entity(accepted.entity_id), accepted);
    client.setQueryData(entitiesQueryKeys.entity(rejected.entity_id), rejected);

    const transaction = await beginEntityCommandLifecycle(
      client,
      [accepted.entity_id, rejected.entity_id],
      { command: "set", state: true }
    );
    acceptEntityCommandLifecycle(client, transaction, accepted.entity_id, "accepted-op");
    failEntityCommandLifecycle(
      client,
      transaction,
      [rejected.entity_id],
      "rejected",
      "Not available."
    );

    const collection = client.getQueryData<EntityCollectionSchema>(collectionKey);
    expect(collection?.entities.find((entity) => entity.entity_id === accepted.entity_id)?.state)
      .toMatchObject({ state: "on" });
    expect(collection?.entities.find((entity) => entity.entity_id === rejected.entity_id)?.state)
      .toMatchObject({ state: "off" });
    expect(
      client.getQueryData(entityCommandQueryKeys.operation(accepted.entity_id, "power"))
    ).toMatchObject({ phase: "accepted" });
    expect(
      client.getQueryData(entityCommandQueryKeys.operation(rejected.entity_id, "power"))
    ).toMatchObject({ phase: "rejected" });

    applyEntityUpdate(client, {
      entity_id: accepted.entity_id,
      entity_data: {
        entity_id: accepted.entity_id,
        device_type: "light",
        raw: { state: "on" },
        timestamp: 1783792800
      }
    });
  });
});
