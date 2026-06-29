/**
 * System Status Page
 *
 * Comprehensive system health and status monitoring page.
 * Enhanced with interactive charts, trend indicators, and responsive design.
 * Consolidates health checks, CAN bus status, entity counts,
 * WebSocket status, and real-time performance metrics.
 */

import { AppLayout } from "@/components/app-layout"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { ChartConfig } from "@/components/ui/chart"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useEntities } from "@/hooks/useEntities"
import { useCANMetrics, useCANStatistics, useHealthStatus, useQueueStatus } from "@/hooks/useSystem"
import { useSystemAnalytics, useAcknowledgeAlert } from "@/hooks/useDashboard"
import { useIsMobile } from "@/hooks/use-mobile"
import { LoadingPatterns } from "@/components/loading-states"
import {
    OverallSystemStatusCard,
    ApplicationHealthSummaryCard,
    PerformanceMetricsSummaryCard,
    CANBusStatusSummaryCard,
    CANMetricsSummaryCard,
    ComponentHealthGrid,
    EventLogStreamCard
} from "@/components/system-status"
import {
    IconActivity,
    IconAlertCircle,
    IconCheck,
    IconChevronRight,
    IconCpu,
    IconDatabase,
    IconHelp,
    IconRefresh,
    IconRouter,
    IconServer,
    IconTrendingDown,
    IconTrendingUp,
    IconWifi,
    IconX
} from "@tabler/icons-react"
import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"
import { Link } from "react-router-dom"

// Generate sample CAN metrics data for demo purposes
const generateCANMetricsData = () => {
  const data = []
  const now = new Date()
  for (let i = 89; i >= 0; i--) {
    const date = new Date(now)
    date.setMinutes(date.getMinutes() - i)
    data.push({
      timestamp: date.toISOString(),
      messageRate: Math.floor(Math.random() * 100) + 50,
      errorRate: Math.floor(Math.random() * 5),
    })
  }
  return data
}

const chartConfig = {
  messageRate: {
    label: "Message Rate",
    color: "var(--primary)",
  },
  errorRate: {
    label: "Error Rate",
    color: "var(--destructive)",
  },
} satisfies ChartConfig

/**
 * Interactive CAN Metrics Chart
 */
