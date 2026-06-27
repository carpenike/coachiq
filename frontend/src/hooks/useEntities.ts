/**
 * Entity Query Hooks
 *
 * Custom React Query hooks for entity management.
 * Provides type-safe, optimized data fetching for all entity types.
 *
 * ENHANCED VERSION: Now supports Domain API v2 with progressive migration.
 * Uses validation-enhanced endpoints when available, falls back to legacy API.
 */

import { queryKeys, STALE_TIMES } from '@/lib/query-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import {
    controlEntity,
    fetchEntities,
    fetchEntity,
    fetchEntityHistory,
    fetchEntityMetadata,
    fetchLights,
    fetchLocks,
    fetchTankSensors,
    fetchTemperatureSensors,
    lockEntity,
    unlockEntity,
} from '../api';
// Domain API v2 imports
import {
    fetchEntitiesV2WithValidation,
    fetchEntityV2WithValidation,
    controlEntityV2WithValidation,
    bulkControlEntitiesV2WithValidation,
    convertEntitySchemaToLegacy,
    convertLegacyEntityCollection,
} from '../api/domains/entities';
import {
    useEntitiesDomainAPIAvailability,
    useControlEntityV2WithValidation,
    useBulkControlEntitiesV2WithValidation,
} from './domains/useEntitiesV2';
import type {
    ControlCommand,
    ControlEntityResponse,
    EntitiesQueryParams,
    EntityBase,
    LightEntity,
    LockEntity,
    TankSensorEntity,
    TemperatureSensorEntity
} from '../api/types';
import type {
    EntitySchema as EntitySchemaV2,
    ControlCommandSchema as ControlCommandSchemaV2,
} from '../api/types/domains';

// Extended types for optimistic updates
type OptimisticEntityBase = EntityBase & { _optimistic?: boolean };
type OptimisticLightEntity = LightEntity & { _optimistic?: boolean };

/**
 * Hook to fetch all entities with Domain API v2 progressive enhancement
 *
 * ENHANCED VERSION: Uses Domain API v2 with validation when available,
 * automatically falls back to legacy API for compatibility.
 *
 * @param params - Query parameters for filtering and pagination
 * @param useV2 - Force use of Domain API v2 (optional, defaults to auto-detect)
 */
export function useEntities(params?: EntitiesQueryParams, useV2?: boolean) {
  const { data: isDomainAPIAvailable } = useEntitiesDomainAPIAvailability();
  const shouldUseV2 = useV2 ?? isDomainAPIAvailable;

  return useQuery({
    queryKey: shouldUseV2 ?
      [...queryKeys.entities.list(params), 'domain-v2'] :
      queryKeys.entities.list(params),
    queryFn: async () => {
      if (shouldUseV2) {
        try {
          // Use Domain API v2 with validation
          const v2Collection = await fetchEntitiesV2WithValidation(params);

          // Convert to legacy format for backward compatibility
          const legacyEntities: Record<string, EntityBase> = {};
          v2Collection.entities.forEach((entity) => {
            legacyEntities[entity.entity_id] = convertEntitySchemaToLegacy(entity) as unknown as EntityBase;
          });
          return legacyEntities;
        } catch (error) {
          console.warn('⚠️ Domain API v2 failed, falling back to legacy API:', error);
          // Fallback to legacy API
          return fetchEntities(params);
        }
      } else {
        return fetchEntities(params);
      }
    },
    staleTime: STALE_TIMES.ENTITIES,
  });
}

/**
 * Hook to fetch a specific entity by ID with Domain API v2 progressive enhancement
 *
 * ENHANCED VERSION: Uses Domain API v2 with validation when available,
 * automatically falls back to legacy API for compatibility.
 *
 * @param entityId - Entity ID to fetch
 * @param useV2 - Force use of Domain API v2 (optional, defaults to auto-detect)
 */
