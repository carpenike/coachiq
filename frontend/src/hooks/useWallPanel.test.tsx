import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useScreenWakeLock } from "@/hooks/useWallPanel"

class MockWakeLockSentinel extends EventTarget {
  released = false
  release = vi.fn(async () => {
    this.released = true
    this.dispatchEvent(new Event("release"))
  })
}

describe("useScreenWakeLock", () => {
  let visibilityState = "visible"

  beforeEach(() => {
    visibilityState = "visible"
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibilityState,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("releases while hidden, reacquires when visible, and releases on unmount", async () => {
    const first = new MockWakeLockSentinel()
    const second = new MockWakeLockSentinel()
    const request = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: { request },
    })

    const { result, unmount } = renderHook(() => useScreenWakeLock(true))

    await waitFor(() => expect(result.current.status).toBe("active"))
    expect(request).toHaveBeenCalledWith("screen")

    visibilityState = "hidden"
    await act(async () => document.dispatchEvent(new Event("visibilitychange")))
    await waitFor(() => expect(first.release).toHaveBeenCalledTimes(1))
    expect(result.current.status).toBe("released")

    visibilityState = "visible"
    await act(async () => document.dispatchEvent(new Event("visibilitychange")))
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.status).toBe("active"))

    unmount()
    await waitFor(() => expect(second.release).toHaveBeenCalledTimes(1))
  })

  it("reports unsupported browsers without requesting a lock", () => {
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: undefined,
    })

    const { result } = renderHook(() => useScreenWakeLock(true))

    expect(result.current.status).toBe("unsupported")
    expect(result.current.error).toBeNull()
  })
})
