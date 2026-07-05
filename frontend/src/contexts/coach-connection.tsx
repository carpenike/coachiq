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
 *
 * The context object, `ICoachConnectionState` type, and `useCoachConnection`
 * hook live in ./coach-connection-context — this file exports only the
 * provider component.
 */

import type { QueryClient, UseQueryResult } from '@tanstack/react-query';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiGet } from '@/api/client';
import type { EntityCollectionSchema, NetworkSummarySchema } from '@/api/types/domains';
import {
  CoachConnectionContext,
  networksStatusQueryKey,
  type CanbusHealth,
  type CoachState,
  type ICoachConnectionState,
  type WebSocketHealth,
} from '@/contexts/coach-connection-context';
import { useAuth } from '@/contexts/auth-context';
import { useWebSocketContext } from '@/contexts/use-websocket-context';
import { entitiesQueryKeys } from '@/hooks/useEntities';
import { tokenStorage } from '@/lib/token-storage';

//
// ===== CONSTANTS =====
//

/** CAN bus considered silent when no interface saw traffic within this window */
const CAN_ACTIVITY_WINDOW_MS = 120_000;
/** How often to poll /api/v1/networks/status */
const NETWORKS_POLL_INTERVAL_MS = 15_000;

interface IWsCloseEventDetail {
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

interface ICanbusActivity {
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
function computeCanbusActivity(interfaces: NetworkInterface[], now: number): ICanbusActivity {
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

interface ICoachVerdict {
  coach: CoachState;
  reason: string;
}

/** Combine websocket + CAN bus health into the single coach verdict shown app-wide. */
function deriveCoachVerdict(
  websocket: WebSocketHealth,
  canbus: CanbusHealth,
  apiReachable: boolean,
  authFailed: boolean
): ICoachVerdict {
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

/** Freshest entity timestamp across all cached entity collections. */
function computeEntitiesFreshestAt(queryClient: QueryClient): Date | null {
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
}

//
// ===== EFFECT HELPERS (extracted to keep the provider body small) =====
//

/** Periodically bump a tick counter so time-window checks re-run between polls. */
function useActivityTick(intervalMs: number): void {
  const [, setTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(interval);
  }, [intervalMs]);
}

/**
 * Listen for the app-wide `coachiq:ws-close` event and attempt a token
 * refresh when the close code indicates an auth failure (4401), guarding
 * against overlapping refresh attempts.
 */
function useAuthCloseListener(
  onRefreshed: () => void,
  onRefreshFailed: () => void
): void {
  const refreshInFlightRef = useRef(false);

  useEffect(() => {
    const handleWsClose = (event: Event) => {
      const detail = (event as CustomEvent<IWsCloseEventDetail | undefined>).detail;
      if (!detail || detail.code !== 4401) return;
      if (refreshInFlightRef.current) return;

      refreshInFlightRef.current = true;
      tokenStorage
        .attemptTokenRefresh()
        .then((success) => (success ? onRefreshed() : onRefreshFailed()))
        .catch(() => onRefreshFailed())
        .finally(() => {
          refreshInFlightRef.current = false;
        });
    };

    window.addEventListener('coachiq:ws-close', handleWsClose);
    return () => window.removeEventListener('coachiq:ws-close', handleWsClose);
  }, [onRefreshed, onRefreshFailed]);
}

/**
 * Poll /api/v1/networks/status on the shared interval, but only once auth is
 * ready. This provider mounts above the AuthGuard, so an ungated query fires
 * on the login page, 401s, and then sits in an errored/stale state — the coach
 * reads STALE ("no CAN traffic since …") until the user hits Retry. Gating on
 * `enabled` means the first request goes out with a valid token right after
 * login and lands fresh telemetry on its own.
 */
function useNetworksStatusQuery(enabled: boolean): UseQueryResult<NetworkSummarySchema, Error> {
  return useQuery({
    queryKey: networksStatusQueryKey,
    queryFn: () => apiGet<NetworkSummarySchema>('/api/v1/networks/status'),
    enabled,
    refetchInterval: NETWORKS_POLL_INTERVAL_MS,
    refetchIntervalInBackground: true,
    staleTime: 5_000,
    retry: 1,
  });
}

//
// ===== PROVIDER =====
//

export function CoachConnectionProvider({ children }: { readonly children: ReactNode }) {
  const queryClient = useQueryClient();
  const wsContext = useWebSocketContext();
  const [authFailed, setAuthFailed] = useState(false);
  // Re-evaluate time-window checks (activity recency) periodically.
  useActivityTick(NETWORKS_POLL_INTERVAL_MS);

  // Only poll telemetry once the session is confirmed (or auth is disabled),
  // matching the WebSocket's auth gating — an unauthenticated poll on the login
  // page would 401 and leave the coach stuck STALE until a manual Retry.
  const { isAuthenticated, authStatus } = useAuth();
  const authReady = authStatus?.mode === 'none' || isAuthenticated;
  const networksQuery = useNetworksStatusQuery(authReady);

  // ===== Auth-close handling (WS close code 4401) =====
  const connectAll = wsContext.connectAll;

  const handleTokenRefreshed = useCallback(() => {
    setAuthFailed(false);
    connectAll();
  }, [connectAll]);

  const handleTokenRefreshFailed = useCallback(() => {
    setAuthFailed(true);
  }, []);

  useAuthCloseListener(handleTokenRefreshed, handleTokenRefreshFailed);

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

  const entitiesFreshestAt = useMemo(
    () => computeEntitiesFreshestAt(queryClient),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cache snapshot; refreshed by poll cycle + tick
    [queryClient, networksQuery.dataUpdatedAt]
  );

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

  const value = useMemo<ICoachConnectionState>(
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
