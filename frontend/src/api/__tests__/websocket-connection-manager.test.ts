/**
 * Tests for WebSocket Connection Manager
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { connectionManager } from '../websocket-connection-manager';
import { RVCWebSocketClient } from '../websocket';

// Mock RVCWebSocketClient
vi.mock('../websocket', () => ({
  RVCWebSocketClient: vi.fn().mockImplementation((endpoint, handlers, config) => ({
    endpoint,
    handlers,
    config,
    isConnected: false,
    state: 'disconnected',
    connect: vi.fn(),
    disconnect: vi.fn(),
    setHandlers: vi.fn(),
  })),
}));

describe('WebSocketConnectionManager', () => {
  beforeEach(() => {
    // Clear all connections before each test
    connectionManager.disconnectAll();
    vi.clearAllMocks();
  });

  afterEach(() => {
    connectionManager.disconnectAll();
  });

  it('should create a new connection for a new endpoint', () => {
    const endpoint = '/ws/test';
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    const client = connectionManager.getConnection(endpoint, handlers, config);

    expect(client).toBeDefined();
    expect(connectionManager.hasConnection(endpoint)).toBe(true);
    expect(connectionManager.getConnectionCount()).toBe(1);
  });

  it('should reuse existing connection for the same endpoint', () => {
    const endpoint = '/ws/test';
    const handlers1 = { onOpen: vi.fn() };
    const handlers2 = { onMessage: vi.fn() };
    const config = { autoReconnect: true };

    const client1 = connectionManager.getConnection(endpoint, handlers1, config);
    const client2 = connectionManager.getConnection(endpoint, handlers2, config);

    // Should be the same instance
    expect(client1).toBe(client2);
    expect(connectionManager.getConnectionCount()).toBe(1);

    // Should have updated handlers
    expect(client2.setHandlers).toHaveBeenCalledWith(handlers2);
  });

  it('should manage reference counting correctly', () => {
    const endpoint = '/ws/test';
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    // Create two references
    const client1 = connectionManager.getConnection(endpoint, handlers, config);
    const client2 = connectionManager.getConnection(endpoint, handlers, config);

    expect(connectionManager.hasConnection(endpoint)).toBe(true);

    // Release first reference
    connectionManager.releaseConnection(endpoint);
    expect(connectionManager.hasConnection(endpoint)).toBe(true);

    // Release second reference
    connectionManager.releaseConnection(endpoint);
    expect(connectionManager.hasConnection(endpoint)).toBe(false);
    expect(client1.disconnect).toHaveBeenCalled();
  });

  it('should handle multiple different endpoints', () => {
    const endpoint1 = '/ws/test1';
    const endpoint2 = '/ws/test2';
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    connectionManager.getConnection(endpoint1, handlers, config);
    connectionManager.getConnection(endpoint2, handlers, config);

    expect(connectionManager.getConnectionCount()).toBe(2);
    expect(connectionManager.hasConnection(endpoint1)).toBe(true);
    expect(connectionManager.hasConnection(endpoint2)).toBe(true);
  });

  it('should disconnect all connections', () => {
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    const client1 = connectionManager.getConnection('/ws/test1', handlers, config);
    const client2 = connectionManager.getConnection('/ws/test2', handlers, config);

    connectionManager.disconnectAll();

    expect(client1.disconnect).toHaveBeenCalled();
    expect(client2.disconnect).toHaveBeenCalled();
    expect(connectionManager.getConnectionCount()).toBe(0);
  });

  it('should prevent duplicate connections in React StrictMode scenario', () => {
    const endpoint = '/ws/features';
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    // Simulate React StrictMode double-mount
    // First mount
    const client1 = connectionManager.getConnection(endpoint, handlers, config);

    // Cleanup (but not immediate)
    setTimeout(() => connectionManager.releaseConnection(endpoint), 10);

    // Second mount (happens immediately)
    const client2 = connectionManager.getConnection(endpoint, handlers, config);

    // Should reuse the same client instance
    expect(client1).toBe(client2);
    expect(connectionManager.getConnectionCount()).toBe(1);
  });
});
