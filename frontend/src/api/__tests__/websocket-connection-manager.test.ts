/**
 * Tests for WebSocket Connection Manager
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { connectionManager } from "../websocket-connection-manager";
import { RVCWebSocketClient, type WebSocketHandlers } from "../websocket";

interface MockClient {
  handlers: WebSocketHandlers;
  isConnected: boolean;
  state: "connecting" | "connected" | "disconnected";
  connect: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
}

// Mock RVCWebSocketClient
vi.mock("../websocket", () => ({
  RVCWebSocketClient: vi.fn().mockImplementation((_endpoint, handlers) => {
    const client: MockClient = {
      handlers,
      isConnected: false,
      state: "disconnected",
      connect: vi.fn(() => {
        client.state = "connecting";
      }),
      disconnect: vi.fn(() => {
        client.isConnected = false;
        client.state = "disconnected";
      })
    };
    return client;
  })
}));

function asMockClient(client: RVCWebSocketClient): MockClient {
  return client as unknown as MockClient;
}

describe("WebSocketConnectionManager", () => {
  beforeEach(() => {
    // Clear all connections before each test
    connectionManager.disconnectAll();
    vi.clearAllMocks();
  });

  afterEach(() => {
    connectionManager.disconnectAll();
  });

  it("creates one transport for a new diagnostic endpoint", () => {
    const endpoint = "/ws/can-sniffer";
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    const lease = connectionManager.acquireConnection(endpoint, handlers, config);

    expect(lease.client).toBeDefined();
    expect(RVCWebSocketClient).toHaveBeenCalledTimes(1);
    expect(connectionManager.hasConnection(endpoint)).toBe(true);
    expect(connectionManager.getConnectionCount()).toBe(1);
  });

  it("reuses one transport while keeping consumer callbacks independent", () => {
    const endpoint = "/ws/can-sniffer";
    const onMessage1 = vi.fn();
    const onMessage2 = vi.fn();
    const config = { autoReconnect: true };

    const lease1 = connectionManager.acquireConnection(endpoint, { onMessage: onMessage1 }, config);
    const lease2 = connectionManager.acquireConnection(endpoint, { onMessage: onMessage2 }, config);

    expect(lease1.client).toBe(lease2.client);
    expect(RVCWebSocketClient).toHaveBeenCalledTimes(1);
    expect(connectionManager.getConnectionCount()).toBe(1);

    lease1.connect();
    lease2.connect();
    const client = asMockClient(lease1.client);
    client.handlers.onMessage?.({ type: "can_message", data: {}, timestamp: "now" });

    expect(onMessage1).toHaveBeenCalledTimes(1);
    expect(onMessage2).toHaveBeenCalledTimes(1);

    lease1.release();
    client.handlers.onMessage?.({ type: "can_message", data: {}, timestamp: "now" });

    expect(onMessage1).toHaveBeenCalledTimes(1);
    expect(onMessage2).toHaveBeenCalledTimes(2);
  });

  it("disconnects the transport only when no consumer wants it", () => {
    const endpoint = "/ws/can-recorder";
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    const lease1 = connectionManager.acquireConnection(endpoint, handlers, config);
    const lease2 = connectionManager.acquireConnection(endpoint, handlers, config);
    const client = asMockClient(lease1.client);

    lease1.connect();
    lease2.connect();
    lease1.disconnect();

    expect(client.disconnect).not.toHaveBeenCalled();

    lease2.disconnect();
    expect(client.disconnect).toHaveBeenCalledTimes(1);
  });

  it("cleans up after the final lease is released exactly once", async () => {
    const endpoint = "/ws/can-analyzer";
    const lease = connectionManager.acquireConnection(endpoint, {}, {});
    const client = asMockClient(lease.client);

    lease.connect();
    lease.release();
    lease.release();
    await Promise.resolve();

    expect(connectionManager.hasConnection(endpoint)).toBe(false);
    expect(client.disconnect).toHaveBeenCalledTimes(1);
  });

  it("handles multiple diagnostic endpoints", () => {
    const endpoint1 = "/ws/can-recorder";
    const endpoint2 = "/ws/can-analyzer";
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    connectionManager.acquireConnection(endpoint1, handlers, config);
    connectionManager.acquireConnection(endpoint2, handlers, config);

    expect(connectionManager.getConnectionCount()).toBe(2);
    expect(connectionManager.hasConnection(endpoint1)).toBe(true);
    expect(connectionManager.hasConnection(endpoint2)).toBe(true);
  });

  it("disconnects all transports", () => {
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    const lease1 = connectionManager.acquireConnection("/ws/can-recorder", handlers, config);
    const lease2 = connectionManager.acquireConnection("/ws/can-analyzer", handlers, config);

    connectionManager.disconnectAll();

    expect(asMockClient(lease1.client).disconnect).toHaveBeenCalledTimes(1);
    expect(asMockClient(lease2.client).disconnect).toHaveBeenCalledTimes(1);
    expect(connectionManager.getConnectionCount()).toBe(0);
  });

  it("reuses the transport during a React StrictMode remount", async () => {
    const endpoint = "/ws/can-filter";
    const handlers = { onOpen: vi.fn() };
    const config = { autoReconnect: true };

    const firstLease = connectionManager.acquireConnection(endpoint, handlers, config);
    firstLease.connect();
    firstLease.release();
    const secondLease = connectionManager.acquireConnection(endpoint, handlers, config);
    secondLease.connect();
    await Promise.resolve();

    expect(firstLease.client).toBe(secondLease.client);
    expect(RVCWebSocketClient).toHaveBeenCalledTimes(1);
    expect(connectionManager.getConnectionCount()).toBe(1);
  });
});
