/**
 * System — app/service status, CAN interface telemetry, and log stream.
 *
 * Replaces the old System Status, Health Dashboard, Performance Analytics
 * and Analytics Dashboard pages with one honest, tabbed page:
 *
 *  - Status:  GET /api/v1/system/services + /api/v1/system/components/health
 *             + /api/v1/system/info + /api/v1/system/status (version/env)
 *  - CAN Bus: GET /api/v1/networks/status (real HOF-001/002/011 telemetry)
 *  - Logs:    WS /ws/logs via the existing log-viewer, with an explicit
 *             "streaming unavailable" state instead of an endless spinner.
 *
 * /api/v1/system/events is NOT bound (sample data per design doc).
 * No number is rendered that the backend doesn't provide — nulls are "—".
 */

import {
  IconAlertTriangle,
  IconPlugConnectedX,
  IconWifi,
} from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"

import { API_BASE, apiGet } from "@/api/client"
import type { NetworkSummarySchema } from "@/api/types/domains"
import { LogList } from "@/components/log-viewer/LogList"
import { LogViewerProvider } from "@/components/log-viewer/log-viewer-context"
import { LogToolbar } from "@/components/log-viewer/LogToolbar"
import { useLogViewer } from "@/components/log-viewer/useLogViewer"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { networksStatusQueryKey } from "@/contexts/coach-connection-context"
import { cn } from "@/lib/utils"

//
// ===== Wire types (match backend /api/v1/system responses) =====
//

interface IServiceInfo {
  name: string
  status: string
  enabled: boolean
  last_check: number
}

interface IComponentHealthInfo {
  id: string
  name: string
  status: string
  message: string
  category: string
  last_checked: number
  guardrail_tier: string | null
}

interface IComponentsHealthResponse {
  components: IComponentHealthInfo[]
}

interface ISystemInfo {
  hostname: string
  platform: string
  architecture: string
  python_version: string
  uptime_seconds: number
  timestamp: number
}

/** /api/v1/system/status — used only for the truthful version/environment block. */
interface ISystemStatusResponse {
  service?: {
    name?: string
    version?: string
    environment?: string
  }
}

//
// ===== Helpers =====
//

function titleCase(value: string): string {
  return value
    .split(/[_\s]+/)
    .map((word) => (word ? word[0]?.toUpperCase() + word.slice(1) : word))
    .join(" ")
}

