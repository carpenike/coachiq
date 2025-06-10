/**
 * API Endpoints for CoachIQ Frontend
 *
 * This module provides typed API endpoint functions that match the backend API structure.
 * All functions return Promises with properly typed responses.
 */

import {
  API_BASE,
  APIClientError,
  apiGet,
  apiPost,
  apiDelete,
  buildQueryString,
  logApiRequest,
  logApiResponse
} from './client';

import type {
  ActivityFeed,
  AllCANStats,
  BaselineDeviation,
  BulkControlRequest,
  BulkControlResponse,
  BulkOperationPayload,
  BulkOperationRequest,
  BulkOperationResponse,
  BulkOperationStatus,
  CANBusSummary,
  CANInterfaceMapping,
  CANMessage,
  CANMetrics,
  CANSendParams,
  CoachConfiguration,
  ConfigurationSystemStatus,
  ConfigurationUpdateRequest,
  ConfigurationUpdateResponse,
  ConfigurationValidation,
  ControlCommand,
  ControlEntityResponse,
  CreateEntityMappingRequest,
  CreateEntityMappingResponse,
  DashboardSummary,
  // Device Discovery Types
  DeviceAvailability,
  DeviceDiscoveryStatus,
  DeviceGroup,
  DeviceGroupRequest,
  DiagnosticStats,
  DiagnosticTroubleCode,
  DiscoverDevicesRequest,
  DiscoverDevicesResponse,
  DTCCollection,
  DTCFilters,
  DTCResolutionResponse,
  EntitiesQueryParams,
  Entity,
  EntityCollection,
  EntitySummary,
  FaultCorrelation,
  FeatureManagementResponse,
  FeatureStatusResponse,
  HealthStatus,
  HistoryEntry,
  HistoryQueryParams,
  // Auth Types
  LoginResponse,
  LockoutStatus,
  RefreshTokenRequest,
  RefreshTokenResponse,
  UnlockAccountRequest,
  User,
  MaintenancePrediction,
  MetadataResponse,
  NetworkTopology,
  OptimizationSuggestion,
  PerformanceAnalyticsStats,
  PerformanceMetrics,
  PerformanceReport,
  PollDeviceRequest,
  PollDeviceResponse,
  ProtocolBridgeStatus,
  QueueStatus,
  ResourceUsage,
  SupportedProtocols,
  SystemAnalytics,
  SystemHealthResponse,
  SystemMetrics,
  SystemSettings,
  TrendData,
  UnknownPGNResponse,
  UnmappedResponse
} from './types';

//
// ===== ENTITIES API (/api/entities) =====
//

/**
 * Fetch all entities with optional filtering
 *
 * @param params - Optional query parameters for filtering
 * @returns Promise resolving to entity collection
 */
