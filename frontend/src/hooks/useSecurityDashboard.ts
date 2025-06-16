/**
 * React hook for security dashboard data management
 *
 * Provides real-time security event monitoring with WebSocket integration,
 * event acknowledgment, and configuration management.
 */

import { useCallback, useEffect, useMemo, useState, useContext } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { WebSocketContext } from '@/contexts/websocket-context';
import {
  fetchSecurityDashboardData,
  fetchSecurityConfiguration,
  updateSecurityConfiguration,
  acknowledgeSecurityEvent,
  fetchSecurityEvents
} from '@/api/endpoints';

// Security event type definition
export interface SecurityEvent {
  event_id: string;
  event_uuid: string;
  timestamp: number;
  event_type: string;
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  source_component: string;
  title: string;
  description: string;
  payload: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: number;
}

// Dashboard statistics
export interface SecurityStatistics {
  total_events: number;
  events_by_type: Record<string, number>;
  events_by_severity: Record<string, number>;
  events_by_component: Record<string, number>;
  recent_rate: number;
}

// Security configuration
export interface SecurityConfig {
  anomaly_detection: {
    enabled: boolean;
    rate_limit: {
      enabled: boolean;
      default_tokens_per_second: number;
      default_burst_size: number;
    };
    access_control: {
      enabled: boolean;
      mode: string;
      whitelist: number[];
      blacklist: number[];
    };
    broadcast_storm: {
      enabled: boolean;
      threshold_multiplier: number;
      window_seconds: number;
    };
  };
  persistence: {
    enabled: boolean;
    batch_size: number;
    batch_timeout: number;
  };
}

// Query keys for React Query
const QUERY_KEYS = {
  DASHBOARD_DATA: ['security', 'dashboard'],
  SECURITY_CONFIG: ['security', 'config'],
  SECURITY_EVENTS: ['security', 'events'],
} as const;

/**
 * Main security dashboard hook
 */
export function useSecurityDashboard(options?: {
  recentEventLimit?: number;
  refetchInterval?: number;
}) {
  const queryClient = useQueryClient();
  const wsContext = useContext(WebSocketContext);
  const [realtimeEvents, setRealtimeEvents] = useState<SecurityEvent[]>([]);

  // Fetch dashboard data
  const dashboardQuery = useQuery({
    queryKey: [...QUERY_KEYS.DASHBOARD_DATA, options?.recentEventLimit],
    queryFn: () => fetchSecurityDashboardData(options?.recentEventLimit ?? 20),
    refetchInterval: options?.refetchInterval ?? 30000, // 30 seconds default
    staleTime: 10000, // Consider data stale after 10 seconds
  });

  // Fetch security configuration
  const configQuery = useQuery({
    queryKey: QUERY_KEYS.SECURITY_CONFIG,
    queryFn: fetchSecurityConfiguration,
    staleTime: 60000, // Config doesn't change often
  });

  // WebSocket event handler - simplified for now
  // In a real implementation, we would need to access the actual WebSocket connection
  // For now, we'll simulate real-time updates through polling
  useEffect(() => {
    // This is a placeholder - actual WebSocket integration would be implemented
    // by extending the WebSocket provider to handle security events
    console.log('Security dashboard WebSocket integration placeholder');
  }, [queryClient]);

  // Merge realtime events with fetched events
  const allEvents = useMemo(() => {
    const fetchedEvents = dashboardQuery.data?.recent_events ?? [];
    const eventMap = new Map<string, SecurityEvent>();

    // Add fetched events with type mapping
    fetchedEvents.forEach(event => {
      const mappedEvent: SecurityEvent = {
        ...event,
        severity: event.severity as SecurityEvent['severity']
      };
      eventMap.set(event.event_id, mappedEvent);
    });

    // Add/update with realtime events
    realtimeEvents.forEach(event => eventMap.set(event.event_id, event));

    // Sort by timestamp descending
    return Array.from(eventMap.values()).sort((a, b) => b.timestamp - a.timestamp);
  }, [dashboardQuery.data?.recent_events, realtimeEvents]);

  // Acknowledge event mutation
  const acknowledgeMutation = useMutation({
    mutationFn: acknowledgeSecurityEvent,
    onSuccess: (data) => {
      // Update local state
      setRealtimeEvents(prev =>
        prev.map(event =>
          event.event_id === data.event_id
            ? { ...event, acknowledged: true, acknowledged_by: data.acknowledged_by, acknowledged_at: data.acknowledged_at }
            : event
        )
      );

      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.DASHBOARD_DATA });
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.SECURITY_EVENTS });
    },
  });

  // Update configuration mutation
  const updateConfigMutation = useMutation({
    mutationFn: updateSecurityConfiguration,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.SECURITY_CONFIG });
    },
  });

  // Get events by severity for quick filtering
  const eventsBySeverity = useMemo(() => {
    const grouped: Record<SecurityEvent['severity'], SecurityEvent[]> = {
      critical: [],
      high: [],
      medium: [],
      low: [],
      info: [],
    };

    allEvents.forEach(event => {
      grouped[event.severity].push(event);
    });

    return grouped;
  }, [allEvents]);

  // Calculate threat level based on recent events
  const threatLevel = useMemo(() => {
    const stats = dashboardQuery.data?.statistics;
    if (!stats) return 'unknown';

    const criticalCount = stats.events_by_severity.critical ?? 0;
    const highCount = stats.events_by_severity.high ?? 0;
    const recentRate = stats.recent_rate ?? 0;

    if (criticalCount > 0 || recentRate > 10) return 'critical';
    if (highCount > 5 || recentRate > 5) return 'high';
    if (highCount > 0 || recentRate > 2) return 'medium';
    if (stats.total_events > 0) return 'low';
    return 'none';
  }, [dashboardQuery.data?.statistics]);

  return {
    // Data
    events: allEvents,
    statistics: dashboardQuery.data?.statistics,
    config: configQuery.data,
    anomalyConfig: dashboardQuery.data?.anomaly_config,

    // Computed
    eventsBySeverity,
    threatLevel,

    // Loading states
    isLoading: dashboardQuery.isLoading || configQuery.isLoading,
    isError: dashboardQuery.isError || configQuery.isError,
    error: dashboardQuery.error || configQuery.error,

    // Actions
    acknowledgeEvent: acknowledgeMutation.mutate,
    updateConfig: updateConfigMutation.mutate,
    refetch: () => {
      dashboardQuery.refetch();
      configQuery.refetch();
    },

    // Mutation states
    isAcknowledging: acknowledgeMutation.isPending,
    isUpdatingConfig: updateConfigMutation.isPending,

    // WebSocket status
    isConnected: wsContext?.isConnected ?? false,
    realtimeEventCount: realtimeEvents.length,
  };
}

