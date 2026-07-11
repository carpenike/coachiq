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
 * from "live bus, genuinely no faults" (per docs/archive/2026-07/frontend-redesign.md).
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
import { useCoachConnection } from "@/contexts/coach-connection-context"
import { toast } from "@/hooks/use-toast"
import { cn } from "@/lib/utils"

//
// ===== Wire types (match backend DiagnosticTroubleCode.to_dict()) =====
//

interface IDtcRecord {
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

interface IDtcCollection {
  dtcs: IDtcRecord[]
  total_count: number
  active_count: number
  by_severity: Record<string, number>
  by_protocol: Record<string, number>
}

interface IDiagnosticsSystemStatus {
  overall_health: string
  health_score: number
  active_systems: string[]
  degraded_systems: string[]
  last_assessment: number
  verdict?: IBackendDiagnosticsVerdict
}

interface IBackendDiagnosticsVerdict {
  code: "offline" | "unavailable" | "action_required" | "degraded" | "healthy"
  label: string
  severity: "critical" | "warning" | "healthy" | "unknown"
  reason_codes: string[]
  requires_attention: boolean
  data_freshness: "current" | "unavailable"
}

interface IDiagnosticsStatistics {
  metrics: {
    total_dtcs: number
    active_dtcs: number
    resolved_dtcs: number
    processing_rate: number
    system_health_trend: "improving" | "stable" | "degrading"
  }
}

type CoachConnectionState = "LIVE" | "STALE" | "OFFLINE"

interface IDiagnosticsVerdict {
  label: string
  detail: string
  tone: "critical" | "warning" | "healthy" | "neutral"
}

const VERDICT_REASON_LABELS = new Map<string, string>([
  ["can_bus_offline", "The CAN bus is offline"],
  ["can_status_unavailable", "CAN status is unavailable"],
  ["diagnostics_status_unavailable", "Diagnostics status is unavailable"],
  ["active_critical_dtc", "An active critical fault requires review"],
  ["active_high_dtc", "An active high-severity fault requires review"],
  ["command_emission_halted", "CoachIQ command emission is halted"],
  ["can_guardrail_degraded", "CAN command guardrails are degraded"],
  ["active_non_urgent_dtc", "One or more active faults need attention"],
  ["degraded_system", "One or more systems are degraded"],
  ["no_active_faults_or_degradation", "No active faults or degraded systems"]
])

function backendVerdictDetail(verdict: IBackendDiagnosticsVerdict): string {
  const reasons = verdict.reason_codes
    .map((reason) => VERDICT_REASON_LABELS.get(reason) ?? titleCase(reason))
  return reasons.join(" · ") || "Review the current diagnostic state"
}

function backendVerdictTone(
  severity: IBackendDiagnosticsVerdict["severity"]
): IDiagnosticsVerdict["tone"] {
  if (severity === "critical") return "critical"
  if (severity === "warning") return "warning"
  if (severity === "healthy") return "healthy"
  return "neutral"
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

// eslint-disable-next-line react-refresh/only-export-components -- pure verdict policy is unit tested directly
export function deriveDiagnosticsVerdict(
  coach: CoachConnectionState,
  status: IDiagnosticsSystemStatus,
  collection: IDtcCollection
): IDiagnosticsVerdict {
  if (status.verdict) {
    return {
      label: status.verdict.label,
      detail: backendVerdictDetail(status.verdict),
      tone: backendVerdictTone(status.verdict.severity)
    }
  }

  const activeDtcs = collection.dtcs.filter((dtc) => dtc.active && !dtc.resolved)
  const urgentCount = activeDtcs.filter(
    (dtc) => dtc.severity === "critical" || dtc.severity === "high"
  ).length

  if (urgentCount > 0) {
    return {
      label: "Action required",
      detail: `${urgentCount} active critical or high severity ${urgentCount === 1 ? "fault" : "faults"}`,
      tone: "critical"
    }
  }

  if (status.degraded_systems.length > 0 || activeDtcs.length > 0) {
    const faultLabel = activeDtcs.length === 1 ? "fault" : "faults"
    const detail = status.degraded_systems.length > 0
      ? `Degraded: ${status.degraded_systems.map(titleCase).join(", ")}`
      : `${activeDtcs.length} active ${faultLabel}`
    return { label: "Attention needed", detail, tone: "warning" }
  }

  if (coach !== "LIVE") {
    return {
      label: coach === "OFFLINE" ? "Health unavailable" : "Last known health",
      detail: "The coach connection is not live, so this assessment may be out of date.",
      tone: "neutral"
    }
  }

  const healthy = ["excellent", "good", "healthy"].includes(
    status.overall_health.toLowerCase()
  )
  return {
    label: titleCase(status.overall_health),
    detail: healthy ? "No active faults or degraded systems" : "Review the current health score",
    tone: healthy ? "healthy" : "warning"
  }
}

//
// ===== Health verdict card =====
//

function HealthVerdictCard({
  status,
  collection,
  isLoading,
  error
}: Readonly<{
  status: IDiagnosticsSystemStatus | undefined
  collection: IDtcCollection | undefined
  isLoading: boolean
  error: Error | null
}>) {
  const { coach } = useCoachConnection()

  if (isLoading) return <Skeleton className="h-32" />

  if (error || !status || !collection) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Health verdict</CardTitle>
          <CardDescription>
            Couldn&apos;t load the health assessment
            {error instanceof Error ? ` — ${error.message}` : ""}.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const verdict = deriveDiagnosticsVerdict(coach, status, collection)

  return (
    <Card
      className={cn(
        verdict.tone === "healthy" && "border-green-300 dark:border-green-900",
        verdict.tone === "warning" && "border-amber-300 dark:border-amber-900",
        verdict.tone === "critical" && "border-red-300 dark:border-red-900"
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
              verdict.tone === "healthy" && "text-green-700 dark:text-green-400",
              verdict.tone === "warning" && "text-amber-700 dark:text-amber-400",
              verdict.tone === "critical" && "text-red-700 dark:text-red-400"
            )}
          >
            {verdict.label}
          </span>
          {verdict.tone === "healthy" && (
            <span className="text-sm text-muted-foreground">
              score {Math.round(status.health_score)}/100
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{verdict.detail}</p>
        <p className="text-xs text-muted-foreground">
          {status.active_systems.length} systems reporting · assessed{" "}
          {formatEpoch(status.last_assessment)}
        </p>
        {coach !== "LIVE" && verdict.tone !== "neutral" && (
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
    queryFn: () => apiGet<IDiagnosticsStatistics>("/api/v1/diagnostics/statistics"),
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
            Couldn&apos;t load fault statistics
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

function ResolveButton({ dtc }: Readonly<{ dtc: IDtcRecord }>) {
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

function DtcTable({ dtcs }: Readonly<{ dtcs: IDtcRecord[] }>) {
  return (
    <div className="hidden overflow-x-auto md:block">
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

function DtcCardList({ dtcs }: Readonly<{ dtcs: IDtcRecord[] }>) {
  return (
    <div className="space-y-3 md:hidden" aria-label="Fault codes">
      {dtcs.map((dtc) => {
        const status = dtc.resolved ? "Resolved" : "Active"
        return (
          <article
            key={`${dtc.protocol}-${dtc.code}-${dtc.source_address ?? 0}`}
            className={cn(
              "space-y-3 rounded-md border border-l-4 p-3",
              dtc.severity === "critical" && "border-l-red-500",
              dtc.severity === "high" && "border-l-orange-500",
              dtc.severity === "medium" && "border-l-amber-500",
              (dtc.severity === "low" || dtc.severity === "info") &&
                "border-l-slate-400",
              dtc.resolved && "opacity-70"
            )}
            aria-label={`${titleCase(dtc.severity)} fault ${dtc.code}, ${status}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className={severityBadgeClass(dtc.severity)}>
                  {titleCase(dtc.severity)}
                </Badge>
                <span className="font-mono text-sm">{dtc.code}</span>
                <span className="text-xs text-muted-foreground">
                  {PROTOCOL_LABELS[dtc.protocol] ?? titleCase(dtc.protocol)}
                </span>
              </div>
              <Badge variant={dtc.resolved ? "secondary" : "outline"}>{status}</Badge>
            </div>
            <div>
              <p className="text-sm font-medium">{dtc.description || "No description provided"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {titleCase(dtc.system_type)} · last occurred {formatEpoch(dtc.last_occurrence)} ·{" "}
                {dtc.occurrence_count} {dtc.occurrence_count === 1 ? "occurrence" : "occurrences"}
              </p>
            </div>
            {!dtc.resolved && (
              <div className="flex justify-end">
                <ResolveButton dtc={dtc} />
              </div>
            )}
          </article>
        )
      })}
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

  const systemStatusQuery = useQuery({
    queryKey: ["diagnostics", "system-status"],
    queryFn: () => apiGet<IDiagnosticsSystemStatus>("/api/v1/diagnostics/system-status"),
    refetchInterval: 45_000,
    staleTime: 30_000,
    retry: 1
  })

  const dtcsQuery = useQuery({
    queryKey: ["diagnostics", "dtcs"],
    queryFn: () => apiGet<IDtcCollection>("/api/v1/diagnostics/dtcs"),
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1
  })

  const dtcs = (dtcsQuery.data?.dtcs ?? []).filter(
    (dtc) =>
      (severity === "all" || dtc.severity === severity) &&
      (protocol === "all" || dtc.protocol === protocol)
  )
  const verdictError = systemStatusQuery.error ?? dtcsQuery.error

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <HealthVerdictCard
          status={systemStatusQuery.data}
          collection={dtcsQuery.data}
          isLoading={systemStatusQuery.isLoading || dtcsQuery.isLoading}
          error={verdictError instanceof Error ? verdictError : null}
        />
        <StatisticsStrip />
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Fault codes</CardTitle>
              <CardDescription>
                Diagnostic trouble codes reported on the coach&apos;s CAN networks.
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
              <p className="text-sm font-medium">Couldn&apos;t load fault codes</p>
              <p className="text-sm text-muted-foreground">
                {dtcsQuery.error instanceof Error ? dtcsQuery.error.message : "Unknown error"}
              </p>
            </div>
          )}

          {!dtcsQuery.isLoading && !dtcsQuery.error && dtcs.length === 0 && (
            <EmptyDtcState filtered={filtersActive} />
          )}

          {!dtcsQuery.isLoading && !dtcsQuery.error && dtcs.length > 0 && (
            <>
              <DtcCardList dtcs={dtcs} />
              <DtcTable dtcs={dtcs} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
