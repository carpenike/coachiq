/**
 * Power — read-only cards for the Victron power system entities.
 *
 * These entities (inverter/charger, battery, solar, system aggregate) are
 * telemetry, not switches: they must never render the generic DeviceRow
 * toggle, which would send a bare `toggle` command at the inverter. All
 * numbers come straight from the entity state dict; anything missing shows
 * as "—" (no fabricated values, per docs/archive/2026-07/frontend-redesign.md).
 */

import {
  IconBattery,
  IconBolt,
  IconChevronRight,
  IconEngine,
  IconPlugConnected,
  IconSun,
  IconTopologyStar3,
} from "@tabler/icons-react"
import { Link } from "react-router-dom"

import type { EntitySchema } from "@/api/types/domains"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { POWER_DEVICE_TYPES } from "@/lib/power"
import { cn } from "@/lib/utils"

/** system /Ac/ActiveIn/Source enum (Venus OS). */
const AC_SOURCE_NAMES = new Map<number, string>([
  [1, "Grid"],
  [2, "Generator"],
  [3, "Shore power"],
  [240, "Inverting"],
])

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function fmtWatts(watts: number | null): string {
  if (watts === null) return "—"
  return Math.abs(watts) >= 1000 ? `${(watts / 1000).toFixed(1)} kW` : `${Math.round(watts)} W`
}

function fmtNumber(value: number | null, unit: string, digits = 1): string {
  return value === null ? "—" : `${value.toFixed(digits)} ${unit}`
}

function statusLabel(state: Record<string, unknown>): string {
  const status = state.status
  return typeof status === "string" ? status.replace(/_/g, " ") : "unknown"
}

