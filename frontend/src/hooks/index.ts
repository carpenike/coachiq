/**
 * Hooks Index
 *
 * Central export point for all custom React hooks.
 * Provides clean imports for components and other modules.
 */

// Entity management hooks
export {
  useBulkControlEntities,
  useBulkControlEntitiesWithValidation,
  useBulkLightControlWithValidation,
  useControlEntity,
  useControlEntityWithValidation,
  useEntities,
  useEntitiesDomainAPIAvailability,
  useEntitiesSchemas,
  useEntitiesWithValidation,
  useEntity,
  useEntityFilters,
  useEntityPagination,
  useEntitySelection,
  useEntitySelectionWithValidation,
  useEntityWithValidation
} from './useEntities';

// System and CAN bus hooks
export {
  useCANInterfaces,
  useCANStatistics, useDataRefresh, useFeatureStatus, useGlobalLoadingState, useHealthStatus, useQueueStatus, useRefreshCANData,
  useRefreshSystemData, useSendCANMessage, useUnknownPGNs,
  useUnmappedEntries
} from './useSystem';

// WebSocket hooks
export {
  useCANScanWebSocket, useEntityWebSocket, useSystemStatusWebSocket,
  useWebSocketManager, useLogWebSocket,
  // Generic WebSocket hook and CAN tool variants
  useWebSocket, useCANRecorderWebSocket, useCANAnalyzerWebSocket, useCANFilterWebSocket,
  // Types
  type IUseWebSocketOptions, type IUseWebSocketReturn, type MessageHandler, type IMessageSubscription
} from './useWebSocket';

// Table and virtualization hooks
export { useVirtualizedTable } from './useVirtualizedTable';

// Diagnostics hooks
export {
  useDiagnosticsState,
  useDiagnosticsStatus,
  useActiveDTCs,
  useSystemHealth,
  useFaultCorrelations,
  useMaintenancePredictions,
  useComputedDiagnosticStats,
  useDiagnosticStatistics,
  useResolveDTC,
  useRefreshDiagnostics
} from './useDiagnostics';

// Bulk operations hooks
export {
  useBulkOperations,
  useBulkOperationStatus,
  useDeviceGroups,
  useSelectionMode,
  useBulkOperationProgress,
  useQuickActions
} from './useBulkOperations';

// Predictive maintenance hooks
export {
  usePredictiveMaintenance,
  usePredictiveMaintenanceStats,
  useHealthOverview,
  useComponentHealth,
  useComponentHealthDetail,
  useMaintenanceRecommendations,
  useAcknowledgeRecommendation,
  useComponentTrends,
  useMaintenanceHistory
} from './usePredictiveMaintenance';

// Health monitoring hooks
export {
  useSystemHealthStatus,
  useHealthMonitoring,
  useReadinessCheck,
  useLivenessCheck,
  useStartupCheck,
  useHumanHealth,
  useAggregatedHealth
} from './useHealthStatus';
