import {
    fetchBaselineDeviations,
  fetchDiagnosticsSystemStatus,
    fetchOptimizationRecommendations,
    fetchPerformanceMetrics,
    fetchProtocolThroughput,
    fetchResourceUtilization,
    generatePerformanceReport
} from '@/api/endpoints';
import type { OptimizationSuggestion, PerformanceMetrics, ResourceUsage } from '@/api/types';
import { AppLayout } from '@/components/app-layout';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useQuery } from '@tanstack/react-query';
import {
    Activity,
    AlertTriangle,
    CheckCircle,
    Download,
    Minus,
    Network,
    RefreshCw,
    TrendingDown,
    TrendingUp
} from 'lucide-react';
import { useState } from 'react';

interface PerformanceScoreProps {
  value: number;
  label: string;
  status?: 'healthy' | 'warning' | 'critical'; // Backend-computed status
  size?: 'compact' | 'full';
}

type PerformanceStatus = NonNullable<PerformanceScoreProps['status']>;

function PerformanceScore({ value, label, status = 'healthy', size = 'compact' }: PerformanceScoreProps) {
  const percentage = Math.round(value * 100);

  // Use backend-computed status instead of frontend thresholds
  const getScoreColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600';
      case 'warning': return 'text-yellow-600';
      case 'critical': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  const getScoreVariant = (status: string): "default" | "secondary" | "destructive" | "outline" => {
    switch (status) {
      case 'healthy': return 'default';
      case 'warning': return 'secondary';
      case 'critical': return 'destructive';
      default: return 'outline';
    }
  };

  if (size === 'compact') {
    return (
      <div className="flex items-center gap-2">
        <Badge variant={getScoreVariant(status)} className="min-w-[60px] justify-center">
          {percentage}%
        </Badge>
        <span className="text-sm text-muted-foreground">{label}</span>
      </div>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-4">
          <div className={`text-3xl font-bold ${getScoreColor(status)}`}>
            {percentage}%
          </div>
          <Progress value={percentage} className="flex-1" />
        </div>
      </CardContent>
    </Card>
  );
}

function diagnosticsHealthToPerformanceStatus(
  overallHealth: string
): PerformanceStatus {
  switch (overallHealth) {
    case 'excellent':
    case 'good':
      return 'healthy';
    case 'fair':
      return 'warning';
    case 'poor':
    case 'critical':
      return 'critical';
    default:
      return 'warning';
  }
}

interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  trend?: 'up' | 'down' | 'stable';
  description?: string;
  status?: 'good' | 'warning' | 'critical';
  severity?: 'low' | 'medium' | 'high' | 'critical'; // Backend-computed severity
}

