import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { PreferencesSyncProvider } from "@/contexts/preferences-sync-provider"

const {
  apiGetMock,
  apiPutMock,
  replaceHomePreferencesMock,
  useAuthMock,
  useHomePreferencesMock,
} = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPutMock: vi.fn(),
  replaceHomePreferencesMock: vi.fn(),
  useAuthMock: vi.fn(),
  useHomePreferencesMock: vi.fn(),
}))

vi.mock("@/api/client", () => ({
  apiGet: apiGetMock,
  apiPut: apiPutMock,
}))

vi.mock("@/contexts/auth-context", () => ({ useAuth: useAuthMock }))

vi.mock("@/hooks/usePreferences", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/hooks/usePreferences")>()
  return {
    ...original,
    replaceHomePreferences: replaceHomePreferencesMock,
    useHomePreferences: useHomePreferencesMock,
  }
})

const localHome = {
  favoriteEntityIds: ["light.local"],
  sectionOrder: ["alerts", "scenes", "power", "zones"] as const,
  hiddenSections: ["power"] as const,
}

const serverHome = {
  favoriteEntityIds: ["light.server"],
  sectionOrder: ["zones", "alerts", "scenes", "power"] as const,
  hiddenSections: ["scenes"] as const,
}

function renderProvider() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesSyncProvider>
        <div>child</div>
      </PreferencesSyncProvider>
    </QueryClientProvider>
  )
}

describe("PreferencesSyncProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useHomePreferencesMock.mockReturnValue(localHome)
    useAuthMock.mockReturnValue({
      authStatus: { mode: "multi" },
      isAuthenticated: true,
      user: { user_id: "user-123" },
    })
  })

  it("hydrates authenticated Home preferences from the server", async () => {
    apiGetMock.mockResolvedValue({
      home: serverHome,
      updated_at: "2026-07-11T12:00:00Z",
    })

    renderProvider()

    await waitFor(() => {
      expect(replaceHomePreferencesMock).toHaveBeenCalledWith(serverHome)
    })
    expect(apiGetMock).toHaveBeenCalledWith("/api/v1/dashboard/preferences")
  })

  it("uploads local Home preferences on first synchronized save", async () => {
    apiGetMock.mockResolvedValue({
      home: null,
      updated_at: "2026-07-11T12:00:00Z",
    })
    apiPutMock.mockResolvedValue({
      home: localHome,
      updated_at: "2026-07-11T12:00:01Z",
    })

    renderProvider()

    await waitFor(
      () => {
        expect(apiPutMock).toHaveBeenCalledWith("/api/v1/dashboard/preferences", {
          home: localHome,
        })
      },
      { timeout: 1_500 }
    )
  })

  it("keeps no-auth deployments entirely local", async () => {
    useAuthMock.mockReturnValue({
      authStatus: { mode: "none" },
      isAuthenticated: false,
      user: null,
    })

    renderProvider()

    await new Promise((resolve) => window.setTimeout(resolve, 20))
    expect(apiGetMock).not.toHaveBeenCalled()
    expect(apiPutMock).not.toHaveBeenCalled()
  })
})
