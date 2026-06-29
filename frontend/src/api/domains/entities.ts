/**
 * Entities Domain API Client
 *
 * This module provides typed API client functions for the entities domain,
 * leveraging the new /api/v1/entities endpoints with enhanced bulk operations
 * and optimistic update support with Zod runtime validation.
 */

import { apiGet, apiPost, buildQueryString, logApiRequest, logApiResponse } from "../client";
import type { Entity as LegacyEntity } from "../types";
import type {
  BulkControlRequestSchema,
  BulkOperationResultSchema,
  ControlCommandSchema,
  EntitiesQueryParams,
  EntityCollectionSchema,
  EntitySchema,
  OperationResultSchema
} from "../types/domains";
import {
  safeParseApiResponse,
  getEntitySchema,
  getOperationResultSchema,
  getBulkOperationResultSchema,
  getEntityCollectionSchema,
  validateControlCommand,
  validateBulkControlRequest
} from "../validation/zod-schemas";

export type {
  BulkControlRequestSchema,
  BulkOperationResultSchema,
  ControlCommandSchema,
  EntitiesQueryParams,
  EntityCollectionSchema,
  EntitySchema,
  OperationResultSchema
} from "../types/domains";

//
// ===== API CLIENT FUNCTIONS =====
//

/**
 * Fetch entities using the new domain API with filtering and pagination
 * Falls back to legacy API if v2 is not available
 *
 * @param params - Optional query parameters for filtering and pagination
 * @returns Promise resolving to paginated entity collection
 */
