/**
 * Diagnostics — THE single fault page.
 *
 * - DTC table from GET /api/v1/diagnostics/dtcs with severity/protocol
 *   filters and an admin-gated Resolve action.
 * - Health verdict from GET /api/v1/diagnostics/system-status, annotated
 *   honestly when the coach connection is not live.
 * - Statistics strip from GET /api/v1/diagnostics/statistics (counts +
 *   trend word only — no fabricated accuracy percentages).
 *
 * Empty states distinguish "bus is silent, faults cannot be reported"
 * from "live bus, genuinely no faults" (per docs/frontend-redesign.md).
 */

import {
  IconAlertTriangle,
  IconCircleCheck,
  IconStethoscope,
  IconVolumeOff,
} from "@tabler/icons-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { apiGet, apiPost } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
import { useAuth } from "@/contexts"
import { useCoachConnection } from "@/contexts/coach-connection"
import { toast } from "@/hooks/use-toast"
import { cn } from "@/lib/utils"

//
// ===== Wire types (match backend DiagnosticTroubleCode.to_dict()) =====
//

interface DtcRecord {
  code: number
  protocol: string
  system_type: string
  severity: string
  first_occurrence: number
  last_occurrence: number
  occurrence_count: number
  source_address: number | null
  pgn: number | null
  dgn: number | null
  description: string
  active: boolean
  intermittent: boolean
  resolved: boolean
  acknowledged: boolean
}

interface DtcCollection {
  dtcs: DtcRecord[]
  total_count: number
  active_count: number
  by_severity: Record<string, number>
  by_protocol: Record<string, number>
}

interface DiagnosticsSystemStatus {
  overall_health: string
  health_score: number
  active_systems: string[]
  degraded_systems: string[]
  last_assessment: number
}

interface DiagnosticsStatistics {
  metrics: {
    total_dtcs: number
    active_dtcs: number
    resolved_dtcs: number
    processing_rate: number
    system_health_trend: "improving" | "stable" | "degrading"
  }
}

//
// ===== Constants =====
//

const SEVERITY_OPTIONS = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "info", label: "Info" },
] as const

const PROTOCOL_OPTIONS = [
  { value: "rvc", label: "RV-C" },
  { value: "j1939", label: "J1939" },
  { value: "firefly", label: "Firefly" },
  { value: "spartan_k2", label: "Spartan K2" },
] as const

const PROTOCOL_LABELS: Record<string, string> = Object.fromEntries(
  PROTOCOL_OPTIONS.map((option) => [option.value, option.label])
)

//
// ===== Helpers =====
//

/** Backend timestamps are epoch seconds (floats). */
function formatEpoch(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) {
    return "—"
  }
  const date = new Date(seconds * 1000)
  if (Number.isNaN(date.getTime())) return "—"
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  const sameDay = new Date().toDateString() === date.toDateString()
  return sameDay ? time : `${date.toLocaleDateString()} ${time}`
}

function severityBadgeClass(severity: string): string {
  switch (severity) {
    case "critical":
      return "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300 border-red-300 dark:border-red-800"
    case "high":
      return "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300 border-orange-300 dark:border-orange-800"
    case "medium":
      return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 border-amber-300 dark:border-amber-800"
    case "low":
      return "bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300 border-slate-300 dark:border-slate-700"
    default:
      return "text-muted-foreground"
  }
}

function titleCase(value: string): string {
  return value
    .split(/[_\s]+/)
    .map((word) => (word ? word[0]?.toUpperCase() + word.slice(1) : word))
    .join(" ")
}

//
// ===== Health verdict card =====
//