function StatRow({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="flex items-center justify-between py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  )
}

interface IPowerCardProps {
  entity: EntitySchema
  icon: typeof IconBolt
  statusVariant?: "default" | "secondary"
  children: React.ReactNode
}

function PowerCard({ entity, icon: Icon, children }: Readonly<IPowerCardProps>) {
  const state = entity.state ?? {}
  const offline = entity.available === false
  return (
    <Card className={cn(offline && "opacity-50")}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="size-4 text-muted-foreground" aria-hidden />
          {entity.name}
        </CardTitle>
        {offline ? (
          <Badge variant="outline" className="gap-1 text-xs text-muted-foreground">
            <span className="size-1.5 rounded-full bg-red-500" aria-hidden />
            offline
          </Badge>
        ) : (
          <Badge variant="secondary" className="text-xs capitalize">
            {statusLabel(state)}
          </Badge>
        )}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function PowerFlowCard({ entity }: Readonly<{ entity: EntitySchema }>) {
  const state = entity.state ?? {}
  const sourceCode = num(state.ac_source_code)
  const acIn = sumWatts(state.ac_in_l1_power, state.ac_in_l2_power)
  const loads = sumWatts(state.ac_loads_l1_power, state.ac_loads_l2_power)
  const batteryPower = num(state.battery_power)
  const source =
    sourceCode !== null ? (AC_SOURCE_NAMES.get(sourceCode) ?? "Off-grid") : "—"

  return (
    <PowerCard entity={entity} icon={IconBolt}>
      <StatRow label="AC source" value={source} />
      <StatRow label="AC input" value={fmtWatts(acIn)} />
      <StatRow label="Loads" value={fmtWatts(loads)} />
      <StatRow label="Battery" value={batteryFlowLabel(batteryPower)} />
      <StatRow label="Solar" value={fmtWatts(num(state.pv_power))} />
    </PowerCard>
  )
}

function sumWatts(...values: unknown[]): number | null {
  const numbers = values.map(num).filter((value): value is number => value !== null)
  return numbers.length === 0 ? null : numbers.reduce((total, value) => total + value, 0)
}

function batteryFlowLabel(watts: number | null): string {
  if (watts === null) return "—"
  if (watts > 0) return `Charging ${fmtWatts(watts)}`
  if (watts < 0) return `Discharging ${fmtWatts(Math.abs(watts))}`
  return "Idle"
}

function InverterChargerCard({ entity }: Readonly<{ entity: EntitySchema }>) {
  const state = entity.state ?? {}
  const shoreConnected = num(state.ac_in_connected) === 1
  const currentLimit = num(state.input_current_limit)
  return (
    <PowerCard entity={entity} icon={IconPlugConnected}>
      <StatRow label="Shore input" value={shoreConnected ? "Connected" : "Disconnected"} />
      <StatRow label="AC in" value={fmtWatts(num(state.ac_in_power))} />
      <StatRow label="AC out" value={fmtWatts(num(state.ac_out_power))} />
      <StatRow label="Input limit" value={fmtNumber(currentLimit, "A", 0)} />
    </PowerCard>
  )
}

function BatteryCard({ entity }: Readonly<{ entity: EntitySchema }>) {
  const state = entity.state ?? {}
  const soc = num(state.soc)
  return (
    <PowerCard entity={entity} icon={IconBattery}>
      <div className="mb-2 space-y-1.5">
        <p className="text-2xl font-semibold tabular-nums">
          {soc === null ? "—" : `${Math.round(soc)}%`}
        </p>
        <Progress value={soc ?? 0} aria-label="Battery state of charge" />
      </div>
      <StatRow label="Power" value={batteryFlowLabel(num(state.power))} />
      <StatRow label="Voltage" value={fmtNumber(num(state.voltage), "V")} />
      <StatRow label="Temperature" value={fmtNumber(num(state.temperature), "°C", 0)} />
    </PowerCard>
  )
}

function SolarCard({ entity }: Readonly<{ entity: EntitySchema }>) {
  const state = entity.state ?? {}
  return (
    <PowerCard entity={entity} icon={IconSun}>
      <div className="mb-2">
        <p className="text-2xl font-semibold tabular-nums">
          {fmtWatts(num(state.pv_power))}
        </p>
      </div>
      <StatRow label="Yield today" value={fmtNumber(num(state.yield_today_kwh), "kWh")} />
      <StatRow label="Yield total" value={fmtNumber(num(state.yield_total_kwh), "kWh", 0)} />
    </PowerCard>
  )
}

function fmtRuntimeHours(seconds: number | null): string {
  if (seconds === null) return "—"
  return `${(seconds / 3600).toFixed(1)} h`
}

function GeneratorCard({ entity }: Readonly<{ entity: EntitySchema }>) {
  const state = entity.state ?? {}
  return (
    <PowerCard entity={entity} icon={IconEngine}>
      <StatRow
        label="Autostart"
        value={num(state.autostart_enabled) === 1 ? "Enabled" : "Disabled"}
      />
      <StatRow label="Run today" value={fmtRuntimeHours(num(state.runtime_today_seconds))} />
      <StatRow label="Total runtime" value={fmtRuntimeHours(num(state.runtime_total_seconds))} />
    </PowerCard>
  )
}

function DcLoadsCard({ entity }: Readonly<{ entity: EntitySchema }>) {
  const state = entity.state ?? {}
  return (
    <PowerCard entity={entity} icon={IconTopologyStar3}>
      <div className="mb-2">
        <p className="text-2xl font-semibold tabular-nums">{fmtWatts(num(state.power))}</p>
      </div>
      <StatRow label="Voltage" value={fmtNumber(num(state.voltage), "V")} />
      <StatRow label="Current" value={fmtNumber(num(state.current), "A")} />
    </PowerCard>
  )
}

const CARD_ORDER: Record<string, number> = {
  power_system: 0,
  inverter_charger: 1,
  battery: 2,
  solar_controller: 3,
  dc_system: 4,
  generator: 5,
}

function cardFor(entity: EntitySchema) {
  switch (entity.device_type) {
    case "power_system":
      return <PowerFlowCard key={entity.entity_id} entity={entity} />
    case "inverter_charger":
      return <InverterChargerCard key={entity.entity_id} entity={entity} />
    case "battery":
      return <BatteryCard key={entity.entity_id} entity={entity} />
    case "solar_controller":
      return <SolarCard key={entity.entity_id} entity={entity} />
    case "generator":
      return <GeneratorCard key={entity.entity_id} entity={entity} />
    case "dc_system":
      return <DcLoadsCard key={entity.entity_id} entity={entity} />
    default:
      return null
  }
}

export function PowerSection({
  entities,
  showTitle = true,
}: Readonly<{ entities: EntitySchema[]; showTitle?: boolean }>) {
  const powerEntities = entities
    .filter((entity) => POWER_DEVICE_TYPES.has(entity.device_type))
    .sort(
      (a, b) => (CARD_ORDER[a.device_type] ?? 9) - (CARD_ORDER[b.device_type] ?? 9)
    )

  if (powerEntities.length === 0) return null

  return (
    <div className="space-y-3">
      {showTitle && (
        <Link
          to="/power"
          className="group flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          Power
          <IconChevronRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </Link>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {powerEntities.map(cardFor)}
      </div>
    </div>
  )
}
