/**
 * WebSocket Hooks
 *
 * Collection of specialized WebSocket hooks for different domains.
 */

// CAN Tool WebSocket Hooks
export { useCANRecorderWebSocket } from './useCANRecorderWebSocket';
export { useCANAnalyzerWebSocket } from './useCANAnalyzerWebSocket';
export { useCANFilterWebSocket } from './useCANFilterWebSocket';

// Re-export generic hook and types
export { useWebSocket, type IUseWebSocketOptions, type IUseWebSocketReturn } from '../useWebSocket';
