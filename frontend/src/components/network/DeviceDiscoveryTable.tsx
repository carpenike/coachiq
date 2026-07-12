/**
 * Device Discovery Table Component
 *
 * Replaces the canvas-based network topology with a practical device discovery table.
 * Provides sortable, filterable view of discovered devices with polling actions.
 */

import type { NetworkTopology, DeviceAvailability } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { pollDevice } from "@/api/endpoints"
import {
  IconDevices,
  IconSearch,
  IconRefresh,
  IconDownload,
  IconAlertTriangle,
  IconWifi,
  IconWifiOff,
  IconClock,
} from "@tabler/icons-react"
import { useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"

interface DeviceTableEntry {
  address: string
  name: string
  notes: string | null
  protocol: string
  deviceType: string
  status: "online" | "offline" | "warning" | "error"
  lastSeen: string
  /** Epoch ms of last activity (0 = never), used for sorting */
  lastSeenMs: number
  responseTime: string
  pgns?: number[]
  capabilities?: string[]
}

/**
 * Normalize a backend timestamp to epoch milliseconds.
 * The backend sends epoch seconds (Python time.time()) or an ISO string;
 * values already in milliseconds pass through unchanged.
 */
function toEpochMs(value: number | string | null | undefined): number | null {
  if (value == null) return null
  if (typeof value === "string") {
    const parsed = Date.parse(value)
    return Number.isNaN(parsed) ? null : parsed
  }
  if (!Number.isFinite(value) || value <= 0) return null
  // Epoch seconds stay below 1e12 until the year 33658; ms values exceed it.
  return value < 1e12 ? value * 1000 : value
}

/** Render a relative time like "3m ago" with a sane fallback. */
function formatRelativeTime(epochMs: number | null): string {
  if (!epochMs) return "never"
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - epochMs) / 1000))
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`
  const minutes = Math.floor(deltaSeconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

/**
 * Accessors for each sortable column, keyed by field name. Avoids dynamic
 * `entry[sortField]` indexing (flagged as an object-injection sink) while
 * still sorting on the numeric timestamp for "lastSeen" rather than its label.
 */
const SORT_ACCESSORS = new Map<keyof DeviceTableEntry, (entry: DeviceTableEntry) => string | number | undefined>([
  ["address", (entry) => entry.address],
  ["protocol", (entry) => entry.protocol],
  ["deviceType", (entry) => entry.deviceType],
  ["status", (entry) => entry.status],
  ["lastSeen", (entry) => entry.lastSeenMs],
  ["lastSeenMs", (entry) => entry.lastSeenMs],
  ["responseTime", (entry) => entry.responseTime],
])

/** Sort-comparable value for a table entry's column, without dynamic property indexing. */
// eslint-disable-next-line sonarjs/function-return-type -- legitimately returns string or number depending on the sorted column
function sortValueFor(entry: DeviceTableEntry, field: keyof DeviceTableEntry) {
  return SORT_ACCESSORS.get(field)?.(entry)
}

interface DeviceDiscoveryTableProps {
  topology?: NetworkTopology
  availability?: DeviceAvailability
  isLoading?: boolean
  onRefresh?: () => void
}

export function DeviceDiscoveryTable({
  topology,
  availability,
  isLoading = false,
  onRefresh
}: DeviceDiscoveryTableProps) {
  const [searchTerm, setSearchTerm] = useState("")
  const [protocolFilter, setProtocolFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [sortField, setSortField] = useState<keyof DeviceTableEntry>("address")
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc")

  const queryClient = useQueryClient()

  // Device polling mutation
  const pollMutation = useMutation({
    mutationFn: async ({ address, pgn, protocol }: { address: string, pgn: number, protocol: string }) => {
      return await pollDevice({
        source_address: parseInt(address, 16),
        pgn,
        protocol,
      })
    },
    onSuccess: () => {
      // Refresh data after successful poll
      void queryClient.invalidateQueries({ queryKey: ['network-topology'] })
      void queryClient.invalidateQueries({ queryKey: ['device-availability'] })
    }
  })

  // Transform topology data into table entries
  const deviceEntries = useMemo((): DeviceTableEntry[] => {
    if (!topology?.devices) return []

    const entries: DeviceTableEntry[] = []

    // Iterate through protocol groups and their device arrays
    Object.entries(topology.devices).forEach(([protocol, deviceArray]) => {
      deviceArray.forEach((device) => {
        const hexAddress = `0x${device.source_address.toString(16).toUpperCase().padStart(2, '0')}`

        // Determine status based on last seen time (normalized to epoch ms)
        const lastSeenMs = toEpochMs(device.last_seen)
        let status: DeviceTableEntry["status"] = "offline"
        if (lastSeenMs) {
          const timeSinceLastSeen = Date.now() - lastSeenMs
          if (timeSinceLastSeen < 30000) { // Less than 30 seconds
            status = "online"
          } else if (timeSinceLastSeen < 300000) { // Less than 5 minutes
            status = "warning"
          }
        }

        // Format response time (DeviceInfo doesn't have avg_response_time)
        const responseTime = "N/A"

        entries.push({
          address: hexAddress,
          name: device.friendly_name || `Unknown (${hexAddress})`,
          notes: device.notes ?? null,
          protocol: device.protocol || protocol,
          deviceType: device.device_type || "Unknown",
          status,
          lastSeen: formatRelativeTime(lastSeenMs),
          lastSeenMs: lastSeenMs ?? 0,
          responseTime,
          pgns: [], // DeviceInfo doesn't have supported_pgns
          capabilities: device.capabilities || []
        })
      })
    })

    return entries
  }, [topology])

  // Apply filters and sorting
  const filteredAndSortedEntries = useMemo(() => {
    let filtered = deviceEntries

    // Apply search filter
    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(entry =>
        entry.address.toLowerCase().includes(term) ||
        entry.name.toLowerCase().includes(term) ||
        entry.protocol.toLowerCase().includes(term) ||
        entry.deviceType.toLowerCase().includes(term)
      )
    }

    // Apply protocol filter
    if (protocolFilter !== "all") {
      filtered = filtered.filter(entry =>
        entry.protocol.toLowerCase() === protocolFilter.toLowerCase()
      )
    }

    // Apply status filter
    if (statusFilter !== "all") {
      filtered = filtered.filter(entry => entry.status === statusFilter)
    }

    // Apply sorting (last-seen sorts on the numeric timestamp, not the label)
    filtered.sort((a, b) => {
      const aValue = sortValueFor(a, sortField)
      const bValue = sortValueFor(b, sortField)

      if (aValue !== undefined && bValue !== undefined) {
        if (aValue < bValue) return sortDirection === "asc" ? -1 : 1
        if (aValue > bValue) return sortDirection === "asc" ? 1 : -1
      }
      return 0
    })

    return filtered
  }, [deviceEntries, searchTerm, protocolFilter, statusFilter, sortField, sortDirection])

  // Handle column header clicks for sorting
  const handleSort = (field: keyof DeviceTableEntry) => {
    if (sortField === field) {
      setSortDirection(prev => prev === "asc" ? "desc" : "asc")
    } else {
      setSortField(field)
      setSortDirection("asc")
    }
  }

  // Handle device polling
  const handlePollDevice = async (entry: DeviceTableEntry) => {
    // Use a common PGN for status polling (0x1FEDA for RV-C lights, 0xFEEE for J1939)
    const pgn = entry.protocol.toLowerCase() === "rvc" ? 0x1FEDA : 0xFEEE

    await pollMutation.mutateAsync({
      address: entry.address,
      pgn,
      protocol: entry.protocol.toLowerCase()
    })
  }

  // Export device list as CSV
  const handleExport = () => {
    const csvContent = [
      ["Device", "Address", "Protocol", "Device Type", "Status", "Last Seen", "Response Time"].join(","),
      ...filteredAndSortedEntries.map(entry => [
        entry.name,
        entry.address,
        entry.protocol,
        entry.deviceType,
        entry.status,
        entry.lastSeen,
        entry.responseTime
      ].join(","))
    ].join("\n")

    const blob = new Blob([csvContent], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `device-discovery-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Get unique protocols for filter
  const availableProtocols = useMemo(() => {
    const protocols = new Set(deviceEntries.map(entry => entry.protocol))
    return Array.from(protocols)
  }, [deviceEntries])

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconDevices className="h-5 w-5" />
            Device Discovery
          </CardTitle>
          <CardDescription>Loading discovered devices...</CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-96 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-start">
          <div>
            <CardTitle className="flex items-center gap-2">
              <IconDevices className="h-5 w-5" />
              Device Discovery
            </CardTitle>
            <CardDescription>
              Active CAN bus devices with status and polling capabilities
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleExport}>
              <IconDownload className="h-4 w-4 mr-1" />
              Export
            </Button>
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <IconRefresh className="h-4 w-4 mr-1" />
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Filters */}
        <div className="flex gap-4 items-center">
          <div className="flex-1 relative">
            <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search devices..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={protocolFilter} onValueChange={setProtocolFilter}>
            <SelectTrigger className="w-32">
              <SelectValue placeholder="Protocol" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Protocols</SelectItem>
              {availableProtocols.map(protocol => (
                <SelectItem key={protocol} value={protocol.toLowerCase()}>
                  {protocol}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-32">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="online">Online</SelectItem>
              <SelectItem value="warning">Warning</SelectItem>
              <SelectItem value="offline">Offline</SelectItem>
              <SelectItem value="error">Error</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Summary Stats */}
        {availability && (
          <div className="grid grid-cols-4 gap-4 p-4 bg-muted/50 rounded-lg">
            <div className="text-center">
              <div className="text-2xl font-bold tracking-tight text-emerald-600">
                {availability.online_devices || 0}
              </div>
              <div className="text-sm text-muted-foreground">Online</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold tracking-tight text-gray-500">
                {availability.offline_devices || 0}
              </div>
              <div className="text-sm text-muted-foreground">Offline</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold tracking-tight text-blue-600">
                {availability.total_devices || 0}
              </div>
              <div className="text-sm text-muted-foreground">Total</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold tracking-tight text-purple-600">
                {availableProtocols.length}
              </div>
              <div className="text-sm text-muted-foreground">Protocols</div>
            </div>
          </div>
        )}

        {/* Device Table */}
        {filteredAndSortedEntries.length === 0 ? (
          <Alert>
            <IconAlertTriangle className="h-4 w-4" />
            <AlertDescription>
              No devices found. Try adjusting your filters or trigger a device discovery.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("name")}
                  >
                    Device {sortField === "name" && (sortDirection === "asc" ? "↑" : "↓")}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("address")}
                  >
                    Address {sortField === "address" && (sortDirection === "asc" ? "↑" : "↓")}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("protocol")}
                  >
                    Protocol {sortField === "protocol" && (sortDirection === "asc" ? "↑" : "↓")}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("deviceType")}
                  >
                    Device Type {sortField === "deviceType" && (sortDirection === "asc" ? "↑" : "↓")}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("status")}
                  >
                    Status {sortField === "status" && (sortDirection === "asc" ? "↑" : "↓")}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("lastSeen")}
                  >
                    Last Seen {sortField === "lastSeen" && (sortDirection === "asc" ? "↑" : "↓")}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("responseTime")}
                  >
                    Response {sortField === "responseTime" && (sortDirection === "asc" ? "↑" : "↓")}
                  </TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAndSortedEntries.map((entry) => (
                  <TableRow key={entry.address}>
                    <TableCell className="font-medium" title={entry.notes ?? undefined}>
                      {entry.name}
                    </TableCell>
                    <TableCell className="font-mono text-sm">{entry.address}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="capitalize">
                        {entry.protocol}
                      </Badge>
                    </TableCell>
                    <TableCell className="capitalize">
                      {entry.deviceType.replace('_', ' ')}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {entry.status === "online" && <IconWifi className="h-4 w-4 text-emerald-500" />}
                        {entry.status === "offline" && <IconWifiOff className="h-4 w-4 text-gray-500" />}
                        {entry.status === "warning" && <IconClock className="h-4 w-4 text-yellow-500" />}
                        {entry.status === "error" && <IconAlertTriangle className="h-4 w-4 text-red-500" />}
                        <Badge variant={
                          entry.status === "online" ? "default" :
                          entry.status === "warning" ? "secondary" :
                          entry.status === "error" ? "destructive" : "outline"
                        }>
                          {entry.status}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {entry.lastSeen}
                    </TableCell>
                    <TableCell className="text-sm">
                      {entry.responseTime}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handlePollDevice(entry)}
                        disabled={pollMutation.isPending}
                        className="gap-1"
                      >
                        <IconRefresh className="h-3 w-3" />
                        Poll
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Results summary */}
        <div className="text-sm text-muted-foreground text-center">
          Showing {filteredAndSortedEntries.length} of {deviceEntries.length} devices
        </div>
      </CardContent>
    </Card>
  )
}
