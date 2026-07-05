/**
 * WebSocket Provider Component
 *
 * Provides global WebSocket connections for real-time updates.
 * Manages entity updates, system status, and other real-time data streams.
 */

import { useAuth } from '@/contexts/auth-context';
import { useWebSocketManager } from '@/hooks/useWebSocket';
import React, { useEffect, useState, useMemo } from 'react';
import { WebSocketContext, type ConnectionMetrics, type WebSocketContextType } from './websocket-context';

interface WebSocketProviderProps {
  children: React.ReactNode;
  enableEntityUpdates?: boolean;
  enableSystemStatus?: boolean;
  enableCANScan?: boolean;
}

/**
 * Provides global WebSocket connections to the application
 */
export function WebSocketProvider({
  children,
  enableEntityUpdates = true,
  enableSystemStatus = true,
  enableCANScan = false
}: WebSocketProviderProps) {
  // Don't dial the sockets until auth is settled. The token rides in the WS
  // URL query param, so connecting before login (or before the user query
  // confirms the session) sends a missing/stale token, the server rejects it,
  // and — because the reconnect path only re-dials previously-connected
  // sockets — it sits down until a manual retry. Auth-disabled coaches
  // (mode "none") have no token and are ready as soon as status loads.
  const { isAuthenticated, authStatus } = useAuth();
  const authReady = authStatus?.mode === 'none' || isAuthenticated;

  const webSocketManager = useWebSocketManager({
    enableEntityUpdates: enableEntityUpdates && authReady,
    enableSystemStatus: enableSystemStatus && authReady,
    enableCANScan: enableCANScan && authReady,
  });

  const [metrics, setMetrics] = useState<ConnectionMetrics>({
    messageCount: 0,
    reconnectAttempts: 0,
  });

  // Track connection metrics
  useEffect(() => {
    if (webSocketManager.isAnyConnected && !metrics.connectedAt) {
      setMetrics(prev => ({
        ...prev,
        connectedAt: new Date(),
      }));
    } else if (!webSocketManager.isAnyConnected && metrics.connectedAt) {
      setMetrics(prev => {
        const { connectedAt, ...rest } = prev;
        void connectedAt; // Explicitly ignore the unused variable
        return rest;
      });
    }
  }, [webSocketManager.isAnyConnected, metrics.connectedAt]);

  // Update message count metrics
  useEffect(() => {
    const interval = setInterval(() => {
      if (webSocketManager.isAnyConnected) {
        setMetrics(prev => ({
          ...prev,
          lastMessage: new Date(),
          messageCount: prev.messageCount + 1,
        }));
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [webSocketManager.isAnyConnected]);

  const contextValue: WebSocketContextType = useMemo(() => ({
    isConnected: webSocketManager.isAnyConnected,
    hasError: Boolean(webSocketManager.hasAnyError),
    connectAll: webSocketManager.connectAll,
    disconnectAll: webSocketManager.disconnectAll,
    metrics,
  }), [webSocketManager.isAnyConnected, webSocketManager.hasAnyError, webSocketManager.connectAll, webSocketManager.disconnectAll, metrics]);

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  );
}
