/**
 * Coach Configuration Hook
 *
 * Fetches the coach mapping config (zones, lighting scenes, lighting groups)
 * from GET /api/v1/entities/config/coach and exposes helpers for zone
 * display names and grouping entities into zones.
 *
 * Zone model source of truth: coach mapping YAML `areas:` hierarchy.
 * Fallback when entity.area is missing/"Unknown": derive zone from the
 * entity_id prefix (flagged as derived so Device Mapping can surface it).
 */

import type { UseQueryResult } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/api/client';
import type { EntitySchema } from '@/api/types/domains';

//
// ===== TYPES (shape of /api/v1/entities/config/coach) =====
//

export interface ICoachZoneConfig {
  display_name: string;
  description?: string;
}

export interface ICoachAreaConfig {
  display_name: string;
  zones: Record<string, ICoachZoneConfig>;
}

export interface ISceneEntityRef {
  entity_id: string;
  brightness?: number;
  action?: 'on' | 'off';
}

export interface ILightingScene {
  name: string;
  description?: string;
  /** Entries are exact ids, glob patterns ("*_light"), or per-entity objects */
  entities: (string | ISceneEntityRef)[];
  /** Default action applied to string entries when the entry has no override */
  action?: 'on' | 'off';
}

export interface ILightingGroup {
  name: string;
  entities: string[];
}

export interface ICoachInfo {
  year?: string;
  make?: string;
  model?: string;
  trim?: string;
  [key: string]: unknown;
}

export interface ICoachConfig {
  coach_info: ICoachInfo;
  areas: Record<string, ICoachAreaConfig>;
  lighting_scenes: Record<string, ILightingScene>;
  lighting_groups: Record<string, ILightingGroup>;
}

//
// ===== QUERY HOOK =====
//

export const coachConfigQueryKey = ['coach-config'] as const;

/**
 * Fetch the coach configuration. The config only changes on redeploy,
 * so it is cached for the lifetime of the session.
 */
