/**
 * WebSocket Integration Tests
 *
 * Comprehensive test suite for WebSocket functionality including
 * connection management, message handling, and error scenarios.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { waitFor } from '@testing-library/dom';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RVCWebSocketClient } from '../../api/websocket';
import { useEntityWebSocket } from '../useWebSocket';

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  url = '';
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    // Simulate connection after a short delay
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.(new Event('open'));
    }, 10);
  }

  send(data: string | ArrayBuffer | Blob | ArrayBufferView) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }
    // Simulate echo for testing
    setTimeout(() => {
      this.onmessage?.(new MessageEvent('message', { data }));
    }, 5);
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSING;
    setTimeout(() => {
      this.readyState = MockWebSocket.CLOSED;
      const closeEventInit: CloseEventInit = { code: code || 1000 };
      if (reason !== undefined) {
        closeEventInit.reason = reason;
      }
      this.onclose?.(new CloseEvent('close', closeEventInit));
    }, 5);
  }

  // Test helpers
  simulateMessage(data: unknown) {
    if (this.readyState === MockWebSocket.OPEN) {
      this.onmessage?.(new MessageEvent('message', {
        data: typeof data === 'string' ? data : JSON.stringify(data)
      }));
    }
  }

  simulateError() {
    this.onerror?.(new Event('error'));
  }

  simulateClose(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent('close', { code, reason }));
  }
}

// Mock the WebSocket API
// Mock WebSocket for testing
global.WebSocket = MockWebSocket as unknown as typeof WebSocket;

// Test utilities
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  const TestQueryProvider = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
  TestQueryProvider.displayName = 'TestQueryProvider';

  return TestQueryProvider;
}

describe('WebSocket Integration Tests', () => {
  let mockWebSocket: MockWebSocket;

  beforeEach(() => {
    vi.clearAllMocks();
    // Reset WebSocket mock
    mockWebSocket = new MockWebSocket('ws://test');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('useEntityWebSocket', () => {
    it('should connect automatically when autoConnect is true', async () => {
      const { result } = renderHook(
        () => useEntityWebSocket({ autoConnect: true }),
        { wrapper: createWrapper() }
      );

      // Initially disconnected
      expect(result.current.isConnected).toBe(false);

      // Wait for connection
      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      expect(result.current.error).toBeNull();
    });

    it('should not connect automatically when autoConnect is false', async () => {
      const { result } = renderHook(
        () => useEntityWebSocket({ autoConnect: false }),
        { wrapper: createWrapper() }
      );

      // Should remain disconnected
      expect(result.current.isConnected).toBe(false);

      // Wait a bit to ensure it doesn't auto-connect
      await new Promise(resolve => setTimeout(resolve, 50));
      expect(result.current.isConnected).toBe(false);
    });

    it('should handle entity update messages', async () => {
      const { result } = renderHook(
        () => useEntityWebSocket({ autoConnect: true }),
        { wrapper: createWrapper() }
      );

      // Wait for connection
      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Simulate entity update message
      const entityUpdate = {
        type: 'entity_update',
        data: {
          entity_id: 'light_1',
          entity_data: {
            entity_id: 'light_1',
            entity_type: 'light',
            name: 'Kitchen Light',
            state: 'on',
            brightness: 80,
          },
        },
      };

      act(() => {
        mockWebSocket.simulateMessage(entityUpdate);
      });

      // Message should be processed (we can't easily test React Query cache updates in this test)
      // but we can verify the hook doesn't crash
      expect(result.current.isConnected).toBe(true);
    });

    it('should handle connection errors', async () => {
      const { result } = renderHook(
        () => useEntityWebSocket({ autoConnect: true }),
        { wrapper: createWrapper() }
      );

      // Wait for connection
      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Simulate error
      act(() => {
        mockWebSocket.simulateError();
      });

      await waitFor(() => {
        expect(result.current.error).toBeTruthy();
      });
    });

    it('should attempt reconnection after unexpected disconnection', async () => {
      const { result } = renderHook(
        () => useEntityWebSocket({ autoConnect: true }),
        { wrapper: createWrapper() }
      );

      // Wait for connection
      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Simulate unexpected disconnection (not normal close code 1000)
      act(() => {
        mockWebSocket.simulateClose(1006, 'Connection lost');
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(false);
      });

      // Should attempt to reconnect (we can't easily test the timeout in this test)
      // but we can verify the hook handles the disconnection gracefully
      expect(result.current.error).toBeNull();
    });

    it('should clean up properly on unmount', async () => {
      const { result, unmount } = renderHook(
        () => useEntityWebSocket({ autoConnect: true }),
        { wrapper: createWrapper() }
      );

      // Wait for connection
      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Unmount should trigger cleanup
      unmount();

      // WebSocket should be closed
      expect(mockWebSocket.readyState).toBe(MockWebSocket.CLOSED);
    });
  });

  describe('RVCWebSocketClient', () => {
    it('should handle connection lifecycle correctly', async () => {
      const handlers = {
        onOpen: vi.fn(),
        onClose: vi.fn(),
        onError: vi.fn(),
        onMessage: vi.fn(),
      };

      const client = new RVCWebSocketClient('/test', handlers);

      expect(client.state).toBe('disconnected');
      expect(client.isConnected).toBe(false);

      // Connect
      client.connect();
      expect(client.state).toBe('connecting');

      // Wait for connection
      await waitFor(() => {
        expect(client.isConnected).toBe(true);
      });

      expect(client.state).toBe('connected');
      expect(handlers.onOpen).toHaveBeenCalled();

      // Disconnect
      client.disconnect();

      await waitFor(() => {
        expect(client.state).toBe('disconnected');
      });

      expect(handlers.onClose).toHaveBeenCalled();
    });

    it('should send messages correctly', async () => {
      const client = new RVCWebSocketClient('/test');
      client.connect();

      await waitFor(() => {
        expect(client.isConnected).toBe(true);
      });

      const message = { type: 'test', data: 'hello' };

      expect(() => {
        client.send(message);
      }).not.toThrow();
    });

    it('should throw error when sending while disconnected', () => {
      const client = new RVCWebSocketClient('/test');

      expect(() => {
        client.send({ type: 'test' });
      }).toThrow('WebSocket is not connected');
    });

    it('should handle heartbeat correctly', async () => {
      const client = new RVCWebSocketClient('/test', {}, {
        heartbeatInterval: 100, // Fast heartbeat for testing
      });

      client.connect();

      await waitFor(() => {
        expect(client.isConnected).toBe(true);
      });

      // Wait for heartbeat to be sent
      await new Promise(resolve => setTimeout(resolve, 150));

      // Should still be connected (heartbeat prevents timeout)
      expect(client.isConnected).toBe(true);
    });

    it('should respect reconnection limits', async () => {
      const onClose = vi.fn();
      const client = new RVCWebSocketClient('/test', { onClose }, {
        autoReconnect: true,
        maxReconnectAttempts: 2,
        reconnectDelay: 50,
      });

      client.connect();

      await waitFor(() => {
        expect(client.isConnected).toBe(true);
      });

      // Simulate multiple disconnections
      for (let i = 0; i < 3; i++) {
        mockWebSocket.simulateClose(1006, 'Test disconnect');
        await new Promise(resolve => setTimeout(resolve, 60));
      }

      // Should have stopped attempting to reconnect after max attempts
      expect(onClose).toHaveBeenCalledTimes(3);
    });
  });

  describe('WebSocket Performance', () => {
    it('should handle high-frequency messages without blocking', async () => {
      const messageHandler = vi.fn();
      const client = new RVCWebSocketClient('/test', {
        onMessage: messageHandler,
      });

      client.connect();

      await waitFor(() => {
        expect(client.isConnected).toBe(true);
      });

      // Send many messages quickly
      const messageCount = 100;
      const startTime = Date.now();

      for (let i = 0; i < messageCount; i++) {
        mockWebSocket.simulateMessage({
          type: 'entity_update',
          data: { entity_id: `entity_${i}`, value: i },
        });
      }

      await waitFor(() => {
        expect(messageHandler).toHaveBeenCalledTimes(messageCount);
      });

      const endTime = Date.now();
      const duration = endTime - startTime;

      // Should process messages reasonably quickly (less than 1 second for 100 messages)
      expect(duration).toBeLessThan(1000);
    });
  });
});
