/**
 * Diagnostics Hooks
 *
 * Custom React hooks for diagnostic data management and DTC handling.
 * These hooks provide optimized data fetching with caching and real-time updates.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  fetchActiveDTCs,
  fetchBackendComputedDiagnosticStatistics,
  fetchDiagnosticStatistics,
  fetchDiagnosticFaultSummary,
  fetchDiagnosticsSystemStatus,
  fetchDiagnosticsStatus,
  fetchFaultCorrelations,
  fetchMaintenancePredictions,
  resolveDTC
} from '@/api/endpoints'
import type {
  DTCCollection,
  DTCFilters,
  DTCResolutionResponse,
  DiagnosticStats,
  FaultCorrelation,
  MaintenancePrediction
} from '@/api/types'

// Query keys for caching
const DIAGNOSTICS_KEYS = {
  status: ['diagnostics', 'status'] as const,
  dtcs: ['diagnostics', 'dtcs'] as const,
  health: ['diagnostics', 'health'] as const,
  correlations: ['diagnostics', 'correlations'] as const,
  predictions: ['diagnostics', 'predictions'] as const,
  statistics: ['diagnostics', 'statistics'] as const,
  computedStats: ['diagnostics', 'computed-stats'] as const,
}

/**
 * Hook for fetching diagnostics system status
 */
export function useDiagnosticsStatus() {
  return useQuery({
    queryKey: DIAGNOSTICS_KEYS.status,
    queryFn: fetchDiagnosticsStatus,
    staleTime: 30000, // 30 seconds
    refetchInterval: 60000, // Refetch every minute
    retry: 2,
  })
}

/**
 * Hook for fetching active DTCs with filtering
 */
export function useActiveDTCs(filters?: DTCFilters) {
  return useQuery<DTCCollection>({
    queryKey: [...DIAGNOSTICS_KEYS.dtcs, filters],
    queryFn: () => fetchActiveDTCs(filters),
    staleTime: 15000, // DTCs should be relatively fresh
    refetchInterval: 30000,
    retry: 2,
  })
}

/**
 * Hook for fetching system health information
 */
export function useSystemHealth(systemType?: string) {
  return useQuery({
    queryKey: [...DIAGNOSTICS_KEYS.health, systemType],
    queryFn: async () => {
      const [systemStatus, faultSummary] = await Promise.all([
        fetchDiagnosticsSystemStatus(),
        fetchDiagnosticFaultSummary(systemType ? { system_type: systemType } : undefined)
      ])
      return { systemStatus, faultSummary }
    },
    staleTime: 30000,
    refetchInterval: 45000,
    retry: 2,
  })
}

/**
 * Hook for fetching fault correlations
 */
export function useFaultCorrelations(timeWindowSeconds?: number) {
  return useQuery<FaultCorrelation[]>({
    queryKey: [...DIAGNOSTICS_KEYS.correlations, timeWindowSeconds],
    queryFn: () => fetchFaultCorrelations(timeWindowSeconds),
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  })
}

/**
 * Hook for fetching maintenance predictions
 */
export function useMaintenancePredictions(timeHorizonDays?: number) {
  return useQuery<MaintenancePrediction[]>({
    queryKey: [...DIAGNOSTICS_KEYS.predictions, timeHorizonDays],
    queryFn: () => fetchMaintenancePredictions(timeHorizonDays),
    staleTime: 300000, // 5 minutes - predictions change slowly
    refetchInterval: 600000, // 10 minutes
    retry: 2,
  })
}

/**
 * Hook for fetching computed diagnostic statistics
 */
export function useComputedDiagnosticStats() {
  return useQuery<DiagnosticStats>({
    queryKey: DIAGNOSTICS_KEYS.computedStats,
    queryFn: fetchBackendComputedDiagnosticStatistics,
    staleTime: 30000,
    refetchInterval: 45000,
    retry: 2,
  })
}

/**
 * Hook for fetching raw diagnostic statistics
 */
export function useDiagnosticStatistics() {
  return useQuery({
    queryKey: DIAGNOSTICS_KEYS.statistics,
    queryFn: fetchDiagnosticStatistics,
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  })
}

/**
 * Hook for resolving DTCs
 */
export function useResolveDTC() {
  const queryClient = useQueryClient()

  return useMutation<DTCResolutionResponse, Error, { protocol: string; code: number; sourceAddress: number }>({
    mutationFn: ({ protocol, code, sourceAddress }) =>
      resolveDTC(protocol, code, sourceAddress),
    onSuccess: (data) => {
      // Invalidate related queries to refresh data
      void void queryClient.invalidateQueries({ queryKey: DIAGNOSTICS_KEYS.dtcs })
      void void queryClient.invalidateQueries({ queryKey: DIAGNOSTICS_KEYS.health })
      void void queryClient.invalidateQueries({ queryKey: DIAGNOSTICS_KEYS.computedStats })
      void void queryClient.invalidateQueries({ queryKey: ['dashboard'] }) // Also invalidate dashboard

      toast.success('DTC Resolved', {
        description: `DTC ${data.dtc_id} has been marked as resolved`,
      })
    },
    onError: (error) => {
      console.error('Failed to resolve DTC:', error)
      toast.error('Failed to Resolve DTC', {
        description: error.message || 'Could not resolve the diagnostic trouble code',
      })
    },
  })
}

/**
 * Hook for invalidating diagnostics cache
 *
 * Useful for forcing refresh of diagnostics data
 */
export function useRefreshDiagnostics() {
  const queryClient = useQueryClient()

  return () => {
    // Invalidate all diagnostics queries
    Object.values(DIAGNOSTICS_KEYS).forEach(key => {
      void void queryClient.invalidateQueries({ queryKey: key })
    })

    toast.info('Diagnostics Refreshed', {
      description: 'Diagnostic data has been refreshed',
    })
  }
}

/**
 * Hook that provides optimized diagnostics state management
 *
 * Combines multiple data sources with intelligent loading states
 */
export function useDiagnosticsState(filters?: DTCFilters) {
  const status = useDiagnosticsStatus()
  const dtcs = useActiveDTCs(filters)
  const stats = useComputedDiagnosticStats()
  const correlations = useFaultCorrelations()

  return {
    // Data
    status: status.data,
    dtcs: dtcs.data,
    stats: stats.data,
    correlations: correlations.data,

    // Loading states
    isLoading: status.isLoading || dtcs.isLoading || stats.isLoading,
    isRefreshing: status.isFetching || dtcs.isFetching || stats.isFetching,

    // Error states
    error: status.error || dtcs.error || stats.error,
    hasError: status.isError || dtcs.isError || stats.isError,

    // Actions
    refresh: () => {
      void status.refetch()
      void dtcs.refetch()
      void stats.refetch()
      void correlations.refetch()
    },

    // Status helpers
    isHealthy: dtcs.data?.active_count === 0,
    activeDTCCount: dtcs.data?.active_count || 0,
    totalDTCCount: dtcs.data?.total_count || 0,
    criticalDTCs: dtcs.data?.by_severity?.critical || 0,
    healthTrend: stats.data?.system_health_trend || 'stable',
  }
}
