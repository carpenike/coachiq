/**
 * Page-scoped diagnostic WebSocket connection manager.
 *
 * One transport is shared per endpoint. Each hook owns an idempotent lease,
 * its own callbacks, and its own connection demand. App-wide realtime state
 * remains on the SSE data plane.
 */

import { RVCWebSocketClient, type WebSocketConfig, type WebSocketHandlers } from "./websocket";

interface ConnectionConsumer {
  handlers: WebSocketHandlers;
  wantsConnection: boolean;
}

interface ConnectionEntry {
  client: RVCWebSocketClient;
  configSignature: string;
  consumers: Map<symbol, ConnectionConsumer>;
  cleanupVersion: number;
}

export interface WebSocketConnectionLease {
  client: RVCWebSocketClient;
  connect: () => void;
  disconnect: () => void;
  release: () => void;
}

class WebSocketConnectionManager {
  private readonly connections = new Map<string, ConnectionEntry>();

  /**
   * Acquire one consumer lease for an endpoint-shared transport.
   */
  acquireConnection(
    endpoint: string,
    handlers: WebSocketHandlers,
    config: WebSocketConfig
  ): WebSocketConnectionLease {
    const configSignature = this.getConfigSignature(config);
    let entry = this.connections.get(endpoint);

    if (entry && entry.configSignature !== configSignature) {
      throw new Error(
        `WebSocket consumers for ${endpoint} must use the same transport configuration`
      );
    }

    if (!entry) {
      const consumers = new Map<symbol, ConnectionConsumer>();
      const client = new RVCWebSocketClient(
        endpoint,
        this.createFanoutHandlers(endpoint, consumers),
        config
      );
      entry = {
        client,
        configSignature,
        consumers,
        cleanupVersion: 0
      };
      this.connections.set(endpoint, entry);
    }

    entry.cleanupVersion++;
    const consumerId = Symbol(endpoint);
    entry.consumers.set(consumerId, {
      handlers,
      wantsConnection: false
    });

    return this.createLease(endpoint, entry, consumerId);
  }

  /**
   * Check if a transport exists for an endpoint.
   */
  hasConnection(endpoint: string): boolean {
    return this.connections.has(endpoint);
  }

  /**
   * Get the number of active endpoint transports.
   */
  getConnectionCount(): number {
    return this.connections.size;
  }

  /**
   * Disconnect all endpoint transports immediately.
   */
  disconnectAll(): void {
    const entries = [...this.connections.values()];
    this.connections.clear();

    entries.forEach((entry) => {
      entry.cleanupVersion++;
      entry.consumers.clear();
      entry.client.disconnect();
    });
  }

  private createLease(
    endpoint: string,
    entry: ConnectionEntry,
    consumerId: symbol
  ): WebSocketConnectionLease {
    let released = false;

    const getConsumer = (): ConnectionConsumer | undefined => {
      if (released || this.connections.get(endpoint) !== entry) return undefined;
      return entry.consumers.get(consumerId);
    };

    return {
      client: entry.client,
      connect: () => {
        const consumer = getConsumer();
        if (!consumer) return;

        const alreadyWantedConnection = consumer.wantsConnection;
        consumer.wantsConnection = true;
        if (entry.client.isConnected) {
          if (!alreadyWantedConnection) {
            this.invokeConsumer(endpoint, "onOpen", consumer.handlers.onOpen);
          }
          return;
        }

        entry.client.connect();
      },
      disconnect: () => {
        const consumer = getConsumer();
        if (!consumer?.wantsConnection) return;

        consumer.wantsConnection = false;
        if (!this.hasConnectionDemand(entry)) {
          entry.client.disconnect();
        }
      },
      release: () => {
        if (released) return;
        released = true;

        const consumer = entry.consumers.get(consumerId);
        if (!consumer) return;

        entry.consumers.delete(consumerId);
        if (entry.consumers.size === 0) {
          this.scheduleCleanup(endpoint, entry);
        } else if (consumer.wantsConnection && !this.hasConnectionDemand(entry)) {
          entry.client.disconnect();
        }
      }
    };
  }

  private createFanoutHandlers(
    endpoint: string,
    consumers: Map<symbol, ConnectionConsumer>
  ): WebSocketHandlers {
    return {
      onOpen: () =>
        this.notifyConsumers(endpoint, consumers, "onOpen", (handlers) => {
          handlers.onOpen?.();
        }),
      onClose: (event) =>
        this.notifyConsumers(endpoint, consumers, "onClose", (handlers) => {
          handlers.onClose?.(event);
        }),
      onError: (event) =>
        this.notifyConsumers(endpoint, consumers, "onError", (handlers) => {
          handlers.onError?.(event);
        }),
      onMessage: (message) =>
        this.notifyConsumers(endpoint, consumers, "onMessage", (handlers) => {
          handlers.onMessage?.(message);
        }),
      onReconnectAttempt: (attempt, maxAttempts, delay) =>
        this.notifyConsumers(endpoint, consumers, "onReconnectAttempt", (handlers) => {
          handlers.onReconnectAttempt?.(attempt, maxAttempts, delay);
        }),
      onReconnectExhausted: (attempts) =>
        this.notifyConsumers(endpoint, consumers, "onReconnectExhausted", (handlers) => {
          handlers.onReconnectExhausted?.(attempts);
        }),
      onCANMessage: (data) =>
        this.notifyConsumers(endpoint, consumers, "onCANMessage", (handlers) => {
          handlers.onCANMessage?.(data);
        })
    };
  }

  private notifyConsumers(
    endpoint: string,
    consumers: Map<symbol, ConnectionConsumer>,
    eventName: keyof WebSocketHandlers,
    callback: (handlers: WebSocketHandlers) => void
  ): void {
    consumers.forEach((consumer) => {
      if (!consumer.wantsConnection) return;

      try {
        callback(consumer.handlers);
      } catch (error) {
        console.error(`WebSocket ${eventName} consumer failed for ${endpoint}:`, error);
      }
    });
  }

  private invokeConsumer<TArgs extends unknown[]>(
    endpoint: string,
    eventName: keyof WebSocketHandlers,
    handler: ((...args: TArgs) => void) | undefined,
    ...args: TArgs
  ): void {
    if (!handler) return;

    try {
      handler(...args);
    } catch (error) {
      console.error(`WebSocket ${eventName} consumer failed for ${endpoint}:`, error);
    }
  }

  private hasConnectionDemand(entry: ConnectionEntry): boolean {
    return [...entry.consumers.values()].some((consumer) => consumer.wantsConnection);
  }

  private scheduleCleanup(endpoint: string, entry: ConnectionEntry): void {
    const cleanupVersion = ++entry.cleanupVersion;

    queueMicrotask(() => {
      if (
        this.connections.get(endpoint) !== entry ||
        entry.cleanupVersion !== cleanupVersion ||
        entry.consumers.size > 0
      ) {
        return;
      }

      entry.client.disconnect();
      this.connections.delete(endpoint);
    });
  }

  private getConfigSignature(config: WebSocketConfig): string {
    return JSON.stringify({
      autoReconnect: config.autoReconnect,
      reconnectDelay: config.reconnectDelay,
      maxReconnectAttempts: config.maxReconnectAttempts,
      connectionTimeout: config.connectionTimeout,
      heartbeatInterval: config.heartbeatInterval
    });
  }
}

export const connectionManager = new WebSocketConnectionManager();
