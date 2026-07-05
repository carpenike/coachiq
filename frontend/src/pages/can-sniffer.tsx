/**
 * CAN Sniffer Page
 *
 * Real-time CAN bus monitoring and packet analysis.
 * Shows live CAN traffic with filtering and analysis capabilities.
 */

import type { CANMessage } from "@/api/types"
import type { WebSocketState } from "@/api/websocket"
import { AppLayout } from "@/components/app-layout"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
// Table components replaced by VirtualizedTable
import { fetchEnhancedCANStatistics } from "@/api/endpoints"
import { VirtualizedTable, type VirtualizedTableColumn } from "@/components/virtualized-table"
import { useCoachConnection } from "@/contexts/coach-connection-context"
import { useCANMetrics, useCANStatistics } from "@/hooks/useSystem"
import { useVirtualizedTable } from "@/hooks/useVirtualizedTable"
import { useCANScanWebSocket } from "@/hooks/useWebSocket"
import {
    IconActivity,
    IconAlertTriangle,
    IconFilter,
    IconPlayerPause,
    IconPlayerPlay,
    IconPlugConnectedX,
    IconRefresh,
    IconTrash
} from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"

/** Bound the initial skeleton state — after this we show an explicit status instead. */
const INITIAL_LOAD_GRACE_MS = 5000

/**
 * CAN message statistics component
 * Uses backend API for aggregated statistics with frontend fallback for PGN-level data
 */
function CANStatistics({ messages }: { messages: CANMessage[] }) {
  // Use backend API for aggregated statistics
  const { data: backendStats } = useCANStatistics()

  // Try to use enhanced backend statistics with PGN-level data (Phase 3 implementation)
  const { data: enhancedStats, isError: enhancedStatsError } = useQuery({
    queryKey: ['can-statistics-enhanced'],
    queryFn: fetchEnhancedCANStatistics,
    refetchInterval: 5000,
    staleTime: 3000,
    // Don't retry on 404 - enhanced API may not be available
    retry: (failureCount, error) => {
      if (error && 'statusCode' in error && (error as { statusCode: number }).statusCode === 404) {
        return false; // Enhanced API not available
      }
      return failureCount < 2;
    }
  })

  // Calculate PGN-level statistics from frontend messages as fallback
  // Only used when enhanced backend API is not available
  const pgnStats = useMemo(() => {
    // If enhanced backend stats are available, skip frontend aggregation
    if (enhancedStats && !enhancedStatsError) {
      return {
        uniquePGNs: enhancedStats.unique_pgns || 0,
        topPGNs: enhancedStats.top_pgns || [],
        topInstances: []
      }
    }

    const byPGN = messages.reduce((acc, msg) => {
      acc[msg.pgn] = (acc[msg.pgn] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const byInstance = messages.reduce((acc, msg) => {
      if (msg.instance !== undefined) {
        acc[msg.instance] = (acc[msg.instance] || 0) + 1
      }
      return acc
    }, {} as Record<number, number>)

    const uniquePGNs = Object.keys(byPGN).length
    const topPGNs = Object.entries(byPGN)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)
      .map(([pgn, count]) => ({ pgn, count }))
    const topInstances = Object.entries(byInstance)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)
      .map(([instance, count]) => ({ instance: Number(instance), count }))

    return { uniquePGNs, topPGNs, topInstances }
  }, [messages, enhancedStats, enhancedStatsError])

  // Combine backend stats with enhanced backend data or frontend fallback
  const stats = {
    // Use enhanced backend data first, then basic backend data, then frontend calculation
    total: (enhancedStats as { total_messages?: number })?.total_messages ?? (backendStats as { total_messages?: number })?.total_messages ?? messages.length,
    errorMessages: (enhancedStats as { total_errors?: number })?.total_errors ?? (backendStats as { total_errors?: number })?.total_errors ?? messages.filter(msg => msg.error).length,
    lastMinute: messages.filter(msg =>
      Date.now() - new Date(msg.timestamp).getTime() < 60000
    ).length, // Keep this frontend for now as it's time-sensitive
    // PGN-level data from enhanced backend or frontend fallback
    uniquePGNs: Number(pgnStats.uniquePGNs) || 0,
    topPGNs: pgnStats.topPGNs,
    topInstances: pgnStats.topInstances
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
          <IconActivity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.total}</div>
          <p className="text-xs text-muted-foreground">
            {stats.lastMinute} in last minute
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Unique PGNs</CardTitle>
          <IconFilter className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.uniquePGNs}</div>
          <p className="text-xs text-muted-foreground">
            Different message types
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Error Messages</CardTitle>
          <IconAlertTriangle className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.errorMessages}</div>
          <p className="text-xs text-muted-foreground">
            {stats.total > 0 ? Math.round((stats.errorMessages / stats.total) * 100) : 0}% error rate
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Message Rate</CardTitle>
          <IconActivity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.lastMinute}</div>
          <p className="text-xs text-muted-foreground">
            messages/minute
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

