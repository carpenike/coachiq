/**
 * Entities Domain Hooks
 *
 * React hooks for the entities domain API with optimistic updates,
 * bulk operations, and enhanced error handling.
 */

import type { QueryClient, UseQueryResult } from '@tanstack/react-query';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState, useSyncExternalStore } from 'react';

import {
  bulkControlEntitiesV2,
  controlEntityV2,
  fetchEntitiesV2,
  fetchEntityV2,
  fetchSchemasV2,
  // Validation-enhanced functions
  fetchEntitiesV2WithValidation,
  fetchEntityV2WithValidation,
  controlEntityV2WithValidation,
  bulkControlEntitiesV2WithValidation,
} from '../api/domains/entities';
import { isDomainAPIAvailable } from '../api/domains/index';
import type {
  BulkControlRequestSchema,
  BulkOperationResultSchema,
  ControlCommandSchema,
  EntitiesQueryParams,
  EntityCollectionSchema,
  EntitySchema,
  OperationResultSchema,
} from '../api/types/domains';
import {
  acceptEntityCommandLifecycle,
  beginEntityCommandLifecycle,
  entityCommandQueryKeys,
  failEntityCommandLifecycle,
  reconcileEntityCommandLifecycle,
  type EntityCommandOperation,
  type IEntityCommandLifecycle,
  type IEntityCommandTransaction,
} from './entity-command-lifecycle';

//
// ===== QUERY KEYS =====
//

export const entitiesQueryKeys = {
  all: ['entities'] as const,
  collections: () => [...entitiesQueryKeys.all, 'collections'] as const,
  collection: (params?: EntitiesQueryParams) =>
    [...entitiesQueryKeys.collections(), params] as const,
  entities: () => [...entitiesQueryKeys.all, 'entity'] as const,
  entity: (id: string) => [...entitiesQueryKeys.entities(), id] as const,
  schemas: () => [...entitiesQueryKeys.all, 'schemas'] as const,
};

function reconcileFetchedEntity(
  queryClient: QueryClient,
  fetched: EntitySchema,
  cached: EntitySchema | undefined
): EntitySchema {
  return reconcileEntityCommandLifecycle(queryClient, fetched, 'refetch')
    ? fetched
    : (cached ?? fetched);
}

function reconcileFetchedCollection(
  queryClient: QueryClient,
  fetched: EntityCollectionSchema,
  cached: EntityCollectionSchema | undefined
): EntityCollectionSchema {
  const cachedById = new Map(cached?.entities.map((entity) => [entity.entity_id, entity]) ?? []);
  return {
    ...fetched,
    entities: fetched.entities.map((entity) =>
      reconcileFetchedEntity(queryClient, entity, cachedById.get(entity.entity_id))
    ),
  };
}

//
// ===== SAFETY HOOKS =====
//

/**
 * Hook to check if entities domain API v1 is available
 *
 * This is critical for safety - optimistic updates should only be used
 * when the v1 API is available and reliable.
 *
 * @returns Query result with availability status
 */
export function useEntitiesDomainAPIAvailability(): UseQueryResult<boolean, Error> {
  return useQuery({
    queryKey: ['domain-api-availability', 'entities'],
    queryFn: () => isDomainAPIAvailable('entities'),
    staleTime: 60000, // Check every minute
    refetchOnWindowFocus: true, // Check when window regains focus
    refetchInterval: 60000, // Poll every minute
  });
}

//
// ===== COLLECTION HOOKS =====
//

/**
 * Hook to fetch entities collection with pagination and filtering
 *
 * @param params - Query parameters for filtering and pagination
 * @returns Query result with entities collection
 */
