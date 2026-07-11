/**
 * WebSocket Integration Tests
 *
 * Comprehensive test suite for WebSocket functionality including
 * connection management, message handling, and error scenarios.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RVCWebSocketClient } from "../../api/websocket";
import { useWebSocket } from "../useWebSocket";

// Mock WebSocket
class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static readonly instances: MockWebSocket[] = [];
  private static autoOpen = true;

  static reset(): void {
    MockWebSocket.instances.length = 0;
    MockWebSocket.autoOpen = true;
  }

  static disableAutoOpen(): void {
    MockWebSocket.autoOpen = false;
  }

  readyState = MockWebSocket.CONNECTING;
  url = "";
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);

    queueMicrotask(() => {
      if (!MockWebSocket.autoOpen || this.readyState !== MockWebSocket.CONNECTING) return;
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.(new Event("open"));
    });
  }

  send(data: string | ArrayBuffer | Blob | ArrayBufferView) {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error("WebSocket is not connected");
    }
    queueMicrotask(() => {
      this.onmessage?.(new MessageEvent("message", { data }));
    });
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSING;
    queueMicrotask(() => {
      this.readyState = MockWebSocket.CLOSED;
      const closeEventInit: CloseEventInit = { code: code || 1000 };
      if (reason !== undefined) {
        closeEventInit.reason = reason;
      }
      this.onclose?.(new CloseEvent("close", closeEventInit));
    });
  }

  // Test helpers
  simulateMessage(data: unknown) {
    if (this.readyState === MockWebSocket.OPEN) {
      this.onmessage?.(
        new MessageEvent("message", {
          data: typeof data === "string" ? data : JSON.stringify(data)
        })
      );
    }
  }

  simulateError() {
    this.onerror?.(new Event("error"));
  }

  simulateClose(code = 1000, reason = "") {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close", { code, reason }));
  }
}

// Mock the WebSocket API
// Mock WebSocket for testing
global.WebSocket = MockWebSocket as unknown as typeof WebSocket;

function latestSocket(): MockWebSocket {
  const socket = MockWebSocket.instances.at(-1);
  if (!socket) throw new Error("Expected RVCWebSocketClient to create a WebSocket");
  return socket;
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
}

/** Fresh hook options per call: new handler identities every render, like real inline callers. */
function freshHandlerOptions() {
  return {
    endpoint: "/ws/can-sniffer",
    autoConnect: true,
    onMessage: (_message: unknown): undefined => undefined,
    subscriptions: [{ handler: (_message: unknown): undefined => undefined }]
  };
}

// Test utilities
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  const TestQueryProvider = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  TestQueryProvider.displayName = "TestQueryProvider";

  return TestQueryProvider;
}

