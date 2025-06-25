/**
 * Generic WebSocket Hook
 *
 * A reusable React hook for WebSocket connections with automatic reconnection,
 * authentication support, and TypeScript types for different message formats.
 * Designed to work with any WebSocket endpoint including CAN tools endpoints.
 */

import { useEffect, useRef, useState, useContext, useCallback, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RVCWebSocketClient, type WebSocketConfig, type WebSocketHandlers, type WebSocketState } from '@/api/websocket';
import { connectionManager } from '@/api/websocket-connection-manager';
import { WebSocketContext } from '@/contexts/websocket-context';
import { env } from '@/api/client';
import { queryKeys } from '@/lib/query-client';

/**
 * Generic WebSocket message handler type
 */
export type MessageHandler<T = unknown> = (message: T) => void;

/**
 * WebSocket message subscription
 */
export interface IMessageSubscription<T = unknown> {
  type?: string;
  handler: MessageHandler<T>;
}

/**
 * Options for the generic useWebSocket hook
 */
export interface IUseWebSocketOptions<T = unknown> {
  /** WebSocket endpoint path (e.g., '/ws/can-recorder') */
  endpoint: string;

  /** Whether to auto-connect on mount */
  autoConnect?: boolean;

  /** WebSocket configuration options */
  config?: WebSocketConfig;

  /** Use existing WebSocket context if available */
  useContext?: boolean;

  /** Message subscriptions by type */
  subscriptions?: IMessageSubscription<T>[];

  /** Generic message handler (called for all messages) */
  onMessage?: MessageHandler<T>;

  /** Connection event handlers */
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (error: Event) => void;
}

/**
 * Return type for the useWebSocket hook
 */
export interface IUseWebSocketReturn<T = unknown> {
  /** WebSocket client instance */
  client: RVCWebSocketClient | null;

  /** Current connection state */
  state: WebSocketState;

  /** Whether the socket is connected */
  isConnected: boolean;

  /** Current error if any */
  error: string | null;

  /** Connect to the WebSocket */
  connect: () => void;

  /** Disconnect from the WebSocket */
  disconnect: () => void;

  /** Send a message through the WebSocket */
  send: (message: T) => void;

  /** Subscribe to messages */
  subscribe: (subscription: IMessageSubscription<T>) => () => void;

  /** Connection metrics */
  metrics: {
    messageCount: number;
    reconnectAttempts: number;
    connectedAt?: Date;
    lastMessage?: Date;
    messagesPerSecond: number;
  };
}

/**
 * Enhanced WebSocket status for better UI feedback
 */
export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error' | 'reconnecting' | 'failed';

/**
 * Calculate exponential backoff delay with jitter
 */
function getExponentialBackoffDelay(attempt: number, baseDelay = 1000, maxDelay = 30000): number {
  const exponentialDelay = Math.min(baseDelay * Math.pow(2, attempt - 1), maxDelay);
  const jitter = Math.random() * 1000; // 0-1000ms jitter
  return exponentialDelay + jitter;
}

/**
 * Generic WebSocket hook for any endpoint
 *
 * @example
 * ```typescript
 * // Basic usage
 * const { isConnected, send } = useWebSocket({
 *   endpoint: '/ws/can-recorder',
 *   autoConnect: true
 * });
 *
 * // With message subscriptions
 * const { subscribe } = useWebSocket<CANMessage>({
 *   endpoint: '/ws/can-analyzer',
 *   subscriptions: [{
 *     type: 'can_message',
 *     handler: (msg) => console.log('CAN:', msg)
 *   }]
 * });
 * ```
 */
