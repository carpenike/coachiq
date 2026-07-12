/**
 * Devices — all entities in one filterable table (replaces "Multi-Protocol Entities").
 *
 * Columns: Name, Type, Zone, Protocol, State, Last changed, Available.
 * Filter options are derived from the coach config (zones) and the actual
 * entity list (types, protocols) — no fabricated protocol-health numbers.
 * Row click opens a detail sheet with the full state dict and controls
 * (same toast feedback contract as Home/Lights).
 */

import { IconSearch, IconX } from "@tabler/icons-react"
import type { CellContext, ColumnDef, SortingState } from "@tanstack/react-table"
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { formatDistanceToNow } from "date-fns"
import { useMemo, useState } from "react"

import type { EntitySchema, OperationResultSchema } from "@/api/types/domains"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useCoachConnection, type CoachState } from "@/contexts/coach-connection-context"
import { toast } from "@/hooks/use-toast"
import {
  useCoachConfig,
  zoneDisplayName,
  zoneIdForEntity,
  type ICoachConfig,
} from "@/hooks/useCoachConfig"
import { useControlEntity, useEntities } from "@/hooks/useEntities"
import { entitySupportsPowerControl, getEntityCapabilityPolicy } from "@/lib/entity-capabilities"

//
// ===== Helpers =====
//

const ALL = "__all__"

/** Stable keys for the loading-skeleton placeholder rows (no entity data exists yet to key on). */
const LOADING_SKELETON_ROW_IDS = [
  "skeleton-row-1",
  "skeleton-row-2",
  "skeleton-row-3",
  "skeleton-row-4",
  "skeleton-row-5",
  "skeleton-row-6",
  "skeleton-row-7",
  "skeleton-row-8",
]

function titleCase(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

function relativeTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "unknown"
  return formatDistanceToNow(date, { addSuffix: true })
}

/** On/off verdict from real state only; null when the state carries no on/off signal. */
function entityOnOff(entity: EntitySchema): boolean | null {
  const state = entity.state ?? {}
  if (typeof state.state === "string") {
    const value = state.state.toLowerCase()
    if (["on", "true", "active"].includes(value)) return true
    if (["off", "false", "inactive"].includes(value)) return false
  }
  if (typeof state.operating_status === "number") {
    return state.operating_status > 0
  }
  return null
}

function StateBadge({ entity }: { readonly entity: EntitySchema }) {
  if (entity.available === false) {
    return (
      <Badge variant="outline" className="gap-1 text-xs text-muted-foreground">
        <span className="size-1.5 rounded-full bg-red-500" aria-hidden />
        offline
      </Badge>
    )
  }
  const onOff = entityOnOff(entity)
  if (onOff === null) {
    return <span className="text-xs text-muted-foreground">—</span>
  }
  return (
    <Badge
      variant={onOff ? "default" : "secondary"}
      className={
        onOff
          ? "bg-yellow-100 text-xs text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
          : "text-xs"
      }
    >
      {onOff ? "On" : "Off"}
    </Badge>
  )
}

/**
 * Human-readable capabilities from the canonical entity contract.
 */
function derivedCapabilities(entity: EntitySchema): string[] {
  return getEntityCapabilityPolicy(entity).rawCapabilities.map(titleCase)
}

function isControllable(entity: EntitySchema): boolean {
  // Only `light` has a working generic power-control path. The backend's
  // control_entity dispatches light / climate / ac_load, but climate and
  // ac_load are parameterized and live on their own pages — the generic
  // power switch here only fits a light. switch / fan / lock have no
  // service-layer handler, so rendering their buttons sent commands the
  // backend rejects (e.g. the read-only entrance door lock 500'd on press).
  // Re-add a type here only once control_entity actually dispatches it.
  return entity.device_type === "light" && entitySupportsPowerControl(entity)
}

function stateChangedAt(entity: EntitySchema): string {
  return entity.state_changed_at ?? entity.last_updated ?? ""
}

//
// ===== Table column cell renderers (module scope — not recreated on render) =====
//

type EntityCellContext = Readonly<CellContext<EntitySchema, unknown>>

function NameCell(context: EntityCellContext) {
  return <span className="font-medium">{context.row.original.name}</span>
}

