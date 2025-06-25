/**
 * CAN Recorder WebSocket Hook
 *
 * Specialized WebSocket hook for CAN recorder functionality.
 * Manages recorder-specific state based on WebSocket messages.
 */

import { useState, useCallback, useEffect } from 'react';
import { useWebSocket } from '../useWebSocket';
import type {
  RecorderStatus,
  RecordingSession,
  RecordingFile
} from '@/api/can-recorder';

interface RecorderStatistics {
  total_messages: number;
  total_bytes: number;
  messages_per_second: number;
  duration_seconds: number;
}

interface CANRecorderMessage {
  type: 'recorder_status' | 'recording_update' | 'statistics_update' | 'recordings_list';
  payload: {
    status?: RecorderStatus;
    session?: RecordingSession;
    recordings?: RecordingFile[];
    statistics?: RecorderStatistics;
  };
  timestamp: number;
}

interface UseCANRecorderWebSocketReturn {
  status: RecorderStatus | null;
  recordings: RecordingFile[];
  statistics: RecorderStatistics | null;
  state: 'connecting' | 'connected' | 'disconnected' | 'error';
  error: string | null;
  connect: () => void;
  disconnect: () => void;
}

/**
 * Hook for CAN recorder WebSocket connection
 *
 * @param enabled - Whether to auto-connect on mount
 * @returns CAN recorder state and connection methods
 */
export function useCANRecorderWebSocket(enabled: boolean = true): UseCANRecorderWebSocketReturn {
  // Domain-specific state
  const [status, setStatus] = useState<RecorderStatus | null>(null);
  const [recordings, setRecordings] = useState<RecordingFile[]>([]);
  const [statistics, setStatistics] = useState<RecorderStatistics | null>(null);

  // Message handler
  const handleMessage = useCallback((message: unknown) => {
    try {
      const data = message as CANRecorderMessage;

      switch (data.type) {
        case 'recorder_status':
          if (data.payload.status) {
            setStatus(data.payload.status);
          }
          if (data.payload.recordings) {
            setRecordings(data.payload.recordings);
          }
          break;

        case 'recording_update':
          if (data.payload.session) {
            // Handle session update if needed
          }
          break;

        case 'recordings_list':
          if (data.payload.recordings) {
            setRecordings(data.payload.recordings);
          }
          break;

        case 'statistics_update':
          if (data.payload.statistics) {
            setStatistics(data.payload.statistics);
          }
          break;
      }
    } catch (error) {
      console.error('[useCANRecorderWebSocket] Failed to handle message:', error);
    }
  }, []);

  // Use generic WebSocket hook
  const { state, error, connect, disconnect } = useWebSocket<CANRecorderMessage>({
    endpoint: '/ws/can-recorder',
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
    recordings,
    statistics,
    state,
    error,
    connect,
    disconnect,
  };
}