export function useWebSocket<T = unknown>(options: IUseWebSocketOptions<T>): IUseWebSocketReturn<T> {
  const {
    endpoint,
    autoConnect = false,
    config: userConfig,
    useContext: useWebSocketContext = true,
    subscriptions = [],
    onMessage,
    onOpen,
    onClose,
    onError,
  } = options;

  // Always call useContext (React hooks must be called unconditionally)
  const contextValue = useContext(WebSocketContext);
  const wsContext = useWebSocketContext ? contextValue : null;

  // State
  const [state, setState] = useState<WebSocketState>('disconnected');
  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<{
    messageCount: number;
    reconnectAttempts: number;
    messagesPerSecond: number;
    connectedAt?: Date;
    lastMessage?: Date;
  }>({
    messageCount: 0,
    reconnectAttempts: 0,
    messagesPerSecond: 0,
  });

  // Refs for stable references
  const clientRef = useRef<RVCWebSocketClient | null>(null);
  const subscriptionsRef = useRef<Map<symbol, IMessageSubscription<T>>>(new Map());
  const metricsIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastMessageCountRef = useRef(0);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttemptsRef = useRef(10);

  // Memoize event handlers to stabilize dependencies
  const memoizedOnOpen = useCallback(() => {
    setState('connected');
    setStatus('connected');
    setError(null);
    reconnectAttemptsRef.current = 0;
    setMetrics(prev => ({
      ...prev,
      connectedAt: new Date(),
      reconnectAttempts: 0,
    }));

    if (env.isDevelopment) {
      console.log(`[useWebSocket] Connected to ${endpoint}`);
    }

    onOpen?.();
  }, [endpoint, onOpen]);

  const memoizedOnClose = useCallback((event: CloseEvent) => {
    const wasConnected = clientRef.current?.isConnected;
    setState('disconnected');

    // Handle reconnection logic
    if (wasConnected && event.code !== 1000 && userConfig?.autoReconnect !== false) {
      const attempts = reconnectAttemptsRef.current;
      if (attempts < maxReconnectAttemptsRef.current) {
        setStatus('reconnecting');
        const delay = getExponentialBackoffDelay(attempts + 1);

        if (env.isDevelopment) {
          console.log(`[useWebSocket] Reconnecting to ${endpoint} (attempt ${attempts + 1}/${maxReconnectAttemptsRef.current}) in ${Math.round(delay)}ms`);
        }

        setTimeout(() => {
          if (clientRef.current && !clientRef.current.isConnected) {
            reconnectAttemptsRef.current++;
            setMetrics(prev => ({ ...prev, reconnectAttempts: attempts + 1 }));
            clientRef.current.connect();
          }
        }, delay);
      } else {
        setStatus('failed');
        if (env.isDevelopment) {
          console.error(`[useWebSocket] Max reconnection attempts reached for ${endpoint}`);
        }
      }
    } else {
      setStatus('disconnected');
    }

    setMetrics(prev => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { connectedAt, ...rest } = prev;
      return rest;
    });

    if (env.isDevelopment && event.code !== 1000) {
      console.log(`[useWebSocket] Disconnected from ${endpoint}`, {
        code: event.code,
        reason: event.reason,
      });
    }

    onClose?.(event);
  }, [endpoint, userConfig?.autoReconnect, onClose]);

  const memoizedOnError = useCallback((event: Event) => {
    setState('error');
    setStatus('error');
    setError(event.type || 'WebSocket error');

    if (env.isDevelopment) {
      console.error(`[useWebSocket] Error on ${endpoint}:`, event);
    }

    onError?.(event);
  }, [endpoint, onError]);

  const memoizedOnMessage = useCallback((message: unknown) => {
    setMetrics(prev => ({
      ...prev,
      messageCount: prev.messageCount + 1,
      lastMessage: new Date(),
    }));

    // Call generic handler
    onMessage?.(message as T);

    // Call subscribed handlers
    subscriptionsRef.current.forEach(sub => {
      if (sub.type && typeof message === 'object' && message && 'type' in message) {
        if ((message as unknown as Record<string, unknown>).type === sub.type) {
          sub.handler(message as T);
        }
      } else if (!sub.type) {
        sub.handler(message as T);
      }
    });

    // Also handle subscriptions from props
    subscriptions.forEach(sub => {
      if (sub.type && typeof message === 'object' && message && 'type' in message) {
        if ((message as unknown as Record<string, unknown>).type === sub.type) {
          sub.handler(message as T);
        }
      } else if (!sub.type) {
        sub.handler(message as T);
      }
    });
  }, [onMessage, subscriptions]);

  // Memoize config with exponential backoff settings
  const config = useMemo(() => ({
    ...userConfig,
    autoReconnect: false, // We handle reconnection ourselves with exponential backoff
    maxReconnectAttempts: 0, // Disable built-in reconnection
  }), [userConfig]);

  // Update metrics
  useEffect(() => {
    metricsIntervalRef.current = setInterval(() => {
      const currentCount = metrics.messageCount;
      const messagesPerSecond = currentCount - lastMessageCountRef.current;
      lastMessageCountRef.current = currentCount;

      setMetrics(prev => ({
        ...prev,
        messagesPerSecond,
      }));
    }, 1000);

    return () => {
      if (metricsIntervalRef.current) {
        clearInterval(metricsIntervalRef.current);
      }
    };
  }, [metrics.messageCount]);

  // Create WebSocket client
  useEffect(() => {
    if (!endpoint) return;

    const handlers: WebSocketHandlers = {
      onOpen: memoizedOnOpen,
      onClose: memoizedOnClose,
      onError: memoizedOnError,
      onMessage: memoizedOnMessage,
    };

    // Get or create client through connection manager
    const wsClient = connectionManager.getConnection(endpoint, handlers, config);
    clientRef.current = wsClient;

    return () => {
      // Release connection reference (connection manager handles cleanup)
      connectionManager.releaseConnection(endpoint);
      clientRef.current = null;
    };
  }, [endpoint, config, memoizedOnOpen, memoizedOnClose, memoizedOnError, memoizedOnMessage]);

  // Handle autoConnect changes separately
  useEffect(() => {
    if (!clientRef.current) return;

    if (autoConnect && !clientRef.current.isConnected && clientRef.current.state !== 'connecting') {
      setStatus('connecting');
      clientRef.current.connect();
    } else if (!autoConnect && clientRef.current.isConnected) {
      clientRef.current.disconnect();
    }
  }, [autoConnect]);

  // Connect function
  const connect = useCallback(() => {
    if (wsContext && useWebSocketContext) {
      wsContext.connectAll();
    } else {
      reconnectAttemptsRef.current = 0; // Reset attempts on manual connect
      setStatus('connecting');
      clientRef.current?.connect();
    }
  }, [wsContext, useWebSocketContext]);

  // Disconnect function
  const disconnect = useCallback(() => {
    if (wsContext && useWebSocketContext) {
      wsContext.disconnectAll();
    } else {
      clientRef.current?.disconnect();
    }
  }, [wsContext, useWebSocketContext]);

  // Send function
  const send = useCallback((message: T) => {
    if (!clientRef.current?.isConnected) {
      throw new Error('WebSocket is not connected');
    }
    clientRef.current.send(message);
  }, []);

  // Subscribe function
  const subscribe = useCallback((subscription: IMessageSubscription<T>) => {
    const id = Symbol('subscription');
    subscriptionsRef.current.set(id, subscription);

    // Return unsubscribe function
    return () => {
      subscriptionsRef.current.delete(id);
    };
  }, []);

  // If using context, merge with context state
  const isConnected = useWebSocketContext && wsContext
    ? wsContext.isConnected
    : state === 'connected';

  return {
    client: clientRef.current,
    state,
    isConnected,
    error,
    connect,
    disconnect,
    send,
    subscribe,
    metrics: useWebSocketContext && wsContext
      ? { ...metrics, ...wsContext.metrics }
      : metrics,
  };
}

