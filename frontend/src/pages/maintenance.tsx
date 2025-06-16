/**
 * Predictive Maintenance Dashboard
 *
 * Component health tracking, trend analysis, and maintenance recommendations
 * following Gemini's hybrid edge/cloud architecture approach.
 */

import { AppLayout } from "@/components/app-layout"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { usePredictiveMaintenance } from "@/hooks/usePredictiveMaintenance"
import {
    IconActivity,
    IconAlertCircle,
    IconAlertTriangle,
    IconBattery,
    IconCalendar,
    IconCheck,
    IconClock,
    IconEngine,
    IconRefresh,
    IconShield,
    IconTool,
    IconTrendingDown,
    IconTrendingUp,
    IconUsers,
} from "@tabler/icons-react"
import { useState } from "react"

/**
 * Component Health Status Badge
 */
function HealthStatusBadge({ status }: { status: string }) {
  const variants = {
    healthy: { variant: "default" as const, icon: IconShield, label: "Healthy", color: "text-green-500" },
    watch: { variant: "secondary" as const, icon: IconClock, label: "Watch", color: "text-blue-500" },
    advise: { variant: "secondary" as const, icon: IconAlertTriangle, label: "Advise", color: "text-amber-500" },
    alert: { variant: "destructive" as const, icon: IconAlertCircle, label: "Alert", color: "text-red-500" },
  }

  const config = variants[status as keyof typeof variants] || variants.healthy
  const Icon = config.icon

  return (
    <Badge variant={config.variant} className="gap-1">
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  )
}

/**
 * Component Type Icon
 */
function ComponentTypeIcon({ type }: { type: string }) {
  const icons = {
    battery: IconBattery,
    generator: IconEngine,
    hvac: IconActivity,
    pump: IconActivity,
    slide_out: IconTool,
    lighting: IconActivity,
    engine: IconEngine,
    transmission: IconEngine,
  }

  const Icon = icons[type as keyof typeof icons] || IconTool
  return <Icon className="h-5 w-5" />
}

/**
 * Trend Direction Icon
 */
function TrendIcon({ direction }: { direction: string }) {
  switch (direction) {
    case "improving":
      return <IconTrendingUp className="h-4 w-4 text-green-500" />
    case "degrading":
      return <IconTrendingDown className="h-4 w-4 text-red-500" />
    default:
      return <IconActivity className="h-4 w-4 text-blue-500" />
  }
}

/**
 * RV Health Overview Card
 */
