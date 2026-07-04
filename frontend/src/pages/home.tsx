/**
 * Home — the owner screen (Vegatouch Mira / Firefly panel replacement).
 *
 * Answers, in order:
 *  1. Is my coach reachable, and is what I'm seeing current?  (hero strip)
 *  2. What state is each zone of the coach in?                (zone grid)
 *  3. Can I change it right now?                              (controls w/ feedback)
 *
 * No fabricated numbers. Every control gives toast feedback per the
 * command feedback contract in docs/frontend-redesign.md.
 */

import {
  IconAlertTriangle,
  IconMoon,
  IconPlugConnectedX,
  IconRefresh,
  IconShieldBolt,
  IconSparkles,
  IconSunOff,
  IconTruck,
} from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"

import { fetchActiveDTCs } from "@/api/domains/diagnostics"
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
  resolveSceneCommands,
  useCoachConfig,
  type LightingScene,
  type ZoneGroup,
} from "@/hooks/useCoachConfig"
import { useBulkControlEntities, useControlEntity, useEntities } from "@/hooks/useEntities"
import { cn } from "@/lib/utils"

//
// ===== Entity state helpers (RV-C operating_status is raw 0..200) =====
//

function entityIsOn(entity: EntitySchema): boolean {
  const state = entity.state ?? {}
  if (typeof state.state === "string") {
    return ["on", "true", "active"].includes(state.state.toLowerCase())
  }
  if (typeof state.operating_status === "number") {
    return state.operating_status > 0
  }
  return false
}

function entityBrightnessPct(entity: EntitySchema): number {
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
 * Whether the entity supports dimming. The v1 entity schema exposes no
 * capabilities list (contract gap) — a light whose state reports a level
 * (operating_status / brightness) is treated as dimmable.
 */
function entityIsDimmable(entity: EntitySchema): boolean {
  if (entity.device_type !== "light") return false
  const state = entity.state ?? {}
  return typeof state.operating_status === "number" || typeof state.brightness === "number"
}

function formatTime(value: string | Date | null): string {
  const date = typeof value === "string" ? new Date(value) : value
  if (!date || Number.isNaN(date.getTime())) return "unknown"
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
}

/** Toast feedback per the command feedback contract. */
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
// ===== Connection hero strip =====
//

function ConnectionHero() {
  const { coach, reason, lastDataAt, retry } = useCoachConnection()

  if (coach === "LIVE") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-1.5 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300">
        <span className="size-2 rounded-full bg-green-500" aria-hidden />
        <span className="font-medium">Live</span>
        <span className="text-green-700/80 dark:text-green-400/80">
          Realtime updates active
        </span>
      </div>
    )
  }

  const isOffline = coach === "OFFLINE"
  return (
    <Card
      className={cn(
        "border-2",
        isOffline
          ? "border-red-300 dark:border-red-900"
          : "border-amber-300 dark:border-amber-900"
      )}
    >
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        {isOffline ? (
          <IconPlugConnectedX className="size-8 shrink-0 text-red-600 dark:text-red-400" />
        ) : (
          <IconAlertTriangle className="size-8 shrink-0 text-amber-600 dark:text-amber-400" />
        )}
        <div className="flex-1">
          <p className="font-semibold">
            {isOffline ? "Can't reach the coach" : "Showing last known state"}
          </p>
          <p className="text-sm text-muted-foreground">
            {reason === "authentication" ? "Session expired — sign in again." : reason}
            {" · "}Last data {formatTime(lastDataAt)}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={retry} className="gap-1 self-start sm:self-auto">
          <IconRefresh className="size-4" />
          Retry
        </Button>
      </CardContent>
    </Card>
  )
}

//
// ===== Active alerts strip (real DTCs only) =====
//