export function useCoachConfig(): UseQueryResult<ICoachConfig, Error> {
  return useQuery({
    queryKey: coachConfigQueryKey,
    queryFn: () => apiGet<ICoachConfig>('/api/v1/entities/config/coach'),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

//
// ===== ZONE HELPERS =====
//

/** Title-case the last segment of a zone id ("interior.bathroom_master" → "Bathroom Master"). */
function titleCaseZoneSegment(zoneId: string): string {
  const segment = zoneId.split('.').pop() ?? zoneId;
  return segment
    .split('_')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Display name for a zone id like "interior.bedroom" → "Master Bedroom".
 * Falls back to a title-cased last segment when the config has no entry.
 */
export function zoneDisplayName(zoneId: string, config?: ICoachConfig): string {
  const [section, ...rest] = zoneId.split('.');
  const zoneKey = rest.join('.');
  if (config && section && zoneKey) {
    const area = Object.entries(config.areas).find(([key]) => key === section)?.[1];
    const displayName = area && Object.entries(area.zones).find(([key]) => key === zoneKey)?.[1]
      .display_name;
    if (displayName) return displayName;
  }
  return titleCaseZoneSegment(zoneId);
}

/** Ordered [pattern-test, zoneId] fallback rules for deriving a zone from an entity id. */
const ZONE_DERIVATION_RULES: [RegExp, string][] = [
  [/^bedroom_/, 'interior.bedroom'],
  [/^master_bath_/, 'interior.bathroom_master'],
  [/^mid_bath_/, 'interior.bathroom_mid'],
  [/(?:^main_)|dinette|sink/, 'interior.living_main'],
  [/^entrance_/, 'interior.entrance'],
  [/awning.*driver|driver.*awning/, 'exterior.awning_driver'],
  [/awning.*passenger|passenger.*awning/, 'exterior.awning_passenger'],
  [/awning/, 'exterior.awning_driver'],
  [/security|motion/, 'exterior.security'],
  [/basement|cargo/, 'exterior.basement'],
  [/^exterior_/, 'exterior.security'],
];

/**
 * Fallback: derive a zone id from the entity_id prefix when the backend
 * did not supply an area. Returns null when no pattern matches.
 */
export function deriveZoneFromEntityId(entityId: string): string | null {
  for (const [pattern, zoneId] of ZONE_DERIVATION_RULES) {
    if (pattern.test(entityId)) return zoneId;
  }
  return null;
}

export type ZoneSection = 'interior' | 'exterior' | 'other';

export interface IZoneGroup {
  zoneId: string;
  displayName: string;
  section: ZoneSection;
  entities: EntitySchema[];
}

const UNASSIGNED_ZONE_ID = 'other';

function sectionForZoneId(zoneId: string): ZoneSection {
  if (zoneId.startsWith('interior.')) return 'interior';
  if (zoneId.startsWith('exterior.')) return 'exterior';
  return 'other';
}

/** Zone id for a single entity: real area, else derived from id, else "other". */
export function zoneIdForEntity(entity: EntitySchema): string {
  if (entity.area && entity.area !== 'Unknown') {
    return entity.area;
  }
  return deriveZoneFromEntityId(entity.entity_id) ?? UNASSIGNED_ZONE_ID;
}

/** Bucket entities by their derived zone id, preserving first-seen order per bucket. */
function bucketEntitiesByZone(entities: EntitySchema[]): Map<string, EntitySchema[]> {
  const byZone = new Map<string, EntitySchema[]>();
  for (const entity of entities) {
    const zoneId = zoneIdForEntity(entity);
    const bucket = byZone.get(zoneId);
    if (bucket) {
      bucket.push(entity);
    } else {
      byZone.set(zoneId, [entity]);
    }
  }
  return byZone;
}

/**
 * Canonical zone id order: interior zones (config order), then exterior
 * zones (config order), then any zones observed on entities but absent
 * from config (insertion order), then "Unassigned".
 */
function orderedZoneIds(observedZoneIds: Iterable<string>, config?: ICoachConfig): string[] {
  const ids: string[] = [];
  for (const section of ['interior', 'exterior']) {
    const area = Object.entries(config?.areas ?? {}).find(([key]) => key === section)?.[1];
    if (!area) continue;
    for (const zoneKey of Object.keys(area.zones)) {
      ids.push(`${section}.${zoneKey}`);
    }
  }
  for (const zoneId of observedZoneIds) {
    if (!ids.includes(zoneId) && zoneId !== UNASSIGNED_ZONE_ID) {
      ids.push(zoneId);
    }
  }
  ids.push(UNASSIGNED_ZONE_ID);
  return ids;
}

/**
 * Group entities into zones, ordered: interior zones (config order),
 * then exterior zones (config order), then any remaining zones, then
 * "Unassigned". Only zones that actually contain entities are returned.
 */
export function groupEntitiesByZone(
  entities: EntitySchema[],
  config?: ICoachConfig
): IZoneGroup[] {
  const byZone = bucketEntitiesByZone(entities);

  const groups: IZoneGroup[] = [];
  for (const zoneId of orderedZoneIds(byZone.keys(), config)) {
    const zoneEntities = byZone.get(zoneId);
    if (!zoneEntities || zoneEntities.length === 0) continue;
    groups.push({
      zoneId,
      displayName:
        zoneId === UNASSIGNED_ZONE_ID ? 'Unassigned' : zoneDisplayName(zoneId, config),
      section: sectionForZoneId(zoneId),
      entities: zoneEntities,
    });
  }
  return groups;
}

//
// ===== SCENE HELPERS =====
//

/**
 * Match a value against a config glob ("*_light") using plain string ops
 * (no dynamic RegExp construction). "*" matches any run of characters,
 * including zero; matching is anchored to the full string on both ends.
 */
function matchesGlob(glob: string, value: string): boolean {
  const segments = glob.split('*');

  // No wildcard: exact match.
  if (segments.length === 1) return value === glob;

  const [first, ...restSegments] = segments;
  const last = restSegments[restSegments.length - 1] ?? '';
  const middleSegments = restSegments.slice(0, -1);

  if (first !== undefined && !value.startsWith(first)) return false;
  if (!value.endsWith(last)) return false;

  // Walk the remaining middle segments left-to-right, each must appear
  // in order after the cursor left off (mirrors "*seg*seg*" semantics).
  let cursor = first?.length ?? 0;
  const searchEnd = value.length - last.length;
  for (const segment of middleSegments) {
    if (segment === '') continue;
    const index = value.indexOf(segment, cursor);
    if (index === -1 || index > searchEnd) return false;
    cursor = index + segment.length;
  }
  return cursor <= searchEnd;
}

export interface IResolvedSceneCommand {
  entityId: string;
  action: 'on' | 'off';
  brightness?: number;
}

function makeCommand(
  entityId: string,
  action: 'on' | 'off',
  brightness?: number
): IResolvedSceneCommand {
  const command: IResolvedSceneCommand = { entityId, action };
  if (brightness !== undefined) command.brightness = brightness;
  return command;
}

/** Resolve a string scene entry (exact id or glob pattern) into concrete commands. */
function resolveStringEntry(
  entry: string,
  entities: EntitySchema[],
  defaultAction: 'on' | 'off'
): IResolvedSceneCommand[] {
  if (!entry.includes('*')) {
    return [makeCommand(entry, defaultAction)];
  }
  return entities
    .filter((entity) => matchesGlob(entry, entity.entity_id))
    .map((entity) => makeCommand(entity.entity_id, defaultAction));
}

/** Resolve an object scene entry, which may override action/brightness per entity. */
function resolveRefEntry(
  entry: ISceneEntityRef,
  defaultAction: 'on' | 'off'
): IResolvedSceneCommand {
  // Brightness implies "on" unless explicitly overridden.
  const action = entry.action ?? (entry.brightness !== undefined ? 'on' : defaultAction);
  return makeCommand(entry.entity_id, action, entry.brightness);
}

/**
 * Resolve a lighting scene definition against the live entity list.
 * String entries may be exact ids or glob patterns; object entries may
 * carry a per-entity action/brightness override. Entities that do not
 * exist are silently skipped (never send commands to phantom devices).
 */
export function resolveSceneCommands(
  scene: ILightingScene,
  entities: EntitySchema[]
): IResolvedSceneCommand[] {
  const knownIds = new Set(entities.map((entity) => entity.entity_id));
  const commands = new Map<string, IResolvedSceneCommand>();
  const defaultAction: 'on' | 'off' = scene.action ?? 'on';

  for (const entry of scene.entities) {
    const resolved =
      typeof entry === 'string'
        ? resolveStringEntry(entry, entities, defaultAction)
        : [resolveRefEntry(entry, defaultAction)];
    for (const command of resolved) {
      if (knownIds.has(command.entityId)) {
        commands.set(command.entityId, command);
      }
    }
  }

  return [...commands.values()];
}
