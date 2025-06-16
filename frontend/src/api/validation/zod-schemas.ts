/**
 * Zod Schema Integration for Domain API v2
 *
 * This module fetches Pydantic schemas from the backend and converts them to
 * Zod schemas for runtime validation. Provides type-safe validation with
 * full synchronization to backend models.
 */

import { z } from 'zod';
import type {
  EntitySchema,
  ControlCommandSchema,
  BulkControlRequestSchema,
  OperationResultSchema,
  BulkOperationResultSchema,
  EntityCollectionSchema,
} from '../types/domains';

//
// ===== SCHEMA CACHE AND MANAGEMENT =====
//

interface SchemaExportResponse {
  version: string;
  schemas: Record<string, JsonSchema>;
  metadata: {
    generated_at: string;
    domain_api_version: string;
    safety_critical: boolean;
    validation_required: boolean;
  };
}

interface JsonSchema {
  type: string;
  properties: Record<string, any>;
  required: string[];
  additionalProperties?: boolean;
}

/** Schema cache with versioning support */
class SchemaCache {
  private readonly cache = new Map<string, z.ZodSchema>();
  private lastFetch: Date | null = null;
  private version: string | null = null;
  private readonly CACHE_TTL = 60 * 60 * 1000; // 1 hour

  /**
   * Get cached schema or fetch from backend
   */
  async getSchema<T extends z.ZodSchema>(schemaName: string): Promise<T> {
    try {
      const cacheKey = `${schemaName}_${this.version}`;

      if (this.isCacheValid() && this.cache.has(cacheKey)) {
        return this.cache.get(cacheKey) as T;
      }

      await this.refreshSchemas();

      // Try with new version after refresh
      const newCacheKey = `${schemaName}_${this.version}`;
      if (!this.cache.has(newCacheKey)) {
        console.warn(`⚠️ Schema '${schemaName}' not found, falling back to static schemas`);
        this.initializeStaticSchemas();

        // Try again with static schemas
        const staticKey = `${schemaName}_static`;
        if (this.cache.has(staticKey)) {
          return this.cache.get(staticKey) as T;
        }

        throw new Error(`Schema '${schemaName}' not available after refresh and static fallback`);
      }

      return this.cache.get(newCacheKey) as T;
    } catch (error) {
      console.error(`❌ Error getting schema '${schemaName}':`, error);

      // Final fallback - try static schemas
      this.initializeStaticSchemas();
      const staticKey = `${schemaName}_static`;
      if (this.cache.has(staticKey)) {
        return this.cache.get(staticKey) as T;
      }

      throw error;
    }
  }

  /**
   * Check if cache is still valid
   */
  private isCacheValid(): boolean {
    if (!this.lastFetch || !this.version) return false;
    return Date.now() - this.lastFetch.getTime() < this.CACHE_TTL;
  }

  /**
   * Refresh schemas from backend
   */
  private async refreshSchemas(): Promise<void> {
    try {
      const response = await fetch('/api/v2/entities/schemas');

      if (!response.ok) {
        throw new Error(`Schema fetch failed: ${response.status} ${response.statusText}`);
      }

      const rawData = await response.json();

      // Handle both wrapped and direct schema responses
      let schemas: Record<string, JsonSchema>;
      let version: string;

      if (rawData.schemas && rawData.version) {
        // Wrapped response format
        const data = rawData as SchemaExportResponse;
        schemas = data.schemas;
        version = data.version;
      } else {
        // Direct schemas response (current backend format)
        schemas = rawData as Record<string, JsonSchema>;
        version = new Date().toISOString(); // Generate version from timestamp
      }

      // Validate schemas exist and are not null/undefined
      if (!schemas || typeof schemas !== 'object') {
        throw new Error('Invalid schema response: schemas object is missing or invalid');
      }

      // Clear existing cache
      this.cache.clear();

      // Convert each schema to Zod
      for (const [name, jsonSchema] of Object.entries(schemas)) {
        if (!jsonSchema || typeof jsonSchema !== 'object') {
          console.warn(`⚠️ Skipping invalid schema: ${name}`);
          continue;
        }
        const zodSchema = this.convertJsonSchemaToZod(jsonSchema);
        this.cache.set(`${name}_${version}`, zodSchema);
      }

      this.version = version;
      this.lastFetch = new Date();

      console.log(`✅ Refreshed ${Object.keys(schemas).length} schemas (v${version})`);
    } catch (error) {
      console.error('❌ Failed to refresh schemas from backend:', error);

      // Fall back to static schemas if backend is unavailable
      this.initializeStaticSchemas();
    }
  }

