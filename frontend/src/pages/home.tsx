/**
 * Home — the owner screen (Vegatouch Mira / Firefly panel replacement).
 *
 * Answers, in order:
 *  1. Is my coach reachable, and is what I'm seeing current?  (global banner)
 *  2. What state is each zone of the coach in?                (zone grid)
 *  3. Can I change it right now?                              (controls w/ feedback)
 *
 * No fabricated numbers. Every control gives toast feedback per the
 * command feedback contract in docs/archive/2026-07/frontend-redesign.md.
 */

import {
  IconAlertTriangle,
  IconArrowDown,
  IconArrowUp,
  IconAdjustments,
  IconMoon,
  IconShieldBolt,
  IconSparkles,
  IconSunOff,
  IconTruck,
} from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"

import { fetchActiveDTCs } from "@/api/domains/diagnostics"
import type { EntitySchema, OperationResultSchema } from "@/api/types/domains"
import { PowerSection } from "@/components/power-section"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useCoachConnection } from "@/contexts/coach-connection-context"
import { toast } from "@/hooks/use-toast"
import {
  groupEntitiesByZone,
  resolveSceneCommands,
  useCoachConfig,
  type ILightingScene,
  type IZoneGroup,
} from "@/hooks/useCoachConfig"
import { useBulkControlEntities, useControlEntity, useEntities } from "@/hooks/useEntities"
import {
  moveHomeSection,
  setFavoriteEntityIds,
  setHomeSectionVisible,
  useHomePreferences,
  type HomeSectionId,
} from "@/hooks/usePreferences"
import {
  entitySupportsBrightnessControl,
  entitySupportsPowerControl,
} from "@/lib/entity-capabilities"
import { cn } from "@/lib/utils"

/** Stable keys for the zone-grid loading-skeleton placeholders (no zone data exists yet to key on). */
const ZONE_LOADING_SKELETON_IDS = [
  "zone-skeleton-1",
  "zone-skeleton-2",
  "zone-skeleton-3",
  "zone-skeleton-4",
  "zone-skeleton-5",
  "zone-skeleton-6",
]

/** Device types whose current UI command contract explicitly supports a binary toggle. */
const HOME_TOGGLE_DEVICE_TYPES = new Set(["light"])
const HOME_SECTION_LABELS = new Map<HomeSectionId, string>([
  ["alerts", "Active alerts"],
  ["scenes", "Scenes"],
  ["power", "Power summary"],
  ["zones", "Zone controls"],
])

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

