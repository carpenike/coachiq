import { useMutation, useQuery } from "@tanstack/react-query"
import {
  Fragment,
  createElement,
  useEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react"

import { apiGet, apiPut } from "@/api/client"
import type { components } from "@/api/generated/openapi-types"
import { useAuth } from "@/contexts/auth-context"
import {
  normalizeHomePreferences,
  replaceHomePreferences,
  useHomePreferences,
  type IHomePreferences,
} from "@/hooks/usePreferences"

const PREFERENCE_SYNC_DELAY_MS = 500

type DashboardPreferencesResponse = components["schemas"]["DashboardPreferencesResponse"]
type DashboardPreferencesUpdate = components["schemas"]["DashboardPreferencesUpdate"]

function fingerprint(home: IHomePreferences): string {
  return JSON.stringify(normalizeHomePreferences(home))
}

export function PreferencesSyncProvider({
  children,
}: Readonly<{ children: ReactNode }>): ReactElement {
  const { authStatus, isAuthenticated, user } = useAuth()
  const home = useHomePreferences()
  const authenticatedUserId =
    authStatus?.mode !== "none" && isAuthenticated ? user?.user_id : undefined
  const [hydratedUserId, setHydratedUserId] = useState<string | null>(null)
  const lastSyncedFingerprint = useRef<string | null>(null)

  const preferencesQuery = useQuery({
    queryKey: ["dashboard", "preferences", authenticatedUserId],
    queryFn: () => apiGet<DashboardPreferencesResponse>("/api/v1/dashboard/preferences"),
    enabled: authenticatedUserId !== undefined,
    staleTime: 60_000,
    retry: 2,
  })

  const { mutate: savePreferences } = useMutation({
    mutationFn: (nextHome: IHomePreferences) =>
      apiPut<DashboardPreferencesResponse>(
        "/api/v1/dashboard/preferences",
        { home: nextHome } satisfies DashboardPreferencesUpdate
      ),
    onSuccess: (response, submittedHome) => {
      const savedHome = normalizeHomePreferences(response.home ?? submittedHome)
      lastSyncedFingerprint.current = fingerprint(savedHome)
      replaceHomePreferences(savedHome)
    },
  })

  useEffect(() => {
    if (authenticatedUserId === undefined) {
      setHydratedUserId(null)
      lastSyncedFingerprint.current = null
      return
    }
    if (!preferencesQuery.data) return

    const serverHome = preferencesQuery.data.home
    if (serverHome) {
      const normalized = normalizeHomePreferences(serverHome)
      lastSyncedFingerprint.current = fingerprint(normalized)
      replaceHomePreferences(normalized)
    } else {
      lastSyncedFingerprint.current = null
    }
    setHydratedUserId(authenticatedUserId)
  }, [authenticatedUserId, preferencesQuery.data])

  useEffect(() => {
    if (
      authenticatedUserId === undefined ||
      hydratedUserId !== authenticatedUserId
    ) return
    const currentFingerprint = fingerprint(home)
    if (currentFingerprint === lastSyncedFingerprint.current) return

    const timer = window.setTimeout(() => {
      savePreferences(normalizeHomePreferences(home))
    }, PREFERENCE_SYNC_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [authenticatedUserId, home, hydratedUserId, savePreferences])

  return createElement(Fragment, null, children)
}