  /**
   * Convert JSON Schema to Zod schema
   */
  private convertJsonSchemaToZod(jsonSchema: JsonSchema): z.ZodSchema {
    if (jsonSchema.type === 'object') {
      const shape: Record<string, z.ZodSchema> = {};

      for (const [propName, propSchema] of Object.entries(jsonSchema.properties || {})) {
        shape[propName] = this.convertPropertyToZod(propSchema, jsonSchema.required?.includes(propName) ?? false);
      }

      const baseSchema = z.object(shape);

      // Handle additional properties
      if (jsonSchema.additionalProperties === false) {
        return baseSchema.strict();
      }

      return baseSchema;
    }

    // Fallback for non-object schemas
    return z.any();
  }

  /**
   * Convert individual property to Zod schema
   */
  private convertPropertyToZod(propSchema: any, isRequired: boolean): z.ZodSchema {
    let schema: z.ZodSchema;

    // Handle array types
    if (Array.isArray(propSchema.type)) {
      // Union type (e.g., ["string", "null"])
      const types = propSchema.type.filter((t: string) => t !== 'null');
      const isNullable = propSchema.type.includes('null');

      if (types.length === 1) {
        schema = this.getZodTypeForJsonType(types[0]);
        if (isNullable) {
          schema = schema.nullable();
        }
      } else {
        // Multiple non-null types - create union
        const unionSchemas = types.map((t: string) => this.getZodTypeForJsonType(t));
        schema = z.union(unionSchemas as [z.ZodSchema, z.ZodSchema, ...z.ZodSchema[]]);
        if (isNullable) {
          schema = schema.nullable();
        }
      }
    } else {
      // Single type
      schema = this.getZodTypeForJsonType(propSchema.type || 'any');

      // Handle nullable
      if (propSchema.nullable === true) {
        schema = schema.nullable();
      }
    }

    // Handle arrays
    if (propSchema.type === 'array' && propSchema.items) {
      const itemSchema = this.convertPropertyToZod(propSchema.items, true);
      schema = z.array(itemSchema);
    }

    // Handle validation constraints
    if (propSchema.type === 'string') {
      if (propSchema.minLength) {
        schema = (schema as z.ZodString).min(propSchema.minLength);
      }
      if (propSchema.maxLength) {
        schema = (schema as z.ZodString).max(propSchema.maxLength);
      }
      if (propSchema.enum) {
        schema = z.enum(propSchema.enum);
      }
    }

    if (propSchema.type === 'number' || propSchema.type === 'integer') {
      if (propSchema.minimum !== undefined) {
        schema = (schema as z.ZodNumber).min(propSchema.minimum);
      }
      if (propSchema.maximum !== undefined) {
        schema = (schema as z.ZodNumber).max(propSchema.maximum);
      }
    }

    // Handle optional vs required
    if (!isRequired) {
      schema = schema.optional();
    }

    return schema;
  }

  /**
   * Get Zod type for JSON Schema type
   */
  private getZodTypeForJsonType(type: string): z.ZodSchema {
    switch (type) {
      case 'string':
        return z.string();
      case 'number':
        return z.number();
      case 'integer':
        return z.number().int();
      case 'boolean':
        return z.boolean();
      case 'array':
        return z.array(z.any());
      case 'object':
        return z.object({});
      default:
        return z.any();
    }
  }

