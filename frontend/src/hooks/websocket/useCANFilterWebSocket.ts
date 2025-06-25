/**
 * CAN Filter WebSocket Hook
 *
 * Specialized WebSocket hook for CAN filter functionality.
 * Manages filter-specific state based on WebSocket messages.
 */

import { useState, useCallback, useEffect } from 'react';
import { useWebSocket } from '../useWebSocket';
import type {
  FilterStatus,
  FilterRule,
  CapturedMessage
} from '@/api/can-filter';

interface CANFilterMessage {
  type: 'filter_status' | 'rules_update' | 'captured_messages';
  payload: {
    status?: FilterStatus;
    rules?: FilterRule[];
    messages?: CapturedMessage[];
  };
  timestamp: number;
}

interface UseCANFilterWebSocketReturn {
  status: FilterStatus | null;
  rules: FilterRule[];
  capturedMessages: CapturedMessage[];
  state: 'connecting' | 'connected' | 'disconnected' | 'error';
  error: string | null;
  connect: () => void;
  disconnect: () => void;
}

/**
 * Hook for CAN filter WebSocket connection
 *
 * @param enabled - Whether to auto-connect on mount
 * @returns CAN filter state and connection methods
 */
export function useCANFilterWebSocket(enabled: boolean = true): UseCANFilterWebSocketReturn {
  // Domain-specific state
  const [status, setStatus] = useState<FilterStatus | null>(null);
  const [rules, setRules] = useState<FilterRule[]>([]);
  const [capturedMessages, setCapturedMessages] = useState<CapturedMessage[]>([]);

  // Message handler
  const handleMessage = useCallback((message: unknown) => {
    try {
      const data = message as CANFilterMessage;

      switch (data.type) {
        case 'filter_status':
          if (data.payload.status) {
            setStatus(data.payload.status);
          }
          if (data.payload.rules) {
            setRules(data.payload.rules);
          }
          break;

        case 'rules_update':
          if (data.payload.rules) {
            setRules(data.payload.rules);
          }
          break;

        case 'captured_messages':
          if (data.payload.messages) {
            // Keep only last 200 messages to prevent memory issues
            setCapturedMessages(prev => {
              const combined = [...data.payload.messages!, ...prev];
              return combined.slice(0, 200);
            });
          }
          break;
      }
    } catch (error) {
      console.error('[useCANFilterWebSocket] Failed to handle message:', error);
    }
  }, []);

  // Use generic WebSocket hook
  const { state, error, connect, disconnect } = useWebSocket<CANFilterMessage>({
    endpoint: '/ws/can-filter',
    autoConnect: enabled,
    onMessage: handleMessage,
    config: {
      heartbeatInterval: 30000, // 30s heartbeat
    }
  });

  // Request initial state when connected
  useEffect(() => {
    if (state === 'connected') {
      // The backend should send initial state on connection
      // but we can request it if needed
    }
  }, [state]);

  return {
    status,
    rules,
    capturedMessages,
    state,
    error,
    connect,
    disconnect,
  };
}
