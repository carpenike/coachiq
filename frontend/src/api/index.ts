/**
 * API Module Index
 *
 * Central export point for all API-related functionality.
 * Provides clean imports for components and other modules.
 */

// Export all types
export type * from './types';
export type * from './types/domains';

// Export client utilities
export {
    APIClientError, API_BASE, WS_BASE, apiDelete, apiGet,
    apiPost,
    apiPut, apiRequest, buildQueryString, env, handleApiResponse, logApiRequest,
    logApiResponse
} from './client';

// Export all endpoint functions
export {
    brightnessDown, brightnessUp, controlEntity,
    // CAN bus endpoints
    fetchCANInterfaces,
    fetchCANMessages,
    fetchCANMetrics,
    fetchCANStatistics,
    // Entity endpoints
    fetchEntities,
    fetchEntity, fetchEntityHistory, fetchEntityMetadata, fetchFeatureStatus,
    // Configuration endpoints
    fetchHealthStatus,
    // Convenience functions
    fetchLights,
    fetchLocks, fetchQueueStatus, fetchTankSensors, fetchTemperatureSensors, fetchUnknownPGNs, fetchUnmappedEntries,
    // Lock control convenience functions
    lockEntity, sendCANMessage, setLightBrightness, toggleLight, turnLightOff,
    // Light control convenience functions
    turnLightOn, unlockEntity
} from './endpoints';

// Export domain APIs - avoid conflicts with main types
export {
    bulkControlEntitiesV2, controlEntityV2, convertLegacyEntityCollection,
    // Entities domain functions
    fetchEntitiesV2,
    fetchEntityV2, fetchSchemasV2
} from './domains';

// Export WebSocket functionality
export {
    RVCWebSocketClient,
    createEntityWebSocket,
    createCANScanWebSocket,
    createSystemStatusWebSocket,
    createLogWebSocket,
    isWebSocketSupported,
    getWebSocketStateString,
    DEBUG_WS
} from './websocket';

export type {
    WebSocketConfig, WebSocketHandlers, WebSocketState
} from './websocket';

// Re-export types that are commonly used
export type {
    APIError, AllCANStats, CANMessage, CANMessageUpdate, CANSendParams, ControlCommand,
    ControlEntityResponse, EntitiesQueryParams, Entity,
    EntityCollection, EntityUpdateMessage, FeatureStatus, HealthStatus, HistoryEntry, HistoryQueryParams, LightEntity,
    LockEntity, MetadataResponse, SystemStatusMessage, TankEntity, TemperatureEntity, UnknownPGNEntry, UnmappedEntry, WebSocketMessage
} from './types';