// Helper functions for table accessors (to avoid inline JSX components)
const renderPGNBadge = (pgn: string) => <PGNBadge pgn={pgn} />;
const renderDescriptionCell = (pgn: string) => <DescriptionCell pgn={pgn} />;
const renderInstanceCell = (instance: number | undefined) => <InstanceCell instance={instance} />;
const renderSourceBadge = (source: number) => <SourceBadge source={source} />;

// Helper components for table cells (defined outside render to avoid recreation)
function PGNBadge({ pgn }: { pgn: string }) {
  return (
    <Badge variant="outline" className="font-mono text-xs">
      {pgn}
    </Badge>
  );
}

function DescriptionCell({ pgn }: { pgn: string }) {
  const getPGNDescription = (pgnStr: string) => {
    // This would normally come from the RV-C spec database
    const knownPGNs: Record<string, string> = {
      '1FFFF': 'Device Control',
      '1FFF0': 'Light Control',
      '1FFE0': 'Tank Status',
      '1FFD0': 'Temperature',
      // Add more as needed
    }
    return knownPGNs[pgnStr] || 'Unknown'
  }

  return <span className="text-sm">{getPGNDescription(pgn)}</span>
}

function InstanceCell({ instance }: { instance: number | undefined }) {
  if (instance !== undefined) {
    return (
      <Badge variant="secondary" className="text-xs">
        {instance}
      </Badge>
    );
  }
  return <span className="text-muted-foreground">-</span>;
}

function SourceBadge({ source }: { source: number }) {
  return (
    <Badge variant="outline" className="text-xs">
      {source}
    </Badge>
  );
}

/** Format a message timestamp as "HH:MM:SS.mmm" (24-hour, zero-padded). */
function formatCANTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  const timeStr = date.toLocaleTimeString([], {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
  const ms = date.getMilliseconds().toString().padStart(3, '0')
  return `${timeStr}.${ms}`
}

/** Format a CAN data payload as space-separated uppercase hex bytes. */
function formatCANData(data: number[]): string {
  return data.map(byte => byte.toString(16).padStart(2, '0').toUpperCase()).join(' ')
}

/** Column definitions for the live CAN message table (module scope: no recreation per render). */
function buildCANMessageColumns(): VirtualizedTableColumn<CANMessage>[] {
  return [
    {
      id: 'timestamp',
      header: 'Time',
      width: 100,
      className: 'font-mono text-xs',
      accessor: (message) => formatCANTimestamp(message.timestamp)
    },
    {
      id: 'interface',
      header: 'Interface',
      width: 70,
      className: 'text-center',
      accessor: (message) => message.interface || 'can0'
    },
    {
      id: 'pgn',
      header: 'PGN',
      width: 80,
      accessor: (message) => renderPGNBadge(message.pgn)
    },
    {
      id: 'description',
      header: 'Description',
      width: 200,
      accessor: (message) => renderDescriptionCell(message.pgn)
    },
    {
      id: 'instance',
      header: 'Inst',
      width: 60,
      className: 'text-center',
      accessor: (message) => renderInstanceCell(message.instance)
    },
    {
      id: 'source',
      header: 'Src',
      width: 60,
      className: 'text-center',
      accessor: (message) => renderSourceBadge(message.source)
    },
    {
      id: 'data',
      header: 'Data',
      width: 200,
      className: 'font-mono text-xs',
      accessor: (message) => formatCANData(message.data)
    },
    {
      id: 'length',
      header: 'Len',
      width: 50,
      className: 'text-center text-xs',
      accessor: (message) => message.data.length
    }
  ]
}

/**
 * Enhanced CAN message table with virtualization
 */
function CANMessageTable({
  messages,
  isPaused,
  emptyMessage,
}: Readonly<{
  messages: CANMessage[]
  isPaused: boolean
  emptyMessage?: string
}>) {
  const { visibleData, totalItems = 0 } = useVirtualizedTable({
    data: messages,
    maxItems: 5000,
    autoScroll: !isPaused
  })

  const columns = buildCANMessageColumns()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconActivity className="h-5 w-5" />
          Live CAN Messages
          {isPaused && <Badge variant="secondary">Paused</Badge>}
        </CardTitle>
        <CardDescription className="flex items-center justify-between">
          <span>Real-time CAN bus traffic monitoring ({totalItems.toLocaleString()} messages)</span>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <VirtualizedTable
          data={visibleData}
          columns={columns}
          height={400}
          itemHeight={40}
          emptyMessage={isPaused ? "Message capture paused" : emptyMessage ?? "No messages received"}
          getRowKey={(message, index) => `${message.timestamp}-${index}`}
          className={visibleData.some(m => m.error) ? "has-errors" : ""}
        />
      </CardContent>
    </Card>
  )
}