export function useEntity(entityId: string, useV2?: boolean) {
  const { data: isDomainAPIAvailable } = useEntitiesDomainAPIAvailability();
  const shouldUseV2 = useV2 ?? isDomainAPIAvailable;

  return useQuery({
    queryKey: shouldUseV2 ?
      [...queryKeys.entities.detail(entityId), 'domain-v2'] :
      queryKeys.entities.detail(entityId),
    queryFn: async () => {
      if (shouldUseV2) {
        try {
          // Use Domain API v2 with validation
          const v2Entity = await fetchEntityV2WithValidation(entityId);

          // Convert to legacy format for backward compatibility
          const legacyEntity = convertEntitySchemaToLegacy(v2Entity) as unknown as EntityBase;
          return legacyEntity;
        } catch (error) {
          console.warn(`⚠️ Domain API v2 failed for entity ${entityId}, falling back to legacy API:`, error);
          // Fallback to legacy API
          return fetchEntity(entityId);
        }
      } else {
        return fetchEntity(entityId);
      }
    },
    staleTime: STALE_TIMES.ENTITIES,
    enabled: !!entityId,
  });
}

/**
 * Hook to fetch entity metadata
 */
export function useEntityMetadata(entityId: string) {
  return useQuery({
    queryKey: queryKeys.entities.metadata(entityId),
    queryFn: () => fetchEntityMetadata(),
    staleTime: STALE_TIMES.ENTITY_METADATA,
    enabled: !!entityId,
  });
}

/**
 * Hook to fetch entity history
 */
export function useEntityHistory(
  entityId: string,
  options?: { limit?: number; offset?: number; start_time?: string; end_time?: string }
) {
  return useQuery({
    queryKey: queryKeys.entities.history(entityId, options),
    queryFn: () => fetchEntityHistory(entityId, options),
    staleTime: STALE_TIMES.ENTITY_METADATA,
    enabled: !!entityId,
  });
}

/**
 * Hook to fetch all light entities
 */
export function useLights() {
  return useQuery({
    queryKey: queryKeys.lights.list(),
    queryFn: fetchLights,
    staleTime: STALE_TIMES.ENTITIES,
  });
}

/**
 * Hook to fetch all lock entities
 */
export function useLocks() {
  return useQuery({
    queryKey: queryKeys.locks.list(),
    queryFn: fetchLocks,
    staleTime: STALE_TIMES.ENTITIES,
  });
}

/**
 * Hook to fetch all tank sensor entities
 */
export function useTankSensors() {
  return useQuery({
    queryKey: queryKeys.tankSensors.list(),
    queryFn: fetchTankSensors,
    staleTime: STALE_TIMES.ENTITIES,
  });
}

/**
 * Hook to fetch all temperature sensor entities
 */
export function useTemperatureSensors() {
  return useQuery({
    queryKey: queryKeys.temperatureSensors.list(),
    queryFn: fetchTemperatureSensors,
    staleTime: STALE_TIMES.ENTITIES,
  });
}

/**
 * Hook for generic entity control commands with Domain API v2 progressive enhancement
 *
 * ENHANCED VERSION: Uses Domain API v2 with validation and safety-aware optimistic updates
 * when available, falls back to legacy API with simplified optimistic updates.
 *
 * @param useV2 - Force use of Domain API v2 (optional, defaults to auto-detect)
 */
