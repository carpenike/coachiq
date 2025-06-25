/**
 * CAN Analyzer WebSocket Hook
 *
 * Specialized WebSocket hook for CAN analyzer functionality.
 * Manages analyzer-specific state based on WebSocket messages.
 */

import { useState, useCallback, useEffect } from 'react';
import { useWebSocket } from '../useWebSocket';
import type {
  ProtocolStatistics,
  AnalyzedMessage,
  CommunicationPattern
} from '@/api/can-analyzer';

interface CANAnalyzerMessage {
  type: 'analyzer_statistics' | 'analyzed_messages' | 'patterns_update' | 'protocols_update';
  payload: {
    statistics?: ProtocolStatistics;
    messages?: AnalyzedMessage[];
    patterns?: CommunicationPattern[];
    protocols?: ProtocolStatistics;
  };
  timestamp: number;
}

interface UseCANAnalyzerWebSocketReturn {
  statistics: ProtocolStatistics | null;
  messages: AnalyzedMessage[];
  patterns: CommunicationPattern[];
  protocols: ProtocolStatistics;
  state: 'connecting' | 'connected' | 'disconnected' | 'error';
  error: string | null;
  connect: () => void;
  disconnect: () => void;
}

/**
 * Hook for CAN analyzer WebSocket connection
 *
 * @param enabled - Whether to auto-connect on mount
 * @returns CAN analyzer state and connection methods
 */
export function useCANAnalyzerWebSocket(enabled: boolean = true): UseCANAnalyzerWebSocketReturn {
  // Domain-specific state
  const [statistics, setStatistics] = useState<ProtocolStatistics | null>(null);
  const [messages, setMessages] = useState<AnalyzedMessage[]>([]);
  const [patterns, setPatterns] = useState<CommunicationPattern[]>([]);
  const [protocols, setProtocols] = useState<ProtocolStatistics>({
    runtime_seconds: 0,
    total_messages: 0,
    total_bytes: 0,
    overall_message_rate: 0,
    bus_utilization_percent: 0,
    protocols: {},
    detected_patterns: 0,
    buffer_usage: 0,
    buffer_capacity: 0
  });

  // Message handler
  const handleMessage = useCallback((message: unknown) => {
    try {
      const data = message as CANAnalyzerMessage;

      switch (data.type) {
        case 'analyzer_statistics':
          if (data.payload.statistics) {
            setStatistics(data.payload.statistics);
          }
          break;

        case 'analyzed_messages':
          if (data.payload.messages) {
            // Keep only last 100 messages to prevent memory issues
            setMessages(prev => {
              const combined = [...data.payload.messages!, ...prev];
              return combined.slice(0, 100);
            });
          }
          break;

        case 'patterns_update':
          if (data.payload.patterns) {
            setPatterns(data.payload.patterns);
          }
          break;

        case 'protocols_update':
          if (data.payload.protocols) {
            setProtocols(data.payload.protocols);
          }
          break;
      }
    } catch (error) {
      console.error('[useCANAnalyzerWebSocket] Failed to handle message:', error);
    }
  }, []);

  // Use generic WebSocket hook
  const { state, error, connect, disconnect } = useWebSocket<CANAnalyzerMessage>({
    endpoint: '/ws/can-analyzer',
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
    statistics,
    messages,
    patterns,
    protocols,
    state,
    error,
    connect,
    disconnect,
  };
}
