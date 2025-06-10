/**
 * CAN Sniffer Page
 *
 * Real-time CAN bus monitoring and packet analysis.
 * Shows live CAN traffic with filtering and analysis capabilities.
 */

import type { CANMessage } from "@/api/types"
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
import { useCANMetrics, useCANStatistics } from "@/hooks/useSystem"
import { useVirtualizedTable } from "@/hooks/useVirtualizedTable"
import { useCANScanWebSocket } from "@/hooks/useWebSocket"
import {
    IconActivity,
    IconAlertTriangle,
    IconFilter,
    IconPlayerPause,
    IconPlayerPlay,
    IconRefresh,
    IconTrash
} from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"
import { useMemo, useState } from "react"

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
    total: (enhancedStats as any)?.total_messages ?? (backendStats as any)?.total_messages ?? messages.length,
    errorMessages: (enhancedStats as any)?.total_errors ?? (backendStats as any)?.total_errors ?? messages.filter(msg => msg.error).length,
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

/**
 * Enhanced CAN message table with virtualization
 */
function CANMessageTable({ messages, isPaused }: { messages: CANMessage[]; isPaused: boolean }) {
  const { visibleData, totalItems = 0 } = useVirtualizedTable({
    data: messages,
    maxItems: 5000,
    autoScroll: !isPaused
  })

  const formatTimestamp = (timestamp: string) => {
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

  const formatData = (data: number[]) => {
    return data.map(byte => byte.toString(16).padStart(2, '0').toUpperCase()).join(' ')
  }

  const getPGNDescription = (pgn: string) => {
    // This would normally come from the RV-C spec database
    const knownPGNs: Record<string, string> = {
      '1FFFF': 'Device Control',
      '1FFF0': 'Light Control',
      '1FFE0': 'Tank Status',
      '1FFD0': 'Temperature',
      // Add more as needed
    }
    return knownPGNs[pgn] || 'Unknown'
  }

  // Define columns for virtualized table
  const columns: VirtualizedTableColumn<CANMessage>[] = [
    {
      id: 'timestamp',
      header: 'Time',
      width: 100,
      className: 'font-mono text-xs',
      accessor: (message) => formatTimestamp(message.timestamp)
    },
    {
      id: 'pgn',
      header: 'PGN',
      width: 80,
      accessor: (message) => (
        <Badge variant="outline" className="font-mono text-xs">
          {message.pgn}
        </Badge>
      )
    },
    {
      id: 'description',
      header: 'Description',
      width: 200,
      accessor: (message) => (
        <span className="text-sm">{getPGNDescription(message.pgn)}</span>
      )
    },
    {
      id: 'instance',
      header: 'Inst',
      width: 60,
      className: 'text-center',
      accessor: (message) =>
        message.instance !== undefined ? (
          <Badge variant="secondary" className="text-xs">
            {message.instance}
          </Badge>
        ) : (
          <span className="text-muted-foreground">-</span>
        )
    },
    {
      id: 'source',
      header: 'Src',
      width: 60,
      className: 'text-center',
      accessor: (message) => (
        <Badge variant="outline" className="text-xs">
          {message.source}
        </Badge>
      )
    },
    {
      id: 'data',
      header: 'Data',
      width: 200,
      className: 'font-mono text-xs',
      accessor: (message) => formatData(message.data)
    },
    {
      id: 'length',
      header: 'Len',
      width: 50,
      className: 'text-center text-xs',
      accessor: (message) => message.data.length
    }
  ]

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
          emptyMessage={isPaused ? "Message capture paused" : "No messages received"}
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

/**
 * Main CAN Sniffer page component
 */
export default function CANSniffer() {
  const [isPaused, setIsPaused] = useState(false)
  const [maxMessages] = useState(1000)
  const [messages, setMessages] = useState<CANMessage[]>([])

  // WebSocket connection for real-time CAN messages
  const { isConnected, error: wsError, connect } = useCANScanWebSocket({
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

  const handleClearMessages = () => {
    setMessages([])
  }

  // Loading state is based on WebSocket connection status
  const isLoading = !isConnected && messages.length === 0
  const error = wsError

  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex justify-between items-center">
            <div>
              <Skeleton className="h-8 w-48 mb-2" />
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

  if (error) {
    // Extract error details for better user messaging
    const getErrorDetails = () => {
      if (error && typeof error === 'object' && (error as any) instanceof Error) {
        // Check for specific API error types
        if ('statusCode' in error && typeof (error as { statusCode?: number }).statusCode === 'number') {
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
                message: (error as any)?.message || "An unexpected error occurred while communicating with the server.",
                isConnectionError: false,
                showRetry: true,
                troubleshooting: ["Try refreshing the page", "Check your network connection"]
              };
          }
        }

        // Generic error handling
        return {
          title: "Connection Error",
          message: (error as any)?.message || "An error occurred while loading CAN data.",
          isConnectionError: true,
          showRetry: true,
          troubleshooting: ["Try refreshing the page", "Check your network connection"]
        };
      }

      // Fallback for unknown error types
      return {
        title: "Unknown Error",
        message: "An unexpected error occurred.",
        isConnectionError: false,
        showRetry: true,
        troubleshooting: ["Try refreshing the page"]
      };
    };

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
                  <Button onClick={connect} variant="outline" size="sm">
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
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">CAN Sniffer</h1>
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
            <Button onClick={connect} variant="outline" className="gap-2">
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
            <CANMessageTable messages={messageArray} isPaused={isPaused} />
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
