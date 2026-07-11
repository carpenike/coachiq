/**
 * WebSocket Client for Page-Scoped Diagnostics
 *
 * App-wide realtime state uses the SSE-based RealtimeProvider. This client is
 * reserved for diagnostic streams such as CAN sniffing, recording, analysis,
 * and filtering.
 */

import { WS_BASE, env, logApiRequest, logApiResponse } from "./client";
import { tokenStorage } from "@/lib/token-storage";
import type { CANMessageUpdate, WebSocketMessage, WebSocketMessageType } from "./types";

// Debug utility for WebSocket connections
export const DEBUG_WS = {
  enabled: import.meta.env.DEV && import.meta.env.VITE_DEBUG_WS === "true",
  log: (...args: unknown[]) => {
    if (DEBUG_WS.enabled) {
      console.debug("[WebSocket Debug]", ...args);
    }
  }
};

/**
 * WebSocket connection states
 */
export type WebSocketState = "connecting" | "connected" | "disconnected" | "error";

/**
 * WebSocket event handlers interface
 */
export interface WebSocketHandlers {
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (error: Event) => void;
  onMessage?: (message: WebSocketMessage) => void;
  onReconnectAttempt?: (attempt: number, maxAttempts: number, delay: number) => void;
  onReconnectExhausted?: (attempts: number) => void;
  onCANMessage?: (data: CANMessageUpdate["data"]) => void;
}

/**
 * WebSocket client configuration
 */
export interface WebSocketConfig {
  /** Auto-reconnect on connection loss */
  autoReconnect?: boolean;
  /** Reconnection delay in milliseconds */
  reconnectDelay?: number;
  /** Maximum reconnection attempts (0 = infinite) */
  maxReconnectAttempts?: number;
  /** Connection timeout in milliseconds */
  connectionTimeout?: number;
  /** Heartbeat interval in milliseconds (0 = disabled) */
  heartbeatInterval?: number;
}

/**
 * Default WebSocket configuration
 */
const defaultConfig: Required<WebSocketConfig> = {
  autoReconnect: true,
  reconnectDelay: 3000,
  maxReconnectAttempts: 0, // Infinite
  connectionTimeout: 10000,
  heartbeatInterval: 30000 // 30 seconds
};

/**
 * WebSocket client class for managing real-time connections
 */
export class RVCWebSocketClient {
  private socket: WebSocket | null = null;
  private handlers: WebSocketHandlers = {};
  private config: Required<WebSocketConfig>;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private connectionTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldBeConnected = false;
  private _state: WebSocketState = "disconnected";

  constructor(
    private readonly endpoint: string,
    handlers: WebSocketHandlers = {},
    config: WebSocketConfig = {}
  ) {
    this.handlers = handlers;
    this.config = { ...defaultConfig, ...config };
  }

  /**
   * Get current connection state
   */
  get state(): WebSocketState {
    return this._state;
  }

  /**
   * Get current connection status
   */
  get isConnected(): boolean {
    return this._state === "connected" && this.socket?.readyState === WebSocket.OPEN;
  }

  /**
   * Connect to the WebSocket endpoint
   */
  connect(): void {
    if (this.socket?.readyState === WebSocket.CONNECTING || this.isConnected) {
      return;
    }

    this.shouldBeConnected = true;
    this.reconnectAttempts = 0;
    this.openSocket();
  }

  /**
   * Open one transport connection without resetting the reconnect budget.
   */
  private openSocket(): void {
    this.disposeCurrentSocket();
    this._state = "connecting";

    // Open the socket SYNCHRONOUSLY. An earlier version awaited a token refresh
    // before dialing, which made connect() async — and that opened a race: the
    // auto-connect effect fires connect() once when auth becomes ready, but if
    // the async path left the client parked at state==='connecting' without a
    // live socket, the effect (which guards on state!=='connecting') never
    // retried, so the coach sat STALE until a manual Retry. A soon-to-expire
    // access token is not worth that: /ws accepts token-less connections, and a
    // mid-session expiry is already recovered by the 4401 close handler below.
    const token = tokenStorage.getAccessToken();
    const baseUrl = `${WS_BASE}${this.endpoint}`;
    const wsUrl = token ? `${baseUrl}?token=${encodeURIComponent(token)}` : baseUrl;

    if (env.isDevelopment) {
      logApiRequest("WS CONNECT", wsUrl);
      DEBUG_WS.log(`Connecting to ${wsUrl} (endpoint: ${this.endpoint})`);
    }

    const socket = new WebSocket(wsUrl);
    this.socket = socket;
    this.setupEventHandlers(socket);
    this.setupConnectionTimeout(socket);
  }

