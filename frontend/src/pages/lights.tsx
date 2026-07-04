/**
 * Lights — owner lighting control page.
 *
 * Zone-grouped light controls: per-zone on-count summary and all-on/all-off,
 * per-light switch + brightness (when dimmable), master all-on/all-off.
 * All counts are computed from real entity state — no fabricated numbers.
 * Toast feedback per the command feedback contract in docs/frontend-redesign.md.
 */

import { IconBulb, IconBulbOff } from "@tabler/icons-react"
import { formatDistanceToNow } from "date-fns"
import { Link } from "react-router-dom"

import type { EntitySchema, OperationResultSchema } from "@/api/types/domains"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useCoachConnection } from "@/contexts/coach-connection"
import { toast } from "@/hooks/use-toast"
import {
  groupEntitiesByZone,
  useCoachConfig,
  type ZoneGroup,
} from "@/hooks/useCoachConfig"
import { useBulkControlEntities, useControlEntity, useEntities } from "@/hooks/useEntities"
import { cn } from "@/lib/utils"

//
// ===== Entity state helpers (RV-C operating_status is raw 0..200) =====
//

function lightIsOn(entity: EntitySchema): boolean {
  const state = entity.state ?? {}
  if (typeof state.state === "string") {
    return ["on", "true", "active"].includes(state.state.toLowerCase())
  }
  if (typeof state.operating_status === "number") {
    return state.operating_status > 0
  }
  return false
}

function lightBrightnessPct(entity: EntitySchema): number {
  const state = entity.state ?? {}
  if (typeof state.brightness === "number") {
    return Math.max(0, Math.min(100, Math.round(state.brightness)))
  }
  if (typeof state.operating_status === "number") {
    return Math.max(0, Math.min(100, Math.round((state.operating_status / 200) * 100)))
  }
  return 0
}

/**
 * Whether the light supports dimming. The v1 entity schema exposes no
 * capabilities list (contract gap) — a light whose state reports a level
 * (operating_status / brightness) is treated as dimmable.
 */
function lightIsDimmable(entity: EntitySchema): boolean {
  if (entity.device_type !== "light") return false
  const state = entity.state ?? {}
  return typeof state.operating_status === "number" || typeof state.brightness === "number"
}

function relativeTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "unknown"
  return formatDistanceToNow(date, { addSuffix: true })
}

//
// ===== Toast feedback (command feedback contract) =====
//

function reportCommandResult(result: OperationResultSchema, entityName: string) {
  if (result.status !== "success") {
    toast({
      variant: "destructive",
      title: `Command not completed: ${entityName}`,
      description: result.error_message || `Backend reported status "${result.status}".`,
    })
  }
}

function reportCommandError(error: Error, entityName: string) {
  toast({
    variant: "destructive",
    title: `Command failed: ${entityName}`,
    description: error.message,
  })
}

//
// ===== Single light row =====
//

interface LightRowProps {
  entity: EntitySchema
  controlsDisabled: boolean
  disabledReason: string
}

function LightRow({ entity, controlsDisabled, disabledReason }: Readonly<LightRowProps>) {
  const control = useControlEntity()
  const isOn = lightIsOn(entity)
  const isAvailable = entity.available !== false
  const dimmable = lightIsDimmable(entity)
  const brightness = lightBrightnessPct(entity)
  const rowDisabled = controlsDisabled || !isAvailable
  const rowReason = !isAvailable
    ? "Light is not responding on the CAN bus"
    : disabledReason

  const sendCommand = (command: Parameters<typeof control.mutate>[0]["command"]) => {
    control.mutate(
      { entityId: entity.entity_id, command },
      {
        onSuccess: (result) => reportCommandResult(result, entity.name),
        onError: (error) => reportCommandError(error, entity.name),
      }
    )
  }

  const controls = (
    <div className="flex items-center gap-3">
      {!isAvailable && (
        <Badge variant="outline" className="gap-1 text-xs text-muted-foreground">
          <span className="size-1.5 rounded-full bg-red-500" aria-hidden />
          offline
        </Badge>
      )}
      <Switch
        checked={isOn}
        disabled={rowDisabled || control.isPending}
        onCheckedChange={() => sendCommand({ command: "toggle" })}
        aria-label={`Toggle ${entity.name}`}
      />
    </div>
  )

  return (
    <div className={cn("space-y-1.5 py-2.5", !isAvailable && "opacity-50")}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{entity.name}</p>
          <p className="text-xs text-muted-foreground">
            Updated {relativeTime(entity.last_updated)}
          </p>
        </div>
        {rowDisabled ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>{controls}</span>
            </TooltipTrigger>
            <TooltipContent>{rowReason}</TooltipContent>
          </Tooltip>
        ) : (
          controls
        )}
      </div>
      {dimmable && isOn && (
        <Slider
          value={[brightness]}
          max={100}
          step={5}
          disabled={rowDisabled || control.isPending}
          onValueCommit={(value) => {
            const level = value[0]
            if (level !== undefined) {
              sendCommand({ command: "set", state: level > 0, brightness: level })
            }
          }}
          aria-label={`${entity.name} brightness`}
        />
      )}
    </div>
  )
}