function RVHealthOverviewCard() {
  const { healthOverview, isLoading, error } = usePredictiveMaintenance()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconShield className="h-5 w-5" />
            <Skeleton className="h-5 w-32" />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (error || !healthOverview) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <IconAlertCircle className="h-5 w-5" />
            RV Health Overview
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Unable to load health overview</p>
        </CardContent>
      </Card>
    )
  }

  const getOverallStatusColor = (status: string) => {
    switch (status) {
      case "healthy": return "text-green-500"
      case "watch": return "text-blue-500"
      case "advise": return "text-amber-500"
      case "alert": return "text-red-500"
      default: return "text-muted-foreground"
    }
  }

  return (
    <Card className="bg-gradient-to-t from-primary/5 to-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconShield className="h-5 w-5" />
          RV Health Overview
        </CardTitle>
        <CardDescription>Overall system health and maintenance status</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="text-center">
            <div className="text-3xl font-bold mb-2">
              {healthOverview.overall_health_score.toFixed(1)}%
            </div>
            <div className={`text-lg font-medium capitalize mb-2 ${getOverallStatusColor(healthOverview.status)}`}>
              {healthOverview.status}
            </div>
            <Progress value={healthOverview.overall_health_score} className="w-full mb-4" />
            <div className="text-sm text-muted-foreground">
              Monitoring {healthOverview.components_monitored} components
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mt-6">
            <div className="text-center p-3 bg-background/50 rounded-lg">
              <div className="text-xl font-semibold text-red-500">
                {healthOverview.critical_alerts}
              </div>
              <div className="text-xs text-muted-foreground">Critical Alerts</div>
            </div>
            <div className="text-center p-3 bg-background/50 rounded-lg">
              <div className="text-xl font-semibold text-amber-500">
                {healthOverview.active_recommendations}
              </div>
              <div className="text-xs text-muted-foreground">Recommendations</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Component Health List
 */
function ComponentHealthList({ systemType }: { systemType?: string }) {
  const filters = systemType ? { systemType } : undefined;
  const { componentHealth, isLoading, error } = usePredictiveMaintenance(filters);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 p-4 border rounded-lg">
            <Skeleton className="h-10 w-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
            <Skeleton className="h-6 w-16" />
          </div>
        ))}
      </div>
    )
  }

  if (error || !componentHealth) {
    return (
      <Alert variant="destructive">
        <IconAlertCircle className="h-4 w-4" />
        <AlertTitle>Error Loading Components</AlertTitle>
        <AlertDescription>
          Unable to load component health data. Please check your connection and try again.
        </AlertDescription>
      </Alert>
    )
  }

  if (componentHealth.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <IconShield className="h-12 w-12 mx-auto mb-4 text-green-500" />
          <h3 className="text-lg font-semibold mb-2">No Components Found</h3>
          <p className="text-muted-foreground">
            No components match the current filter criteria.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      {componentHealth.map((component) => (
        <Card key={component.component_id}>
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-1">
                <ComponentTypeIcon type={component.component_type} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h4 className="font-medium text-sm leading-5 mb-1">
                      {component.component_name}
                    </h4>
                    <div className="flex items-center gap-2 mb-2">
                      <Progress value={component.health_score} className="flex-1 h-2" />
                      <span className="text-sm font-medium tabular-nums">
                        {component.health_score.toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <TrendIcon direction={component.trend_direction} />
                        <span className="capitalize">{component.trend_direction}</span>
                      </div>
                      {component.usage_hours && (
                        <div>{component.usage_hours.toFixed(1)}h usage</div>
                      )}
                      {component.anomaly_count > 0 && (
                        <div className="text-amber-600">
                          {component.anomaly_count} anomalies
                        </div>
                      )}
                      {component.remaining_useful_life_days && (
                        <div>
                          {component.remaining_useful_life_days} days remaining
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex-shrink-0 flex flex-col items-end gap-2">
                    <HealthStatusBadge status={component.status} />
                    {component.next_maintenance_due && (
                      <div className="text-xs text-muted-foreground">
                        Due: {new Date(component.next_maintenance_due).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

/**
 * Maintenance Recommendations List
 */
function MaintenanceRecommendationsList({ level }: { level?: string }) {
  const filters = level ? { recommendationLevel: level } : undefined;
  const { recommendations, acknowledgeRecommendation, isLoading, error } = usePredictiveMaintenance(filters);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="p-4 border rounded-lg">
            <div className="flex items-start gap-3">
              <Skeleton className="h-4 w-4 rounded-full mt-1" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-1/2" />
              </div>
              <Skeleton className="h-8 w-20" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (error || !recommendations) {
    return (
      <Alert variant="destructive">
        <IconAlertCircle className="h-4 w-4" />
        <AlertTitle>Error Loading Recommendations</AlertTitle>
        <AlertDescription>
          Unable to load maintenance recommendations. Please check your connection and try again.
        </AlertDescription>
      </Alert>
    )
  }

  if (recommendations.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <IconCheck className="h-12 w-12 mx-auto mb-4 text-green-500" />
          <h3 className="text-lg font-semibold mb-2">No Active Recommendations</h3>
          <p className="text-muted-foreground">
            All maintenance recommendations have been addressed or no issues detected.
          </p>
        </CardContent>
      </Card>
    )
  }

  const handleAcknowledge = (recommendationId: string) => {
    acknowledgeRecommendation.mutate(recommendationId)
  }

  const getPriorityColor = (priority: number) => {
    if (priority === 1) return "text-red-500"
    if (priority === 2) return "text-amber-500"
    return "text-blue-500"
  }

  return (
    <div className="space-y-3">
      {recommendations.map((rec) => (
        <Card key={rec.recommendation_id}>
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-1">
                <HealthStatusBadge status={rec.level} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h4 className="font-medium text-sm leading-5 mb-1">
                      {rec.title}
                    </h4>
                    <p className="text-sm text-muted-foreground mb-2">
                      {rec.message}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <IconUsers className="h-3 w-3" />
                        {rec.component_name}
                      </div>
                      <div className={`flex items-center gap-1 font-medium ${getPriorityColor(rec.priority)}`}>
                        Priority {rec.priority}
                      </div>
                      {rec.estimated_cost && (
                        <div>${rec.estimated_cost.toFixed(0)}</div>
                      )}
                      {rec.estimated_time_hours && (
                        <div>{rec.estimated_time_hours}h</div>
                      )}
                      {rec.urgency_days && (
                        <div className="flex items-center gap-1">
                          <IconCalendar className="h-3 w-3" />
                          {rec.urgency_days} days
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex-shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleAcknowledge(rec.recommendation_id)}
                      disabled={acknowledgeRecommendation.isPending || !!rec.acknowledged_at}
                      className="gap-2"
                    >
                      <IconCheck className="h-3 w-3" />
                      {rec.acknowledged_at ? 'Acknowledged' : 'Acknowledge'}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

/**
 * System Health Breakdown Chart
 */
function SystemHealthBreakdownCard() {
  const { healthOverview, isLoading, error } = usePredictiveMaintenance()

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>System Health Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-16" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error || !healthOverview?.system_health_breakdown) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>System Health Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center">
            Unable to load system breakdown
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconActivity className="h-5 w-5" />
          System Health Breakdown
        </CardTitle>
        <CardDescription>Health scores by system type</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {Object.entries(healthOverview.system_health_breakdown).map(([system, score]) => (
            <div key={system} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ComponentTypeIcon type={system} />
                <span className="text-sm font-medium capitalize">{system}</span>
              </div>
              <div className="flex items-center gap-2">
                <Progress value={score} className="w-20 h-2" />
                <span className="text-sm font-medium tabular-nums w-12 text-right">
                  {score.toFixed(1)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Main Predictive Maintenance Page
 */
export default function PredictiveMaintenancePage() {
  const [systemFilter, setSystemFilter] = useState<string>("all")
  const [recommendationFilter, setRecommendationFilter] = useState<string>("all")
  const { refresh, isLoading } = usePredictiveMaintenance()

  return (
    <AppLayout pageTitle="Predictive Maintenance">
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Predictive Maintenance</h1>
            <p className="text-muted-foreground">
              Component health tracking, trend analysis, and maintenance recommendations
            </p>
          </div>
          <Button onClick={refresh} variant="outline" className="gap-2" disabled={isLoading}>
            <IconRefresh className="h-4 w-4" />
            Refresh
          </Button>
        </div>

        {/* Overview Cards */}
        <div className="grid gap-6 md:grid-cols-2">
          <RVHealthOverviewCard />
          <SystemHealthBreakdownCard />
        </div>

        {/* Main Content Tabs */}
        <Tabs defaultValue="components" className="space-y-4">
          <TabsList>
            <TabsTrigger value="components" className="gap-2">
              <IconShield className="h-4 w-4" />
              Component Health
            </TabsTrigger>
            <TabsTrigger value="recommendations" className="gap-2">
              <IconTool className="h-4 w-4" />
              Recommendations
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2">
              <IconClock className="h-4 w-4" />
              Maintenance History
            </TabsTrigger>
          </TabsList>

          <TabsContent value="components" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Component Health Status</h2>
              <Select value={systemFilter} onValueChange={setSystemFilter}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="All Systems" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Systems</SelectItem>
                  <SelectItem value="battery">Battery</SelectItem>
                  <SelectItem value="generator">Generator</SelectItem>
                  <SelectItem value="hvac">HVAC</SelectItem>
                  <SelectItem value="pump">Pump</SelectItem>
                  <SelectItem value="slide_out">Slide Out</SelectItem>
                  <SelectItem value="lighting">Lighting</SelectItem>
                  <SelectItem value="engine">Engine</SelectItem>
                  <SelectItem value="transmission">Transmission</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {systemFilter && systemFilter !== 'all' ? (
              <ComponentHealthList systemType={systemFilter} />
            ) : (
              <ComponentHealthList />
            )}
          </TabsContent>

          <TabsContent value="recommendations" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Maintenance Recommendations</h2>
              <Select value={recommendationFilter} onValueChange={setRecommendationFilter}>
                <SelectTrigger className="w-32">
                  <SelectValue placeholder="All Levels" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="alert">Alert</SelectItem>
                  <SelectItem value="advise">Advise</SelectItem>
                  <SelectItem value="watch">Watch</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {recommendationFilter && recommendationFilter !== 'all' ? (
              <MaintenanceRecommendationsList level={recommendationFilter} />
            ) : (
              <MaintenanceRecommendationsList />
            )}
          </TabsContent>

          <TabsContent value="history" className="space-y-4">
            <h2 className="text-lg font-semibold">Maintenance History</h2>
            <Card>
              <CardContent className="p-6 text-center">
                <IconClock className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                <h3 className="text-lg font-semibold mb-2">Maintenance History</h3>
                <p className="text-muted-foreground">
                  Maintenance history tracking is coming soon. Log maintenance activities to track component lifecycles.
                </p>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  )
}