  /**
   * Disconnect from the WebSocket
   */
  disconnect(): void {
    this.shouldBeConnected = false;
    this.clearReconnectTimer();
    this.clearConnectionTimeout();
    this.clearHeartbeat();
    this._state = "disconnected";

    const socket = this.socket;
    if (socket?.readyState === WebSocket.CONNECTING || socket?.readyState === WebSocket.OPEN) {
      socket.close(1000, "Client disconnect");
    }
  }

  /**
   * Send a message through the WebSocket
   *
   * @param message - Message to send
   */
  send(message: unknown): void {
    if (!this.isConnected) {
      throw new Error("WebSocket is not connected");
    }

    const messageStr = typeof message === "string" ? message : JSON.stringify(message);
    this.socket!.send(messageStr);

    if (env.isDevelopment) {
      logApiRequest("WS SEND", this.endpoint, message);
    }
  }

  /**
   * Update event handlers
   */
  setHandlers(handlers: WebSocketHandlers): void {
    this.handlers = { ...this.handlers, ...handlers };
  }

  /**
   * Update configuration
   */
  updateConfig(config: Partial<WebSocketConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Setup WebSocket event handlers
   */
  private setupEventHandlers(socket: WebSocket): void {
    socket.onopen = () => {
      if (this.socket !== socket) return;

      this.clearConnectionTimeout();
      this._state = "connected";
      this.reconnectAttempts = 0;

      if (env.isDevelopment) {
        logApiResponse(`WS CONNECTED`, this.endpoint);
      }

      DEBUG_WS.log("WebSocket connected:", this.endpoint);

      this.setupHeartbeat();
      this.invokeHandler("onOpen", this.handlers.onOpen);
    };

    socket.onclose = (event) => {
      if (this.socket !== socket) return;

      this.clearConnectionTimeout();
      this.clearHeartbeat();
      this.socket = null;
      this._state = "disconnected";

      // Notify app-level listeners (e.g. CoachConnectionProvider) of close
      // codes so cross-cutting concerns like auth (4401) can react without
      // hijacking this connection's handler chain.
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("coachiq:ws-close", {
            detail: { endpoint: this.endpoint, code: event.code, reason: event.reason }
          })
        );
      }

      // Only log unexpected closures (not normal 1000 closure)
      if (env.isDevelopment && event.code !== 1000) {
        console.debug(`🔌 WebSocket closed unexpectedly: ${this.endpoint}`, {
          code: event.code,
          reason: event.reason
        });
      }

      DEBUG_WS.log("WebSocket closed:", this.endpoint, { code: event.code, reason: event.reason });

      this.invokeHandler("onClose", this.handlers.onClose, event);

      if (this.handleAuthenticationClose(event)) {
        return;
      }

      if (this.shouldBeConnected && this.config.autoReconnect) {
        this.scheduleReconnect();
      }
    };

    socket.onerror = (event) => {
      if (this.socket !== socket) return;

      this._state = "error";

      // Only log in development mode and avoid logging for common connection issues
      if (env.isDevelopment) {
        const target = event.target as WebSocket;
        // Don't log 403 or other connection errors that are likely config issues
        if (target && target.readyState !== WebSocket.CONNECTING) {
          console.error(`❌ WebSocket error: ${this.endpoint}`, event);
        }
      }

      DEBUG_WS.log("WebSocket error:", this.endpoint, event);

      this.invokeHandler("onError", this.handlers.onError, event);
    };