//
// ===== Zone card =====
//

interface ZoneLightsCardProps {
  zone: ZoneGroup
  controlsDisabled: boolean
  disabledReason: string
}

function ZoneLightsCard({ zone, controlsDisabled, disabledReason }: Readonly<ZoneLightsCardProps>) {
  const bulkControl = useBulkControlEntities()
  const onCount = zone.entities.filter(lightIsOn).length
  const switchableIds = zone.entities
    .filter((entity) => entity.available !== false)
    .map((entity) => entity.entity_id)

  const setZone = (on: boolean) => {
    bulkControl.mutate(
      {
        entity_ids: switchableIds,
        command: { command: "set", state: on },
        ignore_errors: true,
      },
      {
        onSuccess: (result) => {
          if (result.failed_count > 0) {
            toast({
              variant: "destructive",
              title: `${zone.displayName}: ${result.failed_count} of ${result.total_count} lights failed`,
              description: `Some lights did not turn ${on ? "on" : "off"}.`,
            })
          }
        },
        onError: (error) => reportCommandError(error, zone.displayName),
      }
    )
  }

  const zoneButtonsDisabled =
    controlsDisabled || switchableIds.length === 0 || bulkControl.isPending
  const zoneButtonsReason = controlsDisabled
    ? disabledReason
    : "No lights in this zone are responding"

  const zoneButtons = (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        disabled={zoneButtonsDisabled}
        onClick={() => setZone(true)}
        className="size-7 text-muted-foreground"
        aria-label={`Turn all lights on in ${zone.displayName}`}
      >
        <IconBulb className="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        disabled={zoneButtonsDisabled}
        onClick={() => setZone(false)}
        className="size-7 text-muted-foreground"
        aria-label={`Turn all lights off in ${zone.displayName}`}
      >
        <IconBulbOff className="size-4" />
      </Button>
    </div>
  )

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="min-w-0">
          <CardTitle className="text-base">{zone.displayName}</CardTitle>
          <p className="text-xs text-muted-foreground">
            {onCount} of {zone.entities.length} on
          </p>
        </div>
        {zoneButtonsDisabled ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>{zoneButtons}</span>
            </TooltipTrigger>
            <TooltipContent>{zoneButtonsReason}</TooltipContent>
          </Tooltip>
        ) : (
          zoneButtons
        )}
      </CardHeader>
      <CardContent className="divide-y">
        {zone.entities.map((entity) => (
          <LightRow
            key={entity.entity_id}
            entity={entity}
            controlsDisabled={controlsDisabled}
            disabledReason={disabledReason}
          />
        ))}
      </CardContent>
    </Card>
  )
}

//
// ===== Master summary + all on / all off =====
//

interface MasterBarProps {
  lights: EntitySchema[]
  controlsDisabled: boolean
  disabledReason: string
}