export async function fetchEntitiesV2(params?: EntitiesQueryParams): Promise<EntityCollectionSchema> {
  // Direct Domain API v1 call - no fallback needed since legacy endpoints have been removed
  const queryString = params ? buildQueryString(params as Record<string, unknown>) : '';
  const url = queryString ? `/api/v1/entities?${queryString}` : '/api/v1/entities';

  logApiRequest('GET', url, params);
  const result = await apiGet<EntityCollectionSchema>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch a specific entity by ID using the new domain API
 * Falls back to legacy API if v2 is not available
 *
 * @param entityId - The entity ID to fetch
 * @returns Promise resolving to the entity data
 */
export async function fetchEntityV2(entityId: string): Promise<EntitySchema> {
  // Direct Domain API v1 call - no fallback needed since legacy endpoints have been removed
  const url = `/api/v1/entities/${entityId}`;

  logApiRequest('GET', url);
  const result = await apiGet<EntitySchema>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Control a single entity using the new domain API
 * @param entityId - The entity ID to control
 * @param command - The control command to execute
 * @returns Promise resolving to the operation result
 */
export async function controlEntityV2(
  entityId: string,
  command: ControlCommandSchema
): Promise<OperationResultSchema> {
  const url = `/api/v1/entities/${entityId}/control`;

  logApiRequest('POST', url, command);
  const result = await apiPost<OperationResultSchema>(url, command);
  logApiResponse(url, result);

  return result;
}

/**
 * Execute bulk control operations on multiple entities
 * This is the primary enhancement of the domain API, supporting:
 * - Concurrent entity control with proper timeout handling
 * - Detailed per-entity operation results
 * - Multi-status HTTP responses (200, 207, 400)
 * - Optimistic update patterns
 *
 * @param request - Bulk control request with entity IDs and command
 * @returns Promise resolving to bulk operation results
 */
export async function bulkControlEntitiesV2(
  request: BulkControlRequestSchema
): Promise<BulkOperationResultSchema> {
  const url = '/api/v1/entities/bulk-control';

  logApiRequest('POST', url, request);
  const result = await apiPost<BulkOperationResultSchema>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Get Zod-compatible schemas for frontend validation
 *
 * @returns Promise resolving to schema definitions
 */
export async function fetchSchemasV2(): Promise<Record<string, unknown>> {
  const url = '/api/v1/entities/schemas';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Health check for entities domain API
 *
 * @returns Promise resolving to health status
 */
export async function fetchEntitiesHealthV2(): Promise<Record<string, unknown>> {
  const url = '/api/v1/entities/health';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

//
// ===== CONVENIENCE FUNCTIONS =====
//

/**
 * Turn multiple lights on using bulk operations
 *
 * @param entityIds - Array of light entity IDs
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to bulk operation results
 */
export async function bulkTurnLightsOn(
  entityIds: string[],
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  return bulkControlEntitiesV2({
    entity_ids: entityIds,
    command: {
      command: 'set',
      state: true,
    },
    ignore_errors: ignoreErrors,
  });
}

/**
 * Turn multiple lights off using bulk operations
 *
 * @param entityIds - Array of light entity IDs
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to bulk operation results
 */
export async function bulkTurnLightsOff(
  entityIds: string[],
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  return bulkControlEntitiesV2({
    entity_ids: entityIds,
    command: {
      command: 'set',
      state: false,
    },
    ignore_errors: ignoreErrors,
  });
}

/**
 * Set brightness for multiple lights using bulk operations
 *
 * @param entityIds - Array of light entity IDs
 * @param brightness - Brightness level (0-100)
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to bulk operation results
 */
export async function bulkSetLightBrightness(
  entityIds: string[],
  brightness: number,
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  return bulkControlEntitiesV2({
    entity_ids: entityIds,
    command: {
      command: 'set',
      brightness: Math.max(0, Math.min(100, brightness)),
    },
    ignore_errors: ignoreErrors,
  });
}

/**
 * Toggle multiple entities using bulk operations
 *
 * @param entityIds - Array of entity IDs
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to bulk operation results
 */
export async function bulkToggleEntities(
  entityIds: string[],
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  return bulkControlEntitiesV2({
    entity_ids: entityIds,
    command: {
      command: 'toggle',
    },
    ignore_errors: ignoreErrors,
  });
}

//
// ===== LEGACY COMPATIBILITY =====
//

/**
 * Convert legacy Entity to new EntitySchema format for v1 API compatibility
 *
 * @param legacyEntity - Legacy Entity from legacy API
 * @returns New EntitySchema format
 */
export function convertEntityLegacyToV2(legacyEntity: LegacyEntity): EntitySchema {
  const entity = legacyEntity as LegacyEntity & { available?: boolean; protocol?: string };
  return {
    entity_id: entity.entity_id || entity.id || '',
    name: entity.friendly_name || entity.name || '',
    device_type: entity.device_type || 'unknown',
    protocol: entity.protocol || 'rvc',
    state: (entity.raw as Record<string, string | number | boolean>) || {},
    area: entity.suggested_area || null,
    last_updated: entity.last_updated || new Date().toISOString(),
    available: entity.available !== false,
  };
}

/**
 * Convert new EntitySchema to legacy Entity format for backward compatibility
 *
 * @param entity - New EntitySchema from domain API
 * @returns Legacy Entity format
 */
export function convertEntitySchemaToLegacy(entity: EntitySchema): Record<string, unknown> {
  return {
    entity_id: entity.entity_id,
    name: entity.name,
    friendly_name: entity.name,
    device_type: entity.device_type,
    suggested_area: entity.area || '',
    state: entity.state?.state || 'unknown',
    raw: entity.state || {},
    capabilities: [], // Could be extracted from state if needed
    timestamp: new Date(entity.last_updated).getTime(),
    value: entity.state || {},
    groups: [],
    // Legacy fields
    id: entity.entity_id,
    last_updated: entity.last_updated,
    current_state: entity.state?.state || 'unknown',
  };
}

/**
 * Convert legacy EntityCollection to new EntityCollectionSchema format
 *
 * @param legacyCollection - Legacy entity collection (Record<string, Entity>)
 * @returns New EntityCollectionSchema format
 */
export function convertLegacyEntityCollection(legacyCollection: Record<string, unknown>): EntityCollectionSchema {
  const entities: EntitySchema[] = Object.entries(legacyCollection).map(([id, entity]) => {
    // Type guard for entity object
    const entityObj = entity && typeof entity === 'object' ? entity as Record<string, unknown> : {};

    // Safe state extraction with type assertion
    const extractState = (): Record<string, string | number | boolean> => {
      const rawState = entityObj.raw || entityObj.value;
      if (rawState && typeof rawState === 'object' && rawState !== null) {
        return rawState as Record<string, string | number | boolean>;
      }
      return {};
    };

    return {
      entity_id: id,
      name: (typeof entityObj.friendly_name === 'string' ? entityObj.friendly_name :
             typeof entityObj.name === 'string' ? entityObj.name : id),
      device_type: typeof entityObj.device_type === 'string' ? entityObj.device_type : 'unknown',
      protocol: typeof entityObj.protocol === 'string' ? entityObj.protocol : 'rvc',
      state: extractState(),
      area: typeof entityObj.suggested_area === 'string' ? entityObj.suggested_area : null,
      last_updated: typeof entityObj.last_updated === 'string' ? entityObj.last_updated : new Date().toISOString(),
      available: entityObj.available !== false,
    };
  });

  return {
    entities,
    total_count: entities.length,
    page: 1,
    page_size: entities.length,
    has_next: false,
    filters_applied: {},
  };
}

//
// ===== VALIDATION-ENHANCED API FUNCTIONS =====
//

/**
 * Fetch entities with runtime validation using Zod schemas
 *
 * @param params - Optional query parameters for filtering and pagination
 * @returns Promise resolving to validated paginated entity collection
 */
export async function fetchEntitiesV2WithValidation(params?: EntitiesQueryParams): Promise<EntityCollectionSchema> {
  const rawResult = await fetchEntitiesV2(params);

  // Validate the response using dynamic schema
  const validatedResult = await safeParseApiResponse(rawResult, getEntityCollectionSchema);

  if (validatedResult === null) {
    console.warn('⚠️ Entity collection validation failed, returning unvalidated data');
    return rawResult;
  }
  return validatedResult;
}

/**
 * Fetch entity with runtime validation using Zod schemas
 *
 * @param entityId - The entity ID to fetch
 * @returns Promise resolving to validated entity data
 */
export async function fetchEntityV2WithValidation(entityId: string): Promise<EntitySchema> {
  const rawResult = await fetchEntityV2(entityId);

  // Validate the response using dynamic schema
  const validatedResult = await safeParseApiResponse(rawResult, getEntitySchema);

  if (validatedResult === null) {
    console.warn('⚠️ Entity validation failed, returning unvalidated data');
    return rawResult;
  }
  return validatedResult;
}

/**
 * Control entity with pre-validation of command and post-validation of result
 *
 * @param entityId - The entity ID to control
 * @param command - The control command to execute
 * @returns Promise resolving to validated operation result
 */
export async function controlEntityV2WithValidation(
  entityId: string,
  command: ControlCommandSchema
): Promise<OperationResultSchema> {
  // Pre-validate the command
  const commandValidation = await validateControlCommand(command);
  if (!commandValidation.success) {
    throw new Error(`Invalid control command: ${commandValidation.errors.join(', ')}`);
  }
  // Execute with validated command
  const rawResult = await controlEntityV2(entityId, commandValidation.data);

  // Validate the response
  const validatedResult = await safeParseApiResponse(rawResult, getOperationResultSchema);

  if (validatedResult === null) {
    console.warn('⚠️ Operation result validation failed, returning unvalidated data');
    return rawResult;
  }
  return validatedResult;
}

/**
 * Execute bulk control with comprehensive validation of request and results
 *
 * @param request - Bulk control request with entity IDs and command
 * @returns Promise resolving to validated bulk operation results
 */
export async function bulkControlEntitiesV2WithValidation(
  request: BulkControlRequestSchema
): Promise<BulkOperationResultSchema> {
  // Pre-validate the bulk request
  const requestValidation = await validateBulkControlRequest(request);
  if (!requestValidation.success) {
    throw new Error(`Invalid bulk control request: ${requestValidation.errors.join(', ')}`);
  }
  // Execute with validated request
  const rawResult = await bulkControlEntitiesV2(requestValidation.data);

  // Validate the response
  const validatedResult = await safeParseApiResponse(rawResult, getBulkOperationResultSchema);

  if (validatedResult === null) {
    console.warn('⚠️ Bulk operation result validation failed, returning unvalidated data');
    return rawResult;
  }
  return validatedResult;
}

//
// ===== SAFETY-AWARE CONVENIENCE FUNCTIONS =====
//

/**
 * Turn multiple lights on with validation and safety checks
 *
 * @param entityIds - Array of light entity IDs
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to validated bulk operation results
 */
export async function bulkTurnLightsOnWithValidation(
  entityIds: string[],
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  const request: BulkControlRequestSchema = {
    entity_ids: entityIds,
    command: {
      command: 'set',
      state: true,
    },
    ignore_errors: ignoreErrors,
  };

  return await bulkControlEntitiesV2WithValidation(request);
}

/**
 * Turn multiple lights off with validation and safety checks
 *
 * @param entityIds - Array of light entity IDs
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to validated bulk operation results
 */
export async function bulkTurnLightsOffWithValidation(
  entityIds: string[],
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  const request: BulkControlRequestSchema = {
    entity_ids: entityIds,
    command: {
      command: 'set',
      state: false,
    },
    ignore_errors: ignoreErrors,
  };

  return await bulkControlEntitiesV2WithValidation(request);
}

/**
 * Set brightness for multiple lights with validation and safety limits
 *
 * @param entityIds - Array of light entity IDs
 * @param brightness - Brightness level (0-100, will be clamped)
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to validated bulk operation results
 */
export async function bulkSetLightBrightnessWithValidation(
  entityIds: string[],
  brightness: number,
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  // Safety clamp brightness to valid range
  const safeBrightness = Math.max(0, Math.min(100, brightness));

  if (brightness !== safeBrightness) {
    console.warn(`⚠️ Brightness clamped from ${brightness} to ${safeBrightness} for safety`);
  }

  const request: BulkControlRequestSchema = {
    entity_ids: entityIds,
    command: {
      command: 'set',
      brightness: safeBrightness,
    },
    ignore_errors: ignoreErrors,
  };

  return await bulkControlEntitiesV2WithValidation(request);
}

/**
 * Toggle multiple entities with validation and safety checks
 *
 * @param entityIds - Array of entity IDs
 * @param ignoreErrors - Whether to continue if some operations fail
 * @returns Promise resolving to validated bulk operation results
 */
export async function bulkToggleEntitiesWithValidation(
  entityIds: string[],
  ignoreErrors = true
): Promise<BulkOperationResultSchema> {
  const request: BulkControlRequestSchema = {
    entity_ids: entityIds,
    command: {
      command: 'toggle',
    },
    ignore_errors: ignoreErrors,
  };

  return await bulkControlEntitiesV2WithValidation(request);
}