    socket.onmessage = (event) => {
      if (this.socket !== socket) return;

      let message: WebSocketMessage;

      try {
        message = JSON.parse(event.data) as WebSocketMessage;
      } catch (error) {
        console.error("Failed to parse WebSocket message:", error, event.data);
        DEBUG_WS.log("Failed to parse WebSocket message:", error, event.data);
        return;
      }

      if (env.isDevelopment) {
        logApiResponse(`WS MESSAGE ${this.endpoint}`, message);
      }

      DEBUG_WS.log("WebSocket message received:", this.endpoint, message);

      this.invokeHandler("onMessage", this.handlers.onMessage, message);
      this.handleTypedMessage(message as WebSocketMessageType);
    };
  }

  /**
   * Refresh an expired credential before consuming reconnect budget.
   */
  private handleAuthenticationClose(event: CloseEvent): boolean {
    if (event.code !== 1008) return false;

    console.warn(`WebSocket authentication failed: ${event.reason}`);

    if (!event.reason?.includes("expired") || !tokenStorage.isRefreshTokenValid()) {
      return true;
    }

    void tokenStorage
      .attemptTokenRefresh()
      .then((success) => {
        if (!this.shouldBeConnected) return;

        if (success) {
          this.scheduleReconnect(1000);
        } else {
          console.error("Token refresh failed");
          this.invokeHandler("onError", this.handlers.onError, new Event("auth_failed"));
        }
      })
      .catch((error: unknown) => {
        console.error("Token refresh failed:", error);
        this.invokeHandler("onError", this.handlers.onError, new Event("auth_failed"));
      });

    return true;
  }

  /**
   * Invoke a consumer callback without letting it interrupt transport processing.
   */
  private invokeHandler<TArgs extends unknown[]>(
    name: keyof WebSocketHandlers,
    handler: ((...args: TArgs) => void) | undefined,
    ...args: TArgs
  ): void {
    if (!handler) return;

    try {
      handler(...args);
    } catch (error) {
      console.error(`WebSocket ${name} handler failed:`, error);
    }
  }

  /**
   * Handle typed WebSocket messages
   */
  private handleTypedMessage(message: WebSocketMessageType): void {
    // Only dispatch typed handlers if a type field is present
    if (!message || typeof message !== "object" || !("type" in message)) {
      // No type field: just return silently (message will still be handled by onMessage)
      return;
    }

    switch (message.type) {
      case "can_message":
        this.invokeHandler(
          "onCANMessage",
          this.handlers.onCANMessage,
          (message as CANMessageUpdate).data
        );
        break;
      case "pong":
      case "heartbeat_ack":
        // Handle heartbeat responses silently
        break;
      default:
        // Handle unknown message types gracefully
        DEBUG_WS.log("Unknown WebSocket message type:", message.type, message);
    }
  }

  /**
   * Setup connection timeout
   */
  private setupConnectionTimeout(socket: WebSocket): void {
    this.connectionTimer = setTimeout(() => {
      if (this.socket === socket && this._state === "connecting") {
        this._state = "error";
        console.error(`WebSocket connection timeout: ${this.endpoint}`);
        DEBUG_WS.log("WebSocket connection timeout:", this.endpoint);
        this.invokeHandler("onError", this.handlers.onError, new Event("timeout"));
        socket.close();
      }
    }, this.config.connectionTimeout);
  }

  /**
   * Clear connection timeout
   */
  private clearConnectionTimeout(): void {
    if (this.connectionTimer) {
      clearTimeout(this.connectionTimer);
      this.connectionTimer = null;
    }
  }

  /**
   * Clear the heartbeat timer.
   */
  private clearHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /**
   * Setup heartbeat to keep connection alive
   */
  private setupHeartbeat(): void {
    if (this.config.heartbeatInterval <= 0) return;

    this.heartbeatTimer = setInterval(() => {
      if (this.isConnected) {
        try {
          this.send({ type: "ping", timestamp: new Date().toISOString() });
          DEBUG_WS.log("Heartbeat sent:", this.endpoint);
        } catch (error) {
          console.warn("Failed to send heartbeat:", error);
          DEBUG_WS.log("Failed to send heartbeat:", error);
        }
      }
    }, this.config.heartbeatInterval);
  }

  /**
   * Schedule a reconnection attempt
   */
  private scheduleReconnect(delay = this.config.reconnectDelay): void {
    if (this.reconnectTimer || !this.shouldBeConnected) return;

    if (
      this.config.maxReconnectAttempts !== 0 &&
      this.reconnectAttempts >= this.config.maxReconnectAttempts
    ) {
      this._state = "error";
      this.invokeHandler(
        "onReconnectExhausted",
        this.handlers.onReconnectExhausted,
        this.reconnectAttempts
      );
      return;
    }

    this.reconnectAttempts++;

    DEBUG_WS.log(
      "Scheduling WebSocket reconnect attempt:",
      this.reconnectAttempts,
      this.config.reconnectDelay
    );

    this.invokeHandler(
      "onReconnectAttempt",
      this.handlers.onReconnectAttempt,
      this.reconnectAttempts,
      this.config.maxReconnectAttempts,
      delay
    );

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.shouldBeConnected) {
        this.openSocket();
      }
    }, delay);
  }

  /**
   * Clear a pending reconnect timer.
   */
  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  /**
   * Dispose a superseded socket before opening another one.
   */
  private disposeCurrentSocket(): void {
    this.clearConnectionTimeout();
    this.clearHeartbeat();

    const socket = this.socket;
    if (socket) {
      socket.onopen = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;

      if (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "Connection replaced");
      }

      this.socket = null;
    }
  }
}

//
// ===== UTILITY FUNCTIONS =====
//

/**
 * Check if WebSocket is supported in the current environment
 *
 * @returns True if WebSocket is available
 */
export function isWebSocketSupported(): boolean {
  return typeof WebSocket !== "undefined";
}

/**
 * Get WebSocket ready state as human-readable string
 *
 * @param readyState - WebSocket ready state number
 * @returns Human-readable state string
 */
export function getWebSocketStateString(readyState: number): string {
  switch (readyState) {
    case WebSocket.CONNECTING:
      return "connecting";
    case WebSocket.OPEN:
      return "open";
    case WebSocket.CLOSING:
      return "closing";
    case WebSocket.CLOSED:
      return "closed";
    default:
      return "unknown";
  }
}