function statusBadge(status: string) {
  const normalized = status.toLowerCase()
  if (["healthy", "ok", "pass", "operational"].includes(normalized)) {
    return (
      <Badge
        variant="outline"
        className="border-green-300 text-green-700 dark:border-green-800 dark:text-green-400"
      >
        {titleCase(status)}
      </Badge>
    )
  }
  if (["degraded", "warning", "warn"].includes(normalized)) {
    return (
      <Badge
        variant="outline"
        className="border-amber-300 text-amber-700 dark:border-amber-800 dark:text-amber-400"
      >
        {titleCase(status)}
      </Badge>
    )
  }
  if (["failed", "critical", "error", "unhealthy"].includes(normalized)) {
    return (
      <Badge
        variant="outline"
        className="border-red-300 text-red-700 dark:border-red-800 dark:text-red-400"
      >
        {titleCase(status)}
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="text-muted-foreground">
      {titleCase(status)}
    </Badge>
  )
}

const HEALTHY_STATUSES = new Set(["healthy", "ok", "pass", "operational"])

/**
 * Humanize an uptime duration. The backend currently reports an epoch
 * timestamp in uptime_seconds (known backend bug) — values that large are
 * not a real uptime, so render "—" rather than a fabricated "56 years".
 */
function formatUptime(seconds: number | null | undefined): string {
  if (
    seconds === null ||
    seconds === undefined ||
    !Number.isFinite(seconds) ||
    seconds < 0 ||
    seconds > 10 * 365 * 24 * 3600
  ) {
    return "—"
  }
  const days = Math.floor(seconds / 86_400)
  const hours = Math.floor((seconds % 86_400) / 3_600)
  const minutes = Math.floor((seconds % 3_600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m`
  return `${Math.floor(seconds)}s`
}

/** Relative time from an ISO timestamp — never raw seconds. */
function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  const deltaMs = Date.now() - date.getTime()
  if (deltaMs < 0) return "just now"
  const deltaSec = Math.floor(deltaMs / 1000)
  if (deltaSec < 60) return `${deltaSec}s ago`
  const deltaMin = Math.floor(deltaSec / 60)
  if (deltaMin < 60) return `${deltaMin}m ago`
  const deltaHr = Math.floor(deltaMin / 60)
  if (deltaHr < 24) return `${deltaHr}h ago`
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  return `${date.toLocaleDateString()} ${time}`
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—"
  return value.toLocaleString()
}

function formatBitrate(bitsPerSecond: number | null | undefined): string {
  if (bitsPerSecond === null || bitsPerSecond === undefined || !Number.isFinite(bitsPerSecond)) {
    return "—"
  }
  if (bitsPerSecond >= 1_000_000) return `${(bitsPerSecond / 1_000_000).toLocaleString()} Mbit/s`
  if (bitsPerSecond >= 1_000) return `${(bitsPerSecond / 1_000).toLocaleString()} kbit/s`
  return `${bitsPerSecond.toLocaleString()} bit/s`
}

//
// ===== Status tab =====
//

function ServicesCard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["system", "services"],
    queryFn: () => apiGet<IServiceInfo[]>("/api/v1/system/services"),
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
  })

  const services = data ?? []
  const healthyCount = services.filter((service) =>
    HEALTHY_STATUSES.has(service.status.toLowerCase())
  ).length

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Services</CardTitle>
        {services.length > 0 && (
          <CardDescription>
            {healthyCount} of {services.length} healthy
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-32" />}
        {error && (
          <p className="text-sm text-muted-foreground">
            Couldn&apos;t load services{error instanceof Error ? ` — ${error.message}` : ""}.
          </p>
        )}
        {!isLoading && !error && services.length === 0 && (
          <p className="text-sm text-muted-foreground">No services reported by the backend.</p>
        )}
        {!isLoading && !error && services.length > 0 && (
          <div className="divide-y">
            {services.map((service) => (
              <div key={service.name} className="flex items-center justify-between gap-2 py-2">
                <span className="text-sm font-medium">{titleCase(service.name)}</span>
                <div className="flex items-center gap-2">
                  {!service.enabled && (
                    <Badge variant="secondary" className="text-xs">
                      disabled
                    </Badge>
                  )}
                  {statusBadge(service.status)}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ComponentHealthCard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["system", "components-health"],
    queryFn: () => apiGet<IComponentsHealthResponse>("/api/v1/system/components/health"),
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
  })

  const components = data?.components ?? []
  const healthyCount = components.filter((component) =>
    HEALTHY_STATUSES.has(component.status.toLowerCase())
  ).length

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Component health</CardTitle>
        {components.length > 0 && (
          <CardDescription>
            {healthyCount} of {components.length} healthy
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-32" />}
        {error && (
          <p className="text-sm text-muted-foreground">
            Couldn&apos;t load component health{error instanceof Error ? ` — ${error.message}` : ""}.
          </p>
        )}
        {!isLoading && !error && components.length === 0 && (
          <p className="text-sm text-muted-foreground">No components reported by the backend.</p>
        )}
        {!isLoading && !error && components.length > 0 && (
          <div className="divide-y">
            {components.map((component) => (
              <div key={component.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{component.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {titleCase(component.category)} · {component.message}
                  </p>
                </div>
                {statusBadge(component.status)}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/** Platform label with architecture suffix, e.g. "Linux (x86_64)". */
function formatPlatform(info: ISystemInfo | undefined): string {
  if (!info) return "—"
  const arch = info.architecture ? ` (${info.architecture})` : ""
  return `${info.platform}${arch}`
}

/** Summary rows for the System Info card, derived from the info + status queries. */
function buildSystemInfoRows(
  info: ISystemInfo | undefined,
  service: ISystemStatusResponse["service"]
): { label: string; value: string }[] {
  return [
    { label: "Hostname", value: info?.hostname ?? "—" },
    { label: "Platform", value: formatPlatform(info) },
    { label: "Uptime", value: formatUptime(info?.uptime_seconds) },
    { label: "App version", value: service?.version ?? "—" },
    { label: "Environment", value: service?.environment ?? "—" },
  ]
}

/** Loading skeleton, error message, or the info row list — whichever applies. */
function SystemInfoCardContent({
  isLoading,
  error,
  rows,
}: Readonly<{
  isLoading: boolean
  error: unknown
  rows: { label: string; value: string }[]
}>) {
  if (isLoading) return <Skeleton className="h-32" />
  if (error) {
    return (
      <p className="text-sm text-muted-foreground">
        Couldn&apos;t load system info
        {error instanceof Error ? ` — ${error.message}` : ""}.
      </p>
    )
  }
  return (
    <dl className="divide-y">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center justify-between gap-2 py-2">
          <dt className="text-sm text-muted-foreground">{row.label}</dt>
          <dd className="text-sm font-medium">{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function SystemInfoCard() {
  const infoQuery = useQuery({
    queryKey: ["system", "info"],
    queryFn: () => apiGet<ISystemInfo>("/api/v1/system/info"),
    staleTime: 60_000,
    retry: 1,
  })
  const statusQuery = useQuery({
    queryKey: ["system", "status"],
    queryFn: () => apiGet<ISystemStatusResponse>("/api/v1/system/status"),
    staleTime: 60_000,
    retry: 1,
  })

  const rows = buildSystemInfoRows(infoQuery.data, statusQuery.data?.service)

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">System info</CardTitle>
      </CardHeader>
      <CardContent>
        <SystemInfoCardContent
          isLoading={infoQuery.isLoading}
          error={infoQuery.error}
          rows={rows}
        />
      </CardContent>
    </Card>
  )
}

function StatusTab() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
      <ServicesCard />
      <ComponentHealthCard />
      <SystemInfoCard />
    </div>
  )
}

//
// ===== CAN Bus tab =====
//

function canServiceStatus(healthy: boolean | undefined): string {
  if (healthy === true) return "healthy"
  if (healthy === false) return "unhealthy"
  return "unknown"
}

type CanInterface = NetworkSummarySchema["interfaces"][number]

/** One row of the CAN interfaces table. */
function CanInterfaceRow({ iface }: Readonly<{ iface: CanInterface }>) {
  return (
    <TableRow key={`${iface.logical_name}-${iface.physical_interface}`}>
      <TableCell>
        <span className="font-medium">{iface.logical_name}</span>{" "}
        <span className="text-xs text-muted-foreground">({iface.physical_interface})</span>
      </TableCell>
      <TableCell>{iface.state ? statusBadge(iface.state) : <span>—</span>}</TableCell>
      <TableCell>{formatBitrate(iface.bitrate)}</TableCell>
      <TableCell className="text-right tabular-nums">
        {iface.message_rate !== null && iface.message_rate !== undefined
          ? `${iface.message_rate.toFixed(1)}/s`
          : "—"}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {iface.bus_load_percent !== null && iface.bus_load_percent !== undefined
          ? `${iface.bus_load_percent.toFixed(1)}%`
          : "—"}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {formatNumber(iface.rx_packets)} / {formatNumber(iface.tx_packets)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {formatNumber(iface.rx_errors)} / {formatNumber(iface.tx_errors)} /{" "}
        {formatNumber(iface.bus_errors)}
      </TableCell>
      <TableCell
        className={cn("whitespace-nowrap text-sm", !iface.last_activity && "text-muted-foreground")}
      >
        {iface.last_activity ? (
          formatRelative(iface.last_activity)
        ) : (
          <span className="flex items-center gap-1">
            <IconAlertTriangle className="size-3.5 text-amber-600 dark:text-amber-400" />
            no traffic observed
          </span>
        )}
      </TableCell>
    </TableRow>
  )
}

/** Loading skeleton, error, empty state, or the interfaces table — whichever applies. */
function CanInterfacesCardContent({
  isLoading,
  error,
  interfaces,
}: Readonly<{
  isLoading: boolean
  error: unknown
  interfaces: CanInterface[]
}>) {
  if (isLoading) return <Skeleton className="h-40" />
  if (error) {
    return (
      <p className="text-sm text-muted-foreground">
        Couldn&apos;t load network status{error instanceof Error ? ` — ${error.message}` : ""}.
      </p>
    )
  }
  if (interfaces.length === 0) {
    return <p className="text-sm text-muted-foreground">No CAN interfaces are configured.</p>
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Interface</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Bitrate</TableHead>
            <TableHead className="text-right">Msg rate</TableHead>
            <TableHead className="text-right">Bus load</TableHead>
            <TableHead className="text-right">RX / TX</TableHead>
            <TableHead className="text-right">Errors (rx/tx/bus)</TableHead>
            <TableHead>Last activity</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {interfaces.map((iface) => (
            <CanInterfaceRow key={`${iface.logical_name}-${iface.physical_interface}`} iface={iface} />
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

interface ICanServiceHealth {
  healthy?: boolean
  running?: boolean
  mode?: string
  decoders_loaded?: number
  device_mappings?: number
}

/** CAN service health summary card — status, mode, decoders, device mappings. */
function CanServiceCard({ serviceHealth }: Readonly<{ serviceHealth: ICanServiceHealth }>) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">CAN service</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-3">
        <div>
          <p className="text-xs text-muted-foreground">Status</p>
          <div className="pt-1">{statusBadge(canServiceStatus(serviceHealth.healthy))}</div>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Mode</p>
          <p className="text-sm font-medium">{serviceHealth.mode ?? "—"}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Decoders loaded</p>
          <p className="text-sm font-medium tabular-nums">
            {formatNumber(serviceHealth.decoders_loaded)}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Device mappings</p>
          <p className="text-sm font-medium tabular-nums">
            {formatNumber(serviceHealth.device_mappings)}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

function CanBusTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: networksStatusQueryKey,
    queryFn: () => apiGet<NetworkSummarySchema>("/api/v1/networks/status"),
    refetchInterval: 15_000,
    staleTime: 5_000,
    retry: 1,
  })

  const interfaces = data?.interfaces ?? []
  const serviceHealth = data?.can_service_health as ICanServiceHealth | undefined

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">CAN interfaces</CardTitle>
          <CardDescription>
            Per-interface SocketCAN telemetry. &quot;—&quot; means the value is not reported on this
            platform.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CanInterfacesCardContent isLoading={isLoading} error={error} interfaces={interfaces} />
        </CardContent>
      </Card>

      {serviceHealth && <CanServiceCard serviceHealth={serviceHealth} />}
    </div>
  )
}

//
// ===== Logs tab =====
//

/**
 * Body of the log stream with explicit connection states: when the log
 * WebSocket is down, say so — never an endless "Connecting…" spinner.
 */
function LogStreamBody() {
  const { logs, mode, connectionStatus, reconnect } = useLogViewer()

  if (mode === "live") {
    if (connectionStatus === "error" || connectionStatus === "disconnected") {
      return (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <IconPlugConnectedX className="size-8 text-destructive" />
          <div>
            <p className="text-sm font-medium">Log streaming unavailable</p>
            <p className="text-sm text-muted-foreground">
              WebSocket disconnected — live log entries cannot be received.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={reconnect}>
            Reconnect
          </Button>
        </div>
      )
    }
    if (connectionStatus === "connecting") {
      return (
        <div className="flex flex-col items-center gap-2 py-12 text-center">
          <IconWifi className="size-8 animate-pulse text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Connecting to the log stream…</p>
        </div>
      )
    }
    if (logs.length === 0) {
      return (
        <div className="flex flex-col items-center gap-2 py-12 text-center">
          <IconWifi className="size-8 text-green-600 dark:text-green-400" />
          <p className="text-sm font-medium">Connected — waiting for log entries</p>
          <p className="text-sm text-muted-foreground">
            The stream is live; entries will appear as the backend logs them.
          </p>
        </div>
      )
    }
  }

  return <LogList />
}

function LogsTab() {
  return (
    <Card className="overflow-hidden">
      <div className="flex h-[36rem] flex-col">
        <LogViewerProvider websocketUrl="/ws/logs" apiEndpoint={`${API_BASE}/logs`}>
          <LogToolbar />
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <LogStreamBody />
          </div>
        </LogViewerProvider>
      </div>
    </Card>
  )
}

//
// ===== Page =====
//

export default function SystemPage() {
  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <Tabs defaultValue="status">
        <TabsList>
          <TabsTrigger value="status">Status</TabsTrigger>
          <TabsTrigger value="canbus">CAN Bus</TabsTrigger>
          <TabsTrigger value="logs">Logs</TabsTrigger>
        </TabsList>
        <TabsContent value="status" className="mt-4">
          <StatusTab />
        </TabsContent>
        <TabsContent value="canbus" className="mt-4">
          <CanBusTab />
        </TabsContent>
        <TabsContent value="logs" className="mt-4">
          <LogsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