export async function fetchEntities(params?: EntitiesQueryParams): Promise<EntityCollection> {
  const queryString = params ? buildQueryString(params) : '';
  const url = queryString ? `/api/entities?${queryString}` : '/api/entities';

  logApiRequest('GET', url, params);
  const result = await apiGet<EntityCollection>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch a specific entity by ID
 *
 * @param entityId - The entity ID to fetch
 * @returns Promise resolving to the entity data
 */
export async function fetchEntity(entityId: string): Promise<Entity> {
  const url = `/api/entities/${entityId}`;

  logApiRequest('GET', url);
  const result = await apiGet<Entity>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Control an entity (turn on/off, set brightness, etc.)
 *
 * @param entityId - The entity ID to control
 * @param command - The control command to execute
 * @returns Promise resolving to the control response
 */
export async function controlEntity(
  entityId: string,
  command: ControlCommand
): Promise<ControlEntityResponse> {
  const url = `/api/entities/${entityId}/control`;

  logApiRequest('POST', url, command);
  const result = await apiPost<ControlEntityResponse>(url, command);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch entity history
 *
 * @param entityId - The entity ID to get history for
 * @param params - Optional query parameters (limit, since)
 * @returns Promise resolving to history entries
 */
export async function fetchEntityHistory(
  entityId: string,
  params?: HistoryQueryParams
): Promise<HistoryEntry[]> {
  const queryString = params ? buildQueryString(params) : '';
  const url = queryString
    ? `/api/entities/${entityId}/history?${queryString}`
    : `/api/entities/${entityId}/history`;

  logApiRequest('GET', url, params);
  const result = await apiGet<HistoryEntry[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch unmapped CAN entries
 *
 * @returns Promise resolving to unmapped entries
 */
export async function fetchUnmappedEntries(): Promise<UnmappedResponse> {
  const url = '/api/unmapped';

  logApiRequest('GET', url);
  const result = await apiGet<UnmappedResponse>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Create entity mapping from unmapped entry
 *
 * @param request - Entity mapping configuration details
 * @returns Promise resolving to mapping creation response
 */
export async function createEntityMapping(
  request: CreateEntityMappingRequest
): Promise<CreateEntityMappingResponse> {
  const url = '/api/entities/mappings';

  logApiRequest('POST', url, request);
  const result = await apiPost<CreateEntityMappingResponse>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch unknown PGN entries
 *
 * @returns Promise resolving to unknown PGN entries
 */
export async function fetchUnknownPGNs(): Promise<UnknownPGNResponse> {
  const url = '/api/unknown-pgns';

  logApiRequest('GET', url);
  const result = await apiGet<UnknownPGNResponse>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get entity metadata (device types, areas, etc.)
 *
 * @returns Promise resolving to metadata response
 */
export async function fetchEntityMetadata(): Promise<MetadataResponse> {
  const url = '/api/metadata';

  logApiRequest('GET', url);
  const result = await apiGet<MetadataResponse>(url);
  logApiResponse(url, result);

  return result;
}

//
// ===== CAN BUS API (/api/can) =====
//

/**
 * Get available CAN interfaces
 *
 * @returns Promise resolving to list of interface names
 */
export async function fetchCANInterfaces(): Promise<string[]> {
  const url = '/api/can/interfaces';

  logApiRequest('GET', url);
  const result = await apiGet<string[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get CAN bus statistics for all interfaces
 *
 * @returns Promise resolving to CAN statistics
 */
export async function fetchCANStatistics(): Promise<AllCANStats> {
  const url = '/api/can/statistics';

  logApiRequest('GET', url);
  const result = await apiGet<AllCANStats>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get enhanced CAN statistics with backend-computed business logic and PGN-level data
 *
 * @returns Promise resolving to enhanced CAN statistics with backend aggregation
 */
export async function fetchEnhancedCANStatistics(): Promise<Record<string, unknown>> {
  const url = '/api/can/statistics/enhanced';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get backend-computed CAN metrics in exact frontend format (eliminates field mapping)
 *
 * @returns Promise resolving to CANMetrics format directly from backend
 */
export async function fetchBackendComputedCANMetrics(): Promise<CANMetrics> {
  const url = '/api/can/metrics/computed';

  logApiRequest('GET', url);
  const result = await apiGet<CANMetrics>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Send a CAN message
 *
 * @param params - CAN message parameters
 * @returns Promise resolving to send confirmation
 */
export async function sendCANMessage(params: CANSendParams): Promise<{ success: boolean; message: string }> {
  const url = '/api/can/send';

  logApiRequest('POST', url, params);
  const result = await apiPost<{ success: boolean; message: string }>(url, params);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch recent CAN messages
 *
 * @param params - Optional query parameters (limit)
 * @returns Promise resolving to CAN messages
 */
export async function fetchCANMessages(params?: { limit?: number }): Promise<CANMessage[]> {
  const queryString = params ? buildQueryString(params) : '';
  const url = queryString ? `/api/can/recent?${queryString}` : '/api/can/recent';

  logApiRequest('GET', url, params);
  const result = await apiGet<CANMessage[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get CAN bus metrics and health information with enhanced backend-computed format
 *
 * Uses backend-computed metrics endpoint with graceful fallback to field mapping
 * @returns Promise resolving to CAN metrics
 */
export async function fetchCANMetrics(): Promise<CANMetrics> {
  // Try backend-computed metrics first (Phase 3 enhancement)
  try {
    const backendMetrics = await fetchBackendComputedCANMetrics();
    logApiResponse('/api/can/metrics/computed', backendMetrics);
    return backendMetrics;
  } catch {
    // Graceful fallback to field mapping if backend-computed endpoint unavailable
    console.debug('Backend-computed CAN metrics unavailable, falling back to field mapping');
  }

  // Fallback: Use statistics endpoint with field mapping (legacy approach)
  const url = '/api/can/statistics';
  logApiRequest('GET', url);
  const statsResult = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, statsResult);

  // Transform statistics to metrics format (field name mapping)
  const summary = statsResult.summary as Record<string, unknown> || {};
  const metrics: CANMetrics = {
    messageRate: (summary.message_rate as number) || 0,
    totalMessages: (summary.total_messages as number) || 0,
    errorCount: (summary.total_errors as number) || 0,
    uptime: (summary.uptime as number) || 0
  };

  return metrics;
}

//
// ===== CONFIGURATION API (/api/config) =====
//

/**
 * Get application health status
 *
 * Special handling for health endpoint: accepts both 200 (healthy) and 503 (degraded) as valid responses
 *
 * @returns Promise resolving to health status
 */
export async function fetchHealthStatus(): Promise<HealthStatus> {
  const url = '/healthz';

  logApiRequest('GET', url);

  try {
    const result = await apiGet<HealthStatus>(url);
    logApiResponse(url, result);
    return result;
  } catch (error) {
    // For health endpoint, 503 responses contain valid degraded status data
    if (error instanceof APIClientError && error.statusCode === 503) {
      try {
        // Re-fetch to get the 503 response data directly
        const fullUrl = url.startsWith('/api') ? url : `${API_BASE}${url}`;
        const response = await fetch(fullUrl, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        });

        if (response.status === 503) {
          const degradedData = await response.json() as HealthStatus;
          logApiResponse(url, degradedData);
          return degradedData;
        }
      } catch (fetchError) {
        console.warn('Failed to parse 503 health response:', fetchError);
      }
    }

    // Re-throw other errors
    throw error;
  }
}

/**
 * Get feature status and configuration
 *
 * @returns Promise resolving to feature status response
 */
export async function fetchFeatureStatus(): Promise<FeatureStatusResponse> {
  const url = '/api/status/features';

  logApiRequest('GET', url);
  const result = await apiGet<FeatureStatusResponse>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get message queue status
 *
 * @returns Promise resolving to queue status
 */
export async function fetchQueueStatus(): Promise<QueueStatus> {
  const url = '/api/can/queue/status';

  logApiRequest('GET', url);
  const result = await apiGet<QueueStatus>(url);
  logApiResponse(url, result);

  return result;
}

//
// ===== DASHBOARD AGGREGATION API (/api/dashboard) =====
//

/**
 * Get complete dashboard summary data
 *
 * Optimized endpoint that returns all dashboard data in a single request
 * @returns Promise resolving to complete dashboard summary
 */
export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const url = '/api/dashboard/summary';

  logApiRequest('GET', url);
  const result = await apiGet<DashboardSummary>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get entity summary statistics
 *
 * @returns Promise resolving to aggregated entity statistics
 */
export async function fetchEntitySummary(): Promise<EntitySummary> {
  const url = '/api/dashboard/entities';

  logApiRequest('GET', url);
  const result = await apiGet<EntitySummary>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get system performance metrics
 *
 * @returns Promise resolving to system metrics
 */
export async function fetchSystemMetrics(): Promise<SystemMetrics> {
  const url = '/api/dashboard/system';

  logApiRequest('GET', url);
  const result = await apiGet<SystemMetrics>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get CAN bus summary
 *
 * @returns Promise resolving to CAN bus summary
 */
export async function fetchCANBusSummary(): Promise<CANBusSummary> {
  const url = '/api/dashboard/can-bus';

  logApiRequest('GET', url);
  const result = await apiGet<CANBusSummary>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get activity feed
 *
 * @param params - Optional query parameters (limit, since)
 * @returns Promise resolving to activity feed
 */
export async function fetchActivityFeed(params?: { limit?: number; since?: string }): Promise<ActivityFeed> {
  const queryString = params ? buildQueryString(params) : '';
  const url = queryString ? `/api/dashboard/activity?${queryString}` : '/api/dashboard/activity';

  logApiRequest('GET', url, params);
  const result = await apiGet<ActivityFeed>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Perform bulk control operations on multiple entities
 *
 * @param request - Bulk control request with entity IDs and command
 * @returns Promise resolving to bulk control response
 */
export async function bulkControlEntities(request: BulkControlRequest): Promise<BulkControlResponse> {
  const url = '/api/dashboard/bulk-control';

  logApiRequest('POST', url, request);
  const result = await apiPost<BulkControlResponse>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Get system analytics and monitoring data
 *
 * @returns Promise resolving to system analytics
 */
export async function fetchSystemAnalytics(): Promise<SystemAnalytics> {
  const url = '/api/dashboard/analytics';

  logApiRequest('GET', url);
  const result = await apiGet<SystemAnalytics>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Acknowledge a system alert
 *
 * @param alertId - ID of the alert to acknowledge
 * @returns Promise resolving to acknowledgment response
 */
export async function acknowledgeAlert(alertId: string): Promise<{ success: boolean; message: string }> {
  const url = `/api/dashboard/alerts/${alertId}/acknowledge`;

  logApiRequest('POST', url);
  const result = await apiPost<{ success: boolean; message: string }>(url, {});
  logApiResponse(url, result);

  return result;
}

//
// ===== ADVANCED DIAGNOSTICS API (/api/diagnostics) =====
//

/**
 * Get comprehensive system health status
 *
 * @param systemType - Optional specific system to query, or null for all systems
 * @returns Promise resolving to system health response
 */
export async function fetchSystemHealth(systemType?: string): Promise<SystemHealthResponse> {
  const queryString = systemType ? buildQueryString({ system_type: systemType }) : '';
  const url = queryString ? `/api/diagnostics/health?${queryString}` : '/api/diagnostics/health';

  logApiRequest('GET', url, { systemType });
  const result = await apiGet<SystemHealthResponse>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get backend-computed health status with UI categorization
 *
 * @returns Promise resolving to backend-computed health status
 */
export async function fetchBackendComputedHealthStatus(): Promise<Record<string, unknown>> {
  const url = '/api/performance/health-computed';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get backend-computed resource utilization with status classification
 *
 * @returns Promise resolving to backend-computed resource status
 */
export async function fetchBackendComputedResourceStatus(): Promise<Record<string, unknown>> {
  const url = '/api/performance/resources-computed';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get backend-computed API performance with status classification
 *
 * @returns Promise resolving to backend-computed API performance
 */
export async function fetchBackendComputedAPIPerformance(): Promise<Record<string, unknown>> {
  const url = '/api/performance/api-performance-computed';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get backend-computed DTC collection with aggregated business logic (Phase 3 enhancement)
 *
 * @param filters - Optional filtering parameters (system_type, severity, protocol)
 * @returns Promise resolving to backend-computed DTC collection
 */
export async function fetchBackendComputedDTCs(filters?: DTCFilters): Promise<DTCCollection> {
  const queryString = filters ? buildQueryString(filters as Record<string, unknown>) : '';
  const url = queryString ? `/api/diagnostics/dtcs?${queryString}` : '/api/diagnostics/dtcs';

  logApiRequest('GET', url, filters);
  const result = await apiGet<DTCCollection>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get active diagnostic trouble codes with enhanced backend computation and graceful fallback
 *
 * @param filters - Optional filtering parameters (system_type, severity, protocol)
 * @returns Promise resolving to DTC collection
 */
export async function fetchActiveDTCs(filters?: DTCFilters): Promise<DTCCollection> {
  // Try backend-computed DTCs first (Phase 3 enhancement)
  try {
    const backendDTCs = await fetchBackendComputedDTCs(filters);
    return backendDTCs;
  } catch {
    // Graceful fallback to frontend aggregation if backend-computed endpoint unavailable
    console.debug('Backend-computed DTCs unavailable, falling back to frontend aggregation');
  }

  // Fallback: Use basic endpoint with frontend aggregation (legacy approach)
  const queryString = filters ? buildQueryString(filters as Record<string, unknown>) : '';
  const url = queryString ? `/api/diagnostics/dtcs?${queryString}` : '/api/diagnostics/dtcs';

  logApiRequest('GET', url, filters);
  const rawResult = await apiGet<DiagnosticTroubleCode[]>(url);
  logApiResponse(url, rawResult);

  // Frontend aggregation business logic (temporary fallback)
  const result: DTCCollection = {
    dtcs: rawResult,
    total_count: rawResult.length,
    active_count: rawResult.filter(dtc => !dtc.resolved).length,
    by_severity: rawResult.reduce((acc, dtc) => {
      acc[dtc.severity] = (acc[dtc.severity] || 0) + 1;
      return acc;
    }, {} as Record<string, number>),
    by_protocol: rawResult.reduce((acc, dtc) => {
      acc[dtc.protocol] = (acc[dtc.protocol] || 0) + 1;
      return acc;
    }, {} as Record<string, number>)
  };

  return result;
}

/**
 * Resolve a diagnostic trouble code
 *
 * @param protocol - Protocol name
 * @param code - DTC code number
 * @param sourceAddress - CAN source address
 * @returns Promise resolving to resolution response
 */
export async function resolveDTC(
  protocol: string,
  code: number,
  sourceAddress: number = 0
): Promise<DTCResolutionResponse> {
  const url = '/api/diagnostics/dtc';
  const request = { protocol, code, source_address: sourceAddress };

  logApiRequest('DELETE', url, request);
  const result = await fetch(`${API_BASE}${url}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });

  if (!result.ok) {
    throw new APIClientError(`HTTP ${result.status}: ${result.statusText}`, result.status);
  }

  const response = await result.json() as { resolved: boolean };
  const dtcResponse: DTCResolutionResponse = {
    resolved: response.resolved,
    dtc_id: `${protocol}-${code}-${sourceAddress}`,
    message: response.resolved ? 'DTC resolved successfully' : 'Failed to resolve DTC',
    timestamp: new Date().toISOString()
  };

  logApiResponse(url, dtcResponse);
  return dtcResponse;
}

/**
 * Get fault correlations within a specified time window
 *
 * @param timeWindowSeconds - Optional time window for correlation analysis (seconds)
 * @returns Promise resolving to fault correlations
 */
export async function fetchFaultCorrelations(timeWindowSeconds?: number): Promise<FaultCorrelation[]> {
  const queryString = timeWindowSeconds ? buildQueryString({ time_window_seconds: timeWindowSeconds }) : '';
  const url = queryString ? `/api/diagnostics/correlations?${queryString}` : '/api/diagnostics/correlations';

  logApiRequest('GET', url, { timeWindowSeconds });
  const result = await apiGet<FaultCorrelation[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get maintenance predictions for the specified time horizon
 *
 * @param timeHorizonDays - Planning horizon in days (default: 90)
 * @returns Promise resolving to maintenance predictions
 */
export async function fetchMaintenancePredictions(timeHorizonDays: number = 90): Promise<MaintenancePrediction[]> {
  const queryString = buildQueryString({ time_horizon_days: timeHorizonDays });
  const url = `/api/diagnostics/predictions?${queryString}`;

  logApiRequest('GET', url, { timeHorizonDays });
  const result = await apiGet<MaintenancePrediction[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get backend-computed diagnostic statistics in exact frontend format (Phase 3 enhancement)
 *
 * @returns Promise resolving to backend-computed diagnostic statistics
 */
export async function fetchBackendComputedDiagnosticStatistics(): Promise<DiagnosticStats> {
  const url = '/api/diagnostics/statistics/computed';

  logApiRequest('GET', url);
  const result = await apiGet<DiagnosticStats>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get comprehensive diagnostic processing statistics with enhanced backend computation and graceful fallback
 *
 * @returns Promise resolving to diagnostic statistics
 */
export async function fetchDiagnosticStatistics(): Promise<DiagnosticStats> {
  // Try backend-computed statistics first (Phase 3 enhancement)
  try {
    const backendStats = await fetchBackendComputedDiagnosticStatistics();
    return backendStats;
  } catch {
    // Graceful fallback to field mapping if backend-computed endpoint unavailable
    console.debug('Backend-computed diagnostic statistics unavailable, falling back to field mapping');
  }

  // Fallback: Use basic endpoint with field mapping (legacy approach)
  const url = '/api/diagnostics/statistics';
  logApiRequest('GET', url);
  const rawResult = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, rawResult);

  // Transform the backend response to our expected DiagnosticStats format (field mapping)
  const diagnostics = rawResult.diagnostics as Record<string, unknown> || {};
  const predictive = rawResult.predictive as Record<string, unknown> || {};

  const result: DiagnosticStats = {
    total_dtcs: (diagnostics.total_dtcs as number) || 0,
    active_dtcs: (diagnostics.active_dtcs as number) || 0,
    resolved_dtcs: (diagnostics.resolved_dtcs as number) || 0,
    processing_rate: (diagnostics.processing_rate as number) || 0,
    correlation_accuracy: (predictive.correlation_accuracy as number) || 0,
    prediction_accuracy: (predictive.prediction_accuracy as number) || 0,
    system_health_trend: (diagnostics.system_health_trend as "improving" | "stable" | "degrading") || "stable",
    last_updated: new Date().toISOString()
  };

  return result;
}

/**
 * Get diagnostic feature status
 *
 * @returns Promise resolving to diagnostics status
 */
export async function fetchDiagnosticsStatus(): Promise<Record<string, unknown>> {
  const url = '/api/diagnostics/status';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

//
// ===== PERFORMANCE ANALYTICS API (/api/performance-analytics) =====
//

/**
 * Get performance metrics across all protocols and systems
 *
 * @returns Promise resolving to performance metrics
 */
export async function fetchPerformanceMetrics(): Promise<PerformanceMetrics> {
  const url = '/api/performance/metrics';

  logApiRequest('GET', url);
  const result = await apiGet<PerformanceMetrics>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get system resource utilization metrics
 *
 * @returns Promise resolving to resource usage data
 */
export async function fetchResourceUtilization(): Promise<ResourceUsage> {
  const url = '/api/performance/resource-utilization';

  logApiRequest('GET', url);
  const result = await apiGet<ResourceUsage>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get performance trends for a specified time range
 *
 * @param timeRange - Time range for trend analysis (e.g., '1h', '24h', '7d')
 * @returns Promise resolving to trend data
 */
export async function fetchPerformanceTrends(timeRange: string): Promise<TrendData[]> {
  const queryString = buildQueryString({ time_range: timeRange });
  const url = `/api/performance/trends?${queryString}`;

  logApiRequest('GET', url, { timeRange });
  const result = await apiGet<TrendData[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get optimization recommendations for system performance
 *
 * @returns Promise resolving to optimization suggestions
 */
export async function fetchOptimizationRecommendations(): Promise<OptimizationSuggestion[]> {
  const url = '/api/performance/optimization-recommendations';

  logApiRequest('GET', url);
  const result = await apiGet<OptimizationSuggestion[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get performance analytics feature status
 *
 * @returns Promise resolving to performance analytics status
 */
export async function fetchPerformanceStatus(): Promise<Record<string, unknown>> {
  const url = '/api/performance/status';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get baseline deviations for performance metrics
 *
 * @param timeWindowSeconds - Time window for deviation analysis (default: 3600)
 * @returns Promise resolving to baseline deviation alerts
 */
export async function fetchBaselineDeviations(timeWindowSeconds: number = 3600): Promise<BaselineDeviation[]> {
  const queryString = buildQueryString({ time_window_seconds: timeWindowSeconds });
  const url = `/api/performance/baseline-deviations?${queryString}`;

  logApiRequest('GET', url, { timeWindowSeconds });
  const result = await apiGet<BaselineDeviation[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get protocol throughput metrics
 *
 * @returns Promise resolving to protocol throughput data
 */
export async function fetchProtocolThroughput(): Promise<Record<string, number>> {
  const url = '/api/performance/protocol-throughput';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, number>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get comprehensive performance analytics statistics
 *
 * @returns Promise resolving to analytics statistics
 */
export async function fetchPerformanceStatistics(): Promise<PerformanceAnalyticsStats> {
  const url = '/api/performance/statistics';

  logApiRequest('GET', url);
  const result = await apiGet<PerformanceAnalyticsStats>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Generate comprehensive performance analysis report
 *
 * @param timeWindowSeconds - Time window for report (default: 3600)
 * @returns Promise resolving to performance report
 */
export async function generatePerformanceReport(timeWindowSeconds: number = 3600): Promise<PerformanceReport> {
  const url = '/api/performance/report';

  logApiRequest('POST', url, { time_window_seconds: timeWindowSeconds });
  const result = await apiPost<PerformanceReport>(url, { time_window_seconds: timeWindowSeconds });
  logApiResponse(url, result);

  return result;
}

//
// ===== MULTI-PROTOCOL API (/api/entities with protocol filtering) =====
//

/**
 * Fetch J1939 protocol entities
 *
 * @returns Promise resolving to J1939 entity collection
 */
export async function fetchJ1939Entities(): Promise<EntityCollection> {
  return fetchEntities({ protocol: 'j1939' } as EntitiesQueryParams);
}

/**
 * Fetch Firefly protocol entities
 *
 * @returns Promise resolving to Firefly entity collection
 */
export async function fetchFireflyEntities(): Promise<EntityCollection> {
  return fetchEntities({ protocol: 'firefly' } as EntitiesQueryParams);
}

/**
 * Fetch Spartan K2 protocol entities
 *
 * @returns Promise resolving to Spartan K2 entity collection
 */
export async function fetchSpartanK2Entities(): Promise<EntityCollection> {
  return fetchEntities({ protocol: 'spartan_k2' } as EntitiesQueryParams);
}

/**
 * Get cross-protocol bridge status
 *
 * @returns Promise resolving to protocol bridge status
 */
export async function fetchProtocolBridgeStatus(): Promise<ProtocolBridgeStatus> {
  const url = '/api/multi-network/bridge-status';

  logApiRequest('GET', url);
  const result = await apiGet<ProtocolBridgeStatus>(url);
  logApiResponse(url, result);

  return result;
}

//
// ===== CONVENIENCE FUNCTIONS =====
//

/**
 * Fetch only light entities
 * Convenience function that filters entities by device_type=light
 *
 * @returns Promise resolving to light entities only
 */
export async function fetchLights(): Promise<EntityCollection> {
  return fetchEntities({ device_type: 'light' });
}

/**
 * Fetch only lock entities
 * Convenience function that filters entities by device_type=lock
 *
 * @returns Promise resolving to lock entities only
 */
export async function fetchLocks(): Promise<EntityCollection> {
  return fetchEntities({ device_type: 'lock' });
}

/**
 * Fetch only temperature sensor entities
 * Convenience function that filters entities by device_type=temperature_sensor
 *
 * @returns Promise resolving to temperature sensor entities only
 */
export async function fetchTemperatureSensors(): Promise<EntityCollection> {
  return fetchEntities({ device_type: 'temperature_sensor' });
}

/**
 * Fetch only tank sensor entities
 * Convenience function that filters entities by device_type=tank_sensor
 *
 * @returns Promise resolving to tank sensor entities only
 */
export async function fetchTankSensors(): Promise<EntityCollection> {
  return fetchEntities({ device_type: 'tank_sensor' });
}

//
// ===== LIGHT CONTROL CONVENIENCE FUNCTIONS =====
//

/**
 * Turn a light on
 *
 * @param entityId - The light entity ID
 * @returns Promise resolving to control response
 */
export async function turnLightOn(entityId: string): Promise<ControlEntityResponse> {
  return controlEntity(entityId, { command: 'set', state: true });
}

/**
 * Turn a light off
 *
 * @param entityId - The light entity ID
 * @returns Promise resolving to control response
 */
export async function turnLightOff(entityId: string): Promise<ControlEntityResponse> {
  return controlEntity(entityId, { command: 'set', state: false });
}

/**
 * Toggle a light on/off
 *
 * @param entityId - The light entity ID
 * @returns Promise resolving to control response
 */
export async function toggleLight(entityId: string): Promise<ControlEntityResponse> {
  return controlEntity(entityId, { command: 'toggle', parameters: {} });
}

/**
 * Set light brightness
 *
 * @param entityId - The light entity ID
 * @param brightness - Brightness level (0-100)
 * @returns Promise resolving to control response
 */
export async function setLightBrightness(
  entityId: string,
  brightness: number
): Promise<ControlEntityResponse> {
  return controlEntity(entityId, {
    command: 'set',
    state: true, // Setting brightness usually implies turning the light on
    brightness: Math.max(0, Math.min(100, brightness))
  });
}

/**
 * Increase light brightness by 10%
 *
 * @param entityId - The light entity ID
 * @returns Promise resolving to control response
 */
export async function brightnessUp(entityId: string): Promise<ControlEntityResponse> {
  return controlEntity(entityId, { command: 'brightness_up', parameters: {} });
}

/**
 * Decrease light brightness by 10%
 *
 * @param entityId - The light entity ID
 * @returns Promise resolving to control response
 */
export async function brightnessDown(entityId: string): Promise<ControlEntityResponse> {
  return controlEntity(entityId, { command: 'brightness_down', parameters: {} });
}

//
// ===== LOCK CONTROL CONVENIENCE FUNCTIONS =====
//

/**
 * Lock a lock entity
 *
 * @param entityId - The lock entity ID
 * @returns Promise resolving to control response
 */
export async function lockEntity(entityId: string): Promise<ControlEntityResponse> {
  return controlEntity(entityId, { command: 'lock', parameters: {} });
}

/**
 * Unlock a lock entity
 *
 * @param entityId - The lock entity ID
 * @returns Promise resolving to control response
 */
export async function unlockEntity(entityId: string): Promise<ControlEntityResponse> {
  return controlEntity(entityId, { command: 'unlock', parameters: {} });
}

//
// ===== CONFIGURATION MANAGEMENT API (/api/config) =====
//

/**
 * Fetch complete system settings overview
 *
 * @returns Promise resolving to system settings with all configuration sections
 */
export async function fetchSystemSettings(): Promise<SystemSettings> {
  const url = '/api/config/settings';

  logApiRequest('GET', url);
  const result = await apiGet<SystemSettings>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch feature management information with dependencies
 *
 * @returns Promise resolving to feature management response
 */
export async function fetchFeatureManagement(): Promise<FeatureManagementResponse> {
  const url = '/api/config/features';

  logApiRequest('GET', url);
  const result = await apiGet<FeatureManagementResponse>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Update a configuration setting
 *
 * @param request - Configuration update request
 * @returns Promise resolving to update response
 */
export async function updateConfiguration(request: ConfigurationUpdateRequest): Promise<ConfigurationUpdateResponse> {
  const url = '/api/config/update';

  logApiRequest('POST', url, request);
  const result = await apiPost<ConfigurationUpdateResponse>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Validate configuration settings
 *
 * @param section - Configuration section to validate
 * @returns Promise resolving to validation result
 */
export async function validateConfiguration(section?: string): Promise<ConfigurationValidation> {
  const url = section ? `/api/config/validate?section=${section}` : '/api/config/validate';

  logApiRequest('GET', url);
  const result = await apiGet<ConfigurationValidation>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch CAN interface mappings and convert to array format
 *
 * @returns Promise resolving to CAN interface mappings
 */
export async function fetchCANInterfaceMappings(): Promise<CANInterfaceMapping[]> {
  const url = '/api/config/can/interfaces';

  logApiRequest('GET', url);

  interface CANInterfacesResponse {
    mappings: Record<string, {
      physical_interface?: string;
      bitrate?: number;
      is_active?: boolean;
      last_activity?: string;
      message_count?: number;
      error_count?: number;
    }>;
    validation: Record<string, {
      status?: string;
      message?: string;
    }>;
  }

  const result = await apiGet<CANInterfacesResponse>(url);
  logApiResponse(url, result);

  // Convert the mappings object to an array format expected by the frontend
  const mappingsArray: CANInterfaceMapping[] = Object.entries(result.mappings || {}).map(([logical_name, mapping]) => ({
    logical_name,
    physical_interface: mapping.physical_interface || '',
    bitrate: mapping.bitrate || 0,
    is_active: mapping.is_active || false,
    last_activity: mapping.last_activity,
    message_count: mapping.message_count || 0,
    error_count: mapping.error_count || 0,
    validation_status: (result.validation[logical_name]?.status as "valid" | "invalid" | "warning") || "invalid",
    validation_message: result.validation[logical_name]?.message
  }));

  return mappingsArray;
}

/**
 * Update a CAN interface mapping
 *
 * @param logicalName - Logical interface name
 * @param physicalInterface - Physical interface name
 * @returns Promise resolving to updated mapping
 */
export async function updateCANInterfaceMapping(
  logicalName: string,
  physicalInterface: string
): Promise<CANInterfaceMapping> {
  const url = `/api/config/can/interfaces/${logicalName}`;

  logApiRequest('PUT', url, { physical_interface: physicalInterface });
  const result = await apiPost<CANInterfaceMapping>(url, { physical_interface: physicalInterface });
  logApiResponse(url, result);

  return result;
}

/**
 * Validate CAN interface mappings
 *
 * @returns Promise resolving to validation result
 */
export async function validateCANInterfaceMappings(): Promise<ConfigurationValidation> {
  const url = '/api/config/can/interfaces/validate';

  logApiRequest('POST', url);
  const result = await apiPost<ConfigurationValidation>(url, {});
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch coach configuration metadata
 *
 * @returns Promise resolving to coach configuration
 */
export async function fetchCoachConfiguration(): Promise<CoachConfiguration> {
  const url = '/api/config/coach/metadata';

  logApiRequest('GET', url);
  const result = await apiGet<CoachConfiguration>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch device mapping file content
 *
 * @returns Promise resolving to device mapping data
 */
export async function fetchDeviceMapping(): Promise<Record<string, unknown>> {
  const url = '/api/config/device_mapping';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch RV-C specification file content
 *
 * @returns Promise resolving to RV-C spec data
 */
export async function fetchRVCSpecification(): Promise<Record<string, unknown>> {
  const url = '/api/config/spec';

  logApiRequest('GET', url);
  const result = await apiGet<Record<string, unknown>>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Fetch system status for configuration monitoring
 *
 * @returns Promise resolving to configuration system status
 */
export async function fetchConfigurationSystemStatus(): Promise<ConfigurationSystemStatus> {
  const url = '/api/config/system/status';

  logApiRequest('GET', url);
  const result = await apiGet<ConfigurationSystemStatus>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Enable a feature flag
 *
 * @param featureName - Name of the feature to enable
 * @returns Promise resolving to feature management response
 */
export async function enableFeature(featureName: string): Promise<FeatureManagementResponse> {
  return updateConfiguration({
    section: 'features',
    key: featureName,
    value: true,
    persist: true,
    validate_before_apply: true
  }).then(() => fetchFeatureManagement());
}

/**
 * Disable a feature flag
 *
 * @param featureName - Name of the feature to disable
 * @returns Promise resolving to feature management response
 */
export async function disableFeature(featureName: string): Promise<FeatureManagementResponse> {
  return updateConfiguration({
    section: 'features',
    key: featureName,
    value: false,
    persist: true,
    validate_before_apply: true
  }).then(() => fetchFeatureManagement());
}

//
// ===== DEVICE DISCOVERY API (/api/discovery) =====
//

/**
 * Get network topology information
 *
 * @returns Promise resolving to network topology data
 */
export async function fetchNetworkTopology(): Promise<NetworkTopology> {
  const url = '/api/discovery/topology';

  logApiRequest('GET', url);
  const result = await apiGet<NetworkTopology>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get device availability statistics
 *
 * @returns Promise resolving to device availability data
 */
export async function fetchDeviceAvailability(): Promise<DeviceAvailability> {
  const url = '/api/discovery/availability';

  logApiRequest('GET', url);
  const result = await apiGet<DeviceAvailability>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Perform device discovery for a specific protocol
 *
 * @param protocol - Protocol to use for discovery (default: "rvc")
 * @returns Promise resolving to discovery results
 */
export async function discoverDevices(protocol: string = "rvc"): Promise<DiscoverDevicesResponse> {
  const url = '/api/discovery/discover';
  const request: DiscoverDevicesRequest = { protocol };

  logApiRequest('POST', url, request);
  const result = await apiPost<DiscoverDevicesResponse>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Poll a specific device for status information
 *
 * @param request - Polling configuration
 * @returns Promise resolving to polling result
 */
export async function pollDevice(request: PollDeviceRequest): Promise<PollDeviceResponse> {
  const url = '/api/discovery/poll';

  logApiRequest('POST', url, request);
  const result = await apiPost<PollDeviceResponse>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Get device discovery service status
 *
 * @returns Promise resolving to service status
 */
export async function fetchDeviceDiscoveryStatus(): Promise<DeviceDiscoveryStatus> {
  const url = '/api/discovery/status';

  logApiRequest('GET', url);
  const result = await apiGet<DeviceDiscoveryStatus>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get supported protocols information
 *
 * @returns Promise resolving to supported protocols data
 */
export async function fetchSupportedProtocols(): Promise<SupportedProtocols> {
  const url = '/api/discovery/protocols';

  logApiRequest('GET', url);
  const result = await apiGet<SupportedProtocols>(url);
  logApiResponse(url, result);

  return result;
}

//
// ===== AUTHENTICATION API (/api/auth) =====
//

/**
 * Login with username and password (single-user mode)
 *
 * @param username - Admin username
 * @param password - Admin password
 * @returns Promise resolving to JWT token
 */
export async function login(username: string, password: string): Promise<LoginResponse> {
  const url = '/api/auth/login';
  const formData = new FormData();
  formData.append('username', username);
  formData.append('password', password);

  logApiRequest('POST', url, { username });
  const result = await fetch(`${API_BASE}${url}`, {
    method: 'POST',
    body: formData,
  });

  if (!result.ok) {
    throw new APIClientError(`HTTP ${result.status}: ${result.statusText}`, result.status);
  }

  const data = await result.json() as LoginResponse;
  logApiResponse(url, data);
  return data;
}

/**
 * Refresh access token using refresh token
 *
 * @param refreshToken - Valid refresh token
 * @returns Promise resolving to new token pair
 */
export async function refreshToken(refreshToken: string): Promise<RefreshTokenResponse> {
  const url = '/api/auth/refresh';
  const request: RefreshTokenRequest = { refresh_token: refreshToken };

  logApiRequest('POST', url, { refresh_token: '[REDACTED]' });
  const result = await apiPost<RefreshTokenResponse>(url, request);
  logApiResponse(url, { ...result, refresh_token: '[REDACTED]', access_token: '[REDACTED]' });

  return result;
}

/**
 * Revoke a refresh token
 *
 * @param refreshToken - Refresh token to revoke
 * @returns Promise resolving when token is revoked
 */
export async function revokeRefreshToken(refreshToken: string): Promise<void> {
  const url = '/api/auth/revoke';
  const request: RefreshTokenRequest = { refresh_token: refreshToken };

  logApiRequest('POST', url, { refresh_token: '[REDACTED]' });
  await apiPost<void>(url, request);
  logApiResponse(url, 'Token revoked');
}

/**
 * Send magic link for passwordless authentication (multi-user mode)
 *
 * @param email - Email address for magic link
 * @param redirectUrl - Optional redirect URL after authentication
 * @returns Promise resolving to magic link response
 */
export async function sendMagicLink(email: string, redirectUrl?: string): Promise<{ message: string; email: string; expires_in_minutes: number }> {
  const url = '/api/auth/magic-link';
  const request = { email, redirect_url: redirectUrl };

  logApiRequest('POST', url, request);
  const result = await apiPost<{ message: string; email: string; expires_in_minutes: number }>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Get current user profile information
 *
 * @returns Promise resolving to current user info
 */
export async function getCurrentUser(): Promise<User> {
  const url = '/api/auth/me';

  logApiRequest('GET', url);
  const result = await apiGet<User>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get authentication system status
 *
 * @returns Promise resolving to auth status
 */
export async function getAuthStatus(): Promise<{
  enabled: boolean;
  mode: string;
  jwt_available: boolean;
  magic_links_enabled: boolean;
  oauth_enabled: boolean;
}> {
  const url = '/api/auth/status';

  logApiRequest('GET', url);
  const result = await apiGet<{
    enabled: boolean;
    mode: string;
    jwt_available: boolean;
    magic_links_enabled: boolean;
    oauth_enabled: boolean;
  }>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Logout current user
 *
 * @returns Promise resolving to logout confirmation
 */
export async function logout(): Promise<{ message: string; detail: string }> {
  const url = '/api/auth/logout';

  logApiRequest('POST', url);
  const result = await apiPost<{ message: string; detail: string }>(url, {});
  logApiResponse(url, result);

  return result;
}

/**
 * Get auto-generated admin credentials (one-time display only)
 *
 * @returns Promise resolving to admin credentials
 */
export async function getAdminCredentials(): Promise<{
  username: string;
  password: string;
  created_at: string;
  warning: string;
}> {
  const url = '/api/auth/admin/credentials';

  logApiRequest('GET', url);
  const result = await apiGet<{
    username: string;
    password: string;
    created_at: string;
    warning: string;
  }>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get lockout status for a specific user (admin only)
 *
 * @param username - Username to check lockout status for
 * @returns Promise resolving to lockout status
 */
export async function getLockoutStatus(username: string): Promise<LockoutStatus> {
  const url = `/api/auth/lockout/status/${username}`;

  logApiRequest('GET', url, { username });
  const result = await apiGet<LockoutStatus>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get lockout status for all tracked users (admin only)
 *
 * @returns Promise resolving to list of lockout status
 */
export async function getAllLockoutStatus(): Promise<LockoutStatus[]> {
  const url = '/api/auth/lockout/status';

  logApiRequest('GET', url);
  const result = await apiGet<LockoutStatus[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Manually unlock a user account (admin only)
 *
 * @param username - Username to unlock
 * @returns Promise resolving to unlock confirmation
 */
export async function unlockAccount(username: string): Promise<{ message: string; unlocked_by: string }> {
  const url = '/api/auth/lockout/unlock';
  const request: UnlockAccountRequest = { username };

  logApiRequest('POST', url, request);
  const result = await apiPost<{ message: string; unlocked_by: string }>(url, request);
  logApiResponse(url, result);

  return result;
}

//
// ===== BULK OPERATIONS API (/api/bulk-operations) =====
//

/**
 * Create and execute a bulk operation on multiple devices
 *
 * @param request - Bulk operation request
 * @returns Promise resolving to operation response
 */
export async function createBulkOperation(request: BulkOperationRequest): Promise<BulkOperationResponse> {
  const url = '/api/bulk-operations';

  logApiRequest('POST', url, request);
  const result = await apiPost<BulkOperationResponse>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Get the status of a bulk operation
 *
 * @param operationId - Operation identifier
 * @returns Promise resolving to operation status
 */
export async function fetchBulkOperationStatus(operationId: string): Promise<BulkOperationStatus> {
  const url = `/api/bulk-operations/${operationId}`;

  logApiRequest('GET', url);
  const result = await apiGet<BulkOperationStatus>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get all device groups
 *
 * @returns Promise resolving to list of device groups
 */
export async function fetchDeviceGroups(): Promise<DeviceGroup[]> {
  const url = '/api/bulk-operations/groups';

  logApiRequest('GET', url);
  const result = await apiGet<DeviceGroup[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Create a new device group
 *
 * @param request - Device group creation request
 * @returns Promise resolving to created group
 */
export async function createDeviceGroup(request: DeviceGroupRequest): Promise<DeviceGroup> {
  const url = '/api/bulk-operations/groups';

  logApiRequest('POST', url, request);
  const result = await apiPost<DeviceGroup>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Update an existing device group
 *
 * @param groupId - Group identifier
 * @param request - Device group update request
 * @returns Promise resolving to updated group
 */
export async function updateDeviceGroup(groupId: string, request: DeviceGroupRequest): Promise<DeviceGroup> {
  const url = `/api/bulk-operations/groups/${groupId}`;

  logApiRequest('PUT', url, request);
  const result = await apiPost<DeviceGroup>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Delete a device group
 *
 * @param groupId - Group identifier
 * @returns Promise resolving to deletion confirmation
 */
export async function deleteDeviceGroup(groupId: string): Promise<{ message: string }> {
  const url = `/api/bulk-operations/groups/${groupId}`;

  logApiRequest('DELETE', url);
  const result = await apiDelete<{ message: string }>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Execute a bulk operation on all devices in a group
 *
 * @param groupId - Group identifier
 * @param payload - Operation payload
 * @returns Promise resolving to operation response
 */
export async function executeGroupOperation(
  groupId: string,
  payload: BulkOperationPayload
): Promise<BulkOperationResponse> {
  const url = `/api/bulk-operations/groups/${groupId}/execute`;

  logApiRequest('POST', url, payload);
  const result = await apiPost<BulkOperationResponse>(url, payload);
  logApiResponse(url, result);

  return result;
}