function ProtocolCell(context: EntityCellContext) {
  return <span className="uppercase text-muted-foreground">{context.row.original.protocol}</span>
}

function StateCell(context: EntityCellContext) {
  return <StateBadge entity={context.row.original} />
}

function LastUpdatedCell(context: EntityCellContext) {
  return (
    <span className="text-muted-foreground">
      {relativeTime(stateChangedAt(context.row.original))}
    </span>
  )
}

function AvailableCell(context: EntityCellContext) {
  const available = context.row.original.available !== false
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={`size-2 rounded-full ${available ? "bg-green-500" : "bg-red-500"}`}
        aria-hidden
      />
      <span className="text-xs text-muted-foreground">{available ? "Yes" : "No"}</span>
    </span>
  )
}

/** Zone label for a table row: config display name, or "Unassigned" when derived. */
function zoneLabelForEntity(entity: EntitySchema, config?: ICoachConfig): string {
  const zoneId = zoneIdForEntity(entity)
  return zoneId === "other" ? "Unassigned" : zoneDisplayName(zoneId, config)
}

/**
 * Build the devices table column defs. A factory (rather than a component
 * defined during render) because the "zone" column's accessor needs the
 * coach config — cell renderers themselves stay static, module-level
 * components so TanStack never sees a new component type per render.
 */
function buildDeviceColumns(config: ICoachConfig | undefined): ColumnDef<EntitySchema>[] {
  return [
    {
      accessorKey: "name",
      header: "Name",
      cell: NameCell,
    },
    {
      accessorKey: "device_type",
      header: "Type",
      cell: ({ row }) => titleCase(row.original.device_type),
    },
    {
      id: "zone",
      header: "Zone",
      accessorFn: (entity) => zoneLabelForEntity(entity, config),
    },
    {
      accessorKey: "protocol",
      header: "Protocol",
      cell: ProtocolCell,
    },
    {
      id: "state",
      header: "State",
      enableSorting: false,
      cell: StateCell,
    },
    {
      accessorKey: "last_updated",
      header: "Last changed",
      cell: LastUpdatedCell,
    },
    {
      id: "available",
      header: "Available",
      accessorFn: (entity) => entity.available !== false,
      cell: AvailableCell,
    },
  ]
}

/** Human-readable reason controls are disabled, or "" when they are enabled. */
function controlsDisabledReason(isAvailable: boolean, coach: CoachState, reason: string): string {
  if (!isAvailable) return "Device is not responding on the CAN bus"
  if (coach === "OFFLINE") return "Can't reach the coach — controls disabled"
  return `Coach data is not live — ${reason}`
}

/** "3 devices" / "1 device" / "2 of 5 devices" depending on active filtering. */
function deviceCountLabel(filteredCount: number, totalCount: number): string {
  if (filteredCount !== totalCount) {
    return `${filteredCount} of ${totalCount} devices`
  }
  return `${totalCount} ${totalCount === 1 ? "device" : "devices"}`
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
// ===== Detail sheet =====
//

interface IDeviceDetailSheetProps {
  readonly entity: EntitySchema | null
  readonly config?: ICoachConfig
  readonly onClose: () => void
}

/** Persistent power-state control for a controllable device. */
function devicePowerStateLabel(checked: boolean | null): string {
  if (checked === null) return "State unavailable"
  return checked ? "On" : "Off"
}

export function DevicePowerControl({
  disabled,
  checked,
  entityName,
  onCheckedChange,
}: Readonly<{
  disabled: boolean
  checked: boolean | null
  entityName: string
  onCheckedChange: (checked: boolean) => void
}>) {
  return (
    <div className="flex min-h-11 items-center justify-between gap-3 rounded-md border px-3">
      <div>
        <p className="text-sm font-medium">Power</p>
        <p className="text-xs text-muted-foreground">{devicePowerStateLabel(checked)}</p>
      </div>
      <Switch
        checked={checked ?? false}
        disabled={disabled || checked === null}
        onCheckedChange={onCheckedChange}
        aria-label={`${entityName} power`}
      />
    </div>
  )
}

/** Summary fact list (type, protocol, zone, availability, etc.) for the detail sheet. */
function DeviceSummaryFacts({
  entity,
  config,
  isAvailable,
  capabilities,
}: Readonly<{
  entity: EntitySchema
  config: ICoachConfig | undefined
  isAvailable: boolean
  capabilities: string[]
}>) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      <dt className="text-muted-foreground">Type</dt>
      <dd>{titleCase(entity.device_type)}</dd>
      <dt className="text-muted-foreground">Protocol</dt>
      <dd className="uppercase">{entity.protocol}</dd>
      <dt className="text-muted-foreground">Zone</dt>
      <dd>{zoneDisplayName(zoneIdForEntity(entity), config)}</dd>
      <dt className="text-muted-foreground">Available</dt>
      <dd>{isAvailable ? "Yes" : "No — not responding"}</dd>
      <dt className="text-muted-foreground">Last changed</dt>
      <dd>{relativeTime(stateChangedAt(entity))}</dd>
      <dt className="text-muted-foreground">Capabilities</dt>
      <dd>{capabilities.length > 0 ? capabilities.join(", ") : "—"}</dd>
    </dl>
  )
}