/**
 * Hook for entity updates via WebSocket
 */
export function useEntityWebSocket(options?: { autoConnect?: boolean }) {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);

  return useWebSocket({
    endpoint: '/ws',
    autoConnect: options?.autoConnect ?? true,
    subscriptions: [{
      type: 'entity_update',
      handler: (message: unknown) => {
        const data = (message as Record<string, any>).data as Record<string, any>;
        // Update the specific entity in the cache
        queryClientRef.current.setQueryData(
          queryKeys.entities.detail(data.entity_id),
          data.entity_data
        );
        // Invalidate entity lists to trigger re-render
        void queryClientRef.current.invalidateQueries({ queryKey: queryKeys.entities.lists() });
      }
    }]
  });
}

/**
 * Hook for CAN message scanning via WebSocket
 */
export function useCANScanWebSocket(options?: {
  autoConnect?: boolean;
  onMessage?: (message: unknown) => void;
}) {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  const [messageCount, setMessageCount] = useState(0);

  const { subscribe, ...rest } = useWebSocket({
    endpoint: '/ws/can-sniffer',
    autoConnect: options?.autoConnect ?? false,
    onMessage: (message) => {
      setMessageCount(prev => prev + 1);
      options?.onMessage?.(message);

      // Periodically invalidate CAN statistics
      if (messageCount % 100 === 0) {
        void queryClientRef.current.invalidateQueries({ queryKey: queryKeys.can.statistics() });
      }
    }
  });

  const clearMessageCount = () => setMessageCount(0);

  return {
    ...rest,
    messageCount,
    clearMessageCount,
    subscribe
  };
}