function MetricCard({ title, value, unit, trend, description, status = 'good', severity }: MetricCardProps) {
  // Use backend-computed severity if provided, otherwise fall back to status
  const effectiveStatus = severity ?
    (severity === 'critical' ? 'critical' : severity === 'high' ? 'warning' : 'good') :
    status;
  const getTrendIcon = () => {
    switch (trend) {
      case 'up': return <TrendingUp className="h-4 w-4 text-green-600" />;
      case 'down': return <TrendingDown className="h-4 w-4 text-red-600" />;
      default: return <Minus className="h-4 w-4 text-gray-600" />;
    }
  };

  const getStatusColor = () => {
    switch (effectiveStatus) {
      case 'good': return 'border-green-200 bg-green-50';
      case 'warning': return 'border-yellow-200 bg-yellow-50';
      case 'critical': return 'border-red-200 bg-red-50';
      default: return '';
    }
  };

  return (
    <Card className={getStatusColor()}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
          {trend && getTrendIcon()}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {value}{unit && <span className="text-sm font-normal text-muted-foreground ml-1">{unit}</span>}
        </div>
        {description && (
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

interface ProtocolPerformanceGridProps {
  metrics: PerformanceMetrics;
}

function ProtocolPerformanceGrid({ metrics }: ProtocolPerformanceGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {Object.entries(metrics.protocol_performance).map(([protocol, perf]) => (
        <Card key={protocol}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium capitalize flex items-center gap-2">
              <Network className="h-4 w-4" />
              {protocol}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-xs">
              <span>Messages/sec</span>
              <span className="font-medium">{perf.message_rate.toFixed(1)}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span>Decode Rate</span>
              <span className="font-medium">{perf.decode_rate.toFixed(1)}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span>Error Rate</span>
              <span className="font-medium">{(perf.error_rate * 100).toFixed(2)}%</span>
            </div>
            <div className="flex justify-between text-xs">
              <span>Latency</span>
              <span className="font-medium">{perf.latency_ms.toFixed(1)}ms</span>
            </div>
            <div className="mt-2">
              <div className="flex justify-between text-xs mb-1">
                <span>Efficiency</span>
                <span className="font-medium">{(perf.efficiency * 100).toFixed(1)}%</span>
              </div>
              <Progress value={perf.efficiency * 100} className="h-2" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

interface ResourceMonitorProps {
  resourceUsage: ResourceUsage;
}

function ResourceMonitor({ resourceUsage }: ResourceMonitorProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <MetricCard
        title="CPU Usage"
        value={(resourceUsage.cpu_usage * 100).toFixed(1)}
        unit="%"
        // TODO: Backend should provide resource usage status classification
        status={resourceUsage.cpu_usage > 0.8 ? 'critical' : resourceUsage.cpu_usage > 0.6 ? 'warning' : 'good'}
      />
      <MetricCard
        title="Memory Usage"
        value={(resourceUsage.memory_usage * 100).toFixed(1)}
        unit="%"
        // TODO: Backend should provide resource usage status classification
        status={resourceUsage.memory_usage > 0.8 ? 'critical' : resourceUsage.memory_usage > 0.6 ? 'warning' : 'good'}
      />
      <MetricCard
        title="Disk Usage"
        value={(resourceUsage.disk_usage * 100).toFixed(1)}
        unit="%"
        // TODO: Backend should provide resource usage status classification
        status={resourceUsage.disk_usage > 0.9 ? 'critical' : resourceUsage.disk_usage > 0.7 ? 'warning' : 'good'}
      />
      <MetricCard
        title="Network Usage"
        value={(resourceUsage.network_usage / 1024 / 1024).toFixed(2)}
        unit="MB/s"
      />
      <div className="md:col-span-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">CAN Interface Load</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(resourceUsage.can_interface_usage).map(([iface, usage]) => (
                <div key={iface}>
                  <div className="flex justify-between text-sm mb-1">
                    <span>{iface}</span>
                    <span className="font-medium">{(usage * 100).toFixed(1)}%</span>
                  </div>
                  <Progress value={usage * 100} className="h-2" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

interface OptimizationPanelProps {
  recommendations: OptimizationSuggestion[];
}

function OptimizationPanel({ recommendations }: OptimizationPanelProps) {
  if (recommendations.length === 0) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <div className="text-center">
            <CheckCircle className="h-12 w-12 text-green-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-green-600">All Optimized!</h3>
            <p className="text-muted-foreground">No optimization recommendations at this time.</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {recommendations.map((rec) => (
        <Card key={rec.suggestion_id}>
          <CardHeader>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="text-lg">{rec.title}</CardTitle>
                <CardDescription>{rec.description}</CardDescription>
              </div>
              <div className="flex gap-2">
                <Badge variant="outline" className="capitalize">{rec.category}</Badge>
                <Badge variant={rec.priority === 'critical' ? 'destructive' :
                              rec.priority === 'high' ? 'secondary' : 'default'}>
                  {rec.priority}
                </Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Impact:</span>
                  <div className="flex items-center gap-1">
                    <Progress value={rec.impact_score * 100} className="w-16 h-2" />
                    <span className="text-sm font-medium">{(rec.impact_score * 100).toFixed(0)}%</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Effort:</span>
                  <Badge variant="outline" className="capitalize">{rec.implementation_effort}</Badge>
                </div>
              </div>
              <div>
                <p className="text-sm text-muted-foreground mb-2">Expected Improvement:</p>
                <p className="text-sm">{rec.estimated_improvement}</p>
              </div>
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  Implementation Steps ({rec.implementation_steps.length})
                </summary>
                <ol className="list-decimal list-inside mt-2 space-y-1 text-muted-foreground ml-4">
                  {rec.implementation_steps.map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
                </ol>
              </details>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function PerformancePage() {
  const [refreshInterval] = useState(30000); // 30 seconds
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);

  // System health query (backend-computed status)
  const {
    data: systemHealth,
    isLoading: healthLoading,
    refetch: refetchHealth
  } = useQuery({
    queryKey: ['diagnostics-system-status'],
    queryFn: fetchDiagnosticsSystemStatus,
    refetchInterval: refreshInterval,
    staleTime: 15000,
  });

  // Performance metrics query
  const {
    data: metrics,
    isLoading: metricsLoading,
    refetch: refetchMetrics
  } = useQuery({
    queryKey: ['performance-metrics'],
    queryFn: fetchPerformanceMetrics,
    refetchInterval: refreshInterval,
    staleTime: 15000,
  });

  // Resource utilization query
  const {
    data: resourceUsage,
    isLoading: resourceLoading,
    refetch: refetchResources
  } = useQuery({
    queryKey: ['resource-utilization'],
    queryFn: fetchResourceUtilization,
    refetchInterval: refreshInterval,
    staleTime: 15000,
  });

  // Optimization recommendations query
  const {
    data: recommendations = [],
    isLoading: recommendationsLoading,
    refetch: refetchRecommendations
  } = useQuery({
    queryKey: ['optimization-recommendations'],
    queryFn: fetchOptimizationRecommendations,
    refetchInterval: 60000, // Less frequent for recommendations
    staleTime: 30000,
  });

  // Baseline deviations query
  const {
    data: deviations = [],
    isLoading: deviationsLoading,
    refetch: refetchDeviations
  } = useQuery({
    queryKey: ['baseline-deviations'],
    queryFn: () => fetchBaselineDeviations(3600),
    refetchInterval: refreshInterval,
    staleTime: 15000,
  });

  // Protocol throughput query
  const {
    data: throughput = {},
    isLoading: throughputLoading,
    refetch: refetchThroughput
  } = useQuery({
    queryKey: ['protocol-throughput'],
    queryFn: fetchProtocolThroughput,
    refetchInterval: refreshInterval,
    staleTime: 15000,
  });

  const handleRefreshAll = () => {
    void refetchHealth();
    void refetchMetrics();
    void refetchResources();
    void refetchRecommendations();
    void refetchDeviations();
    void refetchThroughput();
  };

  const handleGenerateReport = async () => {
    setIsGeneratingReport(true);
    try {
      const report = await generatePerformanceReport(3600);
      // Here you could trigger a download or display the report
      // For now, we'll just handle the report - in a real app you'd handle the download
      if (report) {
        // Report generated successfully
      }
    } catch (error) {
      console.error('Failed to generate performance report:', error);
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const isLoading = healthLoading || metricsLoading || resourceLoading || recommendationsLoading || deviationsLoading || throughputLoading;

  if (isLoading) {
    return (
      <AppLayout pageTitle="Performance Analytics">
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <Skeleton className="h-8 w-64 mb-2" />
              <Skeleton className="h-4 w-96" />
            </div>
            <Skeleton className="h-10 w-32" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
          <Skeleton className="h-96" />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout pageTitle="Performance Analytics">
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
              <Activity className="h-8 w-8" />
              Performance Analytics
            </h1>
            <p className="text-muted-foreground">
              Real-time system performance monitoring, trends, and optimization recommendations
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleRefreshAll}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button onClick={() => void handleGenerateReport()} disabled={isGeneratingReport}>
              <Download className="h-4 w-4 mr-2" />
              {isGeneratingReport ? 'Generating...' : 'Export Report'}
            </Button>
          </div>
        </div>

      {/* Overview Cards */}
      {metrics && systemHealth && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <PerformanceScore
            value={metrics.overall_health || 0}
            label="Overall Performance"
            status={diagnosticsHealthToPerformanceStatus(systemHealth.overall_health)}
            size="full"
          />
          {metrics.api_performance ? (
            <MetricCard
              title="API Performance"
              value={metrics.api_performance.average_response_time?.toFixed(1) ?? '0'}
              unit="ms"
              description={`${metrics.api_performance.requests_per_second?.toFixed(1) ?? '0'} req/sec`}
              // TODO: Backend should provide API performance status classification
              status={metrics.api_performance.average_response_time > 500 ? 'critical' :
                      metrics.api_performance.average_response_time > 200 ? 'warning' : 'good'}
            />
          ) : (
            <MetricCard
              title="API Performance"
              value="N/A"
              unit=""
              description="API performance data unavailable"
              status="good"
            />
          )}
          {metrics.websocket_performance ? (
            <MetricCard
              title="WebSocket Latency"
              value={metrics.websocket_performance.latency_ms?.toFixed(1) ?? '0'}
              unit="ms"
              description={`${metrics.websocket_performance.active_connections ?? 0} connections`}
              // TODO: Backend should provide WebSocket performance status classification
              status={metrics.websocket_performance.latency_ms > 100 ? 'warning' : 'good'}
            />
          ) : (
            <MetricCard
              title="WebSocket Latency"
              value="N/A"
              unit=""
              description="WebSocket performance data unavailable"
              status="good"
            />
          )}
        </div>
      )}

      {/* Critical Alerts */}
      {deviations.filter(d => d.severity === 'critical').length > 0 && (
        <Alert className="border-red-200 bg-red-50">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <strong>Critical Performance Issues Detected:</strong> {deviations.filter(d => d.severity === 'critical').length} metrics are critically deviating from baseline.
          </AlertDescription>
        </Alert>
      )}

      {/* Main Content */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="protocols">Protocols</TabsTrigger>
          <TabsTrigger value="resources">Resources</TabsTrigger>
          <TabsTrigger value="optimization">Optimization</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Protocol Throughput</CardTitle>
                <CardDescription>Messages per second by protocol</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {Object.entries(throughput).map(([protocol, rate]) => (
                    <div key={protocol}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="capitalize">{protocol}</span>
                        <span className="font-medium">{rate.toFixed(1)} msg/sec</span>
                      </div>
                      <Progress value={Math.min((rate / 100) * 100, 100)} className="h-2" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Baseline Deviations</CardTitle>
                <CardDescription>Performance metrics outside normal ranges</CardDescription>
              </CardHeader>
              <CardContent>
                {deviations.length === 0 ? (
                  <div className="text-center py-4">
                    <CheckCircle className="h-8 w-8 text-green-600 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">All metrics within baseline</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {deviations.map((deviation, index) => (
                      <div key={index} className="flex items-center justify-between p-2 border rounded">
                        <div>
                          <div className="font-medium text-sm">{deviation.metric_name}</div>
                          <div className="text-xs text-muted-foreground">
                            {deviation.deviation_percent.toFixed(1)}% deviation
                          </div>
                        </div>
                        <Badge variant={deviation.severity === 'critical' ? 'destructive' :
                                      deviation.severity === 'high' ? 'secondary' : 'default'}>
                          {deviation.severity}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="protocols" className="space-y-4">
          {metrics && <ProtocolPerformanceGrid metrics={metrics} />}
        </TabsContent>

        <TabsContent value="resources" className="space-y-4">
          {resourceUsage && <ResourceMonitor resourceUsage={resourceUsage} />}
        </TabsContent>

        <TabsContent value="optimization" className="space-y-4">
          <OptimizationPanel recommendations={recommendations} />
        </TabsContent>
      </Tabs>
      </div>
    </AppLayout>
  );
}
