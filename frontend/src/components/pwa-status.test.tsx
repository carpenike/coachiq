import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { PwaStatus } from "@/components/pwa-status"

const setOfflineReady = vi.fn()
const setNeedRefresh = vi.fn()
const updateServiceWorker = vi.fn()
let needRefresh = false

vi.mock("virtual:pwa-register/react", () => ({
  useRegisterSW: vi.fn(() => ({
    offlineReady: [!needRefresh, setOfflineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker
  }))
}))

describe("PwaStatus", () => {
  beforeEach(() => {
    setOfflineReady.mockClear()
    setNeedRefresh.mockClear()
    updateServiceWorker.mockClear()
    needRefresh = false
  })

  it("describes a cached shell without claiming the coach is offline", () => {
    render(<PwaStatus />)

    expect(
      screen.getByText(
        "CoachIQ is ready for offline viewing. Live controls still require a coach connection."
      )
    ).toBeInTheDocument()
    expect(screen.queryByText(/controls remain disabled/i)).not.toBeInTheDocument()
  })

  it("applies a discovered service worker update automatically", () => {
    needRefresh = true

    render(<PwaStatus />)

    expect(updateServiceWorker).toHaveBeenCalledWith(true)
  })
})
