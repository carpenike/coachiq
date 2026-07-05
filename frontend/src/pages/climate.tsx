/**
 * Climate — owner heating/cooling control page.
 *
 * Modeled on the Vegatouch Mira climate screen: thermostat zone cards
 * (current temp, setpoint stepper, mode, fan) plus heat-only zones
 * (Aqua-Hot bay / floor loops) and read-only equipment status (rooftop
 * ACs, Aqua-Hot). Temperatures are Fahrenheit end-to-end — the backend
 * derives *_f fields from the raw RV-C values.
 *
 * Zone instance -> name mapping is provisional (see coach mapping YAML);
 * all numbers rendered are real bus data per docs/frontend-redesign.md.
 */

import { IconFlame, IconMinus, IconPlus, IconSnowflake, IconWind } from "@tabler/icons-react"
import { formatDistanceToNow } from "date-fns"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"

import type { EntitySchema, OperationResultSchema } from "@/api/types/domains"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useCoachConnection } from "@/contexts/coach-connection-context"
import { toast } from "@/hooks/use-toast"
import { useControlEntity, useEntities } from "@/hooks/useEntities"
import { cn } from "@/lib/utils"

const ZONE_LOADING_SKELETON_IDS = ["climate-skel-1", "climate-skel-2", "climate-skel-3"]

/** RV-C THERMOSTAT operating_mode raw values (mirrors backend climate_units). */
const MODE_LABELS = new Map<number, string>([
  [0, "off"],
  [1, "cool"],
  [2, "heat"],
  [3, "auto"],
  [4, "fan_only"],
  [5, "aux_heat"],
])
const MODE_DISPLAY = new Map<string, string>([
  ["off", "Off"],
  ["cool", "Cool"],
  ["heat", "Heat"],
  ["auto", "Auto"],
  ["fan_only", "Fan Only"],
  ["aux_heat", "Aux Heat"],
])

/** Modes offered in the zone mode selector (aux/defrost intentionally omitted). */
const SELECTABLE_MODES = ["off", "cool", "heat", "auto", "fan_only"]

/** WATERHEATER_STATUS operating_mode display labels. */
const WATER_HEATER_MODE_DISPLAY = new Map<number, string>([
  [0, "Off"],
  [1, "Burner"],
  [2, "Electric"],
  [3, "Burner + Electric"],
  [4, "Auto"],
])

const SETPOINT_MIN_F = 40
const SETPOINT_MAX_F = 105
/** Debounce between setpoint taps and the CAN command. */
const SETPOINT_COMMIT_MS = 700
/** Manual fan level split: <=60% displays as Low, above as High. */
const FAN_LOW_MAX_PCT = 60

//
// ===== Entity state helpers (state == raw signal dict + derived *_f fields) =====
//

function numberField(entity: EntitySchema, key: string): number | null {
  const state = entity.state ?? {}
  const value = Object.hasOwn(state, key) ? state[key as keyof typeof state] : null
  return typeof value === "number" ? value : null
}

function zoneMode(entity: EntitySchema): string {
  const raw = numberField(entity, "operating_mode")
  if (raw === null) return "unknown"
  return MODE_LABELS.get(raw) ?? "unknown"
}

function modeDisplay(mode: string): string {
  return MODE_DISPLAY.get(mode) ?? "Unknown"
}

/**
 * The zone's single displayed setpoint. The G6 keeps heat/cool setpoints in
 * lockstep for the main zones; heat-only zones (bay/floor) use the heat one.
 */
function zoneSetpointF(entity: EntitySchema, heatOnly: boolean): number | null {
  if (heatOnly || zoneMode(entity) === "heat") return numberField(entity, "setpoint_heat_f")
  return numberField(entity, "setpoint_cool_f")
}

/**
 * Heat-only zones (Aqua-Hot heat counterparts / bay / floor loops) have no
 * compressor or fan. The v1 entity schema exposes no capabilities list (same
 * contract gap the Lights page works around), so this keys off the
 * coach-mapping entity ids (climate_front_heat, climate_aux_heat_5, ...).
 */
function zoneIsHeatOnly(entity: EntitySchema): boolean {
  return entity.entity_id.includes("_heat")
}

/** Current fan selection: auto, or manual low/high (the Mira offers Low/High). */
function zoneFanSelection(entity: EntitySchema): string | null {
  const fanModeRaw = numberField(entity, "fan_mode")
  if (fanModeRaw === null) return null
  if (fanModeRaw === 0) return "auto"
  const speed = numberField(entity, "fan_speed_pct") ?? 0
  return speed > FAN_LOW_MAX_PCT ? "high" : "low"
}

