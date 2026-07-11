# Diagnostic WebSocket Connection Manager

CoachIQ uses WebSockets only for page-scoped diagnostic streams such as CAN
sniffing, recording, analysis, and filtering. App-wide realtime state uses the
SSE-based `RealtimeProvider` and must not acquire connections through this manager.

## Ownership

The manager owns one transport per endpoint. Each `useWebSocket` hook owns a
lease with independent callbacks and connection demand:

1. `acquireConnection` creates or reuses the endpoint transport.
2. `lease.connect()` marks that consumer active and opens the transport if needed.
3. Transport events fan out only to active leases, so one consumer cannot replace another's callbacks.
4. `lease.disconnect()` removes only that lease's demand. The transport closes when no lease still wants it.
5. `lease.release()` is idempotent and removes that consumer's callbacks.

Final cleanup runs in a microtask. A React StrictMode unmount/remount in the same
turn can therefore reclaim the existing transport without opening a duplicate.

## Example

```typescript
const lease = connectionManager.acquireConnection("/ws/can-sniffer", handlers, config);

lease.connect();
lease.client.send({ type: "set_filter", canId: 0x1fedb });

// Hook cleanup
lease.release();
```

`RVCWebSocketClient` owns native socket lifecycle, heartbeat, authentication
refresh, reconnect timers, and retry limits. The manager owns sharing. The hook
only maps deterministic transport callbacks into React state and metrics.