/** Full state dict rendered as a key/value list, or an empty-state message. */
function DeviceStateList({ stateEntries }: Readonly<{ stateEntries: [string, unknown][] }>) {
  if (stateEntries.length === 0) {
    return <p className="text-sm text-muted-foreground">No state reported.</p>
  }
  return (
    <div className="rounded-md border">
      {stateEntries.map(([key, value]) => (
        <div
          key={key}
          className="flex items-start justify-between gap-4 border-b px-3 py-2 text-sm last:border-b-0"
        >
          <span className="font-mono text-xs text-muted-foreground">{key}</span>
          <span className="break-all text-right font-mono text-xs">
            {typeof value === "object" && value !== null ? JSON.stringify(value) : String(value)}
          </span>
        </div>
      ))}
    </div>
  )
}

function DeviceDetailSheet({ entity, config, onClose }: IDeviceDetailSheetProps) {
  const { coach, reason } = useCoachConnection()
  const control = useControlEntity()

  if (!entity) return null

  const isAvailable = entity.available !== false
  const controlsDisabled = coach !== "LIVE" || !isAvailable
  const disabledReason = controlsDisabledReason(isAvailable, coach, reason)
  const capabilities = derivedCapabilities(entity)
  const stateEntries = Object.entries(entity.state ?? {})
  const powerState = entityOnOff(entity)

  const sendCommand = (command: Parameters<typeof control.mutate>[0]["command"]) => {
    control.mutate(
      { entityId: entity.entity_id, command },
      {
        onSuccess: (result) => reportCommandResult(result, entity.name),
        onError: (error) => reportCommandError(error, entity.name),
      }
    )
  }

  const controlsAreDisabled = controlsDisabled || powerState === null
  const powerDisabledReason =
    powerState === null ? "Device has not reported a power state" : disabledReason
  const powerControl = (
    <DevicePowerControl
      disabled={controlsAreDisabled}
      checked={powerState}
      entityName={entity.name}
      onCheckedChange={(checked) => sendCommand({ command: "set", state: checked })}
    />
  )

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{entity.name}</SheetTitle>
          <SheetDescription className="font-mono text-xs">{entity.entity_id}</SheetDescription>
        </SheetHeader>

        <div className="space-y-6 px-4 pb-6">
          {/* Summary facts */}
          <DeviceSummaryFacts
            entity={entity}
            config={config}
            isAvailable={isAvailable}
            capabilities={capabilities}
          />

          {/* Controls */}
          {isControllable(entity) && (
            <div className="space-y-2">
              <h3 className="text-sm font-medium">Controls</h3>
              {controlsDisabled || powerState === null ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="block">{powerControl}</span>
                  </TooltipTrigger>
                  <TooltipContent>{powerDisabledReason}</TooltipContent>
                </Tooltip>
              ) : (
                powerControl
              )}
            </div>
          )}

          {/* Full state dict */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium">State</h3>
            <DeviceStateList stateEntries={stateEntries} />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

//
// ===== Filter bar =====
//

interface IDeviceFilterBarProps {
  search: string
  onSearchChange: (value: string) => void
  typeFilter: string
  onTypeFilterChange: (value: string) => void
  typeOptions: string[]
  zoneFilter: string
  onZoneFilterChange: (value: string) => void
  zoneOptions: { value: string; label: string }[]
  protocolFilter: string
  onProtocolFilterChange: (value: string) => void
  protocolOptions: [string, number][]
  hasActiveFilters: boolean
  onClearFilters: () => void
}

/** Search input plus type/zone/protocol filter selects for the devices table. */
function DeviceFilterBar({
  search,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  typeOptions,
  zoneFilter,
  onZoneFilterChange,
  zoneOptions,
  protocolFilter,
  onProtocolFilterChange,
  protocolOptions,
  hasActiveFilters,
  onClearFilters,
}: Readonly<IDeviceFilterBarProps>) {
  return (
    <div className="app-material sticky top-(--header-height) z-30 -mx-1 flex flex-col gap-2 border-b px-1 py-2 lg:flex-row lg:items-center">
      <div className="relative flex-1 lg:max-w-xs">
        <IconSearch className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search devices…"
          className="pl-8"
          aria-label="Search devices"
        />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
        <Select value={typeFilter} onValueChange={onTypeFilterChange}>
          <SelectTrigger className="w-full sm:w-36" aria-label="Filter by type">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All types</SelectItem>
            {typeOptions.map((deviceType) => (
              <SelectItem key={deviceType} value={deviceType}>
                {titleCase(deviceType)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={zoneFilter} onValueChange={onZoneFilterChange}>
          <SelectTrigger className="w-full sm:w-44" aria-label="Filter by zone">
            <SelectValue placeholder="Zone" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All zones</SelectItem>
            {zoneOptions.map((zone) => (
              <SelectItem key={zone.value} value={zone.value}>
                {zone.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={protocolFilter} onValueChange={onProtocolFilterChange}>
          <SelectTrigger className="w-full sm:w-40" aria-label="Filter by protocol">
            <SelectValue placeholder="Protocol" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All protocols</SelectItem>
            {protocolOptions.map(([protocol, count]) => (
              <SelectItem key={protocol} value={protocol}>
                {protocol.toUpperCase()} ({count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="h-11 justify-start gap-1 sm:justify-center"
          >
            <IconX className="size-4" />
            Clear
          </Button>
        )}
      </div>
    </div>
  )
}

/** Compact device rows for narrow screens; all core status fields remain visible. */
function DeviceMobileList({
  entities,
  config,
  hasAnyEntities,
  onSelectEntity,
}: Readonly<{
  entities: EntitySchema[]
  config: ICoachConfig | undefined
  hasAnyEntities: boolean
  onSelectEntity: (entityId: string) => void
}>) {
  if (entities.length === 0) {
    return (
      <div className="rounded-md border px-4 py-10 text-center md:hidden">
        <p className="text-sm text-muted-foreground">
          {hasAnyEntities
            ? "No devices match the current filters."
            : "No entities are mapped for this coach."}
        </p>
      </div>
    )
  }

  return (
    <div className="divide-y rounded-md border md:hidden">
      {entities.map((entity) => {
        const available = entity.available !== false
        return (
          <button
            key={entity.entity_id}
            type="button"
            className="flex min-h-24 w-full flex-col gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
            onClick={() => onSelectEntity(entity.entity_id)}
          >
            <span className="flex w-full items-start justify-between gap-3">
              <span className="min-w-0">
                <span className="block truncate font-medium">{entity.name}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  {titleCase(entity.device_type)} · {zoneLabelForEntity(entity, config)}
                </span>
              </span>
              <StateBadge entity={entity} />
            </span>
            <span className="flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="uppercase">{entity.protocol}</span>
              <span>Last changed {relativeTime(stateChangedAt(entity))}</span>
              <span className="flex items-center gap-1.5">
                <span
                  className={`size-2 rounded-full ${available ? "bg-green-500" : "bg-red-500"}`}
                  aria-hidden
                />
                {available ? "Available" : "Unavailable"}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

//
// ===== Table body =====
//

/** Table header row group, rendered from the TanStack table instance. */
function DeviceTableHeader({
  table,
}: Readonly<{ table: ReturnType<typeof useReactTable<EntitySchema>> }>) {
  return (
    <TableHeader>
      {table.getHeaderGroups().map((headerGroup) => (
        <TableRow key={headerGroup.id}>
          {headerGroup.headers.map((header) => (
            <TableHead
              key={header.id}
              className={header.column.getCanSort() ? "cursor-pointer select-none" : undefined}
              onClick={header.column.getToggleSortingHandler()}
            >
              {flexRender(header.column.columnDef.header, header.getContext())}
              {{ asc: " ↑", desc: " ↓" }[header.column.getIsSorted() as string] ?? ""}
            </TableHead>
          ))}
        </TableRow>
      ))}
    </TableHeader>
  )
}

interface IDeviceTableBodyProps {
  table: ReturnType<typeof useReactTable<EntitySchema>>
  columnCount: number
  hasAnyEntities: boolean
  onSelectEntity: (entityId: string) => void
}

/** Table body: empty-state row, or one row per filtered device. */
function DeviceTableBody({
  table,
  columnCount,
  hasAnyEntities,
  onSelectEntity,
}: Readonly<IDeviceTableBodyProps>) {
  const rows = table.getRowModel().rows
  if (rows.length === 0) {
    return (
      <TableBody>
        <TableRow>
          <TableCell colSpan={columnCount} className="h-24 text-center">
            <p className="text-sm text-muted-foreground">
              {hasAnyEntities
                ? "No devices match the current filters."
                : "No entities are mapped for this coach."}
            </p>
          </TableCell>
        </TableRow>
      </TableBody>
    )
  }
  return (
    <TableBody>
      {rows.map((row) => (
        <TableRow
          key={row.original.entity_id}
          className="cursor-pointer"
          onClick={() => onSelectEntity(row.original.entity_id)}
        >
          {row.getVisibleCells().map((cell) => (
            <TableCell key={cell.id}>
              {flexRender(cell.column.columnDef.cell, cell.getContext())}
            </TableCell>
          ))}
        </TableRow>
      ))}
    </TableBody>
  )
}

//
// ===== Filter option derivation (module scope: pure functions, not recreated per render) =====
//

/** Distinct device types present in the entity list, alphabetically sorted. */
function deriveTypeOptions(entities: EntitySchema[]): string[] {
  return [...new Set(entities.map((entity) => entity.device_type))].sort((a, b) =>
    a.localeCompare(b)
  )
}

/** Distinct protocols present in the entity list, with counts, alphabetically sorted. */
function deriveProtocolOptions(entities: EntitySchema[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const entity of entities) {
    counts.set(entity.protocol, (counts.get(entity.protocol) ?? 0) + 1)
  }
  return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b))
}

/**
 * Zone filter options: coach config areas first (config order), then any
 * zone observed on entities that the config does not declare.
 */
function deriveZoneOptions(
  entities: EntitySchema[],
  config: ICoachConfig | undefined
): { value: string; label: string }[] {
  const zoneIds: string[] = []
  for (const section of ["interior", "exterior"]) {
    const area = Object.entries(config?.areas ?? {}).find(([key]) => key === section)?.[1]
    if (!area) continue
    for (const zoneKey of Object.keys(area.zones)) {
      zoneIds.push(`${section}.${zoneKey}`)
    }
  }
  for (const entity of entities) {
    const zoneId = zoneIdForEntity(entity)
    if (!zoneIds.includes(zoneId)) zoneIds.push(zoneId)
  }
  return zoneIds.map((zoneId) => ({
    value: zoneId,
    label: zoneId === "other" ? "Unassigned" : zoneDisplayName(zoneId, config),
  }))
}

interface IDeviceFilters {
  search: string
  typeFilter: string
  zoneFilter: string
  protocolFilter: string
}

/** Applies the search text and type/zone/protocol filters to the entity list. */
function filterEntities(entities: EntitySchema[], filters: IDeviceFilters): EntitySchema[] {
  const query = filters.search.trim().toLowerCase()
  return entities.filter((entity) => {
    if (filters.typeFilter !== ALL && entity.device_type !== filters.typeFilter) return false
    if (filters.protocolFilter !== ALL && entity.protocol !== filters.protocolFilter) return false
    if (filters.zoneFilter !== ALL && zoneIdForEntity(entity) !== filters.zoneFilter) return false
    return (
      !query ||
      entity.name.toLowerCase().includes(query) ||
      entity.entity_id.toLowerCase().includes(query)
    )
  })
}

interface IDevicesResultsProps {
  isLoading: boolean
  error: Error | null
  table: ReturnType<typeof useReactTable<EntitySchema>>
  columnCount: number
  entities: EntitySchema[]
  filteredEntities: EntitySchema[]
  config: ICoachConfig | undefined
  hasNext: boolean
  totalCount: number
  onSelectEntity: (entityId: string) => void
}

/** Loading skeleton, error card, or the device table + count footer — whichever applies. */
function DevicesResults({
  isLoading,
  error,
  table,
  columnCount,
  entities,
  filteredEntities,
  config,
  hasNext,
  totalCount,
  onSelectEntity,
}: Readonly<IDevicesResultsProps>) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {LOADING_SKELETON_ROW_IDS.map((rowId) => (
          <Skeleton key={rowId} className="h-10 w-full" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-destructive">Couldn&apos;t load devices</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{error.message}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <DeviceMobileList
        entities={filteredEntities}
        config={config}
        hasAnyEntities={entities.length > 0}
        onSelectEntity={onSelectEntity}
      />

      <div className="hidden overflow-x-auto rounded-md border md:block">
        <Table>
          <DeviceTableHeader table={table} />
          <DeviceTableBody
            table={table}
            columnCount={columnCount}
            hasAnyEntities={entities.length > 0}
            onSelectEntity={onSelectEntity}
          />
        </Table>
      </div>

      <p className="text-xs text-muted-foreground">
        {deviceCountLabel(filteredEntities.length, entities.length)}
        {hasNext && ` — showing the first ${entities.length} of ${totalCount}`}
      </p>
    </>
  )
}

//
// ===== Page =====
//

export default function DevicesPage() {
  const { data: config } = useCoachConfig()
  const { data: entityCollection, isLoading, error } = useEntities({ page_size: 100 })

  const [search, setSearch] = useState("")
  const [typeFilter, setTypeFilter] = useState(ALL)
  const [zoneFilter, setZoneFilter] = useState(ALL)
  const [protocolFilter, setProtocolFilter] = useState(ALL)
  const [sorting, setSorting] = useState<SortingState>([])
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null)

  const entities = useMemo(
    () => entityCollection?.entities ?? [],
    [entityCollection]
  )

  // Filter options derived from actual data (types, protocols with real counts).
  const typeOptions = useMemo(() => deriveTypeOptions(entities), [entities])
  const protocolOptions = useMemo(() => deriveProtocolOptions(entities), [entities])
  const zoneOptions = useMemo(() => deriveZoneOptions(entities, config), [config, entities])

  const filteredEntities = useMemo(
    () => filterEntities(entities, { search, typeFilter, zoneFilter, protocolFilter }),
    [entities, search, typeFilter, zoneFilter, protocolFilter]
  )

  const hasActiveFilters =
    search.trim() !== "" || typeFilter !== ALL || zoneFilter !== ALL || protocolFilter !== ALL

  const clearFilters = () => {
    setSearch("")
    setTypeFilter(ALL)
    setZoneFilter(ALL)
    setProtocolFilter(ALL)
  }

  const columns = useMemo<ColumnDef<EntitySchema>[]>(() => buildDeviceColumns(config), [config])

  const table = useReactTable({
    data: filteredEntities,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const selectedEntity =
    entities.find((entity) => entity.entity_id === selectedEntityId) ?? null

  return (
    <div className="flex-1 space-y-4 p-4 pt-6 lg:px-6">
      {/* Filters */}
      <DeviceFilterBar
        search={search}
        onSearchChange={setSearch}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        typeOptions={typeOptions}
        zoneFilter={zoneFilter}
        onZoneFilterChange={setZoneFilter}
        zoneOptions={zoneOptions}
        protocolFilter={protocolFilter}
        onProtocolFilterChange={setProtocolFilter}
        protocolOptions={protocolOptions}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
      />

      <DevicesResults
        isLoading={isLoading}
        error={error}
        table={table}
        columnCount={columns.length}
        entities={entities}
        filteredEntities={filteredEntities}
        config={config}
        hasNext={entityCollection?.has_next ?? false}
        totalCount={entityCollection?.total_count ?? 0}
        onSelectEntity={setSelectedEntityId}
      />

      <DeviceDetailSheet
        entity={selectedEntity}
        {...(config ? { config } : {})}
        onClose={() => setSelectedEntityId(null)}
      />
    </div>
  )
}
