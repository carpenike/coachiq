# WebSocket Connection Manager

## Problem

React StrictMode causes components to be mounted twice in development, which leads to duplicate WebSocket connections. This causes "Insufficient resources" errors when too many connections are opened to the same endpoint.

## Solution

The WebSocketConnectionManager implements a singleton pattern per endpoint with reference counting:

1. **Connection Pooling**: Maintains a single WebSocket connection per endpoint
2. **Reference Counting**: Tracks how many components are using each connection
3. **Automatic Cleanup**: Disconnects when the last reference is released

## How It Works

```typescript
// First component mount
const client1 = connectionManager.getConnection('/ws/features', handlers, config);
// Creates new connection, refCount = 1

// Second component mount (StrictMode)
const client2 = connectionManager.getConnection('/ws/features', handlers, config);
// Returns same connection, refCount = 2

// First component unmount
connectionManager.releaseConnection('/ws/features');
// refCount = 1, connection stays open

// Second component unmount
connectionManager.releaseConnection('/ws/features');
// refCount = 0, connection closed
```

## Benefits

- Prevents duplicate connections in React StrictMode
- Reduces resource usage
- Maintains connection stability
- Transparent to consuming components
