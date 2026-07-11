import type { Entity } from "@/api/types";
import type { EntityCollectionSchema, EntitySchema } from "@/api/types/domains";

export function getEntityState(entity: EntitySchema): string {
  const state = entity.state?.state;
  if (typeof state === "string") {
    return state;
  }
  if (typeof state === "boolean" || typeof state === "number") {
    return String(state);
  }
  return "unknown";
}

export function getEntityTimestamp(entity: EntitySchema): number {
  const value = entity.last_seen_at ?? entity.data_received_at ?? entity.last_updated;
  if (!value) return 0;
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export function getEntityBrightness(entity: EntitySchema): number {
  const brightness = entity.state?.brightness;
  return typeof brightness === "number" ? brightness : 0;
}

export function getEntityDisplayName(entity: EntitySchema): string {
  return entity.name || entity.entity_id;
}

export function isEntityRecentlyUpdated(entity: EntitySchema, maxAgeMs = 300000): boolean {
  const timestamp = getEntityTimestamp(entity);
  return timestamp > 0 && Date.now() - timestamp < maxAgeMs;
}

export function isEntityActive(entity: EntitySchema): boolean {
  return ["on", "true", "unlocked", "active", "online"].includes(getEntityState(entity));
}

export function toDisplayEntity(entity: EntitySchema): Entity {
  const state = getEntityState(entity);
  const raw = entity.state ?? {};
  const displayEntity: Entity = {
    entity_id: entity.entity_id,
    id: entity.entity_id,
    name: entity.name,
    friendly_name: entity.name,
    device_type: entity.device_type,
    suggested_area: entity.area ?? "",
    state,
    current_state: state,
    raw,
    value: raw,
    capabilities: [],
    groups: [],
    timestamp: getEntityTimestamp(entity),
    ...(entity.last_updated ? { last_updated: entity.last_updated } : {}),
    source_type: entity.protocol,
    entity_type: entity.device_type
  };

  if (entity.device_type === "light") {
    return {
      ...displayEntity,
      device_type: "light",
      brightness: getEntityBrightness(entity)
    };
  }

  return displayEntity;
}

export function collectionToDisplayEntities(
  collection: EntityCollectionSchema | undefined
): Entity[] {
  return collection?.entities.map(toDisplayEntity) ?? [];
}