function AlertsStrip() {
  const { data } = useQuery({
    queryKey: ["diagnostics", "dtcs", "home"],
    queryFn: () => fetchActiveDTCs(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const activeCount = data?.active_count ?? 0
  if (activeCount === 0) return null

  return (
    <Link
      to="/diagnostics"
      className="flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 transition-colors hover:bg-red-100 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200 dark:hover:bg-red-950/70"
    >
      <IconAlertTriangle className="size-4 shrink-0" />
      <span className="font-medium">
        {activeCount} active fault {activeCount === 1 ? "code" : "codes"}
      </span>
      <span className="ml-auto underline underline-offset-2">View diagnostics</span>
    </Link>
  )
}

//
// ===== Scenes row =====
//

const SCENE_ICONS = new Map<string, typeof IconSparkles>([
  ["all_off", IconSunOff],
  ["evening", IconMoon],
  ["security", IconShieldBolt],
  ["travel_prep", IconTruck],
])

function ScenesRow({ entities }: Readonly<{ entities: EntitySchema[] }>) {
  const { data: config } = useCoachConfig()
  const { coach } = useCoachConnection()
  const bulkControl = useBulkControlEntities()
  const [runningScene, setRunningScene] = useState<string | null>(null)

  const scenes = Object.entries(config?.lighting_scenes ?? {})
  if (scenes.length === 0) return null

  const disabled = coach !== "LIVE"

  const runScene = async (sceneKey: string, scene: LightingScene) => {
    const commands = resolveSceneCommands(scene, entities)
    if (commands.length === 0) {
      toast({
        title: `No devices matched "${scene.name}"`,
        description: "The scene definition matched no known entities.",
      })
      return
    }

    // Group by identical command so each group is one bulk call.
    const groups = new Map<string, { ids: string[]; action: "on" | "off"; brightness?: number }>()
    for (const command of commands) {
      const key = `${command.action}:${command.brightness ?? ""}`
      const group = groups.get(key)
      if (group) {
        group.ids.push(command.entityId)
      } else {
        const entry: { ids: string[]; action: "on" | "off"; brightness?: number } = {
          ids: [command.entityId],
          action: command.action,
        }
        if (command.brightness !== undefined) entry.brightness = command.brightness
        groups.set(key, entry)
      }
    }

    setRunningScene(sceneKey)
    try {
      const results = await Promise.all(
        [...groups.values()].map((group) =>
          bulkControl.mutateAsync({
            entity_ids: group.ids,
            command:
              group.brightness !== undefined
                ? { command: "set", state: group.action === "on", brightness: group.brightness }
                : { command: "set", state: group.action === "on" },
            ignore_errors: true,
          })
        )
      )
      const failed = results.reduce((sum, result) => sum + result.failed_count, 0)
      const total = results.reduce((sum, result) => sum + result.total_count, 0)
      if (failed > 0) {
        toast({
          variant: "destructive",
          title: `${scene.name}: ${failed} of ${total} devices failed`,
          description: "Some devices did not accept the command. Check Diagnostics.",
        })
      } else {
        toast({
          title: scene.name,
          description: `Applied to ${total} ${total === 1 ? "device" : "devices"}.`,
        })
      }
    } catch (error) {
      toast({
        variant: "destructive",
        title: `${scene.name} failed`,
        description: error instanceof Error ? error.message : "Unknown error",
      })
    } finally {
      setRunningScene(null)
    }
  }

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-medium text-muted-foreground">Scenes</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {scenes.map(([sceneKey, scene]) => {
          const SceneIcon = SCENE_ICONS.get(sceneKey) ?? IconSparkles
          const button = (
            <Button
              key={sceneKey}
              variant="outline"
              disabled={disabled || runningScene !== null}
              onClick={() => void runScene(sceneKey, scene)}
              className="h-auto w-full flex-col gap-1.5 py-3"
            >
              <SceneIcon className={cn("size-5", runningScene === sceneKey && "animate-pulse")} />
              <span className="text-xs">{scene.name}</span>
            </Button>
          )
          if (!disabled) return button
          return (
            <Tooltip key={sceneKey}>
              <TooltipTrigger asChild>
                <span className="w-full">{button}</span>
              </TooltipTrigger>
              <TooltipContent>Controls disabled — coach connection is not live</TooltipContent>
            </Tooltip>
          )
        })}
      </div>
    </div>
  )
}

//
// ===== Zone grid =====
//

interface DeviceRowProps {
  entity: EntitySchema
  controlsDisabled: boolean
  disabledReason: string
  showTimestamps: boolean
}

