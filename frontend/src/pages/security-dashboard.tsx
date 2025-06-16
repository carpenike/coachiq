/**
 * Security Dashboard Page
 *
 * Comprehensive security monitoring interface showing real-time security events,
 * anomaly detection status, and system threat levels.
 */

import { useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  IconAlertTriangle,
  IconShield,
  IconShieldCheck,
  IconShieldOff,
  IconActivity,
  IconAlertCircle,
  IconCircleCheck,
  IconInfoCircle,
  IconRefresh,
  IconSettings,
  IconBolt,
  IconTrendingUp,
  IconClock,
  IconWifi,
  IconWifiOff,
} from '@tabler/icons-react';
import { useSecurityDashboard, useSecurityEventFilters, type SecurityEvent } from '@/hooks/useSecurityDashboard';
import { cn } from '@/lib/utils';

// Severity configuration
const SEVERITY_CONFIG = {
  critical: { icon: IconShieldOff, color: 'text-red-500', bgColor: 'bg-red-50 dark:bg-red-950', label: 'Critical' },
  high: { icon: IconShieldOff, color: 'text-orange-500', bgColor: 'bg-orange-50 dark:bg-orange-950', label: 'High' },
  medium: { icon: IconAlertTriangle, color: 'text-yellow-500', bgColor: 'bg-yellow-50 dark:bg-yellow-950', label: 'Medium' },
  low: { icon: IconInfoCircle, color: 'text-blue-500', bgColor: 'bg-blue-50 dark:bg-blue-950', label: 'Low' },
  info: { icon: IconInfoCircle, color: 'text-gray-500', bgColor: 'bg-gray-50 dark:bg-gray-950', label: 'Info' },
} as const;

// Event type configuration
const EVENT_TYPE_CONFIG = {
  rate_limit_exceeded: { label: 'Rate Limit', icon: IconBolt },
  access_violation: { label: 'Access Violation', icon: IconShieldOff },
  broadcast_storm: { label: 'Broadcast Storm', icon: IconActivity },
  authentication_failure: { label: 'Auth Failure', icon: IconShieldOff },
  network_anomaly: { label: 'Network Anomaly', icon: IconAlertCircle },
} as const;