function HealthVerdictCard() {
  const { coach } = useCoachConnection()
  const { data, isLoading, error } = useQuery({
    queryKey: ["diagnostics", "system-status"],
    queryFn: () => apiGet<DiagnosticsSystemStatus>("/api/v1/diagnostics/system-status"),
    refetchInterval: 45_000,
    staleTime: 30_000,
    retry: 1,
  })

  if (isLoading) return <Skeleton className="h-32" />

  if (error || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Health verdict</CardTitle>
          <CardDescription>
            Couldn't load the health assessment
            {error instanceof Error ? ` — ${error.message}` : ""}.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  // Green verdict styling requires a LIVE coach connection (honesty rule:
  // no "all good" verdict rendered from anything but live data).
  const isLive = coach === "LIVE"
  const looksHealthy = data.degraded_systems.length === 0

  return (
    <Card
      className={cn(
        isLive && looksHealthy && "border-green-300 dark:border-green-900",
        data.degraded_systems.length > 0 && "border-amber-300 dark:border-amber-900"
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Health verdict</CardTitle>
          <IconStethoscope className="size-4 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-baseline gap-3">
          <span
            className={cn(
              "text-2xl font-semibold",
              isLive && looksHealthy && "text-green-700 dark:text-green-400"
            )}
          >
            {titleCase(data.overall_health)}
          </span>
          <span className="text-sm text-muted-foreground">
            score {Math.round(data.health_score)}/100
          </span>
        </div>
        {data.degraded_systems.length > 0 && (
          <p className="text-sm text-amber-700 dark:text-amber-400">
            Degraded: {data.degraded_systems.map(titleCase).join(", ")}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {data.active_systems.length} systems reporting · assessed{" "}
          {formatEpoch(data.last_assessment)}
        </p>
        {!isLive && (
          <p className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
            <IconAlertTriangle className="size-3.5 shrink-0" />
            Based on last known data — the coach connection is not live.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

//
// ===== Statistics strip =====
//

function StatisticsStrip() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["diagnostics", "statistics"],
    queryFn: () => apiGet<DiagnosticsStatistics>("/api/v1/diagnostics/statistics"),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  })

  if (isLoading) return <Skeleton className="h-24" />

  if (error || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Statistics</CardTitle>
          <CardDescription>
            Couldn't load fault statistics
            {error instanceof Error ? ` — ${error.message}` : ""}.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const { metrics } = data
  const stats = [
    { label: "Total fault codes", value: metrics.total_dtcs },
    { label: "Active", value: metrics.active_dtcs },
    { label: "Resolved", value: metrics.resolved_dtcs },
  ]

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Statistics</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-3">
        {stats.map((stat) => (
          <div key={stat.label}>
            <p className="text-xs text-muted-foreground">{stat.label}</p>
            <p className="text-xl font-semibold tabular-nums">{stat.value}</p>
          </div>
        ))}
        <div>
          <p className="text-xs text-muted-foreground">Trend</p>
          <p className="text-xl font-medium capitalize">{metrics.system_health_trend}</p>
        </div>
      </CardContent>
    </Card>
  )
}

//
// ===== Resolve action =====
//

function ResolveButton({ dtc }: Readonly<{ dtc: DtcRecord }>) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const isAdmin = user?.role === "admin"

  const resolveMutation = useMutation({
    mutationFn: () =>
      apiPost<{ resolved: boolean }>("/api/v1/diagnostics/dtcs/resolve", {
        protocol: dtc.protocol,
        code: dtc.code,
        source_address: dtc.source_address ?? 0,
      }),
    onSuccess: (result) => {
      if (result.resolved) {
        toast({
          title: "Fault code resolved",
          description: `${PROTOCOL_LABELS[dtc.protocol] ?? dtc.protocol} code ${dtc.code} marked resolved.`,
        })
        void queryClient.invalidateQueries({ queryKey: ["diagnostics"] })
      } else {
        toast({
          variant: "destructive",
          title: "Could not resolve fault code",
          description: `The backend did not resolve ${PROTOCOL_LABELS[dtc.protocol] ?? dtc.protocol} code ${dtc.code}.`,
        })
      }
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Resolve failed",
        description: error.message,
      })
    },
  })

  const button = (
    <Button
      variant="outline"
      size="sm"
      disabled={!isAdmin || resolveMutation.isPending}
      onClick={() => resolveMutation.mutate()}
    >
      {resolveMutation.isPending ? "Resolving…" : "Resolve"}
    </Button>
  )

  if (isAdmin) return button
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span>{button}</span>
      </TooltipTrigger>
      <TooltipContent>Resolving fault codes requires an administrator account</TooltipContent>
    </Tooltip>
  )
}

//
// ===== DTC table =====
//

function DtcTable({ dtcs }: Readonly<{ dtcs: DtcRecord[] }>) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Severity</TableHead>
            <TableHead>Protocol</TableHead>
            <TableHead>System</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Occurred</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {dtcs.map((dtc) => (
            <TableRow
              key={`${dtc.protocol}-${dtc.code}-${dtc.source_address ?? 0}`}
              className={cn(dtc.resolved && "opacity-60")}
            >
              <TableCell className="font-mono">{dtc.code}</TableCell>
              <TableCell>
                <Badge variant="outline" className={severityBadgeClass(dtc.severity)}>
                  {titleCase(dtc.severity)}
                </Badge>
              </TableCell>
              <TableCell>{PROTOCOL_LABELS[dtc.protocol] ?? titleCase(dtc.protocol)}</TableCell>
              <TableCell>{titleCase(dtc.system_type)}</TableCell>
              <TableCell className="max-w-72 truncate" title={dtc.description}>
                {dtc.description || "—"}
              </TableCell>
              <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                {formatEpoch(dtc.last_occurrence)}
                {dtc.occurrence_count > 1 && ` (×${dtc.occurrence_count})`}
              </TableCell>
              <TableCell>
                {dtc.resolved ? (
                  <Badge variant="secondary">Resolved</Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className="border-red-300 text-red-700 dark:border-red-800 dark:text-red-400"
                  >
                    Active
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-right">
                {!dtc.resolved && <ResolveButton dtc={dtc} />}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

//
// ===== Empty state (honest about a silent bus) =====
//

function EmptyDtcState({ filtered }: Readonly<{ filtered: boolean }>) {
  const { coach, canbus } = useCoachConnection()

  if (filtered) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <p className="text-sm font-medium">No fault codes match the current filters</p>
        <p className="text-sm text-muted-foreground">Clear the filters to see all fault codes.</p>
      </div>
    )
  }

  if (canbus === "silent") {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <IconVolumeOff className="size-8 text-amber-600 dark:text-amber-400" />
        <p className="text-sm font-medium">No fault codes received</p>
        <p className="max-w-md text-sm text-amber-700 dark:text-amber-400">
          Note: the CAN bus is silent — faults cannot be reported. This does not mean the coach
          is fault-free.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center">
      <IconCircleCheck
        className={cn(
          "size-8",
          coach === "LIVE" ? "text-green-600 dark:text-green-400" : "text-muted-foreground"
        )}
      />
      <p className="text-sm font-medium">No fault codes</p>
      <p className="max-w-md text-sm text-muted-foreground">
        The CAN bus is active and no diagnostic trouble codes have been reported.
        {coach !== "LIVE" && " (Realtime connection is degraded — data may lag.)"}
      </p>
    </div>
  )
}

//
// ===== Page =====
//

export default function DiagnosticsPage() {
  const [severity, setSeverity] = useState<string>("all")
  const [protocol, setProtocol] = useState<string>("all")

  const filtersActive = severity !== "all" || protocol !== "all"

  const dtcsQuery = useQuery({
    queryKey: ["diagnostics", "dtcs", { severity, protocol }],
    queryFn: () => {
      const params = new URLSearchParams()
      if (severity !== "all") params.set("severity", severity)
      if (protocol !== "all") params.set("protocol", protocol)
      const query = params.toString()
      const suffix = query ? `?${query}` : ""
      return apiGet<DtcCollection>(`/api/v1/diagnostics/dtcs${suffix}`)
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
  })

  const dtcs = dtcsQuery.data?.dtcs ?? []

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <HealthVerdictCard />
        <StatisticsStrip />
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Fault codes</CardTitle>
              <CardDescription>
                Diagnostic trouble codes reported on the coach's CAN networks.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger className="w-36" aria-label="Filter by severity">
                  <SelectValue placeholder="Severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All severities</SelectItem>
                  {SEVERITY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={protocol} onValueChange={setProtocol}>
                <SelectTrigger className="w-36" aria-label="Filter by protocol">
                  <SelectValue placeholder="Protocol" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All protocols</SelectItem>
                  {PROTOCOL_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {dtcsQuery.isLoading && <Skeleton className="h-40" />}

          {dtcsQuery.error && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <IconAlertTriangle className="size-8 text-destructive" />
              <p className="text-sm font-medium">Couldn't load fault codes</p>
              <p className="text-sm text-muted-foreground">
                {dtcsQuery.error instanceof Error ? dtcsQuery.error.message : "Unknown error"}
              </p>
            </div>
          )}

          {!dtcsQuery.isLoading && !dtcsQuery.error && dtcs.length === 0 && (
            <EmptyDtcState filtered={filtersActive} />
          )}

          {!dtcsQuery.isLoading && !dtcsQuery.error && dtcs.length > 0 && <DtcTable dtcs={dtcs} />}
        </CardContent>
      </Card>
    </div>
  )
}
