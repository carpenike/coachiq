/**
 * Realtime Context
 *
 * Lifecycle state of the app's single SSE event stream (/api/events).
 * Provided by RealtimeProvider; consumed by the coach-connection verdict.
 */

import { createContext, useContext } from 'react'

/** Health of the realtime channel as consumers see it. */
export type RealtimeHealth = 'connected' | 'connecting' | 'down'

export interface IRealtimeContext {
  /** Collapsed lifecycle state of the event stream. */
  status: RealtimeHealth
  /** True when the stream got a 401 and a token refresh failed. */
  authFailed: boolean
  /** Drop the connection (if any) and redial immediately. */
  reconnect: () => void
}

export const RealtimeContext = createContext<IRealtimeContext | null>(null)

/**
 * Hook to access realtime stream state.
 * @throws Error if used outside RealtimeProvider
 */
export function useRealtime(): IRealtimeContext {
  const context = useContext(RealtimeContext)
  if (!context) {
    throw new Error('useRealtime must be used within a RealtimeProvider')
  }
  return context
}