function formatTempF(value: number | null): string {
  return value === null ? "—" : `${Math.round(value)}°`
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
// ===== Mode icon =====
//

function ZoneModeIcon({ mode }: Readonly<{ mode: string }>) {
  if (mode === "cool") return <IconSnowflake className="size-4 text-sky-500" aria-hidden />
  if (mode === "heat" || mode === "aux_heat") {
    return <IconFlame className="size-4 text-orange-500" aria-hidden />
  }
  if (mode === "fan_only") return <IconWind className="size-4 text-muted-foreground" aria-hidden />
  return null
}

//
// ===== Setpoint stepper (debounced) =====
//

interface ISetpointStepperProps {
  entity: EntitySchema
  heatOnly: boolean
  disabled: boolean
}

function SetpointStepper({ entity, heatOnly, disabled }: Readonly<ISetpointStepperProps>) {
  const control = useControlEntity()
  const stateSetpoint = zoneSetpointF(entity, heatOnly)
  const [pending, setPending] = useState<number | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Drop the local pending value once the entity state catches up.
  useEffect(() => {
    if (pending !== null && stateSetpoint !== null && Math.round(stateSetpoint) === pending) {
      setPending(null)
    }
  }, [pending, stateSetpoint])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    []
  )

  const shown = pending ?? (stateSetpoint === null ? null : Math.round(stateSetpoint))

  const step = (delta: number) => {
    if (shown === null) return
    const target = Math.max(SETPOINT_MIN_F, Math.min(SETPOINT_MAX_F, shown + delta))
    setPending(target)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      control.mutate(
        {
          entityId: entity.entity_id,
          command: {
            command: "set",
            parameters: heatOnly ? { setpoint_heat_f: target } : { setpoint_f: target },
          },
        },
        {
          onSuccess: (result) => reportCommandResult(result, entity.name),
          onError: (error) => {
            setPending(null)
            reportCommandError(error, entity.name)
          },
        }
      )
    }, SETPOINT_COMMIT_MS)
  }

  const stepperDisabled = disabled || shown === null

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="outline"
        size="icon"
        className="size-8"
        disabled={stepperDisabled}
        onClick={() => step(-1)}
        aria-label={`Lower ${entity.name} setpoint`}
      >
        <IconMinus className="size-4" />
      </Button>
      <span
        className={cn(
          "w-12 text-center text-lg font-semibold tabular-nums",
          pending !== null && "text-primary"
        )}
      >
        {shown === null ? "—" : `${shown}°`}
      </span>
      <Button
        variant="outline"
        size="icon"
        className="size-8"
        disabled={stepperDisabled}
        onClick={() => step(1)}
        aria-label={`Raise ${entity.name} setpoint`}
      >
        <IconPlus className="size-4" />
      </Button>
    </div>
  )
}

//
// ===== Zone control rows (mode / fan selectors) =====
//

interface IZoneSelectRowProps {
  entity: EntitySchema
  disabled: boolean
  onCommand: (parameters: Record<string, string | number>, label: string) => void
}