  /**
   * Initialize static fallback schemas when backend is unavailable
   */
  private initializeStaticSchemas(): void {
    const fallbackSchemas = {
      Entity: EntitySchemaZod,
      ControlCommand: ControlCommandSchemaZod,
      BulkControlRequest: BulkControlRequestSchemaZod,
      OperationResult: OperationResultSchemaZod,
      BulkOperationResult: BulkOperationResultSchemaZod,
      EntityCollection: EntityCollectionSchemaZod,
    };

    for (const [name, schema] of Object.entries(fallbackSchemas)) {
      this.cache.set(`${name}_static`, schema);
    }

    this.version = 'static';
    this.lastFetch = new Date();

    console.warn('⚠️ Using static fallback schemas (backend unavailable)');
  }
}

// Global schema cache instance
const schemaCache = new SchemaCache();

//
// ===== STATIC ZOD SCHEMAS (FALLBACK) =====
//

/** Entity schema with safety-critical validation */
export const EntitySchemaZod = z.object({
  entity_id: z.string().min(1),
  name: z.string().min(1),
  device_type: z.string().min(1),
  protocol: z.string().min(1),
  state: z.record(z.union([z.string(), z.number(), z.boolean()])),
  area: z.string().nullable().optional(),
  last_updated: z.string().datetime(),
  available: z.boolean(),
}).strict();

/** Control command schema with safety validation */
export const ControlCommandSchemaZod = z.object({
  command: z.enum(['set', 'toggle', 'brightness_up', 'brightness_down']),
  state: z.boolean().nullable().optional(),
  brightness: z.number().min(0).max(100).nullable().optional(),
  parameters: z.record(z.union([z.string(), z.number(), z.boolean()])).nullable().optional(),
}).strict()
  .refine((data) => {
    // Safety validation: set command requires state or brightness
    if (data.command === 'set') {
      return data.state !== undefined || data.brightness !== undefined;
    }
    return true;
  }, {
    message: "Set command requires either 'state' or 'brightness' parameter",
  });

/** Bulk control request schema */
export const BulkControlRequestSchemaZod = z.object({
  entity_ids: z.array(z.string().min(1)).min(1).max(100), // Limit bulk operations
  command: ControlCommandSchemaZod,
  ignore_errors: z.boolean().optional(),
  timeout_seconds: z.number().min(0.1).max(300).nullable().optional(), // Max 5 minutes
}).strict();

/** Operation result schema */
export const OperationResultSchemaZod = z.object({
  entity_id: z.string().min(1),
  status: z.enum(['success', 'failed', 'timeout', 'unauthorized']),
  error_message: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  execution_time_ms: z.number().min(0).nullable().optional(),
}).strict();

/** Bulk operation result schema */
export const BulkOperationResultSchemaZod = z.object({
  operation_id: z.string().min(1),
  total_count: z.number().min(0),
  success_count: z.number().min(0),
  failed_count: z.number().min(0),
  results: z.array(OperationResultSchemaZod),
  total_execution_time_ms: z.number().min(0),
}).strict()
  .refine((data) => {
    // Validate counts match results
    return data.total_count === data.results.length &&
           data.success_count + data.failed_count === data.total_count;
  }, {
    message: "Operation counts must match result arrays",
  });

/** Entity collection schema with pagination */
export const EntityCollectionSchemaZod = z.object({
  entities: z.array(EntitySchemaZod),
  total_count: z.number().min(0),
  page: z.number().min(1),
  page_size: z.number().min(1).max(100),
  has_next: z.boolean(),
  filters_applied: z.record(z.union([z.string(), z.number(), z.boolean(), z.array(z.string())])),
}).strict();

//
// ===== DYNAMIC SCHEMA ACCESS =====
//

/**
 * Get Entity schema (dynamic or fallback)
 */
export async function getEntitySchema(): Promise<z.ZodSchema<EntitySchema>> {
  return await schemaCache.getSchema<z.ZodSchema<EntitySchema>>('Entity');
}

/**
 * Get ControlCommand schema (dynamic or fallback)
 */
export async function getControlCommandSchema(): Promise<z.ZodSchema<ControlCommandSchema>> {
  return await schemaCache.getSchema<z.ZodSchema<ControlCommandSchema>>('ControlCommand');
}

/**
 * Get BulkControlRequest schema (dynamic or fallback)
 */
