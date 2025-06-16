/**
 * Diagnostics Domain API v2 Client
 *
 * Provides access to diagnostic endpoints at /api/v2/diagnostics
 * Implements the Domain API v2 architecture for diagnostics
 */

import { apiGet, apiPost, buildQueryString } from '../client';
import type {
  DiagnosticStats,
  DTCCollection,
  DTCFilters,
  FaultCorrelation,
  MaintenancePrediction,
  DTCResolutionResponse,
} from '../types';

/**
 * Get system health status
 */
export async function fetchDiagnosticsStatus() {
  return apiGet<{
    overall_health: string;
    health_score: number;
    active_systems: string[];
    degraded_systems: string[];
    last_assessment: number;
  }>('/api/v2/diagnostics/health');
}

/**
 * Get diagnostic statistics
 */
export async function fetchDiagnosticStatistics(): Promise<DiagnosticStats> {
  const response = await apiGet<{
    metrics: {
      total_dtcs: number;
      active_dtcs: number;
      resolved_dtcs: number;
      processing_rate: number;
      system_health_trend: 'improving' | 'stable' | 'degrading';
    };
    correlation: {
      accuracy: number;
    };
    prediction: {
      accuracy: number;
    };
  }>('/api/v2/diagnostics/statistics');

  // Transform to frontend format
  return {
    total_dtcs: response.metrics.total_dtcs,
    active_dtcs: response.metrics.active_dtcs,
    resolved_dtcs: response.metrics.resolved_dtcs,
    processing_rate: response.metrics.processing_rate,
    correlation_accuracy: response.correlation.accuracy,
    prediction_accuracy: response.prediction.accuracy,
    system_health_trend: response.metrics.system_health_trend,
    last_updated: new Date().toISOString(),
  };
}

/**
 * Get active diagnostic trouble codes
 */
export async function fetchActiveDTCs(filters?: DTCFilters): Promise<DTCCollection> {
  const queryString = filters ? buildQueryString(filters as Record<string, unknown>) : '';
  const url = queryString ? `/api/v2/diagnostics/dtcs?${queryString}` : '/api/v2/diagnostics/dtcs';

  return apiGet<DTCCollection>(url);
}

/**
 * Resolve a diagnostic trouble code
 */
export async function resolveDTC(
  protocol: string,
  code: number,
  sourceAddress = 0
): Promise<DTCResolutionResponse> {
  const response = await apiPost<{ resolved: boolean }>(
    '/api/v2/diagnostics/dtcs/resolve',
    { protocol, code, source_address: sourceAddress }
  );

  return {
    resolved: response.resolved,
    dtc_id: `${protocol}-${code}-${sourceAddress}`,
    message: response.resolved ? 'DTC resolved successfully' : 'Failed to resolve DTC',
    timestamp: new Date().toISOString(),
  };
}

/**
 * Get fault correlations
 */
export async function fetchFaultCorrelations(
  timeWindowSeconds?: number
): Promise<FaultCorrelation[]> {
  const queryString = timeWindowSeconds
    ? buildQueryString({ time_window_seconds: timeWindowSeconds })
    : '';
  const url = queryString
    ? `/api/v2/diagnostics/correlations?${queryString}`
    : '/api/v2/diagnostics/correlations';

  return apiGet<FaultCorrelation[]>(url);
}

/**
 * Get maintenance predictions
 */
export async function fetchMaintenancePredictions(
  timeHorizonDays = 90
): Promise<MaintenancePrediction[]> {
  const queryString = buildQueryString({ time_horizon_days: timeHorizonDays });
  const url = `/api/v2/diagnostics/predictions?${queryString}`;

  return apiGet<MaintenancePrediction[]>(url);
}

/**
 * Create a diagnostics API client with all endpoints
 */
export function createDiagnosticsClient() {
  return {
    getStatus: fetchDiagnosticsStatus,
    getStatistics: fetchDiagnosticStatistics,
    getDTCs: fetchActiveDTCs,
    resolveDTC,
    getCorrelations: fetchFaultCorrelations,
    getPredictions: fetchMaintenancePredictions,
  };
}
