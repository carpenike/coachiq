/**
 * Realtime Provider — owns the app's single SSE event stream.
 *
 * One CoachEventStream for the whole app: entity updates land directly in the
 * TanStack Query cache, so pages consume realtime state through the queries
 * they already use. Commands stay on REST.
 *
 * On every (re)connect the entity collections are invalidated: a fresh
 * connection has no Last-Event-ID to replay from, and after a replayed
 * reconnect the invalidation is a cheap consistency backstop.
 */

import { useQueryClient } from '@tanstack/react-query'
import React, { useEffect, useMemo, useRef, useState } from 'react'

import { CoachEventStream, type StreamState } from '@/api/sse'
import { useAuth } from '@/contexts/auth-context'
import { applyEntityUpdate, type IEntityUpdatePayload } from './realtime-cache'
import { RealtimeContext, type IRealtimeContext, type RealtimeHealth } from './realtime-context'
import { entitiesQueryKeys } from '@/hooks/useEntities'

function toRealtimeHealth(state: StreamState): RealtimeHealth {
  switch (state) {
    case 'open':
      return 'connected'
    case 'connecting':
      return 'connecting'
    case 'down':
    case 'auth-failed':
      return 'down'
    case 'closed':
      // Not started yet (pre-auth) — the channel is on its way, not broken.
      return 'connecting'
  }
}

export function RealtimeProvider({ children }: { readonly children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [streamState, setStreamState] = useState<StreamState>('closed')

  // Don't dial before auth settles: a token-less request in auth mode is a
  // guaranteed 401 that would surface as a spurious auth failure. Auth-disabled
  // coaches (mode "none") are ready as soon as status loads.
  const { isAuthenticated, authStatus } = useAuth()
  const authReady = authStatus?.mode === 'none' || isAuthenticated

  const queryClientRef = useRef(queryClient)
  queryClientRef.current = queryClient

  const streamRef = useRef<CoachEventStream | null>(null)
  streamRef.current ??= new CoachEventStream({
    onEvent: (event, data) => {
      const client = queryClientRef.current
      if (event === 'entity_update') {
        applyEntityUpdate(client, data as IEntityUpdatePayload)
      } else if (event === 'entity_created' || event === 'halt_command_emission') {
        void client.invalidateQueries({ queryKey: entitiesQueryKeys.collections() })
      }
    },
    onStateChange: (state) => {
      setStreamState(state)
      if (state === 'open') {
        void queryClientRef.current.invalidateQueries({
          queryKey: entitiesQueryKeys.collections(),
        })
      }
    },
  })

  useEffect(() => {
    const stream = streamRef.current
    if (!stream || !authReady) return
    stream.start()
    return () => stream.stop()
  }, [authReady])

  const value = useMemo<IRealtimeContext>(
    () => ({
      status: toRealtimeHealth(streamState),
      authFailed: streamState === 'auth-failed',
      reconnect: () => streamRef.current?.restart(),
    }),
    [streamState]
  )

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>
}
