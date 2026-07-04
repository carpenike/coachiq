/**
 * Coach Connection Provider — the honesty layer.
 *
 * Single derived connectivity state, computed here and consumed everywhere:
 *
 *   websocket: connected | connecting | down     (WS lifecycle)
 *   canbus:    active | silent                   (real CAN rx telemetry)
 *   ────────────────────────────────────────────
 *   coach:     LIVE | STALE | OFFLINE
 *
 * No page may render a "healthy/all good" verdict from any other source.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { apiGet } from '@/api/client';
import type { EntityCollectionSchema, NetworkSummarySchema } from '@/api/types/domains';
import { useWebSocketContext } from '@/contexts/use-websocket-context';
import { entitiesQueryKeys } from '@/hooks/useEntities';
import { tokenStorage } from '@/lib/token-storage';

//
// ===== TYPES =====
//

export type WebSocketHealth = 'connected' | 'connecting' | 'down';
export type CanbusHealth = 'active' | 'silent';
export type CoachState = 'LIVE' | 'STALE' | 'OFFLINE';

export interface CoachConnectionState {
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

const CoachConnectionContext = createContext<CoachConnectionState | null>(null);

//
// ===== CONSTANTS =====
//

/** CAN bus considered silent when no interface saw traffic within this window */
const CAN_ACTIVITY_WINDOW_MS = 120_000;
/** How often to poll /api/v1/networks/status */
const NETWORKS_POLL_INTERVAL_MS = 15_000;

export const networksStatusQueryKey = ['networks', 'status'] as const;

interface WsCloseEventDetail {
  endpoint: string;
  code: number;
  reason: string;
}

//
// ===== PURE HELPERS (derivation logic, kept outside the component) =====
//

/** WebSocket lifecycle health, collapsing auth failure into "down". */
function deriveWebsocketHealth(
  authFailed: boolean,
  isConnected: boolean,
  hasError: boolean
): WebSocketHealth {
  if (authFailed) return 'down';
  if (isConnected) return 'connected';
  if (hasError) return 'down';
  return 'connecting';
}

interface CanbusActivity {
  canbus: CanbusHealth;
  canLastActivity: Date | null;
}

type NetworkInterface = NetworkSummarySchema['interfaces'][number];

/** Parsed last-activity timestamp for an interface, or null if absent/invalid. */
function interfaceLastActivityAt(iface: NetworkInterface): Date | null {
  if (!iface.last_activity) return null;
  const activityAt = new Date(iface.last_activity);
  return Number.isNaN(activityAt.getTime()) ? null : activityAt;
}

/** Whether an interface counts as "active" right now (recent activity or live message rate). */
function isInterfaceActive(iface: NetworkInterface, activityAt: Date | null, now: number): boolean {
  if (activityAt && now - activityAt.getTime() <= CAN_ACTIVITY_WINDOW_MS) return true;
  return (iface.message_rate ?? 0) > 0;
}

/** Derive CAN bus activity state from the latest networks/status snapshot. */
function computeCanbusActivity(interfaces: NetworkInterface[], now: number): CanbusActivity {
  let latest: Date | null = null;
  let active = false;

  for (const iface of interfaces) {
    const activityAt = interfaceLastActivityAt(iface);
    if (activityAt && (!latest || activityAt > latest)) latest = activityAt;
    if (isInterfaceActive(iface, activityAt, now)) active = true;
  }

  return { canbus: active ? 'active' : 'silent', canLastActivity: latest };
}

/** Reason shown for the OFFLINE verdict. */
function offlineReason(authFailed: boolean): string {
  if (authFailed) return 'authentication';
  return 'WebSocket down and the coach API is unreachable';
}

/** Reason shown for the STALE verdict when CAN is active but realtime is degraded. */
function degradedRealtimeReason(authFailed: boolean, websocket: WebSocketHealth): string {
  if (authFailed) return 'authentication';
  if (websocket === 'connecting') return 'Realtime connection is being established';
  return 'Realtime connection down — updates may lag';
}

interface CoachVerdict {
  coach: CoachState;
  reason: string;
}

/** Combine websocket + CAN bus health into the single coach verdict shown app-wide. */
function deriveCoachVerdict(
  websocket: WebSocketHealth,
  canbus: CanbusHealth,
  apiReachable: boolean,
  authFailed: boolean
): CoachVerdict {
  if (websocket === 'connected' && canbus === 'active') {
    return { coach: 'LIVE', reason: 'Realtime connection up, CAN bus active' };
  }
  if (websocket === 'down' && !apiReachable) {
    return { coach: 'OFFLINE', reason: offlineReason(authFailed) };
  }
  if (canbus === 'silent') {
    return { coach: 'STALE', reason: 'No CAN traffic observed — showing last known state' };
  }
  // CAN is active but the realtime channel is degraded.
  return { coach: 'STALE', reason: degradedRealtimeReason(authFailed, websocket) };
}