function CANMetricsChart() {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState("30m")
  const [chartData] = React.useState(() => generateCANMetricsData())

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("10m")
    }
  }, [isMobile])

  const filteredData = React.useMemo(() => {
    const now = new Date()
    let minutesToSubtract = 30
    if (timeRange === "10m") minutesToSubtract = 10
    else if (timeRange === "60m") minutesToSubtract = 60

    const startTime = new Date(now)
    startTime.setMinutes(startTime.getMinutes() - minutesToSubtract)

    return chartData.filter(item => new Date(item.timestamp) >= startTime)
  }, [chartData, timeRange])

  const averageMessageRate = React.useMemo(() => {
    if (filteredData.length === 0) return 0
    return Math.round(filteredData.reduce((sum, item) => sum + item.messageRate, 0) / filteredData.length)
  }, [filteredData])

  const trendDirection = React.useMemo(() => {
    if (filteredData.length < 2) return 'neutral'
    const recent = filteredData.slice(-10).reduce((sum, item) => sum + item.messageRate, 0) / 10
    const earlier = filteredData.slice(0, 10).reduce((sum, item) => sum + item.messageRate, 0) / 10
    return recent > earlier ? 'up' : recent < earlier ? 'down' : 'neutral'
  }, [filteredData])

  return (
    <Card className="@container/card from-primary/5 to-card bg-gradient-to-t shadow-xs">
      <CardHeader>
        <CardTitle className="@[250px]/card:text-lg">CAN Bus Activity</CardTitle>
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            Real-time message rate and performance
          </span>
          <span className="@[540px]/card:hidden">Live CAN metrics</span>
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            value={timeRange}
            onValueChange={setTimeRange}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:!px-3 @[767px]/card:flex"
          >
            <ToggleGroupItem value="10m">10m</ToggleGroupItem>
            <ToggleGroupItem value="30m">30m</ToggleGroupItem>
            <ToggleGroupItem value="60m">1h</ToggleGroupItem>
          </ToggleGroup>
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger
              className="flex w-20 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden"
              size="sm"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="10m">10m</SelectItem>
              <SelectItem value="30m">30m</SelectItem>
              <SelectItem value="60m">1h</SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <div className="mb-4 flex items-center gap-4">
          <div>
            <div className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
              {averageMessageRate}
            </div>
            <div className="text-xs text-muted-foreground">msg/sec avg</div>
          </div>
          <Badge variant="outline" className="ml-auto">
            {trendDirection === 'up' && <IconTrendingUp className="mr-1 h-3 w-3" />}
            {trendDirection === 'down' && <IconTrendingDown className="mr-1 h-3 w-3" />}
            {trendDirection === 'up' ? 'Trending Up' : trendDirection === 'down' ? 'Trending Down' : 'Stable'}
          </Badge>
        </div>

        <ChartContainer
          config={chartConfig}
          className="aspect-auto h-[180px] w-full"
        >
          <AreaChart data={filteredData}>
            <defs>
              <linearGradient id="fillMessageRate" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-messageRate)" stopOpacity={1.0} />
                <stop offset="95%" stopColor="var(--color-messageRate)" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="timestamp"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={32}
              tickFormatter={(value) => {
                const date = new Date(value)
                return date.toLocaleTimeString("en-US", {
                  hour: "2-digit",
                  minute: "2-digit",
                })
              }}
            />
            <ChartTooltip
              cursor={false}
              defaultIndex={isMobile ? -1 : 5}
              content={
                <ChartTooltipContent
                  labelFormatter={(value) => {
                    return new Date(value).toLocaleTimeString("en-US", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  }}
                  indicator="dot"
                />
              }
            />
            <Area
              dataKey="messageRate"
              type="natural"
              fill="url(#fillMessageRate)"
              stroke="var(--color-messageRate)"
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

/**
 * Application Health Overview Card
 */
function ApplicationHealthCard() {
  const { data: health, isLoading, error, refetch } = useHealthStatus()

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy':
      case 'ok':
        return { icon: IconCheck, color: 'text-green-500' }
      case 'error':
      case 'failed':
        return { icon: IconX, color: 'text-red-500' }
      case 'degraded':
      case 'warning':
        return { icon: IconAlertCircle, color: 'text-amber-500' }
      default:
        return { icon: IconHelp, color: 'text-gray-500' }
    }
  }

  const formatFeatureName = (feature: string) => {
    return feature
      .replace(/_/g, ' ')
      .replace(/\b\w/g, l => l.toUpperCase())
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconServer className="size-5" />
            <Skeleton className="h-5 w-40" />
          </CardTitle>
          <CardDescription>
            <Skeleton className="h-4 w-60" />
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-16 w-full" />
          <Separator />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <IconX className="size-5" />
            Application Health
          </CardTitle>
          <CardDescription>System health monitoring and diagnostics</CardDescription>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <IconAlertCircle className="h-4 w-4" />
            <AlertTitle>Health Check Failed</AlertTitle>
            <AlertDescription>
              Unable to retrieve application health status. The health endpoint may be unavailable.
            </AlertDescription>
          </Alert>
          <Button
            onClick={() => void refetch()}
            variant="outline"
            className="mt-4"
          >
            <IconRefresh className="mr-2 h-4 w-4" />
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  const overallStatus = getStatusIcon(health?.status || 'unknown')
  const OverallIcon = overallStatus.icon

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconServer className="size-5" />
          Application Health
        </CardTitle>
        <CardDescription>System health monitoring and diagnostics</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Overall Status */}
        <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
          <div className="flex items-center gap-3">
            <OverallIcon className={`size-6 ${overallStatus.color}`} />
            <div>
              <div className="font-semibold">Overall System Status</div>
              <div className="text-sm text-muted-foreground">
                Application Health Check
              </div>
            </div>
          </div>
          <Badge
            variant={health?.status === "healthy" ? "default" :
                    health?.status === "degraded" ? "secondary" : "destructive"}
            className="text-sm px-3 py-1"
          >
            {health?.status?.toUpperCase() || "UNKNOWN"}
          </Badge>
        </div>

        <Separator />

        {/* Feature Status */}
        <div className="space-y-3">
          <h4 className="font-semibold text-sm">Feature Status</h4>

          {health?.features && Object.keys(health.features).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(health.features).map(([feature, status]) => {
                const statusIcon = getStatusIcon(status)
                const StatusIcon = statusIcon.icon

                return (
                  <div key={feature} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center gap-3">
                      <StatusIcon className={`size-4 ${statusIcon.color}`} />
                      <span className="font-medium">{formatFeatureName(feature)}</span>
                    </div>
                    <Badge
                      variant={status === "healthy" ? "default" : "secondary"}
                      className="text-xs"
                    >
                      {status}
                    </Badge>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-center py-6 text-muted-foreground">
              <IconHelp className="size-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No feature status information available</p>
            </div>
          )}

          {/* Unhealthy Features */}
          {health?.unhealthy_features && Object.keys(health.unhealthy_features).length > 0 && (
            <Alert variant="destructive">
              <IconAlertCircle className="h-4 w-4" />
              <AlertTitle>System Issues Detected</AlertTitle>
              <AlertDescription>
                <div className="mt-2 space-y-1">
                  {Object.entries(health.unhealthy_features).map(([feature, status]) => (
                    <div key={feature} className="text-sm">
                      <strong>{formatFeatureName(feature)}:</strong> {status}
                    </div>
                  ))}
                </div>
              </AlertDescription>
            </Alert>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * CAN Bus Status Card
 */
function CANBusStatusCard() {
  const { data: canStats, isLoading, error, refetch } = useCANStatistics()
  const { data: queueStatus } = useQueueStatus()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconWifi className="size-5" />
            <Skeleton className="h-5 w-32" />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
          <Separator />
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <IconWifi className="size-5" />
            CAN Bus Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <IconAlertCircle className="h-4 w-4" />
            <AlertTitle>CAN Bus Unavailable</AlertTitle>
            <AlertDescription>
              Unable to connect to CAN bus interface. Check that CAN interfaces are configured and active.
            </AlertDescription>
          </Alert>
          <Button
            onClick={() => void refetch()}
            variant="outline"
            className="mt-4"
          >
            <IconRefresh className="mr-2 h-4 w-4" />
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  const totalMessages = canStats?.total_messages || 0
  const totalErrors = canStats?.total_errors || 0
  const interfaces = canStats?.interfaces || {}
  const interfaceCount = Object.keys(interfaces).length

  const errorRate = totalMessages > 0 ? (totalErrors / totalMessages) * 100 : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconWifi className="size-5" />
          CAN Bus Status
        </CardTitle>
        <CardDescription>Real-time CAN network monitoring</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary Statistics */}
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold">{totalMessages.toLocaleString()}</div>
            <div className="text-xs text-muted-foreground">Total Messages</div>
          </div>
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-2xl font-bold">{interfaceCount}</div>
            <div className="text-xs text-muted-foreground">Active Interfaces</div>
          </div>
        </div>

        <Separator />

        {/* Interface Details */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold text-sm">Interface Status</h4>
            <Button asChild variant="outline" size="sm">
              <Link to="/can-sniffer">
                View Details
                <IconChevronRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </div>

          {interfaceCount > 0 ? (
            <div className="space-y-2">
              {Object.entries(interfaces).map(([name, stats]) => (
                <div key={name} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="flex items-center gap-3">
                    <IconRouter className="size-4 text-muted-foreground" />
                    <div>
                      <div className="font-medium text-sm">{name}</div>
                      <div className="text-xs text-muted-foreground">
                        RX: {stats.rx_count || 0} | TX: {stats.tx_count || 0}
                      </div>
                    </div>
                  </div>
                  <Badge variant={stats.state === 'UP' ? 'default' : 'secondary'}>
                    {stats.state || 'Unknown'}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              <IconWifi className="size-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No CAN interfaces found</p>
            </div>
          )}
        </div>

        {/* Queue Status */}
        {queueStatus && (
          <>
            <Separator />
            <div className="space-y-2">
              <h4 className="font-semibold text-sm">Message Queue</h4>
              <div className="flex items-center justify-between p-2 bg-muted/50 rounded">
                <span className="text-sm">Queue Length</span>
                <Badge variant="outline">
                  {queueStatus.length}/{queueStatus.maxsize === "unbounded" ? "∞" : queueStatus.maxsize}
                </Badge>
              </div>
            </div>
          </>
        )}

        {/* Error Rate */}
        {totalMessages > 0 && (
          <>
            <Separator />
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Error Rate</span>
                <span className={errorRate > 5 ? "text-destructive" : "text-muted-foreground"}>
                  {errorRate.toFixed(2)}%
                </span>
              </div>
              <Progress
                value={Math.min(errorRate, 100)}
                className={errorRate > 5 ? "text-destructive" : ""}
              />
              {errorRate > 5 && (
                <p className="text-xs text-destructive">
                  High error rate detected - check CAN bus connections
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Entity Statistics Card
 */
function EntityStatisticsCard() {
  const { data: entities, isLoading, error, refetch } = useEntities()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconCpu className="size-5" />
            <Skeleton className="h-5 w-32" />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Separator />
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <IconCpu className="size-5" />
            Entity Statistics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <IconAlertCircle className="h-4 w-4" />
            <AlertTitle>Entity Data Unavailable</AlertTitle>
            <AlertDescription>
              Unable to load entity information from the system.
            </AlertDescription>
          </Alert>
          <Button
            onClick={() => void refetch()}
            variant="outline"
            className="mt-4"
          >
            <IconRefresh className="mr-2 h-4 w-4" />
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  const entityArray = entities?.entities ?? []
  const totalEntities = entityArray.length

  // Count entities by type
  const entityCounts = entityArray.reduce((acc, entity) => {
    acc[entity.device_type] = (acc[entity.device_type] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const formatEntityType = (type: string) => {
    return type
      .replace(/_/g, ' ')
      .replace(/\b\w/g, l => l.toUpperCase())
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconCpu className="size-5" />
          Entity Statistics
        </CardTitle>
        <CardDescription>Connected devices and sensors overview</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Total Count */}
        <div className="text-center p-3 bg-muted/50 rounded-lg">
          <div className="text-2xl font-bold">{totalEntities}</div>
          <div className="text-xs text-muted-foreground">Total Entities</div>
        </div>

        <Separator />

        {/* Entity Types */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold text-sm">Entity Types</h4>
            <Button asChild variant="outline" size="sm">
              <Link to="/lights">
                Manage Entities
                <IconChevronRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </div>

          {Object.keys(entityCounts).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(entityCounts).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between p-2 border rounded">
                  <span className="text-sm font-medium">{formatEntityType(type)}</span>
                  <Badge variant="outline">{String(count)}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              <IconCpu className="size-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No entities found</p>
              <p className="text-xs">Check your device mapping configuration</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Performance Metrics Card
 */
function PerformanceMetricsCard() {
  const { data: canMetrics, isLoading } = useCANMetrics()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconActivity className="size-5" />
            <Skeleton className="h-5 w-32" />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!canMetrics) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconActivity className="size-5" />
            Performance Metrics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground">
            <IconActivity className="size-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Metrics unavailable</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const messageRate = canMetrics.messageRate || 0
  const uptime = canMetrics.uptime || 0
  const uptimeHours = Math.floor(uptime / 3600)
  const uptimeMinutes = Math.floor((uptime % 3600) / 60)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconActivity className="size-5" />
          Performance Metrics
        </CardTitle>
        <CardDescription>Real-time system performance</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-xl font-bold">{messageRate.toFixed(1)}</div>
            <div className="text-xs text-muted-foreground">Messages/sec</div>
          </div>
          <div className="text-center p-3 bg-muted/50 rounded-lg">
            <div className="text-xl font-bold">
              {uptimeHours > 0 ? `${uptimeHours}h ${uptimeMinutes}m` : `${uptimeMinutes}m`}
            </div>
            <div className="text-xs text-muted-foreground">Uptime</div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * System Alerts Card
 */
function SystemAlertsCard() {
  const { data: analytics, isLoading, error } = useSystemAnalytics()
  const acknowledgeAlert = useAcknowledgeAlert()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconAlertCircle className="size-5" />
            <Skeleton className="h-5 w-32" />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <LoadingPatterns.ListItems count={3} />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <IconAlertCircle className="size-5" />
            System Alerts
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Unable to load system alerts
          </p>
        </CardContent>
      </Card>
    )
  }

  const alerts = analytics?.alerts || []
  const activeAlerts = alerts.filter(alert => !alert.acknowledged)
  const acknowledgedAlerts = alerts.filter(alert => alert.acknowledged)

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-600 bg-red-50 border-red-200'
      case 'error': return 'text-red-500 bg-red-50 border-red-200'
      case 'warning': return 'text-yellow-600 bg-yellow-50 border-yellow-200'
      case 'info': return 'text-blue-600 bg-blue-50 border-blue-200'
      default: return 'text-gray-600 bg-gray-50 border-gray-200'
    }
  }

  const formatTimeAgo = (timestamp: string) => {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`

    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`

    const diffDays = Math.floor(diffHours / 24)
    return `${diffDays}d ago`
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconAlertCircle className="size-5" />
          System Alerts
          {activeAlerts.length > 0 && (
            <Badge variant="destructive">{activeAlerts.length}</Badge>
          )}
        </CardTitle>
        <CardDescription>Active alerts and notifications</CardDescription>
      </CardHeader>
      <CardContent>
        {alerts.length === 0 ? (
          <div className="text-center py-6">
            <IconCheck className="size-8 mx-auto mb-2 text-green-500" />
            <p className="text-sm text-muted-foreground">No active alerts</p>
            <p className="text-xs text-muted-foreground">System is operating normally</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Active Alerts */}
            {activeAlerts.length > 0 && (
              <div>
                <h4 className="font-medium text-sm mb-3">Active Alerts</h4>
                <div className="space-y-2">
                  {activeAlerts.map((alert) => (
                    <div
                      key={alert.alert_id}
                      className={`p-3 rounded-lg border ${getSeverityColor(alert.severity)}`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-sm">{alert.message}</span>
                            <Badge variant="outline" className="text-xs">
                              {alert.severity}
                            </Badge>
                          </div>
                          <div className="text-xs opacity-75">
                            Triggered {formatTimeAgo(alert.triggered_at)} •
                            Current: {alert.current_value.toFixed(2)} •
                            Threshold: {alert.threshold}
                          </div>
                        </div>
                        <Button
                          onClick={() => void acknowledgeAlert.mutate(alert.alert_id)}
                          size="sm"
                          variant="ghost"
                          className="ml-2 text-xs"
                          disabled={acknowledgeAlert.isPending}
                        >
                          Acknowledge
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Acknowledged Alerts */}
            {acknowledgedAlerts.length > 0 && (
              <div>
                <h4 className="font-medium text-sm mb-3 text-muted-foreground">
                  Acknowledged ({acknowledgedAlerts.length})
                </h4>
                <div className="space-y-2">
                  {acknowledgedAlerts.slice(0, 3).map((alert) => (
                    <div
                      key={alert.alert_id}
                      className="p-2 rounded border border-gray-200 bg-gray-50 opacity-60"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm">{alert.message}</span>
                        <span className="text-xs text-muted-foreground">
                          {formatTimeAgo(alert.triggered_at)}
                        </span>
                      </div>
                    </div>
                  ))}
                  {acknowledgedAlerts.length > 3 && (
                    <p className="text-xs text-muted-foreground text-center">
                      +{acknowledgedAlerts.length - 3} more acknowledged alerts
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* System Recommendations */}
            {analytics?.recommendations && analytics.recommendations.length > 0 && (
              <div className="pt-3 border-t">
                <h4 className="font-medium text-sm mb-2">Recommendations</h4>
                <ul className="space-y-1">
                  {analytics.recommendations.map((recommendation, index) => (
                    <li key={index} className="text-xs text-muted-foreground flex items-start gap-2">
                      <IconHelp className="size-3 mt-0.5 flex-shrink-0" />
                      {recommendation}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Main System Status Page
 */
export default function SystemStatus() {
  return (
    <AppLayout>
      <div className="flex-1 space-y-6 p-4 pt-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Operations Monitoring Center</h1>
            <p className="text-muted-foreground">
              Real-time system analytics, performance metrics, and diagnostic tools
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <IconActivity className="h-4 w-4" />
            <span>For quick status, check the sidebar indicator</span>
          </div>
        </div>

        {/* Row 1: Golden Signal Row - Level 1 & 2 of Information Pyramid */}
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          <OverallSystemStatusCard />
          <ApplicationHealthSummaryCard />
          <PerformanceMetricsSummaryCard />
          <CANBusStatusSummaryCard />
        </div>

        {/* Two-Column Layout: Primary (Problems) vs Secondary (Context) */}
        <div className="grid gap-6 grid-cols-1 lg:grid-cols-3">
          {/* LEFT COLUMN (2/3 width): Primary - "What needs attention now?" */}
          <div className="lg:col-span-2 space-y-6">
            {/* System Alerts - Highest priority after Golden Signals */}
            <SystemAlertsCard />

            {/* Event Log Stream - Provides immediate context for alerts */}
            <EventLogStreamCard />
          </div>

          {/* RIGHT COLUMN (1/3 width): Secondary - "What is the overall state?" */}
          <div className="space-y-6">
            {/* Entity Statistics - Context for overall activity */}
            <EntityStatisticsCard />

            {/* Component Health Grid - Which part of the system has issues */}
            <ComponentHealthGrid />

            {/* CAN Metrics Summary - Compact visualization with drill-down */}
            <CANMetricsSummaryCard />

            {/* System Management - Action-oriented tools */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IconServer className="size-5" />
                  System Management
                </CardTitle>
                <CardDescription>Diagnostic tools</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2">
                  <Button asChild variant="outline" size="sm" className="justify-start">
                    <Link to="/can-sniffer">
                      <IconWifi className="mr-2 h-4 w-4" />
                      CAN Monitor
                    </Link>
                  </Button>
                  <Button asChild variant="outline" size="sm" className="justify-start">
                    <Link to="/logs">
                      <IconDatabase className="mr-2 h-4 w-4" />
                      System Logs
                    </Link>
                  </Button>
                  <Button asChild variant="outline" size="sm" className="justify-start">
                    <Link to="/unknown-pgns">
                      <IconAlertCircle className="mr-2 h-4 w-4" />
                      Unknown PGNs
                    </Link>
                  </Button>
                  <Button asChild variant="outline" size="sm" className="justify-start">
                    <Link to="/unmapped-entries">
                      <IconHelp className="mr-2 h-4 w-4" />
                      Unmapped Data
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
