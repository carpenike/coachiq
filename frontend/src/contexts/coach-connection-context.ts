/**
 * Coach Connection Context
 *
 * React context + hook for consuming the derived coach connectivity verdict
 * (LIVE | STALE | OFFLINE). See coach-connection.tsx for the provider that
 * computes this state.
 */

import { createContext, useContext } from 'react';

export type WebSocketHealth = 'connected' | 'connecting' | 'down';
export type CanbusHealth = 'active' | 'silent';
export type CoachState = 'LIVE' | 'STALE' | 'OFFLINE';

export interface ICoachConnectionState {
  websocket: WebSocketHealth;
  canbus: CanbusHealth;
  coach: CoachState;
  /** Freshest entity last_updated across the cache, if any entities loaded */
  entitiesFreshestAt: Date | null;
  /** Best available "last real data" timestamp (entities or CAN activity) */
  lastDataAt: Date | null;
  /** Human-readable explanation of the current (non-LIVE) state */
  reason: string;
  /** Invalidate CAN telemetry + reconnect the WebSocket */
  retry: () => void;
}

export const CoachConnectionContext = createContext<ICoachConnectionState | null>(null);

/** Query key for /api/v1/networks/status, shared with pages that need the raw snapshot. */
export const networksStatusQueryKey = ['networks', 'status'] as const;

/**
 * Hook to access the coach connection verdict.
 * @throws Error if used outside CoachConnectionProvider
 */
export function useCoachConnection(): ICoachConnectionState {
  const context = useContext(CoachConnectionContext);
  if (!context) {
    throw new Error('useCoachConnection must be used within a CoachConnectionProvider');
  }
  return context;
}
