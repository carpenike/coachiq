import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';
import type {
  SystemHealth,
  LivenessResponse,
  ReadinessResponse,
  StartupResponse,
  HumanHealthResponse,
  HealthMonitoringResponse
} from '@/types/health';

/**
 * Hook to fetch comprehensive system health status.
 * Uses the /api/v2/system/status endpoint with IETF format.
 */
export const useSystemHealthStatus = () => {
  return useQuery({
    queryKey: ['systemHealth'],
    queryFn: async () => {
      return await apiGet<SystemHealth>('/api/v2/system/status?format=ietf');
    },
    refetchInterval: 5000, // Poll every 5 seconds
    staleTime: 4000,
    retry: (failureCount, error: any) => {
      // Always retry on network errors, limited retries on server errors
      if (error?.response?.status === 503) {
        // System not ready is expected, don't retry excessively
        return failureCount < 2;
      }
      return failureCount < 3;
    },
  });
};

/**
 * Hook to fetch health monitoring data.
 * Only fetches when enabled (e.g., in technician mode).
 */
export const useHealthMonitoring = (enabled = false) => {
  return useQuery({
    queryKey: ['healthMonitoring'],
    queryFn: async () => {
      const response = await apiGet<HealthMonitoringResponse>('/health/monitoring');
      return response.monitoring_summary;
    },
    refetchInterval: enabled ? 10000 : false, // Poll every 10s when enabled
    enabled, // Only fetch in technician mode
  });
};

/**
 * Hook to check system readiness.
 * Uses the /readyz endpoint for comprehensive dependency checking.
 */
export const useReadinessCheck = (includeDetails = false) => {
  return useQuery({
    queryKey: ['readiness', includeDetails],
    queryFn: async () => {
      try {
        const data = await apiGet<ReadinessResponse>(
          `/readyz${includeDetails ? '?details=true' : ''}`
        );
        return {
          ready: true,
          status: 200,
          data,
        };
      } catch (error: any) {
        // Even on 503, we want to parse the response
        if (error?.status === 503 && error?.data) {
          return {
            ready: false,
            status: 503,
            data: error.data as ReadinessResponse,
          };
        }
        throw error;
      }
    },
    refetchInterval: 10000, // Less frequent for top-level check
    staleTime: 8000,
  });
};

/**
 * Hook to check liveness (process health).
 * Uses the /healthz endpoint for minimal process checking.
 */
export const useLivenessCheck = () => {
  return useQuery({
    queryKey: ['liveness'],
    queryFn: async () => {
      try {
        const data = await apiGet<LivenessResponse>('/healthz');
        return {
          alive: true,
          status: 200,
          data,
        };
      } catch (error: any) {
        if (error?.status === 503 && error?.data) {
          return {
            alive: false,
            status: 503,
            data: error.data as LivenessResponse,
          };
        }
        throw error;
      }
    },
    refetchInterval: 15000, // Less frequent, process health doesn't change often
    staleTime: 12000,
  });
};

/**
 * Hook to check startup status (hardware initialization).
 * Uses the /startupz endpoint for CAN transceiver readiness.
 */
export const useStartupCheck = () => {
  return useQuery({
    queryKey: ['startup'],
    queryFn: async () => {
      try {
        const data = await apiGet<StartupResponse>('/startupz');
        return {
          initialized: true,
          status: 200,
          data,
        };
      } catch (error: any) {
        if (error?.status === 503 && error?.data) {
          return {
            initialized: false,
            status: 503,
            data: error.data as StartupResponse,
          };
        }
        throw error;
      }
    },
    refetchInterval: ({ state }) => {
      // Poll more frequently if not initialized, less if initialized
      return state.data?.initialized ? 30000 : 5000;
    },
    staleTime: 4000,
  });
};

/**
 * Hook to fetch human-readable health information.
 * Uses the /health endpoint for diagnostic information.
 */
export const useHumanHealth = () => {
  return useQuery({
    queryKey: ['humanHealth'],
    queryFn: async () => {
      return await apiGet<HumanHealthResponse>('/health');
    },
    refetchInterval: 30000, // Update every 30s
    staleTime: 25000,
  });
};

/**
 * Combined hook for overall system health status.
 * Aggregates data from multiple health endpoints.
 */
export const useAggregatedHealth = () => {
  const { data: readiness, isError: readinessError } = useReadinessCheck();
  const { data: liveness, isError: livenessError } = useLivenessCheck();
  const { data: startup, isError: startupError } = useStartupCheck();
  const { data: systemHealth, isError: systemHealthError } = useSystemHealthStatus();

  // Determine overall status
  const isHealthy = readiness?.ready && liveness?.alive && startup?.initialized;
  const isLoading = !readiness && !liveness && !startup && !systemHealth;
  const hasError = readinessError || livenessError || startupError || systemHealthError;

  // Determine connection status
  let connectionStatus: 'connected' | 'disconnected' | 'unknown' = 'unknown';
  if (hasError) {
    connectionStatus = 'disconnected';
  } else if (liveness?.alive) {
    connectionStatus = 'connected';
  }

  return {
    isHealthy,
    isLoading,
    hasError,
    connectionStatus,
    readiness: readiness?.data,
    liveness: liveness?.data,
    startup: startup?.data,
    systemHealth,
  };
};
