/**
 * Entity Query Hooks
 *
 * Custom React Query hooks for entity management.
 * Provides type-safe, optimized data fetching for all entity types.
 *
 * Compatibility adapter backed by Domain API v2.
 *
 * UI callers still consume legacy-shaped entity records from this module while
 * they migrate to the native v2 hooks. There is no silent v1 fallback here.
 */

import { queryKeys, STALE_TIMES } from '@/lib/query-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from "sonner";
import {
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
} from '../api/domains/entities';
import { useControlEntityV2WithValidation, useBulkControlEntitiesV2WithValidation } from './domains/useEntitiesV2';
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

function toLegacyEntityBase(entity: EntitySchemaV2): EntityBase {
  const state = entity.state ?? {};
  const currentState = typeof state.state === 'string' ? state.state : 'unknown';

  return {
    entity_id: entity.entity_id,
    name: entity.name,
    friendly_name: entity.name,
    device_type: entity.device_type,
    suggested_area: entity.area ?? '',
    state: currentState,
    raw: state,
    capabilities: [],
    timestamp: new Date(entity.last_updated).getTime(),
    value: state,
    groups: [],
    id: entity.entity_id,
    last_updated: entity.last_updated,
    current_state: currentState,
  };
}

/**
 * Hook to fetch all entities as legacy-shaped records backed by Domain API v2.
 *
 * @param params - Query parameters for filtering and pagination.
 */
export function useEntities(params?: EntitiesQueryParams) {
  return useQuery({
    queryKey: queryKeys.entities.list(params),
    queryFn: async () => {
      const v2Collection = await fetchEntitiesV2WithValidation(params);
      const legacyEntities: Record<string, EntityBase> = {};
      v2Collection.entities.forEach((entity) => {
        legacyEntities[entity.entity_id] = toLegacyEntityBase(entity);
      });
      return legacyEntities;
    },
    staleTime: STALE_TIMES.ENTITIES,
  });
}

/**
 * Hook to fetch a specific entity by ID as a legacy-shaped record backed by Domain API v2.
 *
 * @param entityId - Entity ID to fetch.
 */
export function useEntity(entityId: string) {
  return useQuery({
    queryKey: queryKeys.entities.detail(entityId),
    queryFn: async () => {
      const v2Entity = await fetchEntityV2WithValidation(entityId);
      return toLegacyEntityBase(v2Entity);
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
 * Hook for generic entity control commands backed by Domain API v2.
 *
 * Returns the legacy-shaped `ControlEntityResponse` expected by existing UI callers.
 */
export function useControlEntity() {
  const queryClient = useQueryClient();
  const controlEntityV2 = useControlEntityV2WithValidation();

  return useMutation({
    mutationFn: ({ entityId, command }: { entityId: string; command: ControlCommand }) => {
      const v2Command: ControlCommandSchemaV2 = {
        command: command.command as ControlCommandSchemaV2['command'],
        ...(command.state !== undefined && { state: command.state }),
        ...(command.brightness !== undefined && { brightness: command.brightness }),
        ...(command.parameters && { parameters: command.parameters as Record<string, string | number | boolean> }),
      };

      return controlEntityV2.mutateAsync({ entityId, command: v2Command }).then((result) => ({
        success: result.status === 'success',
        message: result.error_message ?? 'Command executed successfully',
        entity_id: result.entity_id,
        entity_type: 'unknown',
        command,
        timestamp: new Date().toISOString(),
        ...(result.execution_time_ms !== undefined && result.execution_time_ms !== null && { execution_time_ms: result.execution_time_ms }),
      } satisfies ControlEntityResponse));
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
 * Hook for enhanced bulk entity control with Domain API v2 features.
 *
 * Returns the legacy-shaped bulk summary expected by existing UI callers.
 */
export function useBulkEntityControl() {
  const bulkControlV2 = useBulkControlEntitiesV2WithValidation();
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
      const v2Command: ControlCommandSchemaV2 = {
        command: command.command as ControlCommandSchemaV2['command'],
        ...(command.state !== undefined && { state: command.state }),
        ...(command.brightness !== undefined && { brightness: command.brightness }),
        ...(command.parameters && { parameters: command.parameters as Record<string, string | number | boolean> }),
      };

      const result = await bulkControlV2.mutateAsync({
        entity_ids: entityIds,
        command: v2Command,
        ignore_errors: ignoreErrors,
      });

      return {
        successful: result.results.filter(r => r.status === 'success').map(r => r.entity_id),
        failed: result.results.filter(r => r.status !== 'success').map(r => ({
          entityId: r.entity_id,
          error: r.error_message ?? 'Unknown error',
          errorCode: r.error_code,
        })),
        totalTime: result.total_execution_time_ms,
      };
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
