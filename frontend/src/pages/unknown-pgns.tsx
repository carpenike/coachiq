/**
 * Unknown PGNs Page
 *
 * Displays PGN entries that were observed on the CAN bus but not recognized
 * by the system. Provides analysis and potential mapping suggestions.
 */

import type { UnknownPGNEntry } from "@/api/types"
import { AppLayout } from "@/components/app-layout"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useCoachConnection } from "@/contexts/coach-connection"
import { useUnknownPGNs } from "@/hooks/useSystem"
import {
    IconAlertTriangle,
    IconClock,
    IconDownload,
    IconInfoCircle,
    IconQuestionMark,
    IconRefresh
} from "@tabler/icons-react"
import { useMemo } from "react"

/**
 * Unknown PGNs statistics component
 */
function UnknownPGNStats({ unknownPGNs }: { unknownPGNs: UnknownPGNEntry[] }) {
  const stats = useMemo(() => {
    const totalCount = unknownPGNs.reduce((sum, entry) => sum + entry.count, 0)
    const recentEntries = unknownPGNs.filter(entry =>
      Date.now() - (entry.last_seen_timestamp * 1000) < 24 * 60 * 60 * 1000 // Last 24 hours
    ).length
    const highFrequency = unknownPGNs.filter(entry => entry.count > 100).length
    const avgCount = unknownPGNs.length > 0 ? Math.round(totalCount / unknownPGNs.length) : 0

    return {
      totalEntries: unknownPGNs.length,
      totalMessages: totalCount,
      recentEntries,
      highFrequency,
      avgCount,
    }
  }, [unknownPGNs])

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Unknown PGNs</CardTitle>
          <IconQuestionMark className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.totalEntries}</div>
          <p className="text-xs text-muted-foreground">
            Distinct PGN identifiers
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
          <IconAlertTriangle className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.totalMessages.toLocaleString()}</div>
          <p className="text-xs text-muted-foreground">
            Avg {stats.avgCount} per PGN
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Recent Activity</CardTitle>
          <IconClock className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.recentEntries}</div>
          <p className="text-xs text-muted-foreground">
            Seen in last 24 hours
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">High Frequency</CardTitle>
          <IconAlertTriangle className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.highFrequency}</div>
          <p className="text-xs text-muted-foreground">
            Over 100 messages
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Unknown PGNs table component
 */
