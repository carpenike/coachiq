/**
 * Unmapped Entries Page
 *
 * Displays DGN/instance pairs that have been observed on the CAN bus
 * but are not mapped to entities. Provides manual mapping interface.
 */

import { createEntityMapping } from "@/api/endpoints"
import type { UnmappedEntry } from "@/api/types"
import { AppLayout } from "@/components/app-layout"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { MappingDialog } from "@/components/unmapped-entries/mapping-dialog"
import { useCoachConnection } from "@/contexts/coach-connection-context"
import { useUnmappedEntries } from "@/hooks/useSystem"
import {
    IconAlertTriangle,
    IconCircuitSwitchOpen,
    IconClock,
    IconInfoCircle,
    IconMapPin,
    IconPlus,
    IconRefresh,
    IconSettings
} from "@tabler/icons-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

/**
 * Unmapped entries statistics component
 */
function UnmappedEntriesStats({ unmappedEntries }: { unmappedEntries: UnmappedEntry[] }) {
  const stats = useMemo(() => {
    const totalCount = unmappedEntries.reduce((sum, entry) => sum + entry.count, 0)
    const withSuggestions = unmappedEntries.filter(entry =>
      entry.suggestions && entry.suggestions.length > 0
    ).length
    const recentEntries = unmappedEntries.filter(entry =>
      Date.now() - (entry.last_seen_timestamp * 1000) < 24 * 60 * 60 * 1000 // Last 24 hours
    ).length

    const deviceTypes = unmappedEntries.reduce((acc, entry) => {
      if (entry.dgn_name && entry.dgn_name !== 'Unknown') {
        acc.add(entry.dgn_name)
      }
      return acc
    }, new Set<string>())

    return {
      totalEntries: unmappedEntries.length,
      totalMessages: totalCount,
      withSuggestions,
      recentEntries,
      uniqueDeviceTypes: deviceTypes.size,
    }
  }, [unmappedEntries])

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Unmapped Entries</CardTitle>
          <IconCircuitSwitchOpen className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.totalEntries}</div>
          <p className="text-xs text-muted-foreground">
            DGN/instance pairs
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">With Suggestions</CardTitle>
          <IconMapPin className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.withSuggestions}</div>
          <p className="text-xs text-muted-foreground">
            {stats.totalEntries > 0
              ? Math.round((stats.withSuggestions / stats.totalEntries) * 100)
              : 0}% have mapping suggestions
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
          <CardTitle className="text-sm font-medium">Device Types</CardTitle>
          <IconSettings className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.uniqueDeviceTypes}</div>
          <p className="text-xs text-muted-foreground">
            Unique DGN types
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Unmapped entries table component
 */
