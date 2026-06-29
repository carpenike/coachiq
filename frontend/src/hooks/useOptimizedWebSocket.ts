/**
 * Enhanced WebSocket Hook with Performance Optimizations
 *
 * Adds advanced features like message batching, throttling, and
 * selective subscriptions for better performance.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { RVCWebSocketClient, WebSocketHandlers } from '../api';
import type { EntityUpdateMessage } from '../api/types';
import { queryKeys } from '@/lib/query-client';
import { entitiesQueryKeys } from '@/hooks/useEntities';

interface UseOptimizedWebSocketOptions {
  autoConnect?: boolean;
  batchUpdates?: boolean;
  batchDelay?: number;
  throttleDelay?: number;
  maxBatchSize?: number;
  selectiveSubscription?: string[];
}

interface BatchedUpdate {
  entityId: string;
  data: EntityUpdateMessage['data'];
  timestamp: number;
}

export function useOptimizedEntityWebSocket(options: UseOptimizedWebSocketOptions = {}) {
  const {
    autoConnect = true,
    batchUpdates = true,
    batchDelay = 100,
    throttleDelay = 50,
    maxBatchSize = 10,
    selectiveSubscription,
  } = options;

  const queryClient = useQueryClient();
  const [client, setClient] = useState<RVCWebSocketClient | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageCount, setMessageCount] = useState(0);
  const [lastMessageTime, setLastMessageTime] = useState<Date | null>(null);

  // Batching and throttling refs
  const batchRef = useRef<BatchedUpdate[]>([]);
  const batchTimerRef = useRef<NodeJS.Timeout | null>(null);
  const throttleTimerRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Performance metrics
  const [metrics, setMetrics] = useState({
    messagesPerSecond: 0,
    averageLatency: 0,
    totalMessages: 0,
    connectionStartTime: null as Date | null,
  });

  const metricsIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Stable refs to break circular dependencies
  const queryClientRef = useRef(queryClient);
  const selectiveSubscriptionRef = useRef(selectiveSubscription);
  const throttleDelayRef = useRef(throttleDelay);
  const clientRef = useRef<RVCWebSocketClient | null>(null);

  // Stable refs for functions to avoid circular dependencies
  const addToBatchRef = useRef<((entityId: string, data: EntityUpdateMessage['data']) => void) | null>(null);
  const updateMetricsRef = useRef<(() => void) | null>(null);
  const flushBatchRef = useRef<(() => void) | null>(null);

  // Update refs without causing re-renders
  useEffect(() => {
    queryClientRef.current = queryClient;
  }, [queryClient]);

  useEffect(() => {
    selectiveSubscriptionRef.current = selectiveSubscription;
  }, [selectiveSubscription]);

  useEffect(() => {
    throttleDelayRef.current = throttleDelay;
  }, [throttleDelay]);

  // Stable throttled update function using refs
  const throttledUpdate = useCallback((updates: BatchedUpdate[]) => {
    if (throttleTimerRef.current) return;

    throttleTimerRef.current = setTimeout(() => {
      // Process batched updates
      const entityGroups = new Map<string, BatchedUpdate>();

      // Keep only the latest update for each entity
      updates.forEach(update => {
        const existing = entityGroups.get(update.entityId);
        if (!existing || update.timestamp > existing.timestamp) {
          entityGroups.set(update.entityId, update);
        }
      });

      // Apply updates to React Query cache using refs
      const currentQueryClient = queryClientRef.current;
      const currentSelectiveSubscription = selectiveSubscriptionRef.current;

      entityGroups.forEach((update) => {
        // Skip if selective subscription is enabled and entity is not included
        if (currentSelectiveSubscription && !currentSelectiveSubscription.includes(update.entityId)) {
          return;
        }

        currentQueryClient.setQueryData(
          entitiesQueryKeys.entity(update.entityId),
          update.data.entity_data
        );

        // Update type-specific lists based on entity type
        const entityType = update.data.entity_data.entity_type;
        if (entityType === 'light') {
          void currentQueryClient.invalidateQueries({ queryKey: queryKeys.lights.list() });
        } else if (entityType === 'lock') {
          void currentQueryClient.invalidateQueries({ queryKey: queryKeys.locks.list() });
        } else if (entityType === 'tank_sensor') {
          void currentQueryClient.invalidateQueries({ queryKey: queryKeys.tankSensors.list() });
        } else if (entityType === 'temperature_sensor') {
          void currentQueryClient.invalidateQueries({ queryKey: queryKeys.temperatureSensors.list() });
        }
      });

      // Invalidate entity lists once for all updates
      void currentQueryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() });

      throttleTimerRef.current = null;
    }, throttleDelayRef.current);
  }, []); // No dependencies - using refs for all dynamic values

  // Stable flushBatch function using throttledUpdate ref
  const flushBatch = useCallback(() => {
    if (batchRef.current.length === 0) return;

    throttledUpdate([...batchRef.current]);
    batchRef.current = [];

    if (batchTimerRef.current) {
      clearTimeout(batchTimerRef.current);
      batchTimerRef.current = null;
    }
  }, [throttledUpdate]);

  // Stable refs for other functions
  const batchUpdatesRef = useRef(batchUpdates);
  const maxBatchSizeRef = useRef(maxBatchSize);
  const batchDelayRef = useRef(batchDelay);

  // Update refs without causing re-renders
  useEffect(() => {
    batchUpdatesRef.current = batchUpdates;
  }, [batchUpdates]);

  useEffect(() => {
    maxBatchSizeRef.current = maxBatchSize;
  }, [maxBatchSize]);

  useEffect(() => {
    batchDelayRef.current = batchDelay;
  }, [batchDelay]);

  // Stable addToBatch function
  const addToBatch = useCallback((entityId: string, data: EntityUpdateMessage['data']) => {
    const update: BatchedUpdate = {
      entityId,
      data,
      timestamp: Date.now(),
    };

    batchRef.current.push(update);

    if (!batchUpdatesRef.current || batchRef.current.length >= maxBatchSizeRef.current) {
      // Flush immediately if batching is disabled or batch is full
      flushBatch();
    } else {
      // Schedule batch flush
      if (batchTimerRef.current) {
        clearTimeout(batchTimerRef.current);
      }
      batchTimerRef.current = setTimeout(flushBatch, batchDelayRef.current);
    }
  }, [flushBatch]);

  // Stable updateMetrics function
  const updateMetrics = useCallback(() => {
    setMetrics(prev => {
      const now = Date.now();
      const timeSinceStart = prev.connectionStartTime
        ? (now - prev.connectionStartTime.getTime()) / 1000
        : 1;

      return {
        ...prev,
        messagesPerSecond: prev.totalMessages / timeSinceStart,
      };
    });
  }, []);

  // Assign stable functions to refs
  addToBatchRef.current = addToBatch;
  updateMetricsRef.current = updateMetrics;
  flushBatchRef.current = flushBatch;

  useEffect(() => {
    if (!autoConnect) return;

    const handlers: WebSocketHandlers = {
      onEntityUpdate: (data: EntityUpdateMessage['data']) => {
        const now = new Date();
        setLastMessageTime(now);
        setMessageCount(prev => prev + 1);
        setMetrics(prev => ({
          ...prev,
          totalMessages: prev.totalMessages + 1
        }));

        // Use ref to avoid dependency issues
        if (addToBatchRef.current) {
          addToBatchRef.current(data.entity_id, data);
        }
      },

      onOpen: () => {
        setIsConnected(true);
        setError(null);
        setMetrics(prev => ({
          ...prev,
          connectionStartTime: new Date(),
          totalMessages: 0,
        }));
        // Connected to entity updates WebSocket
      },

      onClose: () => {
        setIsConnected(false);
        // Disconnected from entity updates WebSocket

        // Clear metrics interval
        if (metricsIntervalRef.current) {
          clearInterval(metricsIntervalRef.current);
          metricsIntervalRef.current = null;
        }

        // Attempt to reconnect after delay
        reconnectTimeoutRef.current = setTimeout(() => {
          if (client && !client.isConnected) {
            // Attempting to reconnect WebSocket
            client.connect();
          }
        }, 5000);
      },

      onError: (error: Event) => {
        setError(error.type || 'WebSocket error');
        console.error('[WebSocket] Entity updates error:', error);
      },
    };

    // Import the creation function dynamically to avoid circular dependencies
    void import('../api').then(({ createEntityWebSocket }) => {
      const wsClient = createEntityWebSocket(handlers, {
        autoReconnect: true,
        reconnectDelay: 3000,
        maxReconnectAttempts: 0,
        heartbeatInterval: 30000,
      });

      setClient(wsClient);
      clientRef.current = wsClient;
      wsClient.connect();

      // Start metrics collection using ref
      metricsIntervalRef.current = setInterval(() => {
        if (updateMetricsRef.current) {
          updateMetricsRef.current();
        }
      }, 1000);
    });

    return () => {
      // Cleanup
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (batchTimerRef.current) {
        clearTimeout(batchTimerRef.current);
      }
      if (throttleTimerRef.current) {
        clearTimeout(throttleTimerRef.current);
      }
      if (metricsIntervalRef.current) {
        clearInterval(metricsIntervalRef.current);
      }

      // Flush any remaining batched updates using ref
      if (flushBatchRef.current) {
        flushBatchRef.current();
      }

      // Use ref to disconnect client
      if (clientRef.current) {
        clientRef.current.disconnect();
      }
    };
  }, [autoConnect, client]);

  const connect = () => clientRef.current?.connect();
  const disconnect = () => clientRef.current?.disconnect();

  return {
    client,
    isConnected,
    error,
    messageCount,
    lastMessageTime,
    metrics,
    connect,
    disconnect,
    flushPendingUpdates: flushBatch,
  };
}