export function useEntities(
  params?: EntitiesQueryParams
): UseQueryResult<EntityCollectionSchema, Error> {
  return useQuery({
    queryKey: entitiesQueryKeys.collection(params),
    queryFn: async ({ client, queryKey }) => {
      const collection = await fetchEntitiesV2(params);
      return reconcileFetchedCollection(
        client,
        collection,
        client.getQueryData<EntityCollectionSchema>(queryKey)
      );
    },
    staleTime: 30000, // Consider data fresh for 30 seconds
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to fetch a single entity by ID
 *
 * @param entityId - Entity ID to fetch
 * @param enabled - Whether the query should run
 * @returns Query result with entity data
 */
export function useEntity(
  entityId: string,
  enabled = true
): UseQueryResult<EntitySchema, Error> {
  return useQuery({
    queryKey: entitiesQueryKeys.entity(entityId),
    queryFn: async ({ client, queryKey }) => {
      const entity = await fetchEntityV2(entityId);
      return reconcileFetchedEntity(
        client,
        entity,
        client.getQueryData<EntitySchema>(queryKey)
      );
    },
    enabled: enabled && !!entityId,
    staleTime: 30000,
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to fetch API schemas for validation
 *
 * @returns Query result with schema definitions
 */
export function useEntitiesSchemas(): UseQueryResult<Record<string, unknown>, Error> {
  return useQuery({
    queryKey: entitiesQueryKeys.schemas(),
    queryFn: fetchSchemasV2,
    staleTime: 300000, // Schemas change rarely, cache for 5 minutes
    refetchOnWindowFocus: false,
  });
}

//
// ===== MUTATION HOOKS =====
//

interface IEntityControlVariables {
  entityId: string;
  command: ControlCommandSchema;
}

type EntityControlMutation = (
  entityId: string,
  command: ControlCommandSchema
) => Promise<OperationResultSchema>;

type BulkControlMutation = (
  request: BulkControlRequestSchema
) => Promise<BulkOperationResultSchema>;

function resultFailurePhase(status: string): 'rejected' | 'timeout' {
  return status === 'timeout' ? 'timeout' : 'rejected';
}

function invalidateEntityCaches(queryClient: QueryClient, entityIds: readonly string[]): void {
  entityIds.forEach((entityId) => {
    void queryClient.invalidateQueries({
      queryKey: entitiesQueryKeys.entity(entityId),
    });
  });
  void queryClient.invalidateQueries({
    queryKey: entitiesQueryKeys.collections(),
  });
}

function useEntityControlMutation(mutationFn: EntityControlMutation) {
  const queryClient = useQueryClient();

  return useMutation<
    OperationResultSchema,
    Error,
    IEntityControlVariables,
    IEntityCommandTransaction
  >({
    mutationFn: ({ entityId, command }) => mutationFn(entityId, command),
    onMutate: ({ entityId, command }) =>
      beginEntityCommandLifecycle(queryClient, [entityId], command),
    onError: (error, { entityId }, transaction) => {
      if (!transaction) return;
      failEntityCommandLifecycle(
        queryClient,
        transaction,
        [entityId],
        'rejected',
        error.message
      );
    },
    onSuccess: (result, { entityId }, transaction) => {
      if (!transaction) return;
      if (result.status === 'success') {
        acceptEntityCommandLifecycle(
          queryClient,
          transaction,
          entityId,
          result.operation_id
        );
        return;
      }
      failEntityCommandLifecycle(
        queryClient,
        transaction,
        [entityId],
        resultFailurePhase(result.status),
        result.error_message ?? `Command ${result.status}.`
      );
    },
    onSettled: (_data, _error, { entityId }) => {
      invalidateEntityCaches(queryClient, [entityId]);
    },
  });
}

function useBulkEntityControlMutation(mutationFn: BulkControlMutation) {
  const queryClient = useQueryClient();

  return useMutation<
    BulkOperationResultSchema,
    Error,
    BulkControlRequestSchema,
    IEntityCommandTransaction
  >({
    mutationFn: (request) => mutationFn(request),
    onMutate: ({ entity_ids: entityIds, command }) =>
      beginEntityCommandLifecycle(queryClient, entityIds, command),
    onError: (error, request, transaction) => {
      if (!transaction) return;
      failEntityCommandLifecycle(
        queryClient,
        transaction,
        request.entity_ids,
        'rejected',
        error.message
      );
    },
    onSuccess: (result, request, transaction) => {
      if (!transaction) return;
      const resultsByEntity = new Map(
        result.results.map((operationResult) => [operationResult.entity_id, operationResult])
      );
      request.entity_ids.forEach((entityId) => {
        const operationResult = resultsByEntity.get(entityId);
        if (operationResult?.status === 'success') {
          acceptEntityCommandLifecycle(
            queryClient,
            transaction,
            entityId,
            operationResult.operation_id
          );
          return;
        }
        const status = operationResult?.status ?? 'failed';
        failEntityCommandLifecycle(
          queryClient,
          transaction,
          [entityId],
          resultFailurePhase(status),
          operationResult?.error_message ?? `Command ${status}.`
        );
      });
    },
    onSettled: (_data, _error, request) => {
      invalidateEntityCaches(queryClient, request.entity_ids);
    },
  });
}

/**
 * Hook for controlling a single entity with safety-aware optimistic updates
 *
 * SAFETY FEATURE: Optimistic updates are disabled when falling back to legacy API
 * to prevent UI state from diverging from actual vehicle state.
 *
 * @returns Mutation object for entity control
 */
export function useControlEntity() {
  return useEntityControlMutation(controlEntityV2);
}

/**
 * Hook for bulk entity control operations with safety-aware optimistic updates
 *
 * SAFETY FEATURE: Optimistic updates are disabled when falling back to legacy API
 * to prevent UI state from diverging from actual vehicle state.
 *
 * @returns Mutation object for bulk operations
 */
export function useBulkControlEntities() {
  return useBulkEntityControlMutation(bulkControlEntitiesV2);
}

//
// ===== COMPOSITE HOOKS =====
//

/**
 * Hook for managing entity selection and bulk operations
 *
 * @returns Selection state and bulk operation utilities
 */
export function useEntitySelection() {
  const [selectedEntityIds, setSelectedEntityIds] = useState<string[]>([]);
  const bulkControlMutation = useBulkControlEntities();

  const selectEntity = useCallback((entityId: string) => {
    setSelectedEntityIds((prev) =>
      prev.includes(entityId) ? prev : [...prev, entityId]
    );
  }, []);

  const deselectEntity = useCallback((entityId: string) => {
    setSelectedEntityIds((prev) => prev.filter((id) => id !== entityId));
  }, []);

  const toggleEntitySelection = useCallback((entityId: string) => {
    setSelectedEntityIds((prev) =>
      prev.includes(entityId)
        ? prev.filter((id) => id !== entityId)
        : [...prev, entityId]
    );
  }, []);

  const selectAll = useCallback((entityIds: string[]) => {
    setSelectedEntityIds(entityIds);
  }, []);

  const deselectAll = useCallback(() => {
    setSelectedEntityIds([]);
  }, []);

  const executeBulkOperation = useCallback(
    (command: ControlCommandSchema, options?: { ignoreErrors?: boolean; timeout?: number }) => {
      if (selectedEntityIds.length === 0) {
        throw new Error('No entities selected for bulk operation');
      }

      const request: BulkControlRequestSchema = {
        entity_ids: selectedEntityIds,
        command,
        ignore_errors: options?.ignoreErrors ?? true,
      };

      if (options?.timeout !== undefined) {
        request.timeout_seconds = options.timeout;
      }

      return bulkControlMutation.mutate(request);
    },
    [selectedEntityIds, bulkControlMutation]
  );

  return {
    selectedEntityIds,
    selectedCount: selectedEntityIds.length,
    selectEntity,
    deselectEntity,
    toggleEntitySelection,
    selectAll,
    deselectAll,
    executeBulkOperation,
    bulkOperationState: {
      isLoading: bulkControlMutation.isPending,
      error: bulkControlMutation.error,
      data: bulkControlMutation.data,
      reset: bulkControlMutation.reset,
    },
  };
}

//
// ===== UTILITY HOOKS =====
//

/**
 * Hook for managing pagination state
 *
 * @param initialPageSize - Initial page size (default: 50)
 * @returns Pagination state and utilities
 */
export function useEntityPagination(initialPageSize = 50) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);

  const nextPage = useCallback(() => setPage((prev) => prev + 1), []);
  const prevPage = useCallback(() => setPage((prev) => Math.max(1, prev - 1)), []);
  const goToPage = useCallback((newPage: number) => setPage(Math.max(1, newPage)), []);
  const resetPagination = useCallback(() => setPage(1), []);

  return {
    page,
    pageSize,
    setPageSize,
    nextPage,
    prevPage,
    goToPage,
    resetPagination,
    paginationParams: { page, page_size: pageSize },
  };
}

/**
 * Hook for managing entity filtering
 *
 * @returns Filter state and utilities
 */
export function useEntityFilters() {
  const [filters, setFilters] = useState<Partial<EntitiesQueryParams>>({});

  const setFilter = useCallback(
    <K extends keyof EntitiesQueryParams>(key: K, value: EntitiesQueryParams[K]) => {
      setFilters((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const removeFilter = useCallback((key: keyof EntitiesQueryParams) => {
    setFilters((prev) => {
      const entries = Object.entries(prev).filter(([filterKey]) => filterKey !== key);
      return Object.fromEntries(entries) as Partial<EntitiesQueryParams>;
    });
  }, []);

  const clearFilters = useCallback(() => setFilters({}), []);

  const hasActiveFilters = Object.keys(filters).length > 0;

  return {
    filters,
    setFilter,
    removeFilter,
    clearFilters,
    hasActiveFilters,
  };
}

export interface IEntityCommandState {
  lifecycle: IEntityCommandLifecycle | undefined;
  phase: IEntityCommandLifecycle['phase'] | 'idle';
  statusText: string;
  isPending: boolean;
  isAccepted: boolean;
  isUnconfirmed: boolean;
  isConfirmed: boolean;
  isRejected: boolean;
  isTimedOut: boolean;
}

function lifecycleStatusText(lifecycle: IEntityCommandLifecycle | undefined): string {
  if (!lifecycle) return '';
  if (lifecycle.phase === 'pending') return 'Sending command…';
  if (lifecycle.phase === 'accepted') return 'Waiting for device confirmation…';
  if (lifecycle.phase === 'confirmed') {
    return lifecycle.confirmationSource === 'sse'
      ? 'Confirmed by realtime update'
      : 'Confirmed by refresh';
  }
  if (lifecycle.phase === 'timeout') return lifecycle.error ?? 'Confirmation timed out';
  return lifecycle.error ?? 'Command rejected';
}

/** Subscribe to the shared lifecycle for one entity operation. */
export function useEntityCommandState(
  entityId: string,
  operation: EntityCommandOperation
): IEntityCommandState {
  const queryClient = useQueryClient();
  const subscribe = useCallback(
    (onStoreChange: () => void) =>
      queryClient.getQueryCache().subscribe(() => onStoreChange()),
    [queryClient]
  );
  const getSnapshot = useCallback(
    () =>
      queryClient.getQueryData<IEntityCommandLifecycle>(
        entityCommandQueryKeys.operation(entityId, operation)
      ),
    [entityId, operation, queryClient]
  );
  const lifecycle = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const phase = lifecycle?.phase ?? 'idle';

  return {
    lifecycle,
    phase,
    statusText: lifecycleStatusText(lifecycle),
    isPending: phase === 'pending',
    isAccepted: phase === 'accepted',
    isUnconfirmed: phase === 'pending' || phase === 'accepted',
    isConfirmed: phase === 'confirmed',
    isRejected: phase === 'rejected',
    isTimedOut: phase === 'timeout',
  };
}

//
// ===== VALIDATION-ENHANCED HOOKS =====
//

/**
 * Hook to fetch entities with Zod runtime validation
 *
 * Uses validation-enhanced API functions that verify response data
 * against dynamic schemas from the backend, providing additional safety.
 *
 * @param params - Query parameters for filtering and pagination
 * @returns Query result with validated entities collection
 */
export function useEntitiesWithValidation(
  params?: EntitiesQueryParams
): UseQueryResult<EntityCollectionSchema, Error> {
  return useQuery({
    queryKey: [...entitiesQueryKeys.collection(params), 'validated'],
    queryFn: async ({ client, queryKey }) => {
      const collection = await fetchEntitiesV2WithValidation(params);
      return reconcileFetchedCollection(
        client,
        collection,
        client.getQueryData<EntityCollectionSchema>(queryKey)
      );
    },
    staleTime: 30000,
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to fetch a single entity with Zod runtime validation
 *
 * @param entityId - Entity ID to fetch
 * @param enabled - Whether the query should run
 * @returns Query result with validated entity data
 */
export function useEntityWithValidation(
  entityId: string,
  enabled = true
): UseQueryResult<EntitySchema, Error> {
  return useQuery({
    queryKey: [...entitiesQueryKeys.entity(entityId), 'validated'],
    queryFn: async ({ client, queryKey }) => {
      const entity = await fetchEntityV2WithValidation(entityId);
      return reconcileFetchedEntity(
        client,
        entity,
        client.getQueryData<EntitySchema>(queryKey)
      );
    },
    enabled: enabled && !!entityId,
    staleTime: 30000,
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook for controlling a single entity with validation and safety-aware optimistic updates
 *
 * Enhanced version that:
 * - Pre-validates commands with Zod schemas
 * - Post-validates API responses
 * - Provides additional safety logging
 * - Gracefully handles validation failures
 *
 * @returns Mutation object for validated entity control
 */
export function useControlEntityWithValidation() {
  return useEntityControlMutation(controlEntityV2WithValidation);
}

/**
 * Hook for bulk entity control with comprehensive validation and safety checks
 *
 * Enhanced version that:
 * - Pre-validates bulk requests with Zod schemas
 * - Post-validates bulk operation results
 * - Enforces bulk operation safety limits
 * - Provides detailed per-entity error reporting
 *
 * @returns Mutation object for validated bulk operations
 */
export function useBulkControlEntitiesWithValidation() {
  return useBulkEntityControlMutation(bulkControlEntitiesV2WithValidation);
}

//
// ===== SAFETY-AWARE CONVENIENCE HOOKS =====
//

/**
 * Hook for bulk light control with validation and safety limits
 */
export function useBulkLightControlWithValidation() {
  const bulkControlMutation = useBulkControlEntitiesWithValidation();

  const turnOn = useCallback(
    (entityIds: string[], ignoreErrors = true) => {
      return bulkControlMutation.mutate({
        entity_ids: entityIds.slice(0, 50), // Safety limit
        command: { command: 'set', state: true },
        ignore_errors: ignoreErrors,
      });
    },
    [bulkControlMutation]
  );

  const turnOff = useCallback(
    (entityIds: string[], ignoreErrors = true) => {
      return bulkControlMutation.mutate({
        entity_ids: entityIds.slice(0, 50), // Safety limit
        command: { command: 'set', state: false },
        ignore_errors: ignoreErrors,
      });
    },
    [bulkControlMutation]
  );

  const setBrightness = useCallback(
    (entityIds: string[], brightness: number, ignoreErrors = true) => {
      // Safety clamp brightness
      const safeBrightness = Math.max(0, Math.min(100, brightness));

      return bulkControlMutation.mutate({
        entity_ids: entityIds.slice(0, 50), // Safety limit
        command: { command: 'set', brightness: safeBrightness },
        ignore_errors: ignoreErrors,
      });
    },
    [bulkControlMutation]
  );

  const toggle = useCallback(
    (entityIds: string[], ignoreErrors = true) => {
      return bulkControlMutation.mutate({
        entity_ids: entityIds.slice(0, 50), // Safety limit
        command: { command: 'toggle' },
        ignore_errors: ignoreErrors,
      });
    },
    [bulkControlMutation]
  );

  return {
    turnOn,
    turnOff,
    setBrightness,
    toggle,
    isLoading: bulkControlMutation.isPending,
    error: bulkControlMutation.error,
    data: bulkControlMutation.data,
    reset: bulkControlMutation.reset,
  };
}

/**
 * Hook for enhanced entity selection with validation-aware bulk operations
 *
 * Enhanced version of useEntitySelection that integrates with validation
 * and provides additional safety features.
 */
export function useEntitySelectionWithValidation() {
  const [selectedEntityIds, setSelectedEntityIds] = useState<string[]>([]);
  const bulkLightControl = useBulkLightControlWithValidation();
  const bulkControlMutation = useBulkControlEntitiesWithValidation();

  const selectEntity = useCallback((entityId: string) => {
    setSelectedEntityIds((prev) =>
      prev.includes(entityId) ? prev : [...prev, entityId]
    );
  }, []);

  const deselectEntity = useCallback((entityId: string) => {
    setSelectedEntityIds((prev) => prev.filter((id) => id !== entityId));
  }, []);

  const toggleEntitySelection = useCallback((entityId: string) => {
    setSelectedEntityIds((prev) =>
      prev.includes(entityId)
        ? prev.filter((id) => id !== entityId)
        : [...prev, entityId]
    );
  }, []);

  const selectAll = useCallback((entityIds: string[]) => {
    // Safety limit on selection
    const safeEntityIds = entityIds.slice(0, 100);
    if (entityIds.length > 100) {
      console.warn(`⚠️ Selection limited to 100 entities (attempted ${entityIds.length})`);
    }
    setSelectedEntityIds(safeEntityIds);
  }, []);

  const deselectAll = useCallback(() => {
    setSelectedEntityIds([]);
  }, []);

  const executeBulkOperation = useCallback(
    async (command: ControlCommandSchema, options?: { ignoreErrors?: boolean; timeout?: number }) => {
      if (selectedEntityIds.length === 0) {
        throw new Error('No entities selected for bulk operation');
      }

      // Safety check for bulk operation size
      if (selectedEntityIds.length > 50) {
        throw new Error(`Bulk operation size limited to 50 entities (selected ${selectedEntityIds.length})`);
      }

      const request: BulkControlRequestSchema = {
        entity_ids: selectedEntityIds,
        command,
        ignore_errors: options?.ignoreErrors ?? true,
      };

      if (options?.timeout !== undefined) {
        request.timeout_seconds = Math.max(1, Math.min(300, options.timeout)); // Safety clamp timeout
      }

      return bulkControlMutation.mutate(request);
    },
    [selectedEntityIds, bulkControlMutation]
  );

  // Enhanced convenience methods with validation
  const turnOnSelected = useCallback(() => {
    return bulkLightControl.turnOn(selectedEntityIds);
  }, [selectedEntityIds, bulkLightControl]);

  const turnOffSelected = useCallback(() => {
    return bulkLightControl.turnOff(selectedEntityIds);
  }, [selectedEntityIds, bulkLightControl]);

  const setBrightnessSelected = useCallback((brightness: number) => {
    return bulkLightControl.setBrightness(selectedEntityIds, brightness);
  }, [selectedEntityIds, bulkLightControl]);

  const toggleSelected = useCallback(() => {
    return bulkLightControl.toggle(selectedEntityIds);
  }, [selectedEntityIds, bulkLightControl]);

  return {
    selectedEntityIds,
    selectedCount: selectedEntityIds.length,
    selectEntity,
    deselectEntity,
    toggleEntitySelection,
    selectAll,
    deselectAll,
    executeBulkOperation,
    // Enhanced convenience methods
    turnOnSelected,
    turnOffSelected,
    setBrightnessSelected,
    toggleSelected,
    // Operation state
    bulkOperationState: {
      isLoading: bulkControlMutation.isPending || bulkLightControl.isLoading,
      error: bulkControlMutation.error || bulkLightControl.error,
      data: bulkControlMutation.data || bulkLightControl.data,
      reset: () => {
        bulkControlMutation.reset();
        bulkLightControl.reset();
      },
    },
  };
}