function MasterBar({ lights, controlsDisabled, disabledReason }: Readonly<MasterBarProps>) {
  const bulkControl = useBulkControlEntities()
  const available = lights.filter((entity) => entity.available !== false)
  const offlineCount = lights.length - available.length
  const onCount = available.filter(lightIsOn).length
  const offCount = available.length - onCount

  const setAll = (on: boolean) => {
    bulkControl.mutate(
      {
        entity_ids: available.map((entity) => entity.entity_id),
        command: { command: "set", state: on },
        ignore_errors: true,
      },
      {
        onSuccess: (result) => {
          if (result.failed_count > 0) {
            toast({
              variant: "destructive",
              title: `${result.failed_count} of ${result.total_count} lights failed`,
              description: `Some lights did not turn ${on ? "on" : "off"}.`,
            })
          } else {
            toast({
              title: on ? "All lights on" : "All lights off",
              description: `Applied to ${result.total_count} ${
                result.total_count === 1 ? "light" : "lights"
              }.`,
            })
          }
        },
        onError: (error) => reportCommandError(error, "All lights"),
      }
    )
  }

  const masterDisabled = controlsDisabled || available.length === 0 || bulkControl.isPending
  const masterReason = controlsDisabled ? disabledReason : "No lights are responding"

  const buttons = (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={masterDisabled}
        onClick={() => setAll(true)}
        className="gap-1.5"
      >
        <IconBulb className="size-4" />
        All On
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={masterDisabled}
        onClick={() => setAll(false)}
        className="gap-1.5"
      >
        <IconBulbOff className="size-4" />
        All Off
      </Button>
    </div>
  )

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant="secondary"
          className="bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
        >
          {onCount} on
        </Badge>
        <Badge variant="secondary">{offCount} off</Badge>
        {offlineCount > 0 && (
          <Badge variant="outline" className="gap-1 text-muted-foreground">
            <span className="size-1.5 rounded-full bg-red-500" aria-hidden />
            {offlineCount} offline
          </Badge>
        )}
      </div>
      {masterDisabled ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="self-start sm:self-auto">{buttons}</span>
          </TooltipTrigger>
          <TooltipContent>{masterReason}</TooltipContent>
        </Tooltip>
      ) : (
        buttons
      )}
    </div>
  )
}

//
// ===== Page =====
//

export default function LightsPage() {
  const { coach, reason } = useCoachConnection()
  const { data: config } = useCoachConfig()
  const { data: entityCollection, isLoading, error } = useEntities({
    device_type: "light",
    page_size: 100,
  })

  const lights = (entityCollection?.entities ?? []).filter(
    (entity) => entity.device_type === "light"
  )
  const zones = groupEntitiesByZone(lights, config)
  const interior = zones.filter((zone) => zone.section === "interior")
  const exterior = zones.filter((zone) => zone.section === "exterior")
  const other = zones.filter((zone) => zone.section === "other")

  const controlsDisabled = coach !== "LIVE"
  const disabledReason =
    coach === "OFFLINE"
      ? "Can't reach the coach — controls disabled"
      : `Coach data is not live — ${reason}`

  const renderSection = (title: string, sectionZones: ZoneGroup[]) => {
    if (sectionZones.length === 0) return null
    return (
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sectionZones.map((zone) => (
            <ZoneLightsCard
              key={zone.zoneId}
              zone={zone}
              controlsDisabled={controlsDisabled}
              disabledReason={disabledReason}
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      {isLoading && (
        <div className="space-y-6">
          <Skeleton className="h-9 w-full max-w-md" />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-48" />
            ))}
          </div>
        </div>
      )}

      {error && (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">Couldn't load lights</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{error.message}</p>
          </CardContent>
        </Card>
      )}

      {!isLoading && !error && lights.length === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>No light entities are mapped</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No lights are mapped for this coach yet. Map them in{" "}
              <Link
                to="/advanced/device-mapping"
                className="underline underline-offset-2 hover:text-foreground"
              >
                Device Mapping
              </Link>
              .
            </p>
          </CardContent>
        </Card>
      )}

      {!isLoading && !error && lights.length > 0 && (
        <>
          <MasterBar
            lights={lights}
            controlsDisabled={controlsDisabled}
            disabledReason={disabledReason}
          />
          {renderSection("Interior", interior)}
          {renderSection("Exterior", exterior)}
          {renderSection("Unassigned", other)}
        </>
      )}
    </div>
  )
}