function UnknownPGNTable({
  unknownPGNs,
  busSilent,
}: {
  unknownPGNs: UnknownPGNEntry[]
  busSilent: boolean
}) {
  const sortedEntries = useMemo(() => {
    return [...unknownPGNs].sort((a, b) => b.count - a.count)
  }, [unknownPGNs])

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  const getFrequencyBadge = (count: number) => {
    if (count > 1000) return <Badge variant="destructive">Very High</Badge>
    if (count > 100) return <Badge variant="default">High</Badge>
    if (count > 10) return <Badge variant="secondary">Medium</Badge>
    return <Badge variant="outline">Low</Badge>
  }

  const getDataPreview = (hex: string | undefined) => {
    if (!hex) return 'No data'
    // Show first 16 characters of hex data with ellipsis
    return hex.length > 16 ? `${hex.substring(0, 16)}...` : hex
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconQuestionMark className="h-5 w-5" />
          Unknown PGN Entries
        </CardTitle>
        <CardDescription>
          PGN identifiers not found in the RV-C specification
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>PGN ID</TableHead>
                <TableHead>Count</TableHead>
                <TableHead>Frequency</TableHead>
                <TableHead>First Seen</TableHead>
                <TableHead>Last Seen</TableHead>
                <TableHead>Sample Data</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedEntries.map((entry, index) => (
                <TableRow key={`${entry.arbitration_id_hex}-${index}`}>
                  <TableCell className="font-mono">
                    <div className="flex flex-col">
                      <span className="font-semibold">{entry.arbitration_id_hex}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{entry.count.toLocaleString()}</div>
                  </TableCell>
                  <TableCell>
                    {getFrequencyBadge(entry.count)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatTimestamp(entry.first_seen_timestamp)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatTimestamp(entry.last_seen_timestamp)}
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    <span className="text-muted-foreground">
                      {getDataPreview(entry.last_data_hex)}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
              {sortedEntries.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8">
                    <div className="flex flex-col items-center gap-2">
                      <IconInfoCircle className="h-8 w-8 text-muted-foreground" />
                      {busSilent ? (
                        <>
                          <p className="text-muted-foreground">No CAN traffic observed — nothing to analyze yet</p>
                          <p className="text-xs text-muted-foreground">
                            Unknown PGN detection needs live bus traffic to inspect
                          </p>
                        </>
                      ) : (
                        <>
                          <p className="text-muted-foreground">No unknown PGNs detected</p>
                          <p className="text-xs text-muted-foreground">
                            All observed PGNs are recognized by the system
                          </p>
                        </>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * PGN analysis sidebar component
 */
function downloadBlob(content: string, mimeType: string, filename: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function PGNAnalysisSidebar({ unknownPGNs }: { unknownPGNs: UnknownPGNEntry[] }) {
  const exportCSV = () => {
    const header = ["arbitration_id_hex", "count", "first_seen_timestamp", "last_seen_timestamp", "last_data_hex"]
    const rows = unknownPGNs.map(entry => [
      entry.arbitration_id_hex ?? "",
      entry.count,
      entry.first_seen_timestamp,
      entry.last_seen_timestamp,
      entry.last_data_hex ?? "",
    ].join(","))
    downloadBlob(
      [header.join(","), ...rows].join("\n"),
      "text/csv",
      `unknown-pgns-${new Date().toISOString().split("T")[0]}.csv`
    )
  }

  const exportJSON = () => {
    downloadBlob(
      JSON.stringify(unknownPGNs, null, 2),
      "application/json",
      `unknown-pgns-${new Date().toISOString().split("T")[0]}.json`
    )
  }

  const analysis = useMemo(() => {
    // Analyze patterns in unknown PGNs
    const arbitrationIds = unknownPGNs
      .map(entry => entry.arbitration_id_hex)
      .filter((id): id is string => id !== undefined)
    const commonPrefixes = arbitrationIds.reduce((acc, id) => {
      const prefix = id.substring(0, 4) // First 4 hex characters
      acc[prefix] = (acc[prefix] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const topPrefixes = Object.entries(commonPrefixes)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)

    const recentActivity = unknownPGNs
      .filter(entry => Date.now() - (entry.last_seen_timestamp * 1000) < 60 * 60 * 1000) // Last hour
      .length

    return {
      topPrefixes,
      recentActivity,
      patterns: {
        highFrequency: unknownPGNs.filter(e => e.count > 100).length,
        burstActivity: unknownPGNs.filter(e =>
          e.last_seen_timestamp - e.first_seen_timestamp < 300 // 5 minutes
        ).length,
      }
    }
  }, [unknownPGNs])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">PGN Analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <div className="text-sm font-medium mb-2">Common Prefixes</div>
            <div className="space-y-1">
              {analysis.topPrefixes.map(([prefix, count]) => (
                <div key={prefix} className="flex justify-between text-sm">
                  <span className="font-mono">{prefix}xx</span>
                  <Badge variant="outline">{count}</Badge>
                </div>
              ))}
              {analysis.topPrefixes.length === 0 && (
                <div className="text-xs text-muted-foreground">No patterns detected</div>
              )}
            </div>
          </div>

          <div>
            <div className="text-sm font-medium mb-2">Activity Patterns</div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Recent Activity</span>
                <Badge variant="secondary">{analysis.recentActivity}</Badge>
              </div>
              <div className="flex justify-between text-sm">
                <span>High Frequency</span>
                <Badge variant="destructive">{analysis.patterns.highFrequency}</Badge>
              </div>
              <div className="flex justify-between text-sm">
                <span>Burst Activity</span>
                <Badge variant="default">{analysis.patterns.burstActivity}</Badge>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Export Options</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            variant="outline"
            className="w-full gap-2"
            size="sm"
            onClick={exportCSV}
            disabled={unknownPGNs.length === 0}
          >
            <IconDownload className="h-4 w-4" />
            Export CSV
          </Button>
          <Button
            variant="outline"
            className="w-full gap-2"
            size="sm"
            onClick={exportJSON}
            disabled={unknownPGNs.length === 0}
          >
            <IconDownload className="h-4 w-4" />
            Export JSON
          </Button>
          <p className="text-xs text-muted-foreground">
            Export unknown PGN data for analysis
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Main Unknown PGNs page component
 */
export default function UnknownPGNs() {
  const { data: response, isLoading, error, refetch } = useUnknownPGNs()
  const { canbus } = useCoachConnection()

  const unknownPGNsArray = response?.unknown_pgns ? Object.values(response.unknown_pgns) : []

  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex justify-between items-center">
            <div>
              <Skeleton className="h-8 w-48 mb-2" />
              <Skeleton className="h-4 w-96" />
            </div>
            <Skeleton className="h-10 w-24" />
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <Skeleton className="h-4 w-24" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-6 w-16 mb-1" />
                  <Skeleton className="h-3 w-32" />
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-8 lg:grid-cols-4">
            <div className="lg:col-span-3">
              <Card>
                <CardHeader>
                  <Skeleton className="h-6 w-48" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-64 w-full" />
                </CardContent>
              </Card>
            </div>
            <div>
              <Skeleton className="h-96 w-full" />
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <Alert variant="destructive">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertTitle>Error Loading Unknown PGNs</AlertTitle>
            <AlertDescription>
              Failed to load unknown PGN data. Please try again.
            </AlertDescription>
          </Alert>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Header (title comes from the app shell) */}
        <div className="flex justify-between items-center">
          <div>
            <p className="text-muted-foreground">
              Unrecognized PGN identifiers observed on the CAN bus
            </p>
          </div>
          <Button
            onClick={() => void refetch()}
            variant="outline"
            className="gap-2"
          >
            <IconRefresh className="h-4 w-4" />
            Refresh
          </Button>
        </div>

        {/* Statistics Cards */}
        <UnknownPGNStats unknownPGNs={unknownPGNsArray} />

        {/* Info Alert */}
        <Alert>
          <IconInfoCircle className="h-4 w-4" />
          <AlertTitle>Unknown PGN Detection</AlertTitle>
          <AlertDescription>
            These PGN identifiers were observed on the CAN bus but are not defined in the
            RV-C specification. High-frequency unknown PGNs may indicate new devices or
            proprietary extensions.
          </AlertDescription>
        </Alert>

        <div className="grid gap-8 lg:grid-cols-4">
          {/* Unknown PGNs Table - Takes 3/4 width */}
          <div className="lg:col-span-3">
            <UnknownPGNTable unknownPGNs={unknownPGNsArray} busSilent={canbus === "silent"} />
          </div>

          {/* Analysis Sidebar - Takes 1/4 width */}
          <div>
            <PGNAnalysisSidebar unknownPGNs={unknownPGNsArray} />
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
