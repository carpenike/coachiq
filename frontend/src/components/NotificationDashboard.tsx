/**
 * Notification Dashboard Component
 *
 * Provides real-time monitoring and management interface for the notification system.
 * Features health monitoring, metrics visualization, queue management, and alerting.
 *
 * Key Features:
 * - Real-time system health overview
 * - Queue statistics and performance metrics
 * - Rate limiting status monitoring
 * - Channel health checks
 * - Historical trends and analytics
 * - Alert configuration
 * - Test notification triggers
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Clock,
  Mail,
  MessageCircle,
  Send,
  Settings,
  TrendingUp,
  Users,
  Zap,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from 'recharts';

// Types
interface DashboardHealth {
  status: 'healthy' | 'warning' | 'critical';
  timestamp: string;
  queue_healthy: boolean;
  rate_limiter_healthy: boolean;
  dispatcher_healthy: boolean;
  channel_health: Record<string, boolean>;
  avg_processing_time_ms: number | null;
  success_rate_percent: number;
  queue_depth: number;
  alerts: string[];
  warnings: string[];
}

interface DashboardMetrics {
  timestamp: string;
  time_range_hours: number;
  total_notifications: number;
  successful_notifications: number;
  failed_notifications: number;
  rate_limited_notifications: number;
  debounced_notifications: number;
  avg_processing_time_ms: number;
  notifications_per_hour: number;
  channel_stats: Record<string, any>;
  level_distribution: Record<string, number>;
  hourly_volume: {
    hour: string;
    total: number;
    successful: number;
    failed: number;
  }[];
}

interface QueueStatistics {
  timestamp: string;
  pending_count: number;
  processing_count: number;
  completed_count: number;
  failed_count: number;
  dlq_count: number;
  avg_processing_time_ms: number | null;
  success_rate_percent: number;
  throughput_per_minute: number;
  oldest_pending_minutes: number | null;
  dispatcher_running: boolean;
  estimated_drain_time_minutes: number | null;
  capacity_utilization_percent: number;
}

interface RateLimitingStatus {
  timestamp: string;
  current_tokens: number;
  max_tokens: number;
  refill_rate_per_minute: number;
  token_utilization_percent: number;
  requests_last_minute: number;
  requests_blocked_last_hour: number;
  active_debounces: number;
  debounce_hit_rate_percent: number;
  channel_limits: Record<string, any>;
}

// API functions
const fetchDashboardHealth = async (): Promise<DashboardHealth> => {
  const response = await fetch('/api/notifications/dashboard/health');
  if (!response.ok) throw new Error('Failed to fetch health status');
  return response.json();
};

const fetchDashboardMetrics = async (hours = 24): Promise<DashboardMetrics> => {
  const response = await fetch(`/api/notifications/dashboard/metrics?hours=${hours}`);
  if (!response.ok) throw new Error('Failed to fetch metrics');
  return response.json();
};

const fetchQueueStatistics = async (): Promise<QueueStatistics> => {
  const response = await fetch('/api/notifications/dashboard/queue-stats');
  if (!response.ok) throw new Error('Failed to fetch queue statistics');
  return response.json();
};

const fetchRateLimitingStatus = async (): Promise<RateLimitingStatus> => {
  const response = await fetch('/api/notifications/dashboard/rate-limiting');
  if (!response.ok) throw new Error('Failed to fetch rate limiting status');
  return response.json();
};

const triggerTestNotifications = async (channels?: string[]): Promise<any> => {
  const params = channels ? `?${channels.map(c => `channels=${c}`).join('&')}` : '';
  const response = await fetch(`/api/notifications/dashboard/test${params}`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to trigger test notifications');
  return response.json();
};

// Status indicator component
const StatusIndicator: React.FC<{ status: string; size?: 'sm' | 'md' | 'lg' }> = ({
  status,
  size = 'md'
}) => {
  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'healthy':
        return { icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-100', label: 'Healthy' };
      case 'warning':
        return { icon: AlertTriangle, color: 'text-yellow-500', bg: 'bg-yellow-100', label: 'Warning' };
      case 'critical':
        return { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-100', label: 'Critical' };
      default:
        return { icon: Activity, color: 'text-gray-500', bg: 'bg-gray-100', label: 'Unknown' };
    }
  };

  const config = getStatusConfig(status);
  const Icon = config.icon;
  const iconSize = size === 'sm' ? 16 : size === 'lg' ? 24 : 20;

  return (
    <div className={`inline-flex items-center gap-2 px-2 py-1 rounded-full ${config.bg}`}>
      <Icon size={iconSize} className={config.color} />
      <span className={`font-medium ${config.color}`}>{config.label}</span>
    </div>
  );
};

// Health overview component
const HealthOverview: React.FC<{ health: DashboardHealth }> = ({ health }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">System Status</CardTitle>
        </CardHeader>
        <CardContent>
          <StatusIndicator status={health.status} size="lg" />
          <p className="text-xs text-gray-500 mt-2">
            Last updated: {new Date(health.timestamp).toLocaleTimeString()}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Queue Health</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold">{health.queue_depth}</span>
            <Badge variant={health.queue_healthy ? 'default' : 'destructive'}>
              {health.queue_healthy ? 'Healthy' : 'Issues'}
            </Badge>
          </div>
          <p className="text-xs text-gray-500">Pending notifications</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold">{health.success_rate_percent.toFixed(1)}%</span>
            <TrendingUp className="h-4 w-4 text-green-500" />
          </div>
          <Progress value={health.success_rate_percent} className="mt-2" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Avg Processing</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <span className="text-2xl font-bold">
              {health.avg_processing_time_ms ? `${health.avg_processing_time_ms.toFixed(0)}ms` : 'N/A'}
            </span>
            <Clock className="h-4 w-4 text-blue-500" />
          </div>
          <p className="text-xs text-gray-500">Processing time</p>
        </CardContent>
      </Card>
    </div>
  );
};

// Alerts component
const AlertsPanel: React.FC<{ health: DashboardHealth }> = ({ health }) => {
  if (health.alerts.length === 0 && health.warnings.length === 0) {
    return (
      <Alert className="mb-6">
        <CheckCircle className="h-4 w-4" />
        <AlertTitle>All Systems Operational</AlertTitle>
        <AlertDescription>
          No alerts or warnings detected. All notification system components are functioning normally.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4 mb-6">
      {health.alerts.map((alert, index) => (
        <Alert key={index} variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Critical Alert</AlertTitle>
          <AlertDescription>{alert}</AlertDescription>
        </Alert>
      ))}

      {health.warnings.map((warning, index) => (
        <Alert key={index}>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Warning</AlertTitle>
          <AlertDescription>{warning}</AlertDescription>
        </Alert>
      ))}
    </div>
  );
};

// Queue statistics component
const QueueStatisticsCard: React.FC<{ queueStats: QueueStatistics }> = ({ queueStats }) => {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Queue Statistics
        </CardTitle>
        <CardDescription>Real-time notification queue status and performance</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{queueStats.pending_count}</div>
            <div className="text-sm text-gray-500">Pending</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-yellow-600">{queueStats.processing_count}</div>
            <div className="text-sm text-gray-500">Processing</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">{queueStats.completed_count}</div>
            <div className="text-sm text-gray-500">Completed</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">{queueStats.failed_count}</div>
            <div className="text-sm text-gray-500">Failed</div>
          </div>
        </div>

        <Separator className="my-4" />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <div className="font-medium">Success Rate</div>
            <Progress value={queueStats.success_rate_percent} className="mt-1" />
            <div className="text-sm text-gray-500 mt-1">
              {queueStats.success_rate_percent.toFixed(1)}%
            </div>
          </div>

          <div>
            <div className="font-medium">Capacity Utilization</div>
            <Progress value={queueStats.capacity_utilization_percent} className="mt-1" />
            <div className="text-sm text-gray-500 mt-1">
              {queueStats.capacity_utilization_percent.toFixed(1)}%
            </div>
          </div>

          <div>
            <div className="font-medium">Throughput</div>
            <div className="text-lg font-semibold">
              {queueStats.throughput_per_minute.toFixed(1)}/min
            </div>
            <div className="text-sm text-gray-500">
              {queueStats.estimated_drain_time_minutes
                ? `${queueStats.estimated_drain_time_minutes.toFixed(1)}m to drain`
                : 'Queue current'
              }
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <Badge variant={queueStats.dispatcher_running ? 'default' : 'destructive'}>
            Dispatcher: {queueStats.dispatcher_running ? 'Running' : 'Stopped'}
          </Badge>

          {queueStats.oldest_pending_minutes && (
            <div className="text-sm text-gray-500">
              Oldest pending: {queueStats.oldest_pending_minutes.toFixed(1)} minutes
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

// Rate limiting component
const RateLimitingCard: React.FC<{ rateLimiting: RateLimitingStatus }> = ({ rateLimiting }) => {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5" />
          Rate Limiting
        </CardTitle>
        <CardDescription>Token bucket and debouncing status</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <div className="font-medium mb-2">Token Bucket</div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span>Available Tokens</span>
                <span className="font-semibold">
                  {rateLimiting.current_tokens}/{rateLimiting.max_tokens}
                </span>
              </div>
              <Progress
                value={(rateLimiting.current_tokens / rateLimiting.max_tokens) * 100}
                className="h-2"
              />
              <div className="text-sm text-gray-500">
                Refill rate: {rateLimiting.refill_rate_per_minute.toFixed(1)}/min
              </div>
            </div>
          </div>

          <div>
            <div className="font-medium mb-2">Request Statistics</div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span>Last Minute</span>
                <span className="font-semibold">{rateLimiting.requests_last_minute}</span>
              </div>
              <div className="flex justify-between">
                <span>Blocked (1h)</span>
                <span className="font-semibold text-red-600">
                  {rateLimiting.requests_blocked_last_hour}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Active Debounces</span>
                <span className="font-semibold">{rateLimiting.active_debounces}</span>
              </div>
            </div>
          </div>
        </div>

        <Separator className="my-4" />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="font-medium">Token Utilization</div>
            <Progress value={rateLimiting.token_utilization_percent} className="mt-1" />
            <div className="text-sm text-gray-500 mt-1">
              {rateLimiting.token_utilization_percent.toFixed(1)}%
            </div>
          </div>

          <div>
            <div className="font-medium">Debounce Effectiveness</div>
            <Progress value={rateLimiting.debounce_hit_rate_percent} className="mt-1" />
            <div className="text-sm text-gray-500 mt-1">
              {rateLimiting.debounce_hit_rate_percent.toFixed(1)}%
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// Metrics visualization component
const MetricsCharts: React.FC<{ metrics: DashboardMetrics }> = ({ metrics }) => {
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8'];

  // Prepare level distribution data for pie chart
  const levelData = Object.entries(metrics.level_distribution).map(([level, count]) => ({
    name: level.charAt(0).toUpperCase() + level.slice(1),
    value: count,
  }));

  // Prepare channel data for bar chart
  const channelData = Object.entries(metrics.channel_stats).map(([channel, stats]) => ({
    channel: channel.toUpperCase(),
    successful: stats.successful || 0,
    failed: stats.failed || 0,
    success_rate: stats.success_rate || 0,
  }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Volume Trend</CardTitle>
          <CardDescription>Hourly notification volume over time</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={metrics.hourly_volume}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="hour"
                tickFormatter={(value) => new Date(value).toLocaleTimeString([], { hour: '2-digit' })}
              />
              <YAxis />
              <Tooltip
                labelFormatter={(value) => new Date(value).toLocaleString()}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="total"
                stroke="#8884d8"
                strokeWidth={2}
                name="Total"
              />
              <Line
                type="monotone"
                dataKey="successful"
                stroke="#82ca9d"
                strokeWidth={2}
                name="Successful"
              />
              <Line
                type="monotone"
                dataKey="failed"
                stroke="#ff7c7c"
                strokeWidth={2}
                name="Failed"
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Channel Performance</CardTitle>
          <CardDescription>Success/failure breakdown by channel</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={channelData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="channel" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="successful" fill="#82ca9d" name="Successful" />
              <Bar dataKey="failed" fill="#ff7c7c" name="Failed" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notification Levels</CardTitle>
          <CardDescription>Distribution by notification level</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={levelData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {levelData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Key Metrics</CardTitle>
          <CardDescription>Summary statistics for {metrics.time_range_hours}h period</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {metrics.total_notifications.toLocaleString()}
                </div>
                <div className="text-sm text-gray-500">Total Notifications</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">
                  {metrics.notifications_per_hour.toFixed(1)}
                </div>
                <div className="text-sm text-gray-500">Per Hour</div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-yellow-600">
                  {metrics.avg_processing_time_ms.toFixed(0)}ms
                </div>
                <div className="text-sm text-gray-500">Avg Processing</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-purple-600">
                  {metrics.rate_limited_notifications.toLocaleString()}
                </div>
                <div className="text-sm text-gray-500">Rate Limited</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Test panel component
const TestPanel: React.FC = () => {
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [testResult, setTestResult] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  const availableChannels = ['smtp', 'pushover', 'system'];

  const handleTest = async () => {
    setIsLoading(true);
    try {
      const result = await triggerTestNotifications(
        selectedChannels.length > 0 ? selectedChannels : undefined
      );
      setTestResult(result);
    } catch (error) {
      console.error('Test failed:', error);
      setTestResult({ error: 'Test failed' });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Send className="h-5 w-5" />
          Test Notifications
        </CardTitle>
        <CardDescription>Send test notifications to verify system functionality</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Channels to Test</label>
            <div className="flex flex-wrap gap-2">
              {availableChannels.map((channel) => (
                <Button
                  key={channel}
                  variant={selectedChannels.includes(channel) ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => {
                    setSelectedChannels(prev =>
                      prev.includes(channel)
                        ? prev.filter(c => c !== channel)
                        : [...prev, channel]
                    );
                  }}
                >
                  {channel.toUpperCase()}
                </Button>
              ))}
            </div>
            <p className="text-sm text-gray-500 mt-1">
              Leave none selected to test all channels
            </p>
          </div>

          <Button
            onClick={handleTest}
            disabled={isLoading}
            className="w-full"
          >
            {isLoading ? 'Sending Test...' : 'Send Test Notifications'}
          </Button>

          {testResult && (
            <div className="mt-4 p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">Test Results</h4>
              {testResult.error ? (
                <div className="text-red-600">{testResult.error}</div>
              ) : (
                <div>
                  <div className="text-sm text-gray-600 mb-2">
                    Tested at: {new Date(testResult.timestamp).toLocaleString()}
                  </div>
                  <div className="space-y-1">
                    {Object.entries(testResult.test_results || {}).map(([channel, result]) => (
                      <div key={channel} className="flex justify-between">
                        <span>{channel.toUpperCase()}</span>
                        <Badge variant={result ? 'default' : 'destructive'}>
                          {result ? 'Pass' : 'Fail'}
                        </Badge>
                      </div>
                    ))}
                  </div>
                  <div className="mt-2 text-sm text-gray-600">
                    Summary: {testResult.summary?.passed || 0} passed, {testResult.summary?.failed || 0} failed
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

// Main dashboard component
export const NotificationDashboard: React.FC = () => {
  const [health, setHealth] = useState<DashboardHealth | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [queueStats, setQueueStats] = useState<QueueStatistics | null>(null);
  const [rateLimiting, setRateLimiting] = useState<RateLimitingStatus | null>(null);
  const [timeRange, setTimeRange] = useState(24);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [healthData, metricsData, queueData, rateLimitData] = await Promise.all([
        fetchDashboardHealth(),
        fetchDashboardMetrics(timeRange),
        fetchQueueStatistics(),
        fetchRateLimitingStatus(),
      ]);

      setHealth(healthData);
      setMetrics(metricsData);
      setQueueStats(queueData);
      setRateLimiting(rateLimitData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch dashboard data');
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Activity className="h-8 w-8 animate-spin mx-auto mb-2" />
          <p>Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Dashboard Error</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Notification Dashboard</h1>
          <p className="text-gray-600">Real-time monitoring and management</p>
        </div>

        <div className="flex items-center gap-4">
          <Select value={timeRange.toString()} onValueChange={(value: string) => setTimeRange(parseInt(value))}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1 hour</SelectItem>
              <SelectItem value="24">24 hours</SelectItem>
              <SelectItem value="168">7 days</SelectItem>
            </SelectContent>
          </Select>

          <Button onClick={fetchData} variant="outline" size="sm">
            <Activity className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {health && <HealthOverview health={health} />}

      {health && <AlertsPanel health={health} />}

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="queue">Queue</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="test">Test</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {queueStats && <QueueStatisticsCard queueStats={queueStats} />}
            {rateLimiting && <RateLimitingCard rateLimiting={rateLimiting} />}
          </div>
        </TabsContent>

        <TabsContent value="queue" className="space-y-6">
          {queueStats && <QueueStatisticsCard queueStats={queueStats} />}
        </TabsContent>

        <TabsContent value="metrics" className="space-y-6">
          {metrics && <MetricsCharts metrics={metrics} />}
        </TabsContent>

        <TabsContent value="test" className="space-y-6">
          <TestPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default NotificationDashboard;