// eslint-disable-next-line react-refresh/only-export-components -- pure capability policy is unit tested directly
export function entitySupportsHomeToggle(entity: EntitySchema): boolean {
  return HOME_TOGGLE_DEVICE_TYPES.has(entity.device_type) && entitySupportsPowerControl(entity)
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
 * Whether the entity supports dimming according to the canonical contract.
 */
function entityIsDimmable(entity: EntitySchema): boolean {
  return entitySupportsBrightnessControl(entity)
}

function stateChangedAt(entity: EntitySchema): string | null {
  return entity.state_changed_at ?? entity.last_updated ?? null
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
      description: result.error_message ?? `Backend reported status "${result.status}".`,
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

interface ISceneCommandGroup {
  ids: string[]
  action: "on" | "off"
  brightness?: number
}

/** Groups resolved scene commands by identical action+brightness so each group is one bulk call. */
function groupSceneCommands(
  commands: ReturnType<typeof resolveSceneCommands>
): ISceneCommandGroup[] {
  const groups = new Map<string, ISceneCommandGroup>()
  for (const command of commands) {
    const key = `${command.action}:${command.brightness ?? ""}`
    const group = groups.get(key)
    if (group) {
      group.ids.push(command.entityId)
    } else {
      const entry: ISceneCommandGroup = {
        ids: [command.entityId],
        action: command.action,
      }
      if (command.brightness !== undefined) entry.brightness = command.brightness
      groups.set(key, entry)
    }
  }
  return [...groups.values()]
}

/** Runs one bulk-control call per scene command group and reports the combined result via toast. */
async function applySceneGroups(
  scene: ILightingScene,
  groups: ISceneCommandGroup[],
  bulkControl: ReturnType<typeof useBulkControlEntities>
): Promise<void> {
  const results = await Promise.all(
    groups.map((group) =>
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
}

/** A single scene button, wrapped in a tooltip when controls are disabled. */
function SceneButton({
  sceneKey,
  scene,
  disabled,
  runningScene,
  onRun,
}: Readonly<{
  sceneKey: string
  scene: ILightingScene
  disabled: boolean
  runningScene: string | null
  onRun: () => void
}>) {
  const SceneIcon = SCENE_ICONS.get(sceneKey) ?? IconSparkles
  const button = (
    <Button
      variant="outline"
      disabled={disabled || runningScene !== null}
      onClick={onRun}
      className="h-auto min-h-24 w-full flex-col gap-1.5 whitespace-normal py-3"
    >
      <SceneIcon className={cn("size-5", runningScene === sceneKey && "animate-pulse")} />
      <span className="text-sm font-medium">{scene.name}</span>
      {scene.description && (
        <span className="text-xs font-normal text-muted-foreground">{scene.description}</span>
      )}
    </Button>
  )
  if (!disabled) return button
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="w-full">{button}</span>
      </TooltipTrigger>
      <TooltipContent>Controls disabled — coach connection is not live</TooltipContent>
    </Tooltip>
  )
}

function ScenesRow({ entities }: Readonly<{ entities: EntitySchema[] }>) {
  const { data: config } = useCoachConfig()
  const { coach } = useCoachConnection()
  const bulkControl = useBulkControlEntities()
  const [runningScene, setRunningScene] = useState<string | null>(null)

  const scenes = Object.entries(config?.lighting_scenes ?? {})
  if (scenes.length === 0) return null

  const disabled = coach !== "LIVE"

  const runScene = async (sceneKey: string, scene: ILightingScene) => {
    const commands = resolveSceneCommands(scene, entities)
    if (commands.length === 0) {
      toast({
        title: `No devices matched "${scene.name}"`,
        description: "The scene definition matched no known entities.",
      })
      return
    }

    setRunningScene(sceneKey)
    try {
      await applySceneGroups(scene, groupSceneCommands(commands), bulkControl)
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
        {scenes.map(([sceneKey, scene]) => (
          <SceneButton
            key={sceneKey}
            sceneKey={sceneKey}
            scene={scene}
            disabled={disabled}
            runningScene={runningScene}
            onRun={() => void runScene(sceneKey, scene)}
          />
        ))}
      </div>
    </div>
  )
}

//
// ===== Zone grid =====
//

interface IDeviceRowProps {
  entity: EntitySchema
  controlsDisabled: boolean
  disabledReason: string
  showTimestamps: boolean
}

export function ToggleDeviceRow({ entity, controlsDisabled, disabledReason, showTimestamps }: Readonly<IDeviceRowProps>) {
  const control = useControlEntity()
  const isOn = entityIsOn(entity)
  const isAvailable = entity.available !== false
  const dimmable = entityIsDimmable(entity)
  const brightness = entityBrightnessPct(entity)
  const [pendingBrightness, setPendingBrightness] = useState<number | null>(null)
  useEffect(() => {
    if (pendingBrightness !== null && brightness === pendingBrightness) {
      setPendingBrightness(null)
    }
  }, [pendingBrightness, brightness])
  const shownBrightness = pendingBrightness ?? brightness
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
        disabled={rowDisabled}
        onCheckedChange={(checked) => sendCommand({ command: "set", state: checked })}
        aria-label={entity.name}
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
              Last changed at {formatTime(stateChangedAt(entity))}
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
        <div className="flex items-center gap-3">
          <Slider
            value={[shownBrightness]}
            max={100}
            step={5}
            disabled={rowDisabled}
            onValueChange={(value) => {
              const level = value[0]
              if (level !== undefined) setPendingBrightness(level)
            }}
            onValueCommit={(value) => {
              const level = value[0]
              if (level === undefined) return
              control.mutate(
                {
                  entityId: entity.entity_id,
                  command: { command: "set", state: level > 0, brightness: level },
                },
                {
                  onSuccess: (result) => {
                    if (result.status !== "success") setPendingBrightness(null)
                    reportCommandResult(result, entity.name)
                  },
                  onError: (error) => {
                    setPendingBrightness(null)
                    reportCommandError(error, entity.name)
                  },
                }
              )
            }}
            aria-label={`${entity.name} brightness`}
          />
          <output className="w-10 text-right text-xs tabular-nums text-muted-foreground">
            {shownBrightness}%
          </output>
        </div>
      )}
    </div>
  )
}

interface IZoneCardProps {
  zone: IZoneGroup
  controlsDisabled: boolean
  disabledReason: string
  showTimestamps: boolean
}

function ZoneCard({ zone, controlsDisabled, disabledReason, showTimestamps }: Readonly<IZoneCardProps>) {
  const bulkControl = useBulkControlEntities()
  const onCount = zone.entities.filter(
    (entity) => entitySupportsHomeToggle(entity) && entityIsOn(entity)
  ).length
  const switchableIds = zone.entities
    .filter(
      (entity) => entitySupportsHomeToggle(entity) && entity.available !== false
    )
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

  const allOffButton = (
    <Button
      variant="ghost"
      size="sm"
      disabled={controlsDisabled}
      onClick={handleAllOff}
      className="h-11 gap-1.5 px-2 text-muted-foreground"
      aria-label={`Turn all lights off in ${zone.displayName}`}
    >
      <IconSunOff className="size-4" />
      <span>All off</span>
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
          {switchableIds.length > 0 &&
            (controlsDisabled ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>{allOffButton}</span>
                </TooltipTrigger>
                <TooltipContent>{disabledReason}</TooltipContent>
              </Tooltip>
            ) : (
              allOffButton
            ))}
        </div>
      </CardHeader>
      <CardContent className="divide-y">
        {zone.entities.map((entity) => (
          <ToggleDeviceRow
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
  zones: IZoneGroup[]
  controlsDisabled: boolean
  disabledReason: string
  showTimestamps: boolean
}>) {
  const interior = zones.filter((zone) => zone.section === "interior")
  const exterior = zones.filter((zone) => zone.section === "exterior")
  const other = zones.filter((zone) => zone.section === "other")

  const renderSection = (title: string | null, sectionZones: IZoneGroup[]) => {
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

function HomeCustomizationDialog({
  controllableEntities,
}: Readonly<{ controllableEntities: EntitySchema[] }>) {
  const preferences = useHomePreferences()
  const favorites = new Set(preferences.favoriteEntityIds)

  const toggleFavorite = (entityId: string, selected: boolean) => {
    setFavoriteEntityIds(
      selected
        ? [...preferences.favoriteEntityIds, entityId]
        : preferences.favoriteEntityIds.filter((id) => id !== entityId)
    )
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <IconAdjustments className="size-4" />
          Customize Home
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Customize Home</DialogTitle>
          <DialogDescription>
            Choose visible sections, their order, and which quick controls appear first on this
            device.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5">
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Sections</h3>
            {preferences.sectionOrder.map((section, index) => {
              const visible = !preferences.hiddenSections.includes(section)
              return (
                <div key={section} className="flex min-h-11 items-center gap-2 rounded-md border px-2">
                  <Checkbox
                    id={`home-section-${section}`}
                    checked={visible}
                    onCheckedChange={(checked) =>
                      setHomeSectionVisible(section, checked === true)
                    }
                  />
                  <Label htmlFor={`home-section-${section}`} className="flex-1">
                    {HOME_SECTION_LABELS.get(section)}
                  </Label>
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={index === 0}
                    onClick={() => moveHomeSection(section, -1)}
                    aria-label={`Move ${HOME_SECTION_LABELS.get(section)} up`}
                  >
                    <IconArrowUp className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={index === preferences.sectionOrder.length - 1}
                    onClick={() => moveHomeSection(section, 1)}
                    aria-label={`Move ${HOME_SECTION_LABELS.get(section)} down`}
                  >
                    <IconArrowDown className="size-4" />
                  </Button>
                </div>
              )
            })}
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Favorite controls</h3>
            <p className="text-sm text-muted-foreground">
              Favorites stay in their coach zone and sort ahead of other controls.
            </p>
            {controllableEntities.map((entity) => (
              <div key={entity.entity_id} className="flex min-h-11 items-center gap-2">
                <Checkbox
                  id={`favorite-${entity.entity_id}`}
                  checked={favorites.has(entity.entity_id)}
                  onCheckedChange={(checked) => toggleFavorite(entity.entity_id, checked === true)}
                />
                <Label htmlFor={`favorite-${entity.entity_id}`}>{entity.name}</Label>
              </div>
            ))}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}

//
// ===== Page =====
//

export default function HomePage() {
  const { coach, reason } = useCoachConnection()
  const { data: config } = useCoachConfig()
  const { data: entityCollection, isLoading, error } = useEntities({ page_size: 100 })
  const homePreferences = useHomePreferences()

  const entities = entityCollection?.entities ?? []
  // Home is a quick-control surface. Read-only climate, tank, temperature,
  // and power telemetry belongs on its dedicated page instead of masquerading
  // as a generic switch here.
  const favoriteIds = new Set(homePreferences.favoriteEntityIds)
  const zoneEntities = entities
    .filter(entitySupportsHomeToggle)
    .sort((left, right) => Number(favoriteIds.has(right.entity_id)) - Number(favoriteIds.has(left.entity_id)))
  const zones = groupEntitiesByZone(zoneEntities, config)
  const homeToggleEntities = entities.filter(entitySupportsHomeToggle)

  const controlsDisabled = coach !== "LIVE"
  const disabledReason =
    coach === "OFFLINE"
      ? "Can't reach the coach — controls disabled"
      : `Coach data is not live — ${reason}`
  const showTimestamps = coach !== "LIVE"
  const sectionContent = new Map<HomeSectionId, React.ReactNode>([
    ["alerts", <AlertsStrip key="alerts" />],
    ["scenes", <ScenesRow key="scenes" entities={homeToggleEntities} />],
    ["power", <PowerSection key="power" entities={entities} compact />],
    [
      "zones",
      !isLoading && !error && zones.length > 0 ? (
        <ZoneGrid
          key="zones"
          zones={zones}
          controlsDisabled={controlsDisabled}
          disabledReason={disabledReason}
          showTimestamps={showTimestamps}
        />
      ) : null,
    ],
  ])

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <div className="flex justify-end">
        <HomeCustomizationDialog controllableEntities={homeToggleEntities} />
      </div>

      {homePreferences.sectionOrder.map((section) =>
        homePreferences.hiddenSections.includes(section) ? null : sectionContent.get(section)
      )}

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {ZONE_LOADING_SKELETON_IDS.map((skeletonId) => (
            <Skeleton key={skeletonId} className="h-48" />
          ))}
        </div>
      )}

      {error && (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">Couldn&apos;t load devices</CardTitle>
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

    </div>
  )
}