function ZoneModeRow({ entity, disabled, onCommand }: Readonly<IZoneSelectRowProps>) {
  const mode = zoneMode(entity)
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">Mode</span>
      <Select
        {...(SELECTABLE_MODES.includes(mode) ? { value: mode } : {})}
        disabled={disabled}
        onValueChange={(value) => onCommand({ mode: value }, "mode")}
      >
        <SelectTrigger className="h-8 w-32" aria-label={`${entity.name} mode`}>
          <SelectValue placeholder="—" />
        </SelectTrigger>
        <SelectContent>
          {SELECTABLE_MODES.map((value) => (
            <SelectItem key={value} value={value}>
              {modeDisplay(value)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function ZoneFanRow({ entity, disabled, onCommand }: Readonly<IZoneSelectRowProps>) {
  const fanSelection = zoneFanSelection(entity)
  const setFan = (selection: string) => {
    if (selection === "auto") onCommand({ fan_mode: "auto" }, "fan")
    else if (selection === "low") onCommand({ fan_mode: "on", fan_speed_pct: 50 }, "fan")
    else onCommand({ fan_mode: "on", fan_speed_pct: 100 }, "fan")
  }
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground">Fan</span>
      <Select
        {...(fanSelection === null ? {} : { value: fanSelection })}
        disabled={disabled || fanSelection === null}
        onValueChange={setFan}
      >
        <SelectTrigger className="h-8 w-32" aria-label={`${entity.name} fan`}>
          <SelectValue placeholder="—" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="auto">Auto</SelectItem>
          <SelectItem value="low">Low</SelectItem>
          <SelectItem value="high">High</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}

//
// ===== Zone cards =====
//

interface IZoneCardProps {
  entity: EntitySchema
  controlsDisabled: boolean
  disabledReason: string
}

/** Card header shared by both zone card types. */
function ZoneCardHeader({
  entity,
  icon,
  subtitle,
}: Readonly<{ entity: EntitySchema; icon: React.ReactNode; subtitle: string }>) {
  const currentF = numberField(entity, "current_temp_f")
  return (
    <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
      <div className="min-w-0">
        <CardTitle className="flex items-center gap-1.5 text-base">
          {icon}
          {entity.name}
        </CardTitle>
        <p className="text-xs text-muted-foreground">Updated {relativeTime(entity.last_updated)}</p>
      </div>
      <div className="text-right">
        <p className="text-3xl font-semibold tabular-nums">{formatTempF(currentF)}</p>
        <p className="text-xs text-muted-foreground">
          {currentF === null ? "no sensor data" : subtitle}
        </p>
      </div>
    </CardHeader>
  )
}

/** Wrap controls in a tooltip explaining why they're disabled. */
function DisabledTooltip({
  disabled,
  reason,
  children,
}: Readonly<{ disabled: boolean; reason: string; children: React.ReactNode }>) {
  if (!disabled) return <div>{children}</div>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div>{children}</div>
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  )
}

function ThermostatZoneCard({
  entity,
  controlsDisabled,
  disabledReason,
}: Readonly<IZoneCardProps>) {
  const control = useControlEntity()
  const isAvailable = entity.available !== false
  const cardDisabled = controlsDisabled || !isAvailable
  const cardReason = !isAvailable ? "Zone is not responding on the CAN bus" : disabledReason
  const mode = zoneMode(entity)

  const sendParameters = (parameters: Record<string, string | number>, label: string) => {
    control.mutate(
      { entityId: entity.entity_id, command: { command: "set", parameters } },
      {
        onSuccess: (result) => reportCommandResult(result, `${entity.name} ${label}`),
        onError: (error) => reportCommandError(error, `${entity.name} ${label}`),
      }
    )
  }

  const rowDisabled = cardDisabled || control.isPending

  return (
    <Card className={cn(!isAvailable && "opacity-60")}>
      <ZoneCardHeader entity={entity} icon={<ZoneModeIcon mode={mode} />} subtitle={modeDisplay(mode)} />
      <CardContent>
        <DisabledTooltip disabled={cardDisabled} reason={cardReason}>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">Setpoint</span>
              <SetpointStepper entity={entity} heatOnly={false} disabled={rowDisabled} />
            </div>
            <ZoneModeRow entity={entity} disabled={rowDisabled} onCommand={sendParameters} />
            <ZoneFanRow entity={entity} disabled={rowDisabled} onCommand={sendParameters} />
          </div>
        </DisabledTooltip>
      </CardContent>
    </Card>
  )
}

function HeatZoneCard({ entity, controlsDisabled, disabledReason }: Readonly<IZoneCardProps>) {
  const control = useControlEntity()
  const isAvailable = entity.available !== false
  const cardDisabled = controlsDisabled || !isAvailable
  const cardReason = !isAvailable ? "Zone is not responding on the CAN bus" : disabledReason

  const mode = zoneMode(entity)
  const heatOn = mode === "heat" || mode === "aux_heat"

  const setHeat = (on: boolean) => {
    control.mutate(
      {
        entityId: entity.entity_id,
        command: { command: "set", parameters: { mode: on ? "heat" : "off" } },
      },
      {
        onSuccess: (result) => reportCommandResult(result, entity.name),
        onError: (error) => reportCommandError(error, entity.name),
      }
    )
  }

  let heatStatus = "Off"
  if (mode === "unknown") heatStatus = "—"
  else if (heatOn) heatStatus = "Heating"

  return (
    <Card className={cn(!isAvailable && "opacity-60")}>
      <ZoneCardHeader
        entity={entity}
        icon={heatOn ? <IconFlame className="size-4 text-orange-500" aria-hidden /> : null}
        subtitle={heatStatus}
      />
      <CardContent>
        <DisabledTooltip disabled={cardDisabled} reason={cardReason}>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Switch
                checked={heatOn}
                disabled={cardDisabled || control.isPending || mode === "unknown"}
                onCheckedChange={setHeat}
                aria-label={`Toggle ${entity.name}`}
              />
              <span className="text-xs text-muted-foreground">{heatStatus}</span>
            </div>
            <SetpointStepper entity={entity} heatOnly disabled={cardDisabled || control.isPending} />
          </div>
        </DisabledTooltip>
      </CardContent>
    </Card>
  )
}

//
// ===== Read-only equipment status (AC units, Aqua-Hot) =====
//

function AcUnitRow({ entity }: Readonly<{ entity: EntitySchema }>) {
  const output = numberField(entity, "output_pct")
  const fan = numberField(entity, "fan_speed_pct")
  const running = output !== null && output > 0
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium">{entity.name}</p>
        <p className="text-xs text-muted-foreground">Updated {relativeTime(entity.last_updated)}</p>
      </div>
      <div className="flex items-center gap-2">
        {running ? (
          <Badge
            className="bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200"
            variant="secondary"
          >
            cooling {output}%
          </Badge>
        ) : (
          <Badge variant="secondary">idle</Badge>
        )}
        <span className="text-xs text-muted-foreground">fan {fan === null ? "—" : `${fan}%`}</span>
      </div>
    </div>
  )
}

function AquaHotRow({ entity }: Readonly<{ entity: EntitySchema }>) {
  const waterF = numberField(entity, "water_temp_f")
  const modeRaw = numberField(entity, "operating_mode")
  const burner = numberField(entity, "burner_status")
  const element = numberField(entity, "ac_element_status")
  let modeLabel = "—"
  if (modeRaw !== null) {
    modeLabel = WATER_HEATER_MODE_DISPLAY.get(modeRaw) ?? `mode ${modeRaw}`
  }
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium">{entity.name}</p>
        <p className="text-xs text-muted-foreground">Updated {relativeTime(entity.last_updated)}</p>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="secondary">{modeLabel}</Badge>
        {burner === 1 && (
          <Badge
            className="bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200"
            variant="secondary"
          >
            burner lit
          </Badge>
        )}
        {element === 1 && <Badge variant="secondary">element on</Badge>}
        <span className="text-sm tabular-nums">{formatTempF(waterF)}</span>
      </div>
    </div>
  )
}

//
// ===== Page sections =====
//

interface IZoneSectionProps {
  title: string
  zones: EntitySchema[]
  controlsDisabled: boolean
  disabledReason: string
  heatOnly: boolean
}

function ZoneSection({
  title,
  zones,
  controlsDisabled,
  disabledReason,
  heatOnly,
}: Readonly<IZoneSectionProps>) {
  if (zones.length === 0) return null
  const CardComponent = heatOnly ? HeatZoneCard : ThermostatZoneCard
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
      <div
        className={cn(
          "grid grid-cols-1 gap-4 md:grid-cols-2",
          heatOnly ? "xl:grid-cols-4" : "xl:grid-cols-3"
        )}
      >
        {zones.map((entity) => (
          <CardComponent
            key={entity.entity_id}
            entity={entity}
            controlsDisabled={controlsDisabled}
            disabledReason={disabledReason}
          />
        ))}
      </div>
    </div>
  )
}

function EquipmentSection({
  acUnits,
  waterHeaters,
}: Readonly<{ acUnits: EntitySchema[]; waterHeaters: EntitySchema[] }>) {
  if (acUnits.length === 0 && waterHeaters.length === 0) return null
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-muted-foreground">Equipment</h2>
      <Card>
        <CardContent className="divide-y pt-2">
          {acUnits.map((entity) => (
            <AcUnitRow key={entity.entity_id} entity={entity} />
          ))}
          {waterHeaters.map((entity) => (
            <AquaHotRow key={entity.entity_id} entity={entity} />
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

function NoZonesCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>No climate zones are mapped</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          No thermostat zones are mapped for this coach yet. Map them in{" "}
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
  )
}

//
// ===== Page =====
//

export default function ClimatePage() {
  const { coach, reason } = useCoachConnection()
  const zonesQuery = useEntities({ device_type: "climate", page_size: 100 })
  const acQuery = useEntities({ device_type: "air_conditioner", page_size: 100 })
  const waterHeaterQuery = useEntities({ device_type: "water_heater", page_size: 100 })

  const zones = (zonesQuery.data?.entities ?? []).filter(
    (entity) => entity.device_type === "climate"
  )
  const mainZones = zones.filter((zone) => !zoneIsHeatOnly(zone))
  const heatZones = zones.filter(zoneIsHeatOnly)

  const controlsDisabled = coach !== "LIVE"
  const disabledReason =
    coach === "OFFLINE"
      ? "Can't reach the coach — controls disabled"
      : `Coach data is not live — ${reason}`

  const { isLoading, error } = zonesQuery

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {ZONE_LOADING_SKELETON_IDS.map((skeletonId) => (
            <Skeleton key={skeletonId} className="h-56" />
          ))}
        </div>
      )}

      {error && (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">Couldn&apos;t load climate zones</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{error.message}</p>
          </CardContent>
        </Card>
      )}

      {!isLoading && !error && zones.length === 0 && <NoZonesCard />}

      {!isLoading && !error && (
        <>
          <ZoneSection
            title="Zones"
            zones={mainZones}
            controlsDisabled={controlsDisabled}
            disabledReason={disabledReason}
            heatOnly={false}
          />
          <ZoneSection
            title="Aqua-Hot Heat"
            zones={heatZones}
            controlsDisabled={controlsDisabled}
            disabledReason={disabledReason}
            heatOnly
          />
          <EquipmentSection
            acUnits={acQuery.data?.entities ?? []}
            waterHeaters={waterHeaterQuery.data?.entities ?? []}
          />
        </>
      )}
    </div>
  )
}
