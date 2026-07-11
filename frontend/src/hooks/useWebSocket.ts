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

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type {
  RVCWebSocketClient,
  WebSocketConfig,
  WebSocketHandlers,
  WebSocketState
} from "@/api/websocket";
import {
  connectionManager,
  type WebSocketConnectionLease
} from "@/api/websocket-connection-manager";
import { env } from "@/api/client";
import { queryKeys } from "@/lib/query-client";

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

  /** Detailed lifecycle status, including reconnecting and exhausted states */
  status: WebSocketStatus;

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
export type WebSocketStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "error"
  | "reconnecting"
  | "failed";

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
export function useWebSocket<T = unknown>(
  options: IUseWebSocketOptions<T>
): IUseWebSocketReturn<T> {
  const {
    endpoint,
    autoConnect = false,
    config: userConfig,
    subscriptions = [],
    onMessage,
    onOpen,
    onClose,
    onError
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
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // State
  const [state, setState] = useState<WebSocketState>("disconnected");
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
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
    messagesPerSecond: 0
  });

  // Refs for stable references
  const clientRef = useRef<RVCWebSocketClient | null>(null);
  const leaseRef = useRef<WebSocketConnectionLease | null>(null);
  const subscriptionsRef = useRef<Map<symbol, IMessageSubscription<T>>>(new Map());
  const metricsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const messageCountRef = useRef(0);
  const lastMessageCountRef = useRef(0);
  const lastMessageAtRef = useRef<Date | undefined>(undefined);

  // Memoize event handlers to stabilize dependencies
  const memoizedOnOpen = useCallback(() => {
    setState("connected");
    setStatus("connected");
    setError(null);
    setMetrics((prev) => ({
      ...prev,
      connectedAt: new Date(),
      reconnectAttempts: 0
    }));

    onOpenRef.current?.();
  }, []);

  const memoizedOnClose = useCallback((event: CloseEvent) => {
    setState("disconnected");
    setStatus("disconnected");

    setMetrics((prev) => {
      const next = { ...prev };
      delete next.connectedAt;
      return next;
    });

    onCloseRef.current?.(event);
  }, []);

  const memoizedOnError = useCallback(
    (event: Event) => {
      setState("error");
      setStatus("error");
      setError(event.type || "WebSocket error");

      if (env.isDevelopment) {
        console.error(`[useWebSocket] Error on ${endpoint}:`, event);
      }

      onErrorRef.current?.(event);
    },
    [endpoint]
  );

  const memoizedOnReconnectAttempt = useCallback((attempt: number) => {
    setState("connecting");
    setStatus("reconnecting");
    setMetrics((prev) => ({
      ...prev,
      reconnectAttempts: attempt
    }));
  }, []);

  const memoizedOnReconnectExhausted = useCallback(
    (attempts: number) => {
      setState("error");
      setStatus("failed");
      setError(`WebSocket reconnection failed after ${attempts} attempts`);

      if (env.isDevelopment) {
        console.error(`[useWebSocket] Max reconnection attempts reached for ${endpoint}`);
      }
    },
    [endpoint]
  );

  const memoizedOnMessage = useCallback((message: unknown) => {
    messageCountRef.current++;
    lastMessageAtRef.current = new Date();

    // Call generic handler (via ref so this callback stays stable)
    onMessageRef.current?.(message as T);

    // Call subscribed handlers
    subscriptionsRef.current.forEach((sub) => {
      if (sub.type && typeof message === "object" && message && "type" in message) {
        if ((message as unknown as Record<string, unknown>).type === sub.type) {
          sub.handler(message as T);
        }
      } else if (!sub.type) {
        sub.handler(message as T);
      }
    });

    // Also handle subscriptions from props (via ref, for the same reason)
    propSubscriptionsRef.current.forEach((sub) => {
      if (sub.type && typeof message === "object" && message && "type" in message) {
        if ((message as unknown as Record<string, unknown>).type === sub.type) {
          sub.handler(message as T);
        }
      } else if (!sub.type) {
        sub.handler(message as T);
      }
    });
  }, []);

  // Normalize scalar options so inline config objects do not churn the lease.
  const config = useMemo<WebSocketConfig>(
    () => ({
      autoReconnect: userConfig?.autoReconnect ?? true,
      reconnectDelay: userConfig?.reconnectDelay ?? 3000,
      maxReconnectAttempts: userConfig?.maxReconnectAttempts ?? 10,
      connectionTimeout: userConfig?.connectionTimeout ?? 10000,
      heartbeatInterval: userConfig?.heartbeatInterval ?? 30000
    }),
    [
      userConfig?.autoReconnect,
      userConfig?.reconnectDelay,
      userConfig?.maxReconnectAttempts,
      userConfig?.connectionTimeout,
      userConfig?.heartbeatInterval
    ]
  );

  // Update metrics
  useEffect(() => {
    metricsIntervalRef.current = setInterval(() => {
      const currentCount = messageCountRef.current;
      const messagesPerSecond = currentCount - lastMessageCountRef.current;
      lastMessageCountRef.current = currentCount;

      setMetrics((prev) => ({
        ...prev,
        messageCount: currentCount,
        messagesPerSecond,
        ...(lastMessageAtRef.current ? { lastMessage: lastMessageAtRef.current } : {})
      }));
    }, 1000);

    return () => {
      if (metricsIntervalRef.current) {
        clearInterval(metricsIntervalRef.current);
      }
    };
  }, []);

  // Create WebSocket client
  useEffect(() => {
    if (!endpoint) return;

    const handlers: WebSocketHandlers = {
      onOpen: memoizedOnOpen,
      onClose: memoizedOnClose,
      onError: memoizedOnError,
      onMessage: memoizedOnMessage,
      onReconnectAttempt: memoizedOnReconnectAttempt,
      onReconnectExhausted: memoizedOnReconnectExhausted
    };

    const lease = connectionManager.acquireConnection(endpoint, handlers, config);
    leaseRef.current = lease;
    clientRef.current = lease.client;

    return () => {
      lease.release();
      if (leaseRef.current === lease) {
        leaseRef.current = null;
        clientRef.current = null;
      }
    };
  }, [
    endpoint,
    config,
    memoizedOnOpen,
    memoizedOnClose,
    memoizedOnError,
    memoizedOnMessage,
    memoizedOnReconnectAttempt,
    memoizedOnReconnectExhausted
  ]);

  // Handle autoConnect changes separately
  useEffect(() => {
    const lease = leaseRef.current;
    if (!lease) return;

    if (autoConnect) {
      setState("connecting");
      setStatus("connecting");
      lease.connect();
    } else {
      lease.disconnect();
      setState("disconnected");
      setStatus("disconnected");
    }
  }, [autoConnect, endpoint, config]);

  // Connect function
  const connect = useCallback(() => {
    setState("connecting");
    setStatus("connecting");
    setError(null);
    leaseRef.current?.connect();
  }, []);

  // Disconnect function
  const disconnect = useCallback(() => {
    leaseRef.current?.disconnect();
    setState("disconnected");
    setStatus("disconnected");
    setMetrics((prev) => {
      const next = { ...prev };
      delete next.connectedAt;
      return next;
    });
  }, []);

  // Send function
  const send = useCallback((message: T) => {
    if (!clientRef.current?.isConnected) {
      throw new Error("WebSocket is not connected");
    }
    clientRef.current.send(message);
  }, []);

  // Subscribe function
  const subscribe = useCallback((subscription: IMessageSubscription<T>) => {
    const id = Symbol("subscription");
    subscriptionsRef.current.set(id, subscription);

    // Return unsubscribe function
    return () => {
      subscriptionsRef.current.delete(id);
    };
  }, []);

  return {
    client: clientRef.current,
    state,
    status,
    isConnected: state === "connected",
    error,
    connect,
    disconnect,
    send,
    subscribe,
    metrics
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
    endpoint: "/ws/can-sniffer",
    autoConnect: options?.autoConnect ?? false,
    onMessage: (message) => {
      setMessageCount((prev) => prev + 1);
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
export { useCANRecorderWebSocket } from "./websocket/useCANRecorderWebSocket";
export { useCANAnalyzerWebSocket } from "./websocket/useCANAnalyzerWebSocket";
export { useCANFilterWebSocket } from "./websocket/useCANFilterWebSocket";
