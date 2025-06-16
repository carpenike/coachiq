/**
 * Notification Dashboard Hook
 *
 * Custom React hook for managing notification dashboard data and real-time updates.
 * Provides state management, auto-refresh, error handling, and optimistic updates.
 *
 * Features:
 * - Real-time data fetching with configurable intervals
 * - Error handling and retry logic
 * - Loading states and data caching
 * - WebSocket integration for live updates
 * - Manual refresh capabilities
 */

import { useState, useEffect, useCallback, useRef } from 'react';

// Types
interface DashboardHealth {
  status: 'healthy' | 'warning' | 'critical';
  timestamp: string;
  queue_healthy: boolean;
  rate_limiter_healthy: boolean;
  dispatcher_healthy: boolean;
  channel_health: Record<string, boolean>;
  avg_processing_time_ms: number | null;
  success_rate_percent: number;
  queue_depth: number;
  alerts: string[];
  warnings: string[];
}

interface DashboardMetrics {
  timestamp: string;
  time_range_hours: number;
  total_notifications: number;
  successful_notifications: number;
  failed_notifications: number;
  rate_limited_notifications: number;
  debounced_notifications: number;
  avg_processing_time_ms: number;
  notifications_per_hour: number;
  channel_stats: Record<string, any>;
  level_distribution: Record<string, number>;
  hourly_volume: {
    hour: string;
    total: number;
    successful: number;
    failed: number;
  }[];
}

interface QueueStatistics {
  timestamp: string;
  pending_count: number;
  processing_count: number;
  completed_count: number;
  failed_count: number;
  dlq_count: number;
  avg_processing_time_ms: number | null;
  success_rate_percent: number;
  throughput_per_minute: number;
  oldest_pending_minutes: number | null;
  dispatcher_running: boolean;
  estimated_drain_time_minutes: number | null;
  capacity_utilization_percent: number;
}

interface RateLimitingStatus {
  timestamp: string;
  current_tokens: number;
  max_tokens: number;
  refill_rate_per_minute: number;
  token_utilization_percent: number;
  requests_last_minute: number;
  requests_blocked_last_hour: number;
  active_debounces: number;
  debounce_hit_rate_percent: number;
  channel_limits: Record<string, any>;
}

interface ChannelHealth {
  overall_enabled: boolean;
  queue_enabled: boolean;
  timestamp: string;
  channels: Record<string, {
    enabled: boolean;
    test_passed: boolean;
    last_test: string;
    status: string;
    error: string | null;
  }>;
}

interface DashboardData {
  health: DashboardHealth | null;
  metrics: DashboardMetrics | null;
  queueStats: QueueStatistics | null;
  rateLimiting: RateLimitingStatus | null;
  channelHealth: ChannelHealth | null;
}

interface DashboardOptions {
  autoRefresh?: boolean;
  refreshInterval?: number; // in milliseconds
  enableWebSocket?: boolean;
  timeRange?: number; // in hours
  onError?: (error: Error) => void;
  onDataUpdate?: (data: DashboardData) => void;
}

interface DashboardState {
  data: DashboardData;
  loading: boolean;
  error: string | null;
  lastUpdate: Date | null;
  isConnected: boolean;
}

// API functions
const fetchDashboardHealth = async (): Promise<DashboardHealth> => {
  const response = await fetch('/api/notifications/dashboard/health');
  if (!response.ok) {
    throw new Error(`Failed to fetch health status: ${response.statusText}`);
  }
  return response.json();
};

const fetchDashboardMetrics = async (hours = 24): Promise<DashboardMetrics> => {
  const response = await fetch(`/api/notifications/dashboard/metrics?hours=${hours}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch metrics: ${response.statusText}`);
  }
  return response.json();
};

const fetchQueueStatistics = async (): Promise<QueueStatistics> => {
  const response = await fetch('/api/notifications/dashboard/queue-stats');
  if (!response.ok) {
    throw new Error(`Failed to fetch queue statistics: ${response.statusText}`);
  }
  return response.json();
};

const fetchRateLimitingStatus = async (): Promise<RateLimitingStatus> => {
  const response = await fetch('/api/notifications/dashboard/rate-limiting');
  if (!response.ok) {
    throw new Error(`Failed to fetch rate limiting status: ${response.statusText}`);
  }
  return response.json();
};

const fetchChannelHealth = async (): Promise<ChannelHealth> => {
  const response = await fetch('/api/notifications/dashboard/channels/health');
  if (!response.ok) {
    throw new Error(`Failed to fetch channel health: ${response.statusText}`);
  }
  return response.json();
};