function DeviceRow({ entity, controlsDisabled, disabledReason, showTimestamps }: Readonly<DeviceRowProps>) {
  const control = useControlEntity()
  const isOn = entityIsOn(entity)
  const isAvailable = entity.available !== false
  const dimmable = entityIsDimmable(entity)
  const brightness = entityBrightnessPct(entity)
  const rowDisabled = controlsDisabled || !isAvailable
  const rowReason = !isAvailable
    ? "Device is not responding on the CAN bus"
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
      {isAvailable ? (
        <Badge
          variant={isOn ? "default" : "secondary"}
          className={cn(
            "w-10 justify-center text-xs",
            isOn &&
              "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
          )}
        >
          {isOn ? "On" : "Off"}
        </Badge>
      ) : (
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
    <div className={cn("space-y-1.5 py-2", !isAvailable && "opacity-50")}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{entity.name}</p>
          {showTimestamps && (
            <p className="text-xs text-muted-foreground">
              Updated {formatTime(entity.last_updated)}
            </p>
          )}
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

interface ZoneCardProps {
  zone: ZoneGroup
  controlsDisabled: boolean
  disabledReason: string
  showTimestamps: boolean
}

function ZoneCard({ zone, controlsDisabled, disabledReason, showTimestamps }: Readonly<ZoneCardProps>) {
  const bulkControl = useBulkControlEntities()
  const onCount = zone.entities.filter(entityIsOn).length
  const switchableIds = zone.entities
    .filter((entity) => entity.available !== false)
    .map((entity) => entity.entity_id)

  const handleAllOff = () => {
    bulkControl.mutate(
      {
        entity_ids: switchableIds,
        command: { command: "set", state: false },
        ignore_errors: true,
      },
      {
        onSuccess: (result) => {
          if (result.failed_count > 0) {
            toast({
              variant: "destructive",
              title: `${zone.displayName}: ${result.failed_count} of ${result.total_count} devices failed`,
              description: "Some devices did not turn off.",
            })
          }
        },
        onError: (error) => reportCommandError(error, zone.displayName),
      }
    )
  }

  const allOffDisabled = controlsDisabled || switchableIds.length === 0 || bulkControl.isPending

  const allOffButton = (
    <Button
      variant="ghost"
      size="icon"
      disabled={allOffDisabled}
      onClick={handleAllOff}
      className="size-7 text-muted-foreground"
      aria-label={`Turn everything off in ${zone.displayName}`}
    >
      <IconSunOff className="size-4" />
    </Button>
  )

  return (
    <Card className="@container/card">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">{zone.displayName}</CardTitle>
        <div className="flex items-center gap-2">
          {onCount > 0 && (
            <Badge variant="outline" className="text-xs">
              {onCount} on
            </Badge>
          )}
          {allOffDisabled && controlsDisabled ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>{allOffButton}</span>
              </TooltipTrigger>
              <TooltipContent>{disabledReason}</TooltipContent>
            </Tooltip>
          ) : (
            allOffButton
          )}
        </div>
      </CardHeader>
      <CardContent className="divide-y">
        {zone.entities.map((entity) => (
          <DeviceRow
            key={entity.entity_id}
            entity={entity}
            controlsDisabled={controlsDisabled}
            disabledReason={disabledReason}
            showTimestamps={showTimestamps}
          />
        ))}
      </CardContent>
    </Card>
  )
}

function ZoneGrid({ zones, controlsDisabled, disabledReason, showTimestamps }: Readonly<{
  zones: ZoneGroup[]
  controlsDisabled: boolean
  disabledReason: string
  showTimestamps: boolean
}>) {
  const interior = zones.filter((zone) => zone.section === "interior")
  const exterior = zones.filter((zone) => zone.section === "exterior")
  const other = zones.filter((zone) => zone.section === "other")

  const renderSection = (title: string | null, sectionZones: ZoneGroup[]) => {
    if (sectionZones.length === 0) return null
    return (
      <div className="space-y-3">
        {title && <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sectionZones.map((zone) => (
            <ZoneCard
              key={zone.zoneId}
              zone={zone}
              controlsDisabled={controlsDisabled}
              disabledReason={disabledReason}
              showTimestamps={showTimestamps}
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {renderSection("Interior", interior)}
      {renderSection("Exterior", exterior)}
      {renderSection("Unassigned", other)}
    </div>
  )
}

//
// ===== Page =====
//

export default function HomePage() {
  const { coach, reason } = useCoachConnection()
  const { data: config } = useCoachConfig()
  const { data: entityCollection, isLoading, error } = useEntities({ page_size: 100 })

  const entities = entityCollection?.entities ?? []
  const zones = groupEntitiesByZone(entities, config)

  const controlsDisabled = coach !== "LIVE"
  const disabledReason =
    coach === "OFFLINE"
      ? "Can't reach the coach — controls disabled"
      : `Coach data is not live — ${reason}`
  const showTimestamps = coach !== "LIVE"

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <ConnectionHero />
      <AlertsStrip />
      <ScenesRow entities={entities} />

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-48" />
          ))}
        </div>
      )}

      {error && (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">Couldn't load devices</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{error.message}</p>
          </CardContent>
        </Card>
      )}

      {!isLoading && !error && zones.length === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>No devices found</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {coach === "LIVE"
                ? "No entities are mapped for this coach yet. Check Device Mapping under Advanced."
                : "The coach connection is not live, so no devices could be discovered."}
            </p>
          </CardContent>
        </Card>
      )}

      {!isLoading && !error && zones.length > 0 && (
        <ZoneGrid
          zones={zones}
          controlsDisabled={controlsDisabled}
          disabledReason={disabledReason}
          showTimestamps={showTimestamps}
        />
      )}
    </div>
  )
}
