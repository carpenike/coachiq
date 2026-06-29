/**
 * Dashboard Hooks
 *
 * Custom React hooks for dashboard data management and aggregated API calls.
 * These hooks provide optimized data fetching with caching and real-time updates.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { bulkControlEntitiesV2 } from '@/api/domains/entities'
import {
  acknowledgeAlert,
  fetchActivityFeed,
  fetchCANBusSummary,
  fetchDashboardSummary,
  fetchEntitySummary,
  fetchSystemAnalytics,
  fetchSystemMetrics
} from '@/api/endpoints'
import type {
  ActivityFeed,
  CANBusSummary,
  DashboardSummary,
  EntitySummary,
  SystemAnalytics,
  SystemMetrics
} from '@/api/types'
import type { BulkControlRequestSchema, BulkOperationResultSchema } from '@/api/types/domains'
import { entitiesQueryKeys } from '@/hooks/useEntities'

// Query keys for caching
const DASHBOARD_KEYS = {
  summary: ['dashboard', 'summary'] as const,
  entities: ['dashboard', 'entities'] as const,
  system: ['dashboard', 'system'] as const,
  canBus: ['dashboard', 'can-bus'] as const,
  activity: ['dashboard', 'activity'] as const,
  analytics: ['dashboard', 'analytics'] as const,
}

/**
 * Hook for fetching complete dashboard summary
 *
 * Provides all dashboard data in a single optimized request with caching
 */
export function useDashboardSummary() {
  return useQuery<DashboardSummary>({
    queryKey: DASHBOARD_KEYS.summary,
    queryFn: fetchDashboardSummary,
    staleTime: 30000, // 30 seconds
    refetchInterval: 60000, // Refetch every minute
    retry: 2,
  })
}

/**
 * Hook for fetching entity summary statistics
 */
export function useEntitySummary() {
  return useQuery<EntitySummary>({
    queryKey: DASHBOARD_KEYS.entities,
    queryFn: fetchEntitySummary,
    staleTime: 30000,
    refetchInterval: 45000,
    retry: 2,
  })
}

/**
 * Hook for fetching system performance metrics
 */
export function useSystemMetrics() {
  return useQuery<SystemMetrics>({
    queryKey: DASHBOARD_KEYS.system,
    queryFn: fetchSystemMetrics,
    staleTime: 15000, // More frequent updates for system metrics
    refetchInterval: 30000,
    retry: 2,
  })
}

/**
 * Hook for fetching CAN bus summary
 */
export function useCANBusSummary() {
  return useQuery<CANBusSummary>({
    queryKey: DASHBOARD_KEYS.canBus,
    queryFn: fetchCANBusSummary,
    staleTime: 15000,
    refetchInterval: 30000,
    retry: 2,
  })
}

/**
 * Hook for fetching activity feed
 */
export function useActivityFeed(options?: { limit?: number; since?: string }) {
  return useQuery<ActivityFeed>({
    queryKey: [...DASHBOARD_KEYS.activity, options],
    queryFn: () => fetchActivityFeed(options),
    staleTime: 10000, // Activity feed should be fresh
    refetchInterval: 20000,
    retry: 2,
  })
}

/**
 * Hook for fetching system analytics and alerts
 */
export function useSystemAnalytics() {
  return useQuery<SystemAnalytics>({
    queryKey: DASHBOARD_KEYS.analytics,
    queryFn: fetchSystemAnalytics,
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  })
}

/**
 * Hook for bulk entity control operations
 */
export function useBulkControl() {
  const queryClient = useQueryClient()

  return useMutation<BulkOperationResultSchema, Error, BulkControlRequestSchema>({
    mutationFn: bulkControlEntitiesV2,
    onSuccess: (data) => {
      // Invalidate related queries to refresh data
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_KEYS.summary })
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_KEYS.entities })
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_KEYS.activity })
      void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() })

      // Show success toast
      const successMessage = data.failed_count === 0
        ? `Successfully controlled ${data.success_count} entities`
        : `Controlled ${data.success_count} entities, ${data.failed_count} failed`

      toast.success('Bulk Operation Complete', {
        description: successMessage,
      })
    },
    onError: (error) => {
      console.error('Bulk control operation failed:', error)
      toast.error('Bulk Operation Failed', {
        description: error.message || 'Failed to perform bulk control operation',
      })
    },
  })
}

/**
 * Hook for acknowledging system alerts
 */
export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()

  return useMutation<{ success: boolean; message: string }, Error, string>({
    mutationFn: acknowledgeAlert,
    onSuccess: (data, _alertId) => {
      // Invalidate analytics query to refresh alerts
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_KEYS.analytics })
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_KEYS.summary })
      void queryClient.invalidateQueries({ queryKey: DASHBOARD_KEYS.activity })

      toast.success('Alert Acknowledged', {
        description: data.message,
      })
    },
    onError: (error, alertId) => {
      console.error(`Failed to acknowledge alert ${alertId}:`, error)
      toast.error('Failed to Acknowledge Alert', {
        description: error.message || 'Could not acknowledge the alert',
      })
    },
  })
}

/**
 * Hook for invalidating dashboard cache
 *
 * Useful for forcing refresh of dashboard data
 */
export function useRefreshDashboard() {
  const queryClient = useQueryClient()

  return () => {
    // Invalidate all dashboard queries
    Object.values(DASHBOARD_KEYS).forEach(key => {
      void queryClient.invalidateQueries({ queryKey: key })
    })

    toast.info('Dashboard Refreshed', {
      description: 'Dashboard data has been refreshed',
    })
  }
}

/**
 * Hook that provides optimized dashboard state management
 *
 * Combines multiple data sources with intelligent loading states
 */
export function useDashboardState() {
  const summary = useDashboardSummary()
  const analytics = useSystemAnalytics()

  return {
    // Data
    summary: summary.data,
    analytics: analytics.data,

    // Loading states
    isLoading: summary.isLoading || analytics.isLoading,
    isRefreshing: summary.isFetching || analytics.isFetching,

    // Error states
    error: summary.error || analytics.error,
    hasError: summary.isError || analytics.isError,

    // Actions
    refresh: () => {
      void summary.refetch()
      void analytics.refetch()
    },

    // Status helpers
    isHealthy: summary.data?.quick_stats?.system_status === 'operational',
    alertCount: analytics.data?.alerts?.length || 0,
    entitiesOnlineRatio: summary.data?.entities.online_entities && summary.data?.entities.total_entities
      ? summary.data.entities.online_entities / summary.data.entities.total_entities
      : 0,
  }
}
