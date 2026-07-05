/**
 * Global connection banner.
 *
 * Hidden when the coach is LIVE. Renders a persistent, honest banner for
 * STALE (amber) and OFFLINE (red) states with the timestamp of the last
 * real data and a retry action.
 */

import { IconAlertTriangle, IconPlugConnectedX, IconRefresh } from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { useCoachConnection } from "@/contexts/coach-connection-context"
import { cn } from "@/lib/utils"

function formatLastData(date: Date | null): string {
  if (!date) return "unknown"
  const sameDay = new Date().toDateString() === date.toDateString()
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  return sameDay ? time : `${date.toLocaleDateString()} ${time}`
}

export function ConnectionBanner() {
  const { coach, lastDataAt, reason, retry } = useCoachConnection()

  if (coach === "LIVE") return null

  const isOffline = coach === "OFFLINE"
  const time = formatLastData(lastDataAt)

  return (
    <div
      role="status"
      className={cn(
        "flex items-center gap-3 border-b px-4 py-2 text-sm lg:px-6",
        isOffline
          ? "border-red-300 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/60 dark:text-red-200"
          : "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200"
      )}
    >
      {isOffline ? (
        <IconPlugConnectedX className="size-4 shrink-0" />
      ) : (
        <IconAlertTriangle className="size-4 shrink-0" />
      )}
      <span className="flex-1">
        {isOffline
          ? `Can't reach the coach — controls disabled. Last data ${time}.`
          : `${reason} — showing last known state (last data ${time}).`}
      </span>
      <Button
        size="sm"
        variant="outline"
        onClick={retry}
        className={cn(
          "h-7 shrink-0 gap-1 bg-transparent",
          isOffline
            ? "border-red-400 text-red-900 hover:bg-red-100 dark:border-red-800 dark:text-red-200 dark:hover:bg-red-900/40"
            : "border-amber-400 text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-200 dark:hover:bg-amber-900/40"
        )}
      >
        <IconRefresh className="size-3.5" />
        Retry
      </Button>
    </div>
  )
}