/**
 * CAN bus health component
 */
function CANBusHealth() {
  const { data: metrics, isLoading } = useCANMetrics()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-2 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (!metrics) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">CAN Bus Health</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Health metrics unavailable
          </p>
        </CardContent>
      </Card>
    )
  }

  const busLoadPercentage = Math.round((metrics.messageRate / 1000) * 100) // Assuming 1000 msg/s max
  const errorRatePercentage = metrics.totalMessages > 0
    ? Math.round((metrics.errorCount / metrics.totalMessages) * 100)
    : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">CAN Bus Health</CardTitle>
        <CardDescription>Real-time bus performance metrics</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Bus Load</span>
            <span>{busLoadPercentage}%</span>
          </div>
          <Progress value={busLoadPercentage} />
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Error Rate</span>
            <span>{errorRatePercentage}%</span>
          </div>
          <Progress
            value={errorRatePercentage}
            className={errorRatePercentage > 5 ? "text-destructive" : ""}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-muted-foreground">Messages/sec</div>
            <div className="font-medium">{metrics.messageRate.toFixed(1)}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Uptime</div>
            <div className="font-medium">{Math.round(metrics.uptime / 60)}m</div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/** Human-readable label for the sniffer socket state shown in the disconnected-state card. */
function websocketStatusLabel(state: WebSocketState): string {
  if (state === "connecting") return "still connecting"
  if (state === "error") return "down"
  return "not connected"
}

/**
 * Main CAN Sniffer page component
 */
