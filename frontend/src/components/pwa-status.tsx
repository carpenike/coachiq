import { IconCircleCheck, IconDownload, IconX } from "@tabler/icons-react"
import { useEffect } from "react"
import { useRegisterSW } from "virtual:pwa-register/react"

import { Button } from "@/components/ui/button"

const UPDATE_CHECK_INTERVAL_MS = 5 * 60 * 1_000

export function PwaStatus() {
  const {
    offlineReady: [offlineReady, setOfflineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    immediate: true,
    onRegisteredSW: (_scriptUrl, registration) => {
      if (!registration) return
      window.setInterval(() => void registration.update(), UPDATE_CHECK_INTERVAL_MS)
    },
    onRegisterError: (error) => {
      console.warn("CoachIQ service worker registration failed", error)
    },
  })

  useEffect(() => {
    if (needRefresh) void updateServiceWorker(true)
  }, [needRefresh, updateServiceWorker])

  if (!offlineReady && !needRefresh) return null

  const dismiss = () => {
    setOfflineReady(false)
    setNeedRefresh(false)
  }

  return (
    <section
      role="status"
      aria-live="polite"
      className="fixed right-4 bottom-4 z-[90] flex max-w-sm items-center gap-3 rounded-lg border bg-popover p-3 text-popover-foreground shadow-lg"
    >
      {needRefresh ? (
        <IconDownload className="size-5 shrink-0 text-primary" aria-hidden />
      ) : (
        <IconCircleCheck className="size-5 shrink-0 text-emerald-500" aria-hidden />
      )}
      <p className="flex-1 text-sm">
        {needRefresh
          ? "A CoachIQ update is ready."
          : "CoachIQ is ready for offline viewing. Live controls still require a coach connection."}
      </p>
      {needRefresh && (
        <Button size="sm" onClick={() => void updateServiceWorker(true)}>
          Update
        </Button>
      )}
      <Button variant="ghost" size="icon" onClick={dismiss} aria-label="Dismiss PWA status">
        <IconX className="size-4" />
      </Button>
    </section>
  )
}