export function useControlEntity(useV2?: boolean) {
  const queryClient = useQueryClient();
  const { data: isDomainAPIAvailable } = useEntitiesDomainAPIAvailability();
  const shouldUseV2 = useV2 ?? isDomainAPIAvailable;

  // Get the Domain API v2 control hook for enhanced functionality
  const controlEntityV2 = useControlEntityV2WithValidation();

  // Track pending optimistic updates per entity (legacy path only)
  const pendingTimers = useRef<Record<string, number>>({});
  const lastConfirmedTimestamps = useRef<Record<string, number>>({});

  // Listen for WebSocket entity updates to clear pending timers (legacy path only)
  useEffect(() => {
    if (shouldUseV2) return; // Skip legacy timer management when using v2

    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      if (event.type === 'updated' && event.query.queryKey && Array.isArray(event.query.queryKey)) {
        const key = event.query.queryKey;
        // Only care about entity detail updates
        if (key[0] === 'entity' && typeof key[1] === 'string') {
          const entityId = key[1];
          const entity = queryClient.getQueryData<OptimisticEntityBase>(key);
          if (entity && entity.timestamp) {
            // If we have a pending timer and the timestamp is new, clear the timer
            if (
              pendingTimers.current[entityId] &&
              entity.timestamp !== lastConfirmedTimestamps.current[entityId]
            ) {
              clearTimeout(pendingTimers.current[entityId]);
              delete pendingTimers.current[entityId];
              lastConfirmedTimestamps.current[entityId] = entity.timestamp;
            }
          }
        }
      }
    });
    return () => unsubscribe();
  }, [queryClient, shouldUseV2]);

  return useMutation({
    mutationFn: ({ entityId, command }: { entityId: string; command: ControlCommand }) => {
      if (shouldUseV2) {
        try {
          // Convert legacy command to v2 format
          const v2Command: ControlCommandSchemaV2 = {
            command: command.command as ControlCommandSchemaV2['command'],
            ...(command.state !== undefined && { state: command.state }),
            ...(command.brightness !== undefined && { brightness: command.brightness }),
            ...(command.parameters && { parameters: command.parameters as Record<string, string | number | boolean> }),
          };

          // Use Domain API v2 with validation and safety-aware optimistic updates
          return controlEntityV2.mutateAsync({ entityId, command: v2Command }).then((result) => {
            // Convert v2 result to legacy format for backward compatibility
            const legacyResponse: ControlEntityResponse = {
              success: result.status === 'success',
              message: result.error_message || 'Command executed successfully',
              entity_id: result.entity_id,
              entity_type: 'unknown', // Will be enriched by invalidation queries
              command: command,
              timestamp: new Date().toISOString(),
              ...(result.execution_time_ms !== undefined && result.execution_time_ms !== null && { execution_time_ms: result.execution_time_ms }),
            };
            return legacyResponse;
          });
        } catch (error) {
          console.warn(`⚠️ Domain API v2 control failed for ${entityId}, falling back to legacy API:`, error);
          // Fallback to legacy API
          return controlEntity(entityId, command);
        }
      } else {
        return controlEntity(entityId, command);
      }
    },

    onSuccess: (data: ControlEntityResponse, variables) => {
      // Invalidate the specific entity and related queries
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.detail(variables.entityId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.list() });
      if (data.entity_type === 'light') {
        void queryClient.invalidateQueries({ queryKey: queryKeys.lights.list() });
      } else if (data.entity_type === 'lock') {
        void queryClient.invalidateQueries({ queryKey: queryKeys.locks.list() });
      }
    },

    onMutate: async ({ entityId, command: _command }) => {
      if (shouldUseV2) {
        // Domain API v2 handles its own optimistic updates via controlEntityV2
        return {};
      }

      // Legacy optimistic update logic
      await queryClient.cancelQueries({ queryKey: queryKeys.entities.detail(entityId) });
      const previousEntity = queryClient.getQueryData<OptimisticEntityBase>(queryKeys.entities.detail(entityId));
      const previousLights = queryClient.getQueryData<Record<string, OptimisticLightEntity>>(queryKeys.lights.list());

      // Simple optimistic update for visual feedback only - backend handles all business logic
      if (previousEntity) {
        queryClient.setQueryData<OptimisticEntityBase>(
          queryKeys.entities.detail(entityId),
          (old) => {
            if (!old) return old;
            // Simple visual feedback - mark as pending, backend determines final state
            return {
              ...old,
              _optimistic: true, // Visual indicator for pending state
              timestamp: Date.now(),
            };
          }
        );
      }
      // Simple optimistic update for lights list cache - visual feedback only
      if (previousLights && previousLights[entityId]) {
        queryClient.setQueryData<Record<string, OptimisticLightEntity>>(
          queryKeys.lights.list(),
          (old) => {
            if (!old || !old[entityId]) return old;
            return {
              ...old,
              [entityId]: {
                ...old[entityId],
                _optimistic: true, // Visual indicator for pending state
                timestamp: Date.now(),
              },
            };
          }
        );
      }
      // Start a timer to revert the optimistic update if no confirmation is received
      if (pendingTimers.current[entityId]) {
        clearTimeout(pendingTimers.current[entityId]);
      }
      pendingTimers.current[entityId] = window.setTimeout(() => {
        // Revert simple optimistic updates - backend is source of truth
        if (previousEntity) {
          queryClient.setQueryData<OptimisticEntityBase>(
            queryKeys.entities.detail(entityId),
            { ...previousEntity }
          );
        }
        if (previousLights && previousLights[entityId]) {
          queryClient.setQueryData<Record<string, OptimisticLightEntity>>(
            queryKeys.lights.list(),
            { ...previousLights }
          );
        }
        // Show a toast notification
        toast("No confirmation from backend. State reverted.");
        delete pendingTimers.current[entityId];
      }, 2000);

      return { previousEntity, previousLights };
    },

    onError: (_err, variables, context) => {
      if (shouldUseV2) {
        // Domain API v2 handles its own error recovery
        return;
      }

      // Legacy error handling
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.detail(variables.entityId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.lights.list() });
      if (pendingTimers.current[variables.entityId]) {
        clearTimeout(pendingTimers.current[variables.entityId]);
        delete pendingTimers.current[variables.entityId];
      }
    },
  });
}

