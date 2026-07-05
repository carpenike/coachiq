/**
 * CoachEventStream — the app's single realtime channel (SSE over fetch).
 *
 * Replaces the old /ws data socket. fetch + ReadableStream instead of native
 * EventSource because EventSource cannot send an Authorization header and the
 * app's token lives in localStorage, not a cookie.
 *
 * What the transport gives us that the WebSocket stack had to hand-roll:
 * - Reconnection is a plain loop here (no connection manager, no ref-counting,
 *   no StrictMode double-mount hazard — an AbortController tears down cleanly).
 * - Gap recovery: the server replays events after the Last-Event-ID we send on
 *   reconnect; on a fresh connect (no id) the provider resyncs via REST.
 * - Auth failures are ordinary HTTP 401s: refresh the token and redial.
 */

import { API_BASE } from '@/api/client'
import { tokenStorage } from '@/lib/token-storage'

export type StreamState = 'connecting' | 'open' | 'down' | 'auth-failed' | 'closed'

export interface IStreamHandlers {
  /** Called for every named server event (entity_update, entity_created, ...). */
  onEvent: (event: string, data: unknown) => void
  /** Called on every lifecycle transition. */
  onStateChange?: (state: StreamState) => void
}

// Reconnect backoff: base doubles per attempt with jitter, capped.
const BASE_RECONNECT_DELAY_MS = 1_000
const MAX_RECONNECT_DELAY_MS = 30_000
const JITTER_MS = 1_000
// The server heartbeats every 15s; silence beyond this means the connection
// is dead even if the TCP socket hasn't noticed (sleeping tablet, dropped AP).
const STALL_TIMEOUT_MS = 45_000

interface IParsedEvent {
  event: string
  data: string
  id: string | null
}

/**
 * Incremental parser for the text/event-stream format. Feed it decoded
 * chunks; it yields complete events (fields per WHATWG spec, comments and
 * unknown fields ignored).
 */
export class SseParser {
  private buffer = ''
  private eventType = ''
  private dataLines: string[] = []
  private lastId: string | null = null

  feed(chunk: string): IParsedEvent[] {
    this.buffer += chunk
    const events: IParsedEvent[] = []
    let newlineIndex = this.buffer.indexOf('\n')
    while (newlineIndex !== -1) {
      let line = this.buffer.slice(0, newlineIndex)
      this.buffer = this.buffer.slice(newlineIndex + 1)
      if (line.endsWith('\r')) line = line.slice(0, -1)
      const complete = this.processLine(line)
      if (complete) events.push(complete)
      newlineIndex = this.buffer.indexOf('\n')
    }
    return events
  }

  private processLine(line: string): IParsedEvent | null {
    if (line === '') {
      // Blank line dispatches the pending event (if it has data).
      if (this.dataLines.length === 0) {
        this.eventType = ''
        return null
      }
      const event: IParsedEvent = {
        event: this.eventType || 'message',
        data: this.dataLines.join('\n'),
        id: this.lastId,
      }
      this.eventType = ''
      this.dataLines = []
      return event
    }
    if (line.startsWith(':')) return null // comment / keepalive

    const colonIndex = line.indexOf(':')
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex)
    let value = colonIndex === -1 ? '' : line.slice(colonIndex + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    switch (field) {
      case 'event':
        this.eventType = value
        break
      case 'data':
        this.dataLines.push(value)
        break
      case 'id':
        if (!value.includes('\0')) this.lastId = value
        break
      // 'retry' is handled server-side via the hint; client backoff governs.
      default:
        break
    }
    return null
  }
}

export class CoachEventStream {
  private readonly url: string
  private readonly handlers: IStreamHandlers
  private abortController: AbortController | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private stallTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempt = 0
  private lastEventId: string | null = null
  private state: StreamState = 'closed'
  private stopped = true

  constructor(handlers: IStreamHandlers, url = `${API_BASE}/api/events`) {
    this.handlers = handlers
    this.url = url
  }

  /** Current lifecycle state. */
  getState(): StreamState {
    return this.state
  }