function UnmappedEntriesTable({
  unmappedEntries,
  busSilent,
  onMapEntry
}: {
  unmappedEntries: UnmappedEntry[]
  busSilent: boolean
  onMapEntry: (entry: UnmappedEntry) => void
}) {
  const sortedEntries = useMemo(() => {
    return [...unmappedEntries].sort((a, b) => b.count - a.count)
  }, [unmappedEntries])

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  const getFrequencyBadge = (count: number) => {
    if (count > 1000) return <Badge variant="destructive">Very High</Badge>
    if (count > 100) return <Badge variant="default">High</Badge>
    if (count > 10) return <Badge variant="secondary">Medium</Badge>
    return <Badge variant="outline">Low</Badge>
  }

  const getSuggestionsBadge = (suggestions: string[]) => {
    if (!suggestions || suggestions.length === 0) {
      return <Badge variant="outline">None</Badge>
    }
    if (suggestions.length === 1) {
      return <Badge variant="default">{suggestions[0]}</Badge>
    }
    return <Badge variant="secondary">{suggestions.length} suggestions</Badge>
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconCircuitSwitchOpen className="h-5 w-5" />
          Unmapped Entries
        </CardTitle>
        <CardDescription>
          DGN/instance pairs observed on the bus but not mapped to entities
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>PGN/DGN</TableHead>
                <TableHead>Instance</TableHead>
                <TableHead>Count</TableHead>
                <TableHead>Frequency</TableHead>
                <TableHead>Suggestions</TableHead>
                <TableHead>Last Seen</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedEntries.map((entry, index) => (
                <TableRow key={`${entry.pgn_hex}-${entry.instance}-${index}`}>
                  <TableCell>
                    <div className="flex flex-col">
                      <div className="font-mono text-sm">
                        <span className="font-semibold">PGN:</span> {entry.pgn_hex}
                      </div>
                      <div className="font-mono text-sm">
                        <span className="font-semibold">DGN:</span> {entry.dgn_hex}
                      </div>
                      {entry.dgn_name && entry.dgn_name !== 'Unknown' && (
                        <div className="text-xs text-muted-foreground">
                          {entry.dgn_name}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{entry.instance}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{entry.count.toLocaleString()}</div>
                  </TableCell>
                  <TableCell>
                    {getFrequencyBadge(entry.count)}
                  </TableCell>
                  <TableCell>
                    {getSuggestionsBadge(entry.suggestions)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatTimestamp(entry.last_seen_timestamp)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1"
                      onClick={() => onMapEntry(entry)}
                    >
                      <IconPlus className="h-3 w-3" />
                      Map
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {sortedEntries.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8">
                    <div className="flex flex-col items-center gap-2">
                      <IconInfoCircle className="h-8 w-8 text-muted-foreground" />
                      {busSilent ? (
                        <>
                          <p className="text-muted-foreground">No CAN traffic observed — nothing to analyze yet</p>
                          <p className="text-xs text-muted-foreground">
                            Unmapped-entry detection needs live bus traffic to inspect
                          </p>
                        </>
                      ) : (
                        <>
                          <p className="text-muted-foreground">No unmapped entries found</p>
                          <p className="text-xs text-muted-foreground">
                            All observed DGN/instance pairs are mapped to entities
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
 * Mapping tools sidebar component
 */
function MappingToolsSidebar({ unmappedEntries }: Readonly<{ unmappedEntries: UnmappedEntry[] }>) {
  const analysis = useMemo(() => {
    // Analyze common device types and suggestions
    const dgnTypes = unmappedEntries.reduce((acc, entry) => {
      if (entry.dgn_name && entry.dgn_name !== 'Unknown') {
        acc[entry.dgn_name] = (acc[entry.dgn_name] || 0) + 1
      }
      return acc
    }, {} as Record<string, number>)

    const allSuggestions = unmappedEntries
      .flatMap(entry => entry.suggestions || [])
      .reduce((acc, suggestion) => {
        acc[suggestion] = (acc[suggestion] || 0) + 1
        return acc
      }, {} as Record<string, number>)

    const topDGNTypes = Object.entries(dgnTypes)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)

    const topSuggestions = Object.entries(allSuggestions)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)

    return {
      topDGNTypes,
      topSuggestions,
      totalWithSuggestions: unmappedEntries.filter(e => e.suggestions && e.suggestions.length > 0).length,
    }
  }, [unmappedEntries])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Mapping Analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <div className="text-sm font-medium mb-2">Common DGN Types</div>
            <div className="space-y-1">
              {analysis.topDGNTypes.map(([dgn, count]) => (
                <div key={dgn} className="flex justify-between text-sm">
                  <span className="truncate text-xs">{dgn}</span>
                  <Badge variant="outline">{count}</Badge>
                </div>
              ))}
              {analysis.topDGNTypes.length === 0 && (
                <div className="text-xs text-muted-foreground">No known DGN types</div>
              )}
            </div>
          </div>

          <div>
            <div className="text-sm font-medium mb-2">Common Suggestions</div>
            <div className="space-y-1">
              {analysis.topSuggestions.map(([suggestion, count]) => (
                <div key={suggestion} className="flex justify-between text-sm">
                  <span className="truncate text-xs">{suggestion}</span>
                  <Badge variant="secondary">{count}</Badge>
                </div>
              ))}
              {analysis.topSuggestions.length === 0 && (
                <div className="text-xs text-muted-foreground">No suggestions available</div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Mapping Stats</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Ready to Map</span>
            <Badge variant="default">{analysis.totalWithSuggestions}</Badge>
          </div>
          <div className="flex justify-between text-sm">
            <span>Need Manual Review</span>
            <Badge variant="outline">{unmappedEntries.length - analysis.totalWithSuggestions}</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Main Unmapped Entries page component
 */
export default function UnmappedEntries() {
  const { data: response, isLoading, error, refetch } = useUnmappedEntries()
  const { canbus } = useCoachConnection()

  // State for mapping dialog
  const [selectedEntry, setSelectedEntry] = useState<UnmappedEntry | null>(null)
  const [isMappingDialogOpen, setIsMappingDialogOpen] = useState(false)

  const unmappedEntriesArray = response?.unmapped_entries ? Object.values(response.unmapped_entries) : []

  // Callback functions for mapping operations
  const handleMapEntry = (entry: UnmappedEntry) => {
    setSelectedEntry(entry)
    setIsMappingDialogOpen(true)
  }

  const handleMappingSubmit = async (mappingData: {
    entity_id: string
    friendly_name: string
    device_type: string
    suggested_area?: string | undefined
    capabilities?: string[] | undefined
    notes?: string | undefined
  }) => {
    try {
      if (!selectedEntry) {
        throw new Error("No unmapped entry selected")
      }

      const result = await createEntityMapping({
        // Source unmapped entry information
        pgn_hex: selectedEntry.pgn_hex,
        instance: selectedEntry.instance,

        // Entity configuration
        entity_id: mappingData.entity_id,
        friendly_name: mappingData.friendly_name,
        device_type: mappingData.device_type,
        suggested_area: mappingData.suggested_area ?? "",
        capabilities: mappingData.capabilities ?? [],
        notes: mappingData.notes ?? "",
      })

      if (result.status === "success") {
        toast("Mapping created", {
          description: `Successfully mapped ${mappingData.entity_id} to DGN ${selectedEntry?.dgn_hex}/${selectedEntry?.instance}`,
        })

        setIsMappingDialogOpen(false)
        setSelectedEntry(null)
        void refetch() // Refresh the data
      } else {
        throw new Error(result.message)
      }
    } catch (err) {
      console.error('Failed to create mapping:', err)
      const errorMessage = err instanceof Error ? err.message : "Unknown error occurred"
      toast.error("Mapping failed", {
        description: `Failed to create entity mapping: ${errorMessage}`,
      })
    }
  }

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
            <AlertTitle>Error Loading Unmapped Entries</AlertTitle>
            <AlertDescription>
              Failed to load unmapped entry data. Please try again.
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
              DGN/instance pairs observed but not mapped to entities
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
        <UnmappedEntriesStats unmappedEntries={unmappedEntriesArray} />

        {/* Info Alert */}
        <Alert>
          <IconInfoCircle className="h-4 w-4" />
          <AlertTitle>Device Mapping</AlertTitle>
          <AlertDescription>
            These DGN/instance pairs have been observed on the CAN bus but are not currently
            mapped to entities. Use the mapping tools to create entity configurations for these devices.
          </AlertDescription>
        </Alert>

        <div className="grid gap-8 lg:grid-cols-4">
          {/* Unmapped Entries Table - Takes 3/4 width */}
          <div className="lg:col-span-3">
            <UnmappedEntriesTable
              unmappedEntries={unmappedEntriesArray}
              busSilent={canbus === "silent"}
              onMapEntry={handleMapEntry}
            />
          </div>

          {/* Mapping Tools Sidebar - Takes 1/4 width */}
          <div>
            <MappingToolsSidebar unmappedEntries={unmappedEntriesArray} />
          </div>
        </div>
      </div>

      {/* Mapping Dialog */}
      <MappingDialog
        open={isMappingDialogOpen}
        onOpenChange={setIsMappingDialogOpen}
        unmappedEntry={selectedEntry}
        onSubmit={handleMappingSubmit}
      />
    </AppLayout>
  )
}