const triggerTestNotifications = async (channels?: string[]): Promise<any> => {
  const params = channels ? `?${channels.map(c => `channels=${c}`).join('&')}` : '';
  const response = await fetch(`/api/notifications/dashboard/test${params}`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to trigger test notifications: ${response.statusText}`);
  }
  return response.json();
};

const exportMetrics = async (format = 'json', hours = 24): Promise<any> => {
  const response = await fetch(`/api/notifications/dashboard/export/metrics?format=${format}&hours=${hours}`);
  if (!response.ok) {
    throw new Error(`Failed to export metrics: ${response.statusText}`);
  }
  return response.json();
};

// Main hook
export const useNotificationDashboard = (options: DashboardOptions = {}) => {
  const {
    autoRefresh = true,
    refreshInterval = 30000, // 30 seconds
    enableWebSocket = false,
    timeRange = 24,
    onError,
    onDataUpdate,
  } = options;

  const [state, setState] = useState<DashboardState>({
    data: {
      health: null,
      metrics: null,
      queueStats: null,
      rateLimiting: null,
      channelHealth: null,
    },
    loading: true,
    error: null,
    lastUpdate: null,
    isConnected: false,
  });

  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const maxRetries = 3;

  // Fetch all dashboard data
  const fetchAllData = useCallback(async (showLoading = false): Promise<void> => {
    if (showLoading) {
      setState(prev => ({ ...prev, loading: true, error: null }));
    }

    try {
      const [health, metrics, queueStats, rateLimiting, channelHealth] = await Promise.all([
        fetchDashboardHealth(),
        fetchDashboardMetrics(timeRange),
        fetchQueueStatistics(),
        fetchRateLimitingStatus(),
        fetchChannelHealth(),
      ]);

      const newData = {
        health,
        metrics,
        queueStats,
        rateLimiting,
        channelHealth,
      };

      setState(prev => ({
        ...prev,
        data: newData,
        loading: false,
        error: null,
        lastUpdate: new Date(),
        isConnected: true,
      }));

      // Reset retry count on success
      retryCountRef.current = 0;

      // Call onDataUpdate callback
      if (onDataUpdate) {
        onDataUpdate(newData);
      }

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch dashboard data';

      setState(prev => ({
        ...prev,
        loading: false,
        error: errorMessage,
        isConnected: false,
      }));

      // Call onError callback
      if (onError && error instanceof Error) {
        onError(error);
      }

      // Implement exponential backoff for retries
      retryCountRef.current++;
      if (retryCountRef.current < maxRetries && autoRefresh) {
        const retryDelay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
        setTimeout(() => fetchAllData(false), retryDelay);
      }
    }
  }, [timeRange, onError, onDataUpdate, autoRefresh]);

  // Manual refresh function
  const refresh = useCallback(async (): Promise<void> => {
    await fetchAllData(true);
  }, [fetchAllData]);

  // Test notifications function
  const testNotifications = useCallback(async (channels?: string[]): Promise<any> => {
    try {
      const result = await triggerTestNotifications(channels);

      // Refresh data after test to see updated statistics
      setTimeout(() => fetchAllData(false), 2000);

      return result;
    } catch (error) {
      if (onError && error instanceof Error) {
        onError(error);
      }
      throw error;
    }
  }, [fetchAllData, onError]);

  // Export metrics function
  const exportDashboardMetrics = useCallback(async (format = 'json'): Promise<any> => {
    try {
      return await exportMetrics(format, timeRange);
    } catch (error) {
      if (onError && error instanceof Error) {
        onError(error);
      }
      throw error;
    }
  }, [timeRange, onError]);

  // WebSocket connection setup
  const setupWebSocket = useCallback(() => {
    if (!enableWebSocket) return;

    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/notifications/dashboard`;

      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('Dashboard WebSocket connected');
        setState(prev => ({ ...prev, isConnected: true }));
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          // Handle different message types
          switch (message.type) {
            case 'health_update':
              setState(prev => ({
                ...prev,
                data: { ...prev.data, health: message.data },
                lastUpdate: new Date(),
              }));
              break;

            case 'queue_update':
              setState(prev => ({
                ...prev,
                data: { ...prev.data, queueStats: message.data },
                lastUpdate: new Date(),
              }));
              break;

            case 'rate_limit_update':
              setState(prev => ({
                ...prev,
                data: { ...prev.data, rateLimiting: message.data },
                lastUpdate: new Date(),
              }));
              break;

            case 'full_refresh':
              // Server requesting full refresh
              fetchAllData(false);
              break;

            default:
              console.log('Unknown WebSocket message type:', message.type);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      wsRef.current.onclose = (event) => {
        console.log('Dashboard WebSocket disconnected:', event.code, event.reason);
        setState(prev => ({ ...prev, isConnected: false }));

        // Attempt to reconnect after delay
        if (enableWebSocket) {
          setTimeout(setupWebSocket, 5000);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('Dashboard WebSocket error:', error);
        setState(prev => ({ ...prev, isConnected: false }));
      };

    } catch (error) {
      console.error('Failed to setup WebSocket:', error);
    }
  }, [enableWebSocket, fetchAllData]);

  // Setup auto-refresh
  useEffect(() => {
    if (autoRefresh && !enableWebSocket) {
      refreshIntervalRef.current = setInterval(() => {
        fetchAllData(false);
      }, refreshInterval);

      return () => {
        if (refreshIntervalRef.current) {
          clearInterval(refreshIntervalRef.current);
        }
      };
    }
    return undefined;
  }, [autoRefresh, enableWebSocket, refreshInterval, fetchAllData]);

  // Initial data fetch
  useEffect(() => {
    fetchAllData(true);
  }, [fetchAllData]);

  // Setup WebSocket if enabled
  useEffect(() => {
    if (enableWebSocket) {
      setupWebSocket();

      return () => {
        if (wsRef.current) {
          wsRef.current.close();
        }
      };
    }
    return undefined;
  }, [enableWebSocket, setupWebSocket]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Derived state
  const isHealthy = state.data.health?.status === 'healthy';
  const hasAlerts = (state.data.health?.alerts?.length || 0) > 0;
  const hasWarnings = (state.data.health?.warnings?.length || 0) > 0;
  const queueDepth = state.data.queueStats?.pending_count || 0;
  const successRate = state.data.health?.success_rate_percent || 0;

  return {
    // Data
    ...state.data,

    // State
    loading: state.loading,
    error: state.error,
    lastUpdate: state.lastUpdate,
    isConnected: state.isConnected,

    // Derived state
    isHealthy,
    hasAlerts,
    hasWarnings,
    queueDepth,
    successRate,

    // Actions
    refresh,
    testNotifications,
    exportMetrics: exportDashboardMetrics,

    // Configuration
    timeRange,
    autoRefresh,
    enableWebSocket,
  };
};

export default useNotificationDashboard;