  /** Start (or restart) the stream. Safe to call repeatedly. */
  start(): void {
    this.stopped = false
    this.clearReconnectTimer()
    if (this.abortController) return // already dialing/connected
    void this.runConnection()
  }

  /** Stop the stream and cancel any pending reconnect. */
  stop(): void {
    this.stopped = true
    this.clearReconnectTimer()
    this.clearStallTimer()
    this.abortController?.abort()
    this.abortController = null
    this.setState('closed')
  }

  /** Drop the current connection and redial immediately (manual retry). */
  restart(): void {
    this.abortController?.abort()
    this.abortController = null
    this.reconnectAttempt = 0
    this.start()
  }

  private setState(state: StreamState): void {
    if (this.state === state) return
    this.state = state
    this.handlers.onStateChange?.(state)
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private clearStallTimer(): void {
    if (this.stallTimer) {
      clearTimeout(this.stallTimer)
      this.stallTimer = null
    }
  }

  /** Any bytes from the server (events or keepalives) re-arm the watchdog. */
  private armStallWatchdog(): void {
    this.clearStallTimer()
    this.stallTimer = setTimeout(() => {
      this.abortController?.abort()
    }, STALL_TIMEOUT_MS)
  }

  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    const token = tokenStorage.getAccessToken()
    if (token) headers.Authorization = `Bearer ${token}`
    if (this.lastEventId !== null) headers['Last-Event-ID'] = this.lastEventId
    return headers
  }

  /** Read and dispatch events until the server closes the stream. */
  private async consumeStream(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader()
    const decoder = new TextDecoder()
    const parser = new SseParser()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) return
      this.armStallWatchdog()
      for (const parsed of parser.feed(decoder.decode(value, { stream: true }))) {
        if (parsed.id !== null) this.lastEventId = parsed.id
        this.dispatch(parsed)
      }
    }
  }

  private async runConnection(): Promise<void> {
    this.setState('connecting')
    const abortController = new AbortController()
    this.abortController = abortController
    try {
      const response = await fetch(this.url, {
        headers: this.buildHeaders(),
        signal: abortController.signal,
        cache: 'no-store',
      })

      if (response.status === 401) {
        await this.handleAuthFailure()
        return
      }
      if (!response.ok || !response.body) {
        throw new Error(`SSE connect failed: ${response.status}`)
      }

      this.setState('open')
      this.reconnectAttempt = 0
      this.armStallWatchdog()
      await this.consumeStream(response.body)
      // Server closed the stream (shutdown/restart): fall through to reconnect.
      throw new Error('SSE stream ended')
    } catch {
      // The failure reason doesn't change the response: back off and redial.
      if (this.stopped || abortController !== this.abortController) return
      this.scheduleReconnect()
    } finally {
      this.clearStallTimer()
      if (this.abortController === abortController) this.abortController = null
    }
  }

  private dispatch(parsed: IParsedEvent): void {
    let data: unknown = parsed.data
    try {
      data = JSON.parse(parsed.data)
    } catch {
      // Non-JSON payloads pass through as raw strings.
    }
    this.handlers.onEvent(parsed.event, data)
  }

  /** 401: try one token refresh, then either redial or surface auth failure. */
  private async handleAuthFailure(): Promise<void> {
    let refreshed = false
    if (tokenStorage.isRefreshTokenValid()) {
      try {
        refreshed = await tokenStorage.attemptTokenRefresh()
      } catch {
        refreshed = false
      }
    }
    if (this.stopped) return
    this.abortController = null
    if (refreshed) {
      this.scheduleReconnect()
    } else {
      this.setState('auth-failed')
    }
  }

  private scheduleReconnect(): void {
    this.setState('down')
    this.reconnectAttempt += 1
    const delay = Math.min(
      BASE_RECONNECT_DELAY_MS * 2 ** (this.reconnectAttempt - 1),
      MAX_RECONNECT_DELAY_MS
      // eslint-disable-next-line sonarjs/pseudo-random -- backoff jitter, not security-sensitive
    ) + Math.random() * JITTER_MS
    this.clearReconnectTimer()
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (!this.stopped) void this.runConnection()
    }, delay)
  }
}
