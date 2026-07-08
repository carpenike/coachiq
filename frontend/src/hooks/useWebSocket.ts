/**
 * Generic WebSocket Hook
 *
 * A reusable React hook for the page-scoped diagnostic WebSocket streams
 * (CAN sniffer/recorder/analyzer/filter), with automatic reconnection
 * and per-endpoint connection sharing.
 *
 * App-wide realtime state (entity updates) does NOT go through here — it
 * rides the SSE stream owned by RealtimeProvider (see @/api/sse). Log
 * streaming is also SSE now (GET /api/logs/stream, see the log-viewer).
 */

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { RVCWebSocketClient, WebSocketConfig, WebSocketHandlers, WebSocketState } from '@/api/websocket';
import { connectionManager } from '@/api/websocket-connection-manager';
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
 *     handler: handleCanMessage
 *   }]
 * });
 * ```
 */
export function useWebSocket<T = unknown>(options: IUseWebSocketOptions<T>): IUseWebSocketReturn<T> {
  const {
    endpoint,
    autoConnect = false,
    config: userConfig,
    subscriptions = [],
    onMessage,
    onOpen,
    onClose,
    onError,
  } = options;

  // Keep the latest message handlers in refs so `memoizedOnMessage` can stay
  // referentially STABLE. Callers routinely pass an inline `onMessage` or a
  // fresh `subscriptions` array every render (e.g. useEntityWebSocket), which
  // would otherwise change the handler identity each render, re-run the
  // connection-creation effect, and tear the socket down before it finishes
  // connecting — the coach then never leaves the "connecting" state on load.
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const propSubscriptionsRef = useRef(subscriptions);
  propSubscriptionsRef.current = subscriptions;

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

    // Call generic handler (via ref so this callback stays stable)
    onMessageRef.current?.(message as T);

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

    // Also handle subscriptions from props (via ref, for the same reason)
    propSubscriptionsRef.current.forEach(sub => {
      if (sub.type && typeof message === 'object' && message && 'type' in message) {
        if ((message as unknown as Record<string, unknown>).type === sub.type) {
          sub.handler(message as T);
        }
      } else if (!sub.type) {
        sub.handler(message as T);
      }
    });
  }, []);

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
    reconnectAttemptsRef.current = 0; // Reset attempts on manual connect
    setStatus('connecting');
    clientRef.current?.connect();
  }, []);

  // Disconnect function
  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
  }, []);

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

  return {
    client: clientRef.current,
    state,
    isConnected: state === 'connected',
    error,
    connect,
    disconnect,
    send,
    subscribe,
    metrics,
  };
}

/**
 * Hook for CAN message scanning via WebSocket.
 *
 * The generic `TMessage` lets call sites opt into a narrower payload
 * shape (e.g. `useCANScanWebSocket<CANMessage>({ onMessage: m => ... })`).
 * Defaults to `unknown` because WebSocket frames are untrusted JSON;
 * narrowing is the caller's responsibility.
 */
export function useCANScanWebSocket<TMessage = unknown>(options?: {
  autoConnect?: boolean;
  onMessage?: (message: TMessage) => void;
}) {
  const queryClient = useQueryClient();
  const queryClientRef = useRef(queryClient);
  const [messageCount, setMessageCount] = useState(0);

  const { subscribe, ...rest } = useWebSocket({
    endpoint: '/ws/can-sniffer',
    autoConnect: options?.autoConnect ?? false,
    onMessage: (message) => {
      setMessageCount(prev => prev + 1);
      options?.onMessage?.(message as TMessage);

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

// Export specialized hooks from their separate files
export { useCANRecorderWebSocket } from './websocket/useCANRecorderWebSocket';
export { useCANAnalyzerWebSocket } from './websocket/useCANAnalyzerWebSocket';
export { useCANFilterWebSocket } from './websocket/useCANFilterWebSocket';