/** Best available "last real data" timestamp between two candidate sources. */
function pickLastDataAt(entitiesFreshestAt: Date | null, canLastActivity: Date | null): Date | null {
  if (entitiesFreshestAt && canLastActivity) {
    return entitiesFreshestAt > canLastActivity ? entitiesFreshestAt : canLastActivity;
  }
  return entitiesFreshestAt ?? canLastActivity;
}

//
// ===== PROVIDER =====
//

export function CoachConnectionProvider({ children }: { readonly children: ReactNode }) {
  const queryClient = useQueryClient();
  const wsContext = useWebSocketContext();
  const [authFailed, setAuthFailed] = useState(false);
  // Re-evaluate time-window checks (activity recency) periodically.
  const [, setTick] = useState(0);
  const refreshInFlightRef = useRef(false);

  const networksQuery = useQuery({
    queryKey: networksStatusQueryKey,
    queryFn: () => apiGet<NetworkSummarySchema>('/api/v1/networks/status'),
    refetchInterval: NETWORKS_POLL_INTERVAL_MS,
    refetchIntervalInBackground: true,
    staleTime: 5_000,
    retry: 1,
  });

  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), NETWORKS_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // ===== Auth-close handling (WS close code 4401) =====
  const connectAll = wsContext.connectAll;

  const handleTokenRefreshed = useCallback(() => {
    setAuthFailed(false);
    connectAll();
  }, [connectAll]);

  const handleTokenRefreshFailed = useCallback(() => {
    setAuthFailed(true);
  }, []);

  useEffect(() => {
    const handleWsClose = (event: Event) => {
      const detail = (event as CustomEvent<WsCloseEventDetail>).detail;
      if (!detail || detail.code !== 4401) return;
      if (refreshInFlightRef.current) return;

      refreshInFlightRef.current = true;
      tokenStorage
        .attemptTokenRefresh()
        .then((success) => (success ? handleTokenRefreshed() : handleTokenRefreshFailed()))
        .catch(() => handleTokenRefreshFailed())
        .finally(() => {
          refreshInFlightRef.current = false;
        });
    };

    window.addEventListener('coachiq:ws-close', handleWsClose);
    return () => window.removeEventListener('coachiq:ws-close', handleWsClose);
  }, [handleTokenRefreshed, handleTokenRefreshFailed]);

  // ===== Derived state =====
  const websocket: WebSocketHealth = deriveWebsocketHealth(
    authFailed,
    wsContext.isConnected,
    wsContext.hasError
  );

  const { canbus, canLastActivity } = useMemo(
    // The tick state (re-rendered every NETWORKS_POLL_INTERVAL_MS) re-runs
    // this render so the time-window check stays honest even between polls.
    () => computeCanbusActivity(networksQuery.data?.interfaces ?? [], Date.now()),
    [networksQuery.data]
  );

  // Freshest entity timestamp across all cached entity collections.
  const entitiesFreshestAt = useMemo(() => {
    let freshest: Date | null = null;
    const collections = queryClient.getQueriesData<EntityCollectionSchema>({
      queryKey: entitiesQueryKeys.collections(),
    });
    for (const [, collection] of collections) {
      for (const entity of collection?.entities ?? []) {
        const updatedAt = new Date(entity.last_updated);
        if (!Number.isNaN(updatedAt.getTime()) && (!freshest || updatedAt > freshest)) {
          freshest = updatedAt;
        }
      }
    }
    return freshest;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cache snapshot; refreshed by poll cycle + tick
  }, [queryClient, networksQuery.dataUpdatedAt]);

  const apiReachable = networksQuery.isSuccess || (networksQuery.isFetching && !networksQuery.isError);

  const { coach, reason } = deriveCoachVerdict(websocket, canbus, apiReachable, authFailed);

  const lastDataAt = useMemo(
    () => pickLastDataAt(entitiesFreshestAt, canLastActivity),
    [entitiesFreshestAt, canLastActivity]
  );

  const retry = useCallback(() => {
    setAuthFailed(false);
    void queryClient.invalidateQueries({ queryKey: networksStatusQueryKey });
    void queryClient.invalidateQueries({ queryKey: entitiesQueryKeys.collections() });
    connectAll();
  }, [queryClient, connectAll]);

  const value = useMemo<CoachConnectionState>(
    () => ({
      websocket,
      canbus,
      coach,
      entitiesFreshestAt,
      lastDataAt,
      reason,
      retry,
    }),
    [websocket, canbus, coach, entitiesFreshestAt, lastDataAt, reason, retry]
  );

  return (
    <CoachConnectionContext.Provider value={value}>{children}</CoachConnectionContext.Provider>
  );
}

//
// ===== HOOK =====
//

export function useCoachConnection(): CoachConnectionState {
  const context = useContext(CoachConnectionContext);
  if (!context) {
    throw new Error('useCoachConnection must be used within a CoachConnectionProvider');
  }
  return context;
}