/**
 * Hook for light control commands
 * Exposes only mutate and isPending for each action.
 */
export function useLightControl() {
  const controlEntity = useControlEntity();

  return {
    toggle: {
      mutate: ({ entityId }: { entityId: string }) =>
        controlEntity.mutate({ entityId, command: { command: 'toggle' } }),
      isPending: controlEntity.isPending,
    },
    turnOn: {
      mutate: ({ entityId }: { entityId: string }) =>
        controlEntity.mutate({ entityId, command: { command: 'set', state: true } }),
      isPending: controlEntity.isPending,
    },
    turnOff: {
      mutate: ({ entityId }: { entityId: string }) =>
        controlEntity.mutate({ entityId, command: { command: 'set', state: false } }),
      isPending: controlEntity.isPending,
    },
    setBrightness: {
      mutate: ({ entityId, brightness }: { entityId: string; brightness: number }) =>
        controlEntity.mutate({ entityId, command: { command: 'set', state: true, brightness } }),
      isPending: controlEntity.isPending,
    },
    brightnessUp: {
      mutate: ({ entityId }: { entityId: string }) =>
        controlEntity.mutate({ entityId, command: { command: 'brightness_up' } }),
      isPending: controlEntity.isPending,
    },
    brightnessDown: {
      mutate: ({ entityId }: { entityId: string }) =>
        controlEntity.mutate({ entityId, command: { command: 'brightness_down' } }),
      isPending: controlEntity.isPending,
    },
  };
}

//
// ===== ENHANCED DOMAIN API V2 HOOKS =====
//

/**
 * Hook for enhanced bulk entity control with Domain API v2 features
 *
 * ENHANCED VERSION: Uses Domain API v2 bulk operations when available,
 * provides comprehensive error handling and partial success support.
 * Falls back to individual legacy control operations when v2 is not available.
 *
 * @param useV2 - Force use of Domain API v2 (optional, defaults to auto-detect)
 */