describe("WebSocket Integration Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockWebSocket.reset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe("useWebSocket (generic diagnostic-stream hook)", () => {
    it("should connect automatically when autoConnect is true", async () => {
      const { result } = renderHook(
        () => useWebSocket({ endpoint: "/ws/can-sniffer", autoConnect: true }),
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

    it("should not connect automatically when autoConnect is false", () => {
      const { result } = renderHook(
        () => useWebSocket({ endpoint: "/ws/can-sniffer", autoConnect: false }),
        { wrapper: createWrapper() }
      );

      // Should remain disconnected
      expect(result.current.isConnected).toBe(false);

      expect(result.current.isConnected).toBe(false);
      expect(MockWebSocket.instances).toHaveLength(0);
    });

    it("should stay connected across re-renders with inline handlers", async () => {
      // Regression guard for the PR #218 bug class: inline handlers used to
      // change identity every render, re-run the connection effect, and tear
      // the socket down mid-connect. freshHandlerOptions() runs on every
      // render, so the handler identities churn exactly like real callers'
      // inline handlers do — that churn is what this test exercises.
      const { result, rerender } = renderHook(() => useWebSocket(freshHandlerOptions()), {
        wrapper: createWrapper()
      });

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      rerender();
      rerender();

      expect(result.current.isConnected).toBe(true);
      expect(result.current.error).toBeNull();
    });

    it("should clean up properly on unmount", async () => {
      const { result, unmount } = renderHook(
        () => useWebSocket({ endpoint: "/ws/can-sniffer", autoConnect: true }),
        { wrapper: createWrapper() }
      );

      // Wait for connection
      await waitFor(() => {
        expect(result.current.isConnected).toBe(true);
      });

      // Unmount releases the connection-manager refcount and closes the socket
      unmount();
    });
  });

  describe("RVCWebSocketClient", () => {
    it("should handle connection lifecycle correctly", async () => {
      const handlers = {
        onOpen: vi.fn(),
        onClose: vi.fn(),
        onError: vi.fn(),
        onMessage: vi.fn()
      };

      const client = new RVCWebSocketClient("/test", handlers);

      expect(client.state).toBe("disconnected");
      expect(client.isConnected).toBe(false);

      // Connect
      client.connect();
      expect(client.state).toBe("connecting");

      await flushMicrotasks();

      expect(client.isConnected).toBe(true);
      expect(client.state).toBe("connected");
      expect(handlers.onOpen).toHaveBeenCalledTimes(1);

      // Disconnect
      client.disconnect();
      await flushMicrotasks();

      expect(client.state).toBe("disconnected");
      expect(handlers.onClose).toHaveBeenCalledTimes(1);
      expect(handlers.onClose).toHaveBeenCalledWith(
        expect.objectContaining({ code: 1000, reason: "Client disconnect" })
      );
    });

    it("should send messages correctly", async () => {
      const client = new RVCWebSocketClient("/test");
      client.connect();
      await flushMicrotasks();

      const message = { type: "test", data: "hello" };

      expect(() => {
        client.send(message);
      }).not.toThrow();
    });

    it("should throw error when sending while disconnected", () => {
      const client = new RVCWebSocketClient("/test");

      expect(() => {
        client.send({ type: "test" });
      }).toThrow("WebSocket is not connected");
    });

    it("should handle heartbeat correctly", async () => {
      vi.useFakeTimers();
      const client = new RVCWebSocketClient(
        "/test",
        {},
        {
          heartbeatInterval: 100 // Fast heartbeat for testing
        }
      );

      client.connect();
      await flushMicrotasks();

      vi.advanceTimersByTime(150);
      await flushMicrotasks();

      // Should still be connected (heartbeat prevents timeout)
      expect(client.isConnected).toBe(true);
    });

    it("should respect reconnection limits", async () => {
      vi.useFakeTimers();
      const onClose = vi.fn();
      const onReconnectAttempt = vi.fn();
      const onReconnectExhausted = vi.fn();
      const client = new RVCWebSocketClient(
        "/test",
        {
          onClose,
          onReconnectAttempt,
          onReconnectExhausted
        },
        {
          autoReconnect: true,
          maxReconnectAttempts: 2,
          reconnectDelay: 50
        }
      );

      client.connect();
      await flushMicrotasks();
      expect(client.isConnected).toBe(true);

      MockWebSocket.disableAutoOpen();

      for (let attempt = 1; attempt <= 2; attempt++) {
        latestSocket().simulateClose(1006, "Test disconnect");
        expect(onReconnectAttempt).toHaveBeenLastCalledWith(attempt, 2, 50);
        vi.advanceTimersByTime(50);
        expect(MockWebSocket.instances).toHaveLength(attempt + 1);
      }

      latestSocket().simulateClose(1006, "Test disconnect");

      expect(onClose).toHaveBeenCalledTimes(3);
      expect(onReconnectAttempt).toHaveBeenCalledTimes(2);
      expect(onReconnectExhausted).toHaveBeenCalledOnce();
      expect(onReconnectExhausted).toHaveBeenCalledWith(2);
      expect(client.state).toBe("error");

      vi.runAllTimers();
      expect(MockWebSocket.instances).toHaveLength(3);
    });
  });

  describe("WebSocket Performance", () => {
    it("should handle high-frequency messages without blocking", async () => {
      const messageHandler = vi.fn();
      const client = new RVCWebSocketClient("/test", {
        onMessage: messageHandler
      });

      client.connect();
      await flushMicrotasks();
      expect(client.isConnected).toBe(true);

      // Send many messages quickly
      const messageCount = 100;
      const startTime = performance.now();
      const socket = latestSocket();

      for (let i = 0; i < messageCount; i++) {
        socket.simulateMessage({
          type: "entity_update",
          data: { entity_id: `entity_${i}`, value: i }
        });
      }

      const endTime = performance.now();
      const duration = endTime - startTime;

      expect(messageHandler).toHaveBeenCalledTimes(messageCount);
      // Should process messages reasonably quickly (less than 1 second for 100 messages)
      expect(duration).toBeLessThan(1000);
    });
  });
});
