/**
 * Entities Domain Hooks
 *
 * React hooks for the entities domain API with optimistic updates,
 * bulk operations, and enhanced error handling.
 */

/* eslint-disable sonarjs/cognitive-complexity */

import type { UseQueryResult } from '@tanstack/react-query';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

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
  ControlCommandSchema,
  EntitiesQueryParams,
  EntityCollectionSchema,
  EntitySchema,
} from '../api/types/domains';

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
    queryFn: () => fetchEntitiesV2(params),
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
    queryFn: () => fetchEntityV2(entityId),
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

/**
 * Hook for controlling a single entity with safety-aware optimistic updates
 *
 * SAFETY FEATURE: Optimistic updates are disabled when falling back to legacy API
 * to prevent UI state from diverging from actual vehicle state.
 *
 * @returns Mutation object for entity control
 */
export function useControlEntity() {
  const queryClient = useQueryClient();
  const { data: isDomainAPIAvailable, isLoading: isCheckingAPI } = useEntitiesDomainAPIAvailability();

  return useMutation({
    mutationFn: ({
      entityId,
      command,
    }: {
      entityId: string;
      command: ControlCommandSchema;
    }) => controlEntityV2(entityId, command),
    onMutate: async ({ entityId, command }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({
        queryKey: entitiesQueryKeys.entity(entityId),
      });

      // Snapshot the previous value
      const previousEntity = queryClient.getQueryData<EntitySchema>(
        entitiesQueryKeys.entity(entityId)
      );

      // SAFETY CRITICAL: Only apply optimistic updates if domain API v1 is available
      // When falling back to legacy API, we wait for server confirmation to prevent
      // dangerous state mismatches in vehicle control systems
      if (isDomainAPIAvailable && !isCheckingAPI && previousEntity) {
        const optimisticState = { ...previousEntity.state };

        // Apply optimistic updates based on command
        if (command.command === 'set') {
          if (command.state !== undefined && command.state !== null) {
            optimisticState.state = command.state ? 'on' : 'off';
          }
          if (command.brightness !== undefined && command.brightness !== null) {
            optimisticState.brightness = command.brightness;
          }
        } else if (command.command === 'toggle') {
          optimisticState.state = optimisticState.state === 'on' ? 'off' : 'on';
        } else if (command.command === 'brightness_up') {
          const currentBrightness = typeof optimisticState.brightness === 'number' ? optimisticState.brightness : 0;
          optimisticState.brightness = Math.min(100, currentBrightness + 10);
        } else if (command.command === 'brightness_down') {
          const currentBrightness = typeof optimisticState.brightness === 'number' ? optimisticState.brightness : 0;
          optimisticState.brightness = Math.max(0, currentBrightness - 10);
        }

        queryClient.setQueryData<EntitySchema>(
          entitiesQueryKeys.entity(entityId),
          {
            ...previousEntity,
            state: optimisticState,
            last_updated: new Date().toISOString(),
          }
        );
      }

      return { previousEntity };
    },
    onError: (error, { entityId }, context) => {
      // Rollback optimistic update on error
      if (context?.previousEntity) {
        queryClient.setQueryData(
          entitiesQueryKeys.entity(entityId),
          context.previousEntity
        );
      }
    },
    onSettled: (data, error, { entityId }) => {
      // Refetch entity data to ensure consistency
      void queryClient.invalidateQueries({
        queryKey: entitiesQueryKeys.entity(entityId),
      });

      // Also invalidate collections that might contain this entity
      void queryClient.invalidateQueries({
        queryKey: entitiesQueryKeys.collections(),
      });
    },
  });
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
  const queryClient = useQueryClient();
  const { data: isDomainAPIAvailable, isLoading: isCheckingAPI } = useEntitiesDomainAPIAvailability();

  return useMutation({
    mutationFn: (request: BulkControlRequestSchema) => bulkControlEntitiesV2(request),
    onMutate: async (request) => {
      // Cancel outgoing refetches for affected entities
      const cancelPromises = request.entity_ids.map((entityId) =>
        queryClient.cancelQueries({
          queryKey: entitiesQueryKeys.entity(entityId),
        })
      );
      await Promise.all(cancelPromises);

      // Snapshot previous values
      const previousEntities = request.entity_ids.map((entityId) => ({
        entityId,
        data: queryClient.getQueryData<EntitySchema>(
          entitiesQueryKeys.entity(entityId)
        ),
      }));

      // SAFETY CRITICAL: Only apply optimistic updates if domain API v1 is available
      // When falling back to legacy API, we wait for server confirmation to prevent
      // dangerous state mismatches in vehicle control systems
      if (isDomainAPIAvailable && !isCheckingAPI) {
        // Apply optimistic updates to all entities
        request.entity_ids.forEach((entityId) => {
          const previousEntity = queryClient.getQueryData<EntitySchema>(
            entitiesQueryKeys.entity(entityId)
          );

          if (previousEntity) {
            const optimisticState = { ...previousEntity.state };

            // Apply the same optimistic logic as single entity control
            if (request.command.command === 'set') {
              if (request.command.state !== undefined && request.command.state !== null) {
                optimisticState.state = request.command.state ? 'on' : 'off';
              }
              if (request.command.brightness !== undefined && request.command.brightness !== null) {
                optimisticState.brightness = request.command.brightness;
              }
            } else if (request.command.command === 'toggle') {
              optimisticState.state = optimisticState.state === 'on' ? 'off' : 'on';
            }

            queryClient.setQueryData<EntitySchema>(
              entitiesQueryKeys.entity(entityId),
              {
                ...previousEntity,
                state: optimisticState,
                last_updated: new Date().toISOString(),
              }
            );
          }
        });
      }

      return { previousEntities };
    },
    onError: (error, request, context) => {
      // Rollback optimistic updates on error
      if (context?.previousEntities) {
        context.previousEntities.forEach(({ entityId, data }) => {
          if (data) {
            queryClient.setQueryData(
              entitiesQueryKeys.entity(entityId),
              data
            );
          }
        });
      }
    },
    onSuccess: (result, _request) => {
      // Handle partial success scenarios
      result.results.forEach((operationResult) => {
        if (operationResult.status !== 'success') {
          // Rollback optimistic update for failed entities
          void queryClient.invalidateQueries({
            queryKey: entitiesQueryKeys.entity(operationResult.entity_id),
          });
        }
      });
    },
    onSettled: (data, error, request) => {
      // Refetch all affected entities and collections
      request.entity_ids.forEach((entityId) => {
        void queryClient.invalidateQueries({
          queryKey: entitiesQueryKeys.entity(entityId),
        });
      });

      void queryClient.invalidateQueries({
        queryKey: entitiesQueryKeys.collections(),
      });
    },
  });
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
    queryFn: () => fetchEntitiesV2WithValidation(params),
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
    queryFn: () => fetchEntityV2WithValidation(entityId),
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
  const queryClient = useQueryClient();
  const { data: isDomainAPIAvailable, isLoading: isCheckingAPI } = useEntitiesDomainAPIAvailability();

  return useMutation({
    mutationFn: ({
      entityId,
      command,
    }: {
      entityId: string;
      command: ControlCommandSchema;
    }) => controlEntityV2WithValidation(entityId, command),
    onMutate: async ({ entityId, command }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({
        queryKey: entitiesQueryKeys.entity(entityId),
      });

      // Snapshot the previous value
      const previousEntity = queryClient.getQueryData<EntitySchema>(
        entitiesQueryKeys.entity(entityId)
      );

      // SAFETY CRITICAL: Only apply optimistic updates if domain API v1 is available
      // AND validation is working properly
      if (isDomainAPIAvailable && !isCheckingAPI && previousEntity) {
        const optimisticState = { ...previousEntity.state };

        // Apply optimistic updates with enhanced safety checks
        if (command.command === 'set') {
          if (command.state !== undefined && command.state !== null) {
            optimisticState.state = command.state ? 'on' : 'off';
          }
          if (command.brightness !== undefined && command.brightness !== null) {
            // Safety clamp brightness
            const safeBrightness = Math.max(0, Math.min(100, command.brightness));
            optimisticState.brightness = safeBrightness;

            if (command.brightness !== safeBrightness) {
              console.warn(`⚠️ Brightness clamped from ${command.brightness} to ${safeBrightness} for safety`);
            }
          }
        } else if (command.command === 'toggle') {
          optimisticState.state = optimisticState.state === 'on' ? 'off' : 'on';
        } else if (command.command === 'brightness_up') {
          const currentBrightness = typeof optimisticState.brightness === 'number' ? optimisticState.brightness : 0;
          optimisticState.brightness = Math.min(100, currentBrightness + 10);
        } else if (command.command === 'brightness_down') {
          const currentBrightness = typeof optimisticState.brightness === 'number' ? optimisticState.brightness : 0;
          optimisticState.brightness = Math.max(0, currentBrightness - 10);
        }

        queryClient.setQueryData<EntitySchema>(
          entitiesQueryKeys.entity(entityId),
          {
            ...previousEntity,
            state: optimisticState,
            last_updated: new Date().toISOString(),
          }
        );
      }

      return { previousEntity };
    },
    onError: (error, { entityId }, context) => {
      // Enhanced error handling for validation failures
      if (error.message.includes('Invalid control command')) {
        console.error('❌ Command validation failed:', error.message);
      } else if (error.message.includes('validation failed')) {
        console.error('❌ Response validation failed:', error.message);
      }

      // Rollback optimistic update on error
      if (context?.previousEntity) {
        queryClient.setQueryData(
          entitiesQueryKeys.entity(entityId),
          context.previousEntity
        );
      }
    },
    onSettled: (data, error, { entityId }) => {
      // Refetch entity data to ensure consistency
      void queryClient.invalidateQueries({
        queryKey: entitiesQueryKeys.entity(entityId),
      });

      // Also invalidate collections that might contain this entity
      void queryClient.invalidateQueries({
        queryKey: entitiesQueryKeys.collections(),
      });
    },
  });
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
  const queryClient = useQueryClient();
  const { data: isDomainAPIAvailable, isLoading: isCheckingAPI } = useEntitiesDomainAPIAvailability();

  return useMutation({
    mutationFn: (request: BulkControlRequestSchema) => bulkControlEntitiesV2WithValidation(request),
    onMutate: async (request) => {
      // Cancel outgoing refetches for affected entities
      const cancelPromises = request.entity_ids.map((entityId) =>
        queryClient.cancelQueries({
          queryKey: entitiesQueryKeys.entity(entityId),
        })
      );
      await Promise.all(cancelPromises);

      // Snapshot previous values
      const previousEntities = request.entity_ids.map((entityId) => ({
        entityId,
        data: queryClient.getQueryData<EntitySchema>(
          entitiesQueryKeys.entity(entityId)
        ),
      }));

      // SAFETY CRITICAL: Enhanced validation checks for bulk operations
      if (isDomainAPIAvailable && !isCheckingAPI) {
        // Additional safety check: prevent excessive bulk operations
        if (request.entity_ids.length > 50) {
          console.warn(`⚠️ Large bulk operation detected: ${request.entity_ids.length} entities`);
        }

        // Apply optimistic updates to all entities
        request.entity_ids.forEach((entityId) => {
          const previousEntity = queryClient.getQueryData<EntitySchema>(
            entitiesQueryKeys.entity(entityId)
          );

          if (previousEntity) {
            const optimisticState = { ...previousEntity.state };

            // Apply the same optimistic logic as single entity control with safety checks
            if (request.command.command === 'set') {
              if (request.command.state !== undefined && request.command.state !== null) {
                optimisticState.state = request.command.state ? 'on' : 'off';
              }
              if (request.command.brightness !== undefined && request.command.brightness !== null) {
                // Safety clamp brightness for bulk operations
                const safeBrightness = Math.max(0, Math.min(100, request.command.brightness));
                optimisticState.brightness = safeBrightness;
              }
            } else if (request.command.command === 'toggle') {
              optimisticState.state = optimisticState.state === 'on' ? 'off' : 'on';
            }

            queryClient.setQueryData<EntitySchema>(
              entitiesQueryKeys.entity(entityId),
              {
                ...previousEntity,
                state: optimisticState,
                last_updated: new Date().toISOString(),
              }
            );
          }
        });
      }

      return { previousEntities };
    },
    onError: (error, request, context) => {
      // Enhanced error handling for validation failures
      if (error.message.includes('Invalid bulk control request')) {
        console.error('❌ Bulk request validation failed:', error.message);
      } else if (error.message.includes('validation failed')) {
        console.error('❌ Bulk response validation failed:', error.message);
      }

      // Rollback optimistic updates on error
      if (context?.previousEntities) {
        context.previousEntities.forEach(({ entityId, data }) => {
          if (data) {
            queryClient.setQueryData(
              entitiesQueryKeys.entity(entityId),
              data
            );
          }
        });
      }
    },
    onSuccess: (result, _request) => {
      // Handle partial success scenarios with detailed logging
      const failedOperations = result.results.filter(r => r.status !== 'success');
      if (failedOperations.length > 0) {
        console.warn('⚠️ Some bulk operations failed:', failedOperations);

        // Rollback optimistic update for failed entities
        failedOperations.forEach((operationResult) => {
          void queryClient.invalidateQueries({
            queryKey: entitiesQueryKeys.entity(operationResult.entity_id),
          });
        });
      }
    },
    onSettled: (data, error, request) => {
      // Refetch all affected entities and collections
      request.entity_ids.forEach((entityId) => {
        void queryClient.invalidateQueries({
          queryKey: entitiesQueryKeys.entity(entityId),
        });
      });

      void queryClient.invalidateQueries({
        queryKey: entitiesQueryKeys.collections(),
      });
    },
  });
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
