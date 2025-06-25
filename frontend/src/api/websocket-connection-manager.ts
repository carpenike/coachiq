/**
 * WebSocket Connection Manager
 *
 * Manages WebSocket connections to prevent duplicates, especially in React StrictMode.
 * Implements a singleton pattern per endpoint to ensure only one connection exists.
 */

import { RVCWebSocketClient, type WebSocketConfig, type WebSocketHandlers } from './websocket';

interface ConnectionEntry {
  client: RVCWebSocketClient;
  refCount: number;
}

class WebSocketConnectionManager {
  private connections = new Map<string, ConnectionEntry>();

  /**
   * Get or create a WebSocket connection for the given endpoint
   */
  getConnection(
    endpoint: string,
    handlers: WebSocketHandlers,
    config: WebSocketConfig
  ): RVCWebSocketClient {
    const existing = this.connections.get(endpoint);

    if (existing) {
      // Reuse existing connection
      existing.refCount++;
      // Update handlers for this consumer
      existing.client.setHandlers(handlers);
      return existing.client;
    }

    // Create new connection
    const client = new RVCWebSocketClient(endpoint, handlers, config);
    this.connections.set(endpoint, {
      client,
      refCount: 1,
    });

    return client;
  }

  /**
   * Release a connection reference
   */
  releaseConnection(endpoint: string): void {
    const entry = this.connections.get(endpoint);
    if (!entry) return;

    entry.refCount--;

    if (entry.refCount <= 0) {
      // No more consumers, disconnect and remove
      entry.client.disconnect();
      this.connections.delete(endpoint);
    }
  }

  /**
   * Check if a connection exists for an endpoint
   */
  hasConnection(endpoint: string): boolean {
    return this.connections.has(endpoint);
  }

  /**
   * Get active connection count
   */
  getConnectionCount(): number {
    return this.connections.size;
  }

  /**
   * Disconnect all connections (for cleanup)
   */
  disconnectAll(): void {
    this.connections.forEach(entry => {
      entry.client.disconnect();
    });
    this.connections.clear();
  }
}

// Global singleton instance
export const connectionManager = new WebSocketConnectionManager();