/**
 * Hook for paginated security event history
 */
export function useSecurityEventHistory(params?: {
  limit?: number;
  offset?: number;
  severity?: string;
  event_type?: string;
  source_component?: string;
  start_time?: number;
  end_time?: number;
  acknowledged?: boolean;
}) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: [...QUERY_KEYS.SECURITY_EVENTS, params],
    queryFn: () => fetchSecurityEvents(params),
  });

  // Pagination helpers
  const nextPage = useCallback(() => {
    const currentOffset = params?.offset ?? 0;
    const limit = params?.limit ?? 20;
    queryClient.invalidateQueries({
      queryKey: [...QUERY_KEYS.SECURITY_EVENTS, { ...params, offset: currentOffset + limit }],
    });
  }, [params, queryClient]);

  const previousPage = useCallback(() => {
    const currentOffset = params?.offset ?? 0;
    const limit = params?.limit ?? 20;
    const newOffset = Math.max(0, currentOffset - limit);
    queryClient.invalidateQueries({
      queryKey: [...QUERY_KEYS.SECURITY_EVENTS, { ...params, offset: newOffset }],
    });
  }, [params, queryClient]);

  return {
    events: query.data?.events ?? [],
    total: query.data?.total ?? 0,
    offset: query.data?.offset ?? 0,
    limit: query.data?.limit ?? 20,

    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,

    hasNextPage: (query.data?.offset ?? 0) + (query.data?.limit ?? 20) < (query.data?.total ?? 0),
    hasPreviousPage: (query.data?.offset ?? 0) > 0,

    nextPage,
    previousPage,
    refetch: query.refetch,
  };
}

/**
 * Hook for security event filtering
 */
export function useSecurityEventFilters() {
  const [filters, setFilters] = useState({
    severity: undefined as string | undefined,
    event_type: undefined as string | undefined,
    source_component: undefined as string | undefined,
    acknowledged: undefined as boolean | undefined,
    timeRange: '24h' as '1h' | '24h' | '7d' | '30d' | 'custom',
    customStartTime: undefined as number | undefined,
    customEndTime: undefined as number | undefined,
  });

  // Calculate time range
  const timeParams = useMemo(() => {
    const now = Date.now();
    switch (filters.timeRange) {
      case '1h':
        return { start_time: now - 3600000, end_time: now };
      case '24h':
        return { start_time: now - 86400000, end_time: now };
      case '7d':
        return { start_time: now - 604800000, end_time: now };
      case '30d':
        return { start_time: now - 2592000000, end_time: now };
      case 'custom':
        return {
          start_time: filters.customStartTime,
          end_time: filters.customEndTime,
        };
      default:
        return {};
    }
  }, [filters.timeRange, filters.customStartTime, filters.customEndTime]);

  // Build query params
  const queryParams = useMemo(() => ({
    severity: filters.severity,
    event_type: filters.event_type,
    source_component: filters.source_component,
    acknowledged: filters.acknowledged,
    ...timeParams,
  }), [filters, timeParams]);

  return {
    filters,
    setFilters,
    queryParams,

    // Individual filter setters
    setSeverity: (severity: string | undefined) =>
      setFilters(prev => ({ ...prev, severity })),
    setEventType: (event_type: string | undefined) =>
      setFilters(prev => ({ ...prev, event_type })),
    setSourceComponent: (source_component: string | undefined) =>
      setFilters(prev => ({ ...prev, source_component })),
    setAcknowledged: (acknowledged: boolean | undefined) =>
      setFilters(prev => ({ ...prev, acknowledged })),
    setTimeRange: (timeRange: typeof filters.timeRange) =>
      setFilters(prev => ({ ...prev, timeRange })),
    setCustomTimeRange: (start: number, end: number) =>
      setFilters(prev => ({
        ...prev,
        timeRange: 'custom',
        customStartTime: start,
        customEndTime: end
      })),

    // Reset filters
    reset: () => setFilters({
      severity: undefined,
      event_type: undefined,
      source_component: undefined,
      acknowledged: undefined,
      timeRange: '24h',
      customStartTime: undefined,
      customEndTime: undefined,
    }),
  };
}