/**
 * Hook for system status updates via WebSocket
 */
export function useSystemStatusWebSocket(options?: { autoConnect?: boolean }) {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);

  return useWebSocket({
    endpoint: '/ws/features',
    autoConnect: options?.autoConnect ?? true,
    onMessage: () => {
      // Update system queries
      void queryClientRef.current.invalidateQueries({ queryKey: queryKeys.system.health() });
      void queryClientRef.current.invalidateQueries({ queryKey: queryKeys.system.queueStatus() });
      void queryClientRef.current.invalidateQueries({ queryKey: queryKeys.can.statistics() });
    }
  });
}

/**
 * Hook for log streaming via WebSocket
 */
export function useLogWebSocket(options?: {
  autoConnect?: boolean;
  onLog?: (log: unknown) => void;
}) {
  return useWebSocket({
    endpoint: '/ws/logs',
    autoConnect: options?.autoConnect ?? false,
    onMessage: (message) => {
      // Accept log messages with or without a type field
      if (
        message && typeof message === 'object' &&
        'timestamp' in message && 'level' in message && 'message' in message
      ) {
        options?.onLog?.(message);
      } else if (typeof message === 'string') {
        // Try to parse as JSON, fallback to raw string
        try {
          const parsed = JSON.parse(message);
          if (
            parsed && typeof parsed === 'object' &&
            'timestamp' in parsed && 'level' in parsed && 'message' in parsed
          ) {
            options?.onLog?.(parsed);
            return;
          }
        } catch {
          // Not JSON, pass as raw string
        }
        options?.onLog?.(message);
      } else {
        // Fallback: pass any message
        options?.onLog?.(message);
      }
    }
  });
}

/**
 * Hook for managing all WebSocket connections
 */
export function useWebSocketManager(options?: {
  enableEntityUpdates?: boolean;
  enableSystemStatus?: boolean;
  enableCANScan?: boolean;
}) {
  const {
    enableEntityUpdates = true,
    enableSystemStatus = true,
    enableCANScan = false,
  } = options || {};

  const entityWS = useEntityWebSocket({ autoConnect: enableEntityUpdates });
  const systemWS = useSystemStatusWebSocket({ autoConnect: enableSystemStatus });
  const canWS = useCANScanWebSocket({ autoConnect: enableCANScan });

  const connectAll = () => {
    if (enableEntityUpdates) entityWS.connect();
    if (enableSystemStatus) systemWS.connect();
    if (enableCANScan) canWS.connect();
  };

  const disconnectAll = () => {
    entityWS.disconnect();
    systemWS.disconnect();
    canWS.disconnect();
  };

  const isAnyConnected = entityWS.isConnected || systemWS.isConnected || canWS.isConnected;
  const hasAnyError = entityWS.error || systemWS.error || canWS.error;

  return {
    entity: entityWS,
    system: systemWS,
    can: canWS,
    connectAll,
    disconnectAll,
    isAnyConnected,
    hasAnyError,
    isSupported: true,
  };
}

// Export specialized hooks from their separate files
export { useCANRecorderWebSocket } from './websocket/useCANRecorderWebSocket';
export { useCANAnalyzerWebSocket } from './websocket/useCANAnalyzerWebSocket';
export { useCANFilterWebSocket } from './websocket/useCANFilterWebSocket';