export async function getBulkControlRequestSchema(): Promise<z.ZodSchema<BulkControlRequestSchema>> {
  return await schemaCache.getSchema<z.ZodSchema<BulkControlRequestSchema>>('BulkControlRequest');
}

/**
 * Get OperationResult schema (dynamic or fallback)
 */
export async function getOperationResultSchema(): Promise<z.ZodSchema<OperationResultSchema>> {
  return await schemaCache.getSchema<z.ZodSchema<OperationResultSchema>>('OperationResult');
}

/**
 * Get BulkOperationResult schema (dynamic or fallback)
 */
export async function getBulkOperationResultSchema(): Promise<z.ZodSchema<BulkOperationResultSchema>> {
  return await schemaCache.getSchema<z.ZodSchema<BulkOperationResultSchema>>('BulkOperationResult');
}

/**
 * Get EntityCollection schema (dynamic or fallback)
 */
export async function getEntityCollectionSchema(): Promise<z.ZodSchema<EntityCollectionSchema>> {
  return await schemaCache.getSchema<z.ZodSchema<EntityCollectionSchema>>('EntityCollection');
}

//
// ===== VALIDATION HELPERS =====
//

/**
 * Validate entity data with comprehensive error reporting
 */
export async function validateEntity(data: unknown): Promise<{ success: true; data: EntitySchema } | { success: false; errors: string[] }> {
  try {
    const schema = await getEntitySchema();
    const result = schema.parse(data);
    return { success: true, data: result };
  } catch (error) {
    if (error instanceof z.ZodError) {
      return {
        success: false,
        errors: error.errors.map(e => `${e.path.join('.')}: ${e.message}`)
      };
    }
    return { success: false, errors: ['Unknown validation error'] };
  }
}

/**
 * Validate control command with safety checks
 */
export async function validateControlCommand(data: unknown): Promise<{ success: true; data: ControlCommandSchema } | { success: false; errors: string[] }> {
  try {
    const schema = await getControlCommandSchema();
    const result = schema.parse(data);
    return { success: true, data: result };
  } catch (error) {
    if (error instanceof z.ZodError) {
      return {
        success: false,
        errors: error.errors.map(e => `${e.path.join('.')}: ${e.message}`)
      };
    }
    return { success: false, errors: ['Unknown validation error'] };
  }
}

/**
 * Validate bulk control request with safety limits
 */
export async function validateBulkControlRequest(data: unknown): Promise<{ success: true; data: BulkControlRequestSchema } | { success: false; errors: string[] }> {
  try {
    const schema = await getBulkControlRequestSchema();
    const result = schema.parse(data);
    return { success: true, data: result };
  } catch (error) {
    if (error instanceof z.ZodError) {
      return {
        success: false,
        errors: error.errors.map(e => `${e.path.join('.')}: ${e.message}`)
      };
    }
    return { success: false, errors: ['Unknown validation error'] };
  }
}

/**
 * Safe parse with fallback for API responses
 */
export async function safeParseApiResponse<T>(
  data: unknown,
  schemaGetter: () => Promise<z.ZodSchema<T>>
): Promise<T | null> {
  try {
    const schema = await schemaGetter();
    return schema.parse(data);
  } catch (error) {
    console.warn('API response validation failed:', error);
    return null;
  }
}

//
// ===== SCHEMA MANAGEMENT =====
//

/**
 * Force refresh of schemas from backend
 */
export async function refreshSchemas(): Promise<void> {
  // Clear cache to force refresh
  schemaCache['cache'].clear();
  schemaCache['lastFetch'] = null;

  // Trigger refresh by requesting a schema
  await getEntitySchema();
}

/**
 * Get schema cache status for debugging
 */
export function getSchemaStatus(): {
  version: string | null;
  lastFetch: Date | null;
  cachedSchemas: string[];
  isValid: boolean;
} {
  return {
    version: schemaCache['version'],
    lastFetch: schemaCache['lastFetch'],
    cachedSchemas: Array.from(schemaCache['cache'].keys()),
    isValid: schemaCache['isCacheValid'](),
  };
}