export function useBulkEntityControl(useV2?: boolean) {
  const { data: isDomainAPIAvailable } = useEntitiesDomainAPIAvailability();
  const shouldUseV2 = useV2 ?? isDomainAPIAvailable;

  // Get the Domain API v2 bulk control hook for enhanced functionality
  const bulkControlV2 = useBulkControlEntitiesV2WithValidation();
  const legacyControlEntity = useControlEntity(false); // Force legacy for fallback
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      entityIds,
      command,
      ignoreErrors = true
    }: {
      entityIds: string[];
      command: ControlCommand;
      ignoreErrors?: boolean
    }) => {
      if (shouldUseV2) {
        try {
          // Convert legacy command to v2 format
          const v2Command: ControlCommandSchemaV2 = {
            command: command.command as ControlCommandSchemaV2['command'],
            ...(command.state !== undefined && { state: command.state }),
            ...(command.brightness !== undefined && { brightness: command.brightness }),
            ...(command.parameters && { parameters: command.parameters as Record<string, string | number | boolean> }),
          };

          // Use Domain API v2 bulk operations with validation
          const result = await bulkControlV2.mutateAsync({
            entity_ids: entityIds,
            command: v2Command,
            ignore_errors: ignoreErrors,
          });
          // Convert v2 result to legacy-compatible format
          return {
            successful: result.results.filter(r => r.status === 'success').map(r => r.entity_id),
            failed: result.results.filter(r => r.status !== 'success').map(r => ({
              entityId: r.entity_id,
              error: r.error_message || 'Unknown error',
              errorCode: r.error_code,
            })),
            totalTime: result.total_execution_time_ms,
          };
        } catch (error) {
          console.warn(`⚠️ Domain API v2 bulk control failed, falling back to individual legacy calls:`, error);
          // Fallback to individual legacy calls
        }
      }

      // Legacy bulk operation: individual calls
      const results = { successful: [] as string[], failed: [] as { entityId: string; error: string; errorCode?: string }[], totalTime: 0 };
      const startTime = Date.now();

      for (const entityId of entityIds) {
        try {
          await legacyControlEntity.mutateAsync({ entityId, command });
          results.successful.push(entityId);
        } catch (error) {
          results.failed.push({
            entityId,
            error: error instanceof Error ? error.message : 'Unknown error',
            errorCode: 'LEGACY_BULK_ERROR'
          });

          if (!ignoreErrors) {
            break; // Stop on first error if ignoreErrors is false
          }
        }
      }

      results.totalTime = Date.now() - startTime;

      return results;
    },
    onSuccess: (data, variables) => {
      // Invalidate all affected entities
      variables.entityIds.forEach((entityId) => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.entities.detail(entityId) });
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.list() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.lights.list() });

      // Show user feedback
      if (data.failed.length === 0) {
        toast.success(`Successfully controlled ${data.successful.length} entities`);
      } else if (data.successful.length > 0) {
        toast.warning(`Controlled ${data.successful.length} entities, ${data.failed.length} failed`);
      } else {
        toast.error(`Failed to control all ${data.failed.length} entities`);
      }
    },
    onError: (error, variables) => {
      // Invalidate queries on error
      variables.entityIds.forEach((entityId) => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.entities.detail(entityId) });
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.entities.list() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.lights.list() });

      toast.error(`Bulk operation failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    },
  });
}

/**
 * Hook for lock control commands
 */
export function useLockControl() {
  const queryClient = useQueryClient();

  const invalidateLock = (entityId: string) => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.entities.detail(entityId) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.locks.list() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.entities.list() });
  };

  return {
    lock: useMutation({
      mutationFn: lockEntity,
      onSuccess: (_, entityId) => invalidateLock(entityId),
    }),

    unlock: useMutation({
      mutationFn: unlockEntity,
      onSuccess: (_, entityId) => invalidateLock(entityId),
    }),
  };
}

/**
 * Hook to get a light entity with type safety
 */
export function useLight(entityId: string) {
  const { data, ...rest } = useEntity(entityId);

  return {
    data: data as LightEntity | undefined,
    ...rest,
  };
}

/**
 * Hook to get a lock entity with type safety
 */
export function useLock(entityId: string) {
  const { data, ...rest } = useEntity(entityId);

  return {
    data: data as LockEntity | undefined,
    ...rest,
  };
}

/**
 * Hook to get a tank sensor entity with type safety
 */
export function useTankSensor(entityId: string) {
  const { data, ...rest } = useEntity(entityId);

  return {
    data: data as TankSensorEntity | undefined,
    ...rest,
  };
}

/**
 * Hook to get a temperature sensor entity with type safety
 */
export function useTemperatureSensor(entityId: string) {
  const { data, ...rest } = useEntity(entityId);

  return {
    data: data as TemperatureSensorEntity | undefined,
    ...rest,
  };
}
