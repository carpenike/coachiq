/**
 * System & CAN Bus Query Hooks
 *
 * Custom React Query hooks for system status, CAN bus data, and configuration.
 * Provides optimized data fetching for monitoring and diagnostic features.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchCANInterfaces,
  fetchCANMessages,
  fetchCANMetrics,
  fetchCANStatistics,
  fetchFeatureStatus,
  fetchHealthStatus,
  fetchQueueStatus,
  fetchUnknownPGNs,
  fetchUnmappedEntries,
  sendCANMessage,
} from '../api';
import { queryKeys, STALE_TIMES } from '@/lib/query-client';
import { useEntities } from './useEntities';

/**
 * Hook to fetch CAN interface information
 */
export function useCANInterfaces() {
  return useQuery({
    queryKey: queryKeys.can.interfaces(),
    queryFn: fetchCANInterfaces,
    staleTime: STALE_TIMES.CAN_INTERFACES,
  });
}

/**
 * Hook to fetch CAN bus statistics
 */
export function useCANStatistics() {
  return useQuery({
    queryKey: queryKeys.can.statistics(),
    queryFn: fetchCANStatistics,
    staleTime: STALE_TIMES.CAN_STATISTICS,
    refetchInterval: 5000, // Auto-refetch every 5 seconds for real-time stats
    retry: (failureCount, error) => {
      // Don't retry 503 errors as they indicate CAN is not supported on this platform
      if (error instanceof Error && error.message.includes('503')) {
        return false;
      }
      return failureCount < 3;
    },
  });
}

/**
 * Hook to fetch recent CAN messages with real-time updates
 */
export function useCANMessages(options?: {
  enabled?: boolean;
  maxMessages?: number;
  refetchInterval?: number;
}) {
  const { enabled = true, maxMessages = 1000, refetchInterval = 2000 } = options || {};

  return useQuery({
    queryKey: queryKeys.can.messages(maxMessages),
    queryFn: () => fetchCANMessages({ limit: maxMessages }),
    staleTime: STALE_TIMES.CAN_STATISTICS,
    refetchInterval: enabled ? refetchInterval : false,
    enabled,
  });
}

/**
 * Hook to fetch CAN bus metrics for health monitoring
 */
export function useCANMetrics() {
  return useQuery({
    queryKey: queryKeys.can.metrics(),
    queryFn: fetchCANMetrics,
    staleTime: STALE_TIMES.CAN_STATISTICS,
    refetchInterval: 5000, // Auto-refetch every 5 seconds for real-time metrics
    retry: (failureCount, error) => {
      // Don't retry 503 errors as they indicate CAN is not supported on this platform
      if (error instanceof Error && error.message.includes('503')) {
        return false;
      }
      return failureCount < 3;
    },
  });
}

/**
 * Hook to fetch unknown PGN entries
 */
export function useUnknownPGNs() {
  return useQuery({
    queryKey: queryKeys.can.unknownPgns(),
    queryFn: fetchUnknownPGNs,
    staleTime: STALE_TIMES.UNKNOWN_PGNS,
  });
}

/**
 * Hook to fetch unmapped entries
 */
export function useUnmappedEntries() {
  return useQuery({
    queryKey: queryKeys.can.unmappedEntries(),
    queryFn: fetchUnmappedEntries,
    staleTime: STALE_TIMES.UNMAPPED_ENTRIES,
  });
}

/**
 * Hook to fetch system health status
 */
export function useHealthStatus() {
  return useQuery({
    queryKey: queryKeys.system.health(),
    queryFn: fetchHealthStatus,
    staleTime: STALE_TIMES.HEALTH_STATUS,
    refetchInterval: 30000, // Auto-refetch every 30 seconds
  });
}

/**
 * Hook to fetch feature status
 */
export function useFeatureStatus() {
  return useQuery({
    queryKey: queryKeys.system.features(),
    queryFn: fetchFeatureStatus,
    staleTime: STALE_TIMES.FEATURE_STATUS,
  });
}

/**
 * Hook to fetch queue status
 */
export function useQueueStatus() {
  return useQuery({
    queryKey: queryKeys.system.queueStatus(),
    queryFn: fetchQueueStatus,
    staleTime: STALE_TIMES.HEALTH_STATUS,
    refetchInterval: 10000, // Auto-refetch every 10 seconds
  });
}

/**
 * Hook for sending CAN messages
 */
export function useSendCANMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: sendCANMessage,

    onSuccess: () => {
      // Invalidate CAN statistics after sending a message
      void queryClient.invalidateQueries({ queryKey: queryKeys.can.statistics() });
    },
  });
}

/**
 * Hook for refreshing all CAN-related data
 */
export function useRefreshCANData() {
  const queryClient = useQueryClient();

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.can.all });
  };

  const refreshStatistics = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.can.statistics() });
  };

  const refreshUnknownPGNs = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.can.unknownPgns() });
  };

  const refreshUnmappedEntries = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.can.unmappedEntries() });
  };

  return {
    refreshAll,
    refreshStatistics,
    refreshUnknownPGNs,
    refreshUnmappedEntries,
  };
}

/**
 * Hook for refreshing all system data
 */
export function useRefreshSystemData() {
  const queryClient = useQueryClient();

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.system.all });
  };

  const refreshHealth = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.system.health() });
  };

  const refreshFeatures = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.system.features() });
  };

  const refreshQueue = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.system.queueStatus() });
  };

  return {
    refreshAll,
    refreshHealth,
    refreshFeatures,
    refreshQueue,
  };
}

/**
 * Hook for manual data refresh operations
 */
export function useDataRefresh() {
  const queryClient = useQueryClient();

  const refreshEntities = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.entities.all });
  };

  const refreshEntity = (entityId: string) => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.entities.detail(entityId) });
  };

  const refreshAll = () => {
    void queryClient.invalidateQueries();
  };

  return {
    refreshEntities,
    refreshEntity,
    refreshAll,
  };
}

/**
 * Hook for checking loading states across multiple queries
 */
export function useGlobalLoadingState() {
  const entitiesQuery = useEntities();
  const healthQuery = useHealthStatus();
  const featuresQuery = useFeatureStatus();

  const isLoading = entitiesQuery.isLoading || healthQuery.isLoading || featuresQuery.isLoading;
  const isError = entitiesQuery.isError || healthQuery.isError || featuresQuery.isError;
  const hasData = entitiesQuery.data && healthQuery.data && featuresQuery.data;

  return {
    isLoading,
    isError,
    hasData,
    errors: {
      entities: entitiesQuery.error,
      health: healthQuery.error,
      features: featuresQuery.error,
    },
  };
}

// Re-export entity hooks for convenience
export { useEntities } from './useEntities';