export default function CANSniffer() {
  const [isPaused, setIsPaused] = useState(false)
  const [maxMessages] = useState(1000)
  const [messages, setMessages] = useState<CANMessage[]>([])
  const { reason, retry } = useCoachConnection()

  // Bound the initial skeleton state: after the grace window, show an
  // explicit connection/empty state instead of skeletons-forever.
  const [graceExpired, setGraceExpired] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setGraceExpired(true), INITIAL_LOAD_GRACE_MS)
    return () => clearTimeout(timer)
  }, [])

  // WebSocket connection for real-time CAN messages.
  // The generic `<CANMessage>` opts into a typed callback; payloads are
  // still untrusted JSON at the wire — narrow further if/when the schema
  // is validated server-side.
  const { isConnected, state: wsState, error: wsError, connect } = useCANScanWebSocket<CANMessage>({
    autoConnect: !isPaused,
    onMessage: (message: CANMessage) => {
      if (!isPaused) {
        setMessages(prev => {
          const newMessages = [...prev, message]
          // Keep only the last maxMessages
          return newMessages.slice(-maxMessages)
        })
      }
    }
  })

  const messageArray = messages

  // Track when we started listening on a live connection, so an empty
  // table can honestly say "no traffic observed since HH:MM:SS".
  const [listeningSince, setListeningSince] = useState<Date | null>(null)
  useEffect(() => {
    if (isConnected) {
      setListeningSince((prev) => prev ?? new Date())
    } else {
      setListeningSince(null)
    }
  }, [isConnected])

  const handleClearMessages = () => {
    setMessages([])
  }

  const error = wsError

  // Genuine initial load only: sniffer socket still coming up, nothing
  // received yet, and we're within the bounded grace window.
  const isInitialLoad = !isConnected && messages.length === 0 && !graceExpired && !error

  if (isInitialLoad) {
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex justify-between items-center">
            <div>
              <Skeleton className="h-4 w-96" />
            </div>
            <div className="flex gap-2">
              <Skeleton className="h-10 w-24" />
              <Skeleton className="h-10 w-24" />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <Skeleton className="h-4 w-24" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-8 w-16 mb-1" />
                  <Skeleton className="h-3 w-32" />
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
              <Skeleton className="h-4 w-64" />
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </AppLayout>
    )
  }

  // WebSocket is not connected (and the grace window elapsed): show an
  // explicit disconnected state instead of skeletons or an empty table.
  if (!isConnected && !isPaused && !error) {
    const websocketLabel = websocketStatusLabel(wsState)
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <Card>
            <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
              <IconPlugConnectedX className="h-12 w-12 text-muted-foreground" />
              <div className="space-y-1">
                <p className="font-medium">
                  CAN sniffer requires the realtime connection — WebSocket is {websocketLabel}
                </p>
                <p className="text-sm text-muted-foreground">{reason}</p>
              </div>
              <Button
                onClick={() => {
                  retry()
                  connect()
                }}
                variant="outline"
                className="gap-2"
              >
                <IconRefresh className="h-4 w-4" />
                Retry Connection
              </Button>
            </CardContent>
          </Card>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    // Extract error details for better user messaging
    const getErrorDetails = () => {
      if (error && typeof error === 'object' && 'statusCode' in error && typeof (error as { statusCode?: number }).statusCode === 'number') {
        // Check for specific API error types
        const statusCode = (error as { statusCode: number }).statusCode;

        switch (statusCode) {
          case 404:
            return {
              title: "CAN Feature Disabled",
              message: "The CAN interface feature is currently disabled in the system configuration.",
              isConnectionError: false,
              showRetry: false,
              troubleshooting: [
                "Contact your system administrator to enable the CAN interface feature",
                "Check the system configuration settings"
              ]
            };
          case 503:
            return {
              title: "CAN Bus Connection Error",
              message: "Failed to connect to CAN bus interface. No interfaces are available or connected.",
              isConnectionError: true,
              showRetry: true,
              troubleshooting: [
                "Ensure CAN interfaces are configured and connected",
                "Check that vCAN interfaces are available (if using virtual CAN)",
                "Verify physical CAN connections and termination",
                "Check interface status with 'ip link show' or 'ifconfig'"
              ]
            };
          default:
            return {
              title: "API Error",
              message: (error as { message?: string })?.message || "An unexpected error occurred while communicating with the server.",
              isConnectionError: false,
              showRetry: true,
              troubleshooting: ["Try refreshing the page", "Check your network connection"]
            };
        }
      }

      // Generic error handling for string errors or non-object errors
      return {
        title: "Connection Error",
        message: typeof error === 'string' ? error : "An error occurred while loading CAN data.",
        isConnectionError: true,
        showRetry: true,
        troubleshooting: ["Try refreshing the page", "Check your network connection"]
      };
    }

    const errorDetails = getErrorDetails();

    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <Alert variant="destructive">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertTitle>{errorDetails.title}</AlertTitle>
            <AlertDescription className="space-y-3">
              <p>{errorDetails.message}</p>

              {errorDetails.showRetry && (
                <div className="flex gap-2">
                  <Button onClick={() => void connect()} variant="outline" size="sm">
                    <IconRefresh className="h-4 w-4 mr-2" />
                    {errorDetails.isConnectionError ? "Retry Connection" : "Retry"}
                  </Button>
                </div>
              )}

              {errorDetails.troubleshooting.length > 0 && (
                <div className="text-sm text-muted-foreground">
                  <p><strong>Troubleshooting tips:</strong></p>
                  <ul className="list-disc list-inside space-y-1 mt-2">
                    {errorDetails.troubleshooting.map((tip, index) => (
                      <li key={index}>{tip}</li>
                    ))}
                  </ul>
                </div>
              )}
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
              Real-time CAN bus monitoring and message analysis
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => setIsPaused(!isPaused)}
              variant={isPaused ? "default" : "secondary"}
              className="gap-2"
            >
              {isPaused ? (
                <>
                  <IconPlayerPlay className="h-4 w-4" />
                  Resume
                </>
              ) : (
                <>
                  <IconPlayerPause className="h-4 w-4" />
                  Pause
                </>
              )}
            </Button>
            <Button onClick={handleClearMessages} variant="outline" className="gap-2">
              <IconTrash className="h-4 w-4" />
              Clear
            </Button>
            <Button onClick={() => void connect()} variant="outline" className="gap-2">
              <IconRefresh className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Statistics */}
        <CANStatistics messages={messageArray} />

        <div className="grid gap-8 lg:grid-cols-4">
          {/* Message Table - Takes 3/4 width */}
          <div className="lg:col-span-3">
            <CANMessageTable
              messages={messageArray}
              isPaused={isPaused}
              emptyMessage={
                listeningSince
                  ? `Listening — no CAN traffic observed since ${listeningSince.toLocaleTimeString()}`
                  : "No messages received"
              }
            />
          </div>

          {/* Sidebar - Takes 1/4 width */}
          <div className="space-y-6">
            <CANBusHealth />

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Message Buffer</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Buffer Size</span>
                    <span>{messageArray.length}/{maxMessages}</span>
                  </div>
                  <Progress value={(messageArray.length / maxMessages) * 100} />
                </div>
                <p className="text-xs text-muted-foreground">
                  Messages are automatically trimmed when buffer is full
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
