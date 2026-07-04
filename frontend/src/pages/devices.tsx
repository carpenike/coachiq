/**
 * Devices — all entities in one filterable table (replaces "Multi-Protocol Entities").
 *
 * Columns: Name, Type, Zone, Protocol, State, Last updated, Available.
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

//
// ===== Helpers =====
//

const ALL = "__all__"

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
 * Derived capabilities. The v1 entity schema exposes no capabilities list
 * (contract gap) — these are inferred from device_type and observed state.
 */
function derivedCapabilities(entity: EntitySchema): string[] {
  const capabilities: string[] = []
  const state = entity.state ?? {}
  if (isControllable(entity)) capabilities.push("on/off")
  if (
    entity.device_type === "light" &&
    (typeof state.operating_status === "number" || typeof state.brightness === "number")
  ) {
    capabilities.push("dimmable")
  }
  return capabilities
}

function isControllable(entity: EntitySchema): boolean {
  return ["light", "switch", "fan", "lock"].includes(entity.device_type)
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
      {relativeTime(context.row.original.last_updated)}
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
      header: "Last updated",
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
// ===== Detail sheet =====
//

interface DeviceDetailSheetProps {
  readonly entity: EntitySchema | null
  readonly config?: ICoachConfig
  readonly onClose: () => void
}

function DeviceDetailSheet({ entity, config, onClose }: DeviceDetailSheetProps) {
  const { coach, reason } = useCoachConnection()
  const control = useControlEntity()

  if (!entity) return null

  const isAvailable = entity.available !== false
  const controlsDisabled = coach !== "LIVE" || !isAvailable
  const disabledReason = controlsDisabledReason(isAvailable, coach, reason)
  const capabilities = derivedCapabilities(entity)
  const stateEntries = Object.entries(entity.state ?? {})

  const sendCommand = (command: Parameters<typeof control.mutate>[0]["command"]) => {
    control.mutate(
      { entityId: entity.entity_id, command },
      {
        onSuccess: (result) => reportCommandResult(result, entity.name),
        onError: (error) => reportCommandError(error, entity.name),
      }
    )
  }

  const controlButtons = (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={controlsDisabled || control.isPending}
        onClick={() => sendCommand({ command: "set", state: true })}
      >
        Turn On
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={controlsDisabled || control.isPending}
        onClick={() => sendCommand({ command: "set", state: false })}
      >
        Turn Off
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={controlsDisabled || control.isPending}
        onClick={() => sendCommand({ command: "toggle" })}
      >
        Toggle
      </Button>
    </div>
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
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Type</dt>
            <dd>{titleCase(entity.device_type)}</dd>
            <dt className="text-muted-foreground">Protocol</dt>
            <dd className="uppercase">{entity.protocol}</dd>
            <dt className="text-muted-foreground">Zone</dt>
            <dd>{zoneDisplayName(zoneIdForEntity(entity), config)}</dd>
            <dt className="text-muted-foreground">Available</dt>
            <dd>{isAvailable ? "Yes" : "No — not responding"}</dd>
            <dt className="text-muted-foreground">Last updated</dt>
            <dd>{relativeTime(entity.last_updated)}</dd>
            <dt className="text-muted-foreground">Capabilities</dt>
            <dd>{capabilities.length > 0 ? capabilities.join(", ") : "—"}</dd>
          </dl>

          {/* Controls */}
          {isControllable(entity) && (
            <div className="space-y-2">
              <h3 className="text-sm font-medium">Controls</h3>
              {controlsDisabled ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-block">{controlButtons}</span>
                  </TooltipTrigger>
                  <TooltipContent>{disabledReason}</TooltipContent>
                </Tooltip>
              ) : (
                controlButtons
              )}
            </div>
          )}

          {/* Full state dict */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium">State</h3>
            {stateEntries.length === 0 ? (
              <p className="text-sm text-muted-foreground">No state reported.</p>
            ) : (
              <div className="rounded-md border">
                {stateEntries.map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-start justify-between gap-4 border-b px-3 py-2 text-sm last:border-b-0"
                  >
                    <span className="font-mono text-xs text-muted-foreground">{key}</span>
                    <span className="break-all text-right font-mono text-xs">
                      {typeof value === "object" && value !== null
                        ? JSON.stringify(value)
                        : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
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
  const typeOptions = useMemo(
    () =>
      [...new Set(entities.map((entity) => entity.device_type))].sort((a, b) =>
        a.localeCompare(b)
      ),
    [entities]
  )
  const protocolOptions = useMemo(() => {
    const counts = new Map<string, number>()
    for (const entity of entities) {
      counts.set(entity.protocol, (counts.get(entity.protocol) ?? 0) + 1)
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [entities])

  // Zone options: coach config areas first (config order), then any zone
  // observed on entities that the config does not declare.
  const zoneOptions = useMemo(() => {
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
  }, [config, entities])

  const filteredEntities = useMemo(() => {
    const query = search.trim().toLowerCase()
    return entities.filter((entity) => {
      if (typeFilter !== ALL && entity.device_type !== typeFilter) return false
      if (protocolFilter !== ALL && entity.protocol !== protocolFilter) return false
      if (zoneFilter !== ALL && zoneIdForEntity(entity) !== zoneFilter) return false
      return (
        !query ||
        entity.name.toLowerCase().includes(query) ||
        entity.entity_id.toLowerCase().includes(query)
      )
    })
  }, [entities, search, typeFilter, zoneFilter, protocolFilter])

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
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <div className="relative flex-1 lg:max-w-xs">
          <IconSearch className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search devices…"
            className="pl-8"
            aria-label="Search devices"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-36" aria-label="Filter by type">
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
          <Select value={zoneFilter} onValueChange={setZoneFilter}>
            <SelectTrigger className="w-44" aria-label="Filter by zone">
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
          <Select value={protocolFilter} onValueChange={setProtocolFilter}>
            <SelectTrigger className="w-40" aria-label="Filter by protocol">
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
            <Button variant="ghost" size="sm" onClick={clearFilters} className="gap-1">
              <IconX className="size-4" />
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      )}

      {/* Error */}
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

      {/* Table */}
      {!isLoading && !error && (
        <>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead
                        key={header.id}
                        className={
                          header.column.getCanSort() ? "cursor-pointer select-none" : undefined
                        }
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {{ asc: " ↑", desc: " ↓" }[header.column.getIsSorted() as string] ?? ""}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      <p className="text-sm text-muted-foreground">
                        {entities.length === 0
                          ? "No entities are mapped for this coach."
                          : "No devices match the current filters."}
                      </p>
                    </TableCell>
                  </TableRow>
                ) : (
                  table.getRowModel().rows.map((row) => (
                    <TableRow
                      key={row.original.entity_id}
                      className="cursor-pointer"
                      onClick={() => setSelectedEntityId(row.original.entity_id)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <p className="text-xs text-muted-foreground">
            {deviceCountLabel(filteredEntities.length, entities.length)}
            {entityCollection?.has_next &&
              ` — showing the first ${entities.length} of ${entityCollection.total_count}`}
          </p>
        </>
      )}

      <DeviceDetailSheet
        entity={selectedEntity}
        {...(config ? { config } : {})}
        onClose={() => setSelectedEntityId(null)}
      />
    </div>
  )
}
