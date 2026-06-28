/**
 * Diagnostics Components Index
 *
 * Exports all diagnostic-related components for easy importing
 */

export { SystemHealthScore } from './SystemHealthScore';
export { DTCManager } from './DTCManager';

// Re-export types for convenience
export type { DiagnosticTroubleCode, DTCFilters } from '@/api/types';
export type {
	DiagnosticFaultSummarySchema,
	DiagnosticsSystemStatusSchema
} from '@/api/types/domains';
