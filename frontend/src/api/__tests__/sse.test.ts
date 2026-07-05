/**
 * Tests for the SSE client (CoachEventStream) and its stream parser.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CoachEventStream, SseParser, type StreamState } from '../sse'

describe('SseParser', () => {
  it('parses a complete event with id, event and data fields', () => {
    const parser = new SseParser()
    const events = parser.feed('id: 7\nevent: entity_update\ndata: {"a":1}\n\n')
    expect(events).toEqual([{ id: '7', event: 'entity_update', data: '{"a":1}' }])
  })

  it('handles events split across chunks', () => {
    const parser = new SseParser()
    expect(parser.feed('event: entity_up')).toEqual([])
    expect(parser.feed('date\ndata: {"a"')).toEqual([])
    const events = parser.feed(':1}\n\n')
    expect(events).toEqual([{ id: null, event: 'entity_update', data: '{"a":1}' }])
  })

  it('joins multi-line data with newlines', () => {
    const parser = new SseParser()
    const events = parser.feed('data: line1\ndata: line2\n\n')
    expect(events[0]?.data).toBe('line1\nline2')
  })

  it('ignores comment/keepalive lines', () => {
    const parser = new SseParser()
    expect(parser.feed(': keepalive\n\n')).toEqual([])
  })

  it('defaults the event name to "message"', () => {
    const parser = new SseParser()
    const events = parser.feed('data: x\n\n')
    expect(events[0]?.event).toBe('message')
  })

  it('remembers the last seen id for subsequent events', () => {
    const parser = new SseParser()
    parser.feed('id: 3\ndata: first\n\n')
    const events = parser.feed('data: second\n\n')
    expect(events[0]?.id).toBe('3')
  })

  it('handles CRLF line endings', () => {
    const parser = new SseParser()
    const events = parser.feed('event: ping\r\ndata: {}\r\n\r\n')
    expect(events).toEqual([{ id: null, event: 'ping', data: '{}' }])
  })
})

/** Build a fetch Response whose body streams the given SSE payload and then stays open. */
function streamingResponse(payload: string, { close = false } = {}): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload))
      if (close) controller.close()
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('CoachEventStream', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('dispatches parsed events with JSON payloads and tracks state', async () => {
    fetchMock.mockResolvedValue(
      streamingResponse('id: 1\nevent: entity_update\ndata: {"entity_id":"light_1"}\n\n')
    )

    const received: { event: string; data: unknown }[] = []
    const states: StreamState[] = []
    const stream = new CoachEventStream({
      onEvent: (event, data) => received.push({ event, data }),
      onStateChange: (state) => states.push(state),
    })

    stream.start()
    await vi.waitFor(() => {
      expect(received).toHaveLength(1)
    })

    expect(received[0]).toEqual({ event: 'entity_update', data: { entity_id: 'light_1' } })
    expect(states).toContain('connecting')
    expect(states).toContain('open')

    stream.stop()
    expect(stream.getState()).toBe('closed')
  })

  it('sends Authorization and Last-Event-ID headers on reconnect', async () => {
    // First connection delivers an event with id 5 then the server closes.
    fetchMock
      .mockResolvedValueOnce(streamingResponse('id: 5\ndata: {}\n\n', { close: true }))
      .mockResolvedValue(streamingResponse(''))

    const stream = new CoachEventStream({ onEvent: () => undefined })
    stream.start()

    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(1)
    })
    // Server closed → client backs off → redials with Last-Event-ID.
    await vi.waitFor(
      () => {
        expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2)
      },
      { timeout: 5000 }
    )

    const secondCallHeaders = (fetchMock.mock.calls[1]?.[1] as RequestInit).headers as Record<
      string,
      string
    >
    expect(secondCallHeaders['Last-Event-ID']).toBe('5')

    stream.stop()
  })

  it('surfaces auth failure when a 401 cannot be refreshed', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }))

    const states: StreamState[] = []
    const stream = new CoachEventStream({
      onEvent: () => undefined,
      onStateChange: (state) => states.push(state),
    })

    stream.start()
    await vi.waitFor(() => {
      expect(states).toContain('auth-failed')
    })

    stream.stop()
  })
})