export default function SecurityDashboardPage() {
  const [selectedTab, setSelectedTab] = useState('overview');
  const {
    events,
    statistics,
    config,
    anomalyConfig,
    eventsBySeverity,
    threatLevel,
    isLoading,
    isError,
    acknowledgeEvent,
    updateConfig,
    refetch,
    isAcknowledging,
    isUpdatingConfig,
    isConnected,
    realtimeEventCount,
  } = useSecurityDashboard({ recentEventLimit: 50 });

  const filters = useSecurityEventFilters();

  if (isLoading) {
    return (
      <AppLayout pageTitle="Security Dashboard">
        <div className="flex-1 space-y-4 p-4 md:p-8 pt-6">
          <SecurityDashboardSkeleton />
        </div>
      </AppLayout>
    );
  }

  if (isError) {
    return (
      <AppLayout pageTitle="Security Dashboard">
        <div className="flex-1 space-y-4 p-4 md:p-8 pt-6">
          <Alert variant="destructive">
            <IconAlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>
              Failed to load security dashboard data. Please try again.
            </AlertDescription>
          </Alert>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout pageTitle="Security Dashboard">
      <div className="flex-1 space-y-4 p-4 md:p-8 pt-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-3xl font-bold tracking-tight">Security Dashboard</h2>
            <p className="text-muted-foreground">
              Monitor CAN bus security events and anomaly detection
            </p>
          </div>
          <div className="flex items-center gap-4">
            <Badge variant={isConnected ? 'default' : 'secondary'}>
              {isConnected ? (
                <>
                  <IconWifi className="mr-1 h-3 w-3" />
                  Live
                </>
              ) : (
                <>
                  <IconWifiOff className="mr-1 h-3 w-3" />
                  Offline
                </>
              )}
            </Badge>
            <Button onClick={() => refetch()} size="sm" variant="outline">
              <IconRefresh className="mr-2 h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Threat Level Alert */}
        <ThreatLevelAlert threatLevel={threatLevel} />

        {/* Statistics Cards */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Total Events"
            value={statistics?.total_events ?? 0}
            icon={IconShield}
            description="Security events detected"
          />
          <StatCard
            title="Critical Events"
            value={statistics?.events_by_severity?.critical ?? 0}
            icon={IconShieldOff}
            description="Requires immediate attention"
            variant="destructive"
          />
          <StatCard
            title="High Risk Events"
            value={statistics?.events_by_severity?.high ?? 0}
            icon={IconShieldOff}
            description="Potential security threats"
            variant="warning"
          />
          <StatCard
            title="Event Rate"
            value={`${(statistics?.recent_rate ?? 0).toFixed(1)}/min`}
            icon={IconTrendingUp}
            description="Recent event frequency"
          />
        </div>

        {/* Main Content Tabs */}
        <Tabs value={selectedTab} onValueChange={setSelectedTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="configuration">Configuration</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              {/* Recent Events */}
              <Card>
                <CardHeader>
                  <CardTitle>Recent Security Events</CardTitle>
                  <CardDescription>
                    Last 10 events ({realtimeEventCount} real-time)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-[400px]">
                    <div className="space-y-2">
                      {events.slice(0, 10).map((event) => (
                        <SecurityEventItem
                          key={event.event_id}
                          event={event}
                          onAcknowledge={() => acknowledgeEvent(event.event_id)}
                          isAcknowledging={isAcknowledging}
                        />
                      ))}
                      {events.length === 0 && (
                        <div className="text-center py-8 text-muted-foreground">
                          No security events detected
                        </div>
                      )}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>

              {/* Event Distribution */}
              <Card>
                <CardHeader>
                  <CardTitle>Event Distribution</CardTitle>
                  <CardDescription>
                    Events by severity and type
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <h4 className="text-sm font-medium mb-2">By Severity</h4>
                    <div className="space-y-2">
                      {Object.entries(SEVERITY_CONFIG).map(([severity, config]) => {
                        const count = statistics?.events_by_severity?.[severity] ?? 0;
                        const percentage = statistics?.total_events
                          ? (count / statistics.total_events) * 100
                          : 0;

                        return (
                          <div key={severity} className="space-y-1">
                            <div className="flex items-center justify-between text-sm">
                              <div className="flex items-center gap-2">
                                <config.icon className={cn("h-4 w-4", config.color)} />
                                <span>{config.label}</span>
                              </div>
                              <span className="text-muted-foreground">{count}</span>
                            </div>
                            <Progress value={percentage} className="h-2" />
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <Separator />

                  <div>
                    <h4 className="text-sm font-medium mb-2">By Type</h4>
                    <div className="space-y-2">
                      {Object.entries(statistics?.events_by_type ?? {}).slice(0, 5).map(([type, count]) => {
                        const config = EVENT_TYPE_CONFIG[type as keyof typeof EVENT_TYPE_CONFIG];
                        const Icon = config?.icon ?? IconAlertCircle;

                        return (
                          <div key={type} className="flex items-center justify-between text-sm">
                            <div className="flex items-center gap-2">
                              <Icon className="h-4 w-4 text-muted-foreground" />
                              <span>{config?.label ?? type}</span>
                            </div>
                            <Badge variant="secondary">{count}</Badge>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Anomaly Detection Status */}
            <Card>
              <CardHeader>
                <CardTitle>Anomaly Detection Status</CardTitle>
                <CardDescription>
                  Current security monitoring configuration
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Rate Limiting</Label>
                      <Badge variant={anomalyConfig?.rate_limit?.enabled ? "default" : "secondary"}>
                        {anomalyConfig?.rate_limit?.enabled ? "Active" : "Inactive"}
                      </Badge>
                    </div>
                    {anomalyConfig?.rate_limit?.enabled && (
                      <p className="text-sm text-muted-foreground">
                        {anomalyConfig.rate_limit.tokens_per_second} tokens/sec,
                        burst: {anomalyConfig.rate_limit.burst_size}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Access Control</Label>
                      <Badge variant={anomalyConfig?.access_control?.enabled ? "default" : "secondary"}>
                        {anomalyConfig?.access_control?.enabled ? "Active" : "Inactive"}
                      </Badge>
                    </div>
                    {anomalyConfig?.access_control?.enabled && (
                      <p className="text-sm text-muted-foreground">
                        Mode: {anomalyConfig.access_control.mode}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label>Broadcast Storm</Label>
                      <Badge variant={anomalyConfig?.broadcast_storm?.enabled ? "default" : "secondary"}>
                        {anomalyConfig?.broadcast_storm?.enabled ? "Active" : "Inactive"}
                      </Badge>
                    </div>
                    {anomalyConfig?.broadcast_storm?.enabled && (
                      <p className="text-sm text-muted-foreground">
                        Threshold: {anomalyConfig.broadcast_storm.threshold_multiplier}x
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="events" className="space-y-4">
            <SecurityEventsTab filters={filters} />
          </TabsContent>

          <TabsContent value="configuration" className="space-y-4">
            <SecurityConfigurationTab
              config={config}
              updateConfig={updateConfig}
              isUpdating={isUpdatingConfig}
            />
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}

// Component for individual security event display
function SecurityEventItem({
  event,
  onAcknowledge,
  isAcknowledging
}: {
  event: SecurityEvent;
  onAcknowledge: () => void;
  isAcknowledging: boolean;
}) {
  const severityConfig = SEVERITY_CONFIG[event.severity];
  const Icon = severityConfig.icon;

  return (
    <div className={cn(
      "p-3 rounded-lg border",
      severityConfig.bgColor,
      event.acknowledged && "opacity-60"
    )}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 flex-1">
          <Icon className={cn("h-5 w-5 mt-0.5", severityConfig.color)} />
          <div className="space-y-1 flex-1">
            <div className="flex items-center gap-2">
              <p className="font-medium text-sm">{event.title}</p>
              <Badge variant="outline" className="text-xs">
                {event.source_component}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">{event.description}</p>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <IconClock className="h-3 w-3" />
                {new Date(event.timestamp).toLocaleString()}
              </span>
              {event.acknowledged && event.acknowledged_by && (
                <span>Acknowledged by {event.acknowledged_by}</span>
              )}
            </div>
          </div>
        </div>
        {!event.acknowledged && (
          <Button
            size="sm"
            variant="ghost"
            onClick={onAcknowledge}
            disabled={isAcknowledging}
          >
            <IconCircleCheck className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

// Threat level alert component
function ThreatLevelAlert({ threatLevel }: { threatLevel: string }) {
  if (threatLevel === 'none' || threatLevel === 'unknown') return null;

  const config = {
    critical: {
      variant: 'destructive' as const,
      title: 'Critical Security Threat',
      description: 'Multiple critical security events detected. Immediate action required.',
      icon: IconShieldOff,
    },
    high: {
      variant: 'destructive' as const,
      title: 'High Security Risk',
      description: 'Significant security events detected. Investigation recommended.',
      icon: IconShieldOff,
    },
    medium: {
      variant: 'default' as const,
      title: 'Moderate Security Activity',
      description: 'Unusual security events detected. Monitor closely.',
      icon: IconAlertTriangle,
    },
    low: {
      variant: 'default' as const,
      title: 'Low Security Activity',
      description: 'Minor security events detected. System operating normally.',
      icon: IconInfoCircle,
    },
  }[threatLevel] ?? {
    variant: 'default' as const,
    title: 'Security Status',
    description: 'System security status',
    icon: IconShield,
  };

  return (
    <Alert variant={config.variant}>
      <config.icon className="h-4 w-4" />
      <AlertTitle>{config.title}</AlertTitle>
      <AlertDescription>{config.description}</AlertDescription>
    </Alert>
  );
}

// Statistics card component
function StatCard({
  title,
  value,
  icon: Icon,
  description,
  variant = 'default'
}: {
  title: string;
  value: string | number;
  icon: any;
  description: string;
  variant?: 'default' | 'destructive' | 'warning';
}) {
  const variantStyles = {
    default: '',
    destructive: 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950',
    warning: 'border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-950',
  };

  return (
    <Card className={variantStyles[variant]}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

// Skeleton loader
function SecurityDashboardSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-96 mt-2" />
        </div>
        <div className="flex gap-4">
          <Skeleton className="h-8 w-20" />
          <Skeleton className="h-8 w-24" />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-3 w-32 mt-2" />
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Events tab component (placeholder - would be expanded)
function SecurityEventsTab({ filters }: { filters: any }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Security Event History</CardTitle>
        <CardDescription>
          Filter and search through all security events
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground">
          Event filtering and history view would be implemented here...
        </p>
      </CardContent>
    </Card>
  );
}

// Configuration tab component (placeholder - would be expanded)
function SecurityConfigurationTab({
  config,
  updateConfig,
  isUpdating
}: {
  config: any;
  updateConfig: any;
  isUpdating: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Security Configuration</CardTitle>
        <CardDescription>
          Manage anomaly detection and security settings
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label htmlFor="anomaly-detection">Anomaly Detection</Label>
            <Switch
              id="anomaly-detection"
              checked={config?.anomaly_detection?.enabled ?? false}
              disabled={isUpdating}
            />
          </div>
          <p className="text-sm text-muted-foreground">
            Additional configuration options would be implemented here...
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
