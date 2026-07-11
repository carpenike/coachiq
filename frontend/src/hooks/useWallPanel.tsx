import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import { usePreferences } from "@/hooks/usePreferences"

export type WakeLockStatus =
  | "disabled"
  | "unsupported"
  | "requesting"
  | "active"
  | "released"
  | "error"

interface IWakeLockSentinel extends EventTarget {
  readonly released: boolean
  release: () => Promise<void>
}

interface IWakeLockManager {
  request: (type: "screen") => Promise<IWakeLockSentinel>
}

interface IWallPanelContext {
  wakeLockStatus: WakeLockStatus
  wakeLockError: string | null
  fullscreenSupported: boolean
  isFullscreen: boolean
  toggleFullscreen: () => Promise<void>
}

const WallPanelContext = createContext<IWallPanelContext | null>(null)

function getWakeLockManager(): IWakeLockManager | null {
  const candidate = navigator as Navigator & { wakeLock?: IWakeLockManager }
  return candidate.wakeLock ?? null
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The display could not be kept awake."
}

export function useScreenWakeLock(enabled: boolean) {
  const [status, setStatus] = useState<WakeLockStatus>(enabled ? "requesting" : "disabled")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) {
      setStatus("disabled")
      setError(null)
      return
    }

    const wakeLock = getWakeLockManager()
    if (!wakeLock) {
      setStatus("unsupported")
      setError(null)
      return
    }

    let disposed = false
    let requestPending = false
    let sentinel: IWakeLockSentinel | null = null

    const release = async () => {
      const current = sentinel
      sentinel = null
      if (current && !current.released) {
        await current.release()
      }
    }

    const acquire = async () => {
      if (disposed || requestPending || sentinel || document.visibilityState !== "visible") {
        return
      }

      requestPending = true
      setStatus("requesting")
      setError(null)
      try {
        const nextSentinel = await wakeLock.request("screen")
        if (disposed || document.visibilityState !== "visible") {
          await nextSentinel.release()
          return
        }

        sentinel = nextSentinel
        nextSentinel.addEventListener(
          "release",
          () => {
            if (sentinel === nextSentinel) sentinel = null
            if (!disposed) setStatus("released")
          },
          { once: true }
        )
        setStatus("active")
      } catch (requestError) {
        if (!disposed) {
          setStatus("error")
          setError(errorMessage(requestError))
        }
      } finally {
        requestPending = false
      }
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void acquire()
      } else {
        void release().then(() => {
          if (!disposed) setStatus("released")
        })
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    void acquire()

    return () => {
      disposed = true
      document.removeEventListener("visibilitychange", handleVisibilityChange)
      void release()
    }
  }, [enabled])

  return { status, error }
}

export function WallPanelProvider({ children }: Readonly<{ children: ReactNode }>) {
  const preferences = usePreferences()
  const wakeLock = useScreenWakeLock(preferences.wallPanelEnabled)
  const [isFullscreen, setIsFullscreen] = useState(Boolean(document.fullscreenElement))
  const fullscreenSupported =
    typeof document.documentElement.requestFullscreen === "function" &&
    typeof document.exitFullscreen === "function"

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener("fullscreenchange", handleFullscreenChange)
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange)
  }, [])

  const toggleFullscreen = useCallback(async () => {
    if (!fullscreenSupported) return

    if (document.fullscreenElement) {
      await document.exitFullscreen()
    } else {
      await document.documentElement.requestFullscreen()
    }
  }, [fullscreenSupported])

  const contextValue = useMemo<IWallPanelContext>(
    () => ({
      wakeLockStatus: wakeLock.status,
      wakeLockError: wakeLock.error,
      fullscreenSupported,
      isFullscreen,
      toggleFullscreen,
    }),
    [fullscreenSupported, isFullscreen, toggleFullscreen, wakeLock.error, wakeLock.status]
  )

  return (
    <WallPanelContext.Provider value={contextValue}>
      {children}
    </WallPanelContext.Provider>
  )
}

export function useWallPanel() {
  const context = useContext(WallPanelContext)
  if (!context) throw new Error("useWallPanel must be used within WallPanelProvider")
  return context
}
