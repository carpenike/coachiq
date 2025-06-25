/**
 * Notification Dashboard Page
 *
 * Main page component that provides comprehensive monitoring and management
 * of the notification system. Integrates all dashboard components and hooks
 * for a complete monitoring experience.
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Activity,
  AlertCircle,
  Download,
  RefreshCw,
  Settings,
  Shield,
  Zap,
} from 'lucide-react';
import { NotificationDashboard } from '@/components/NotificationDashboard';
import { useNotificationDashboard } from '@/hooks/useNotificationDashboard';
import { useToast } from '@/hooks/use-toast';

const NotificationDashboardPage: React.FC = () => {
  const { toast } = useToast();
  const [exportFormat, setExportFormat] = useState<'json' | 'csv' | 'prometheus'>('json');
  const [isExporting, setIsExporting] = useState(false);

  // Initialize dashboard with WebSocket for real-time updates
  const dashboard = useNotificationDashboard({
    autoRefresh: true,
    refreshInterval: 30000, // 30 seconds
    enableWebSocket: true,
    timeRange: 24,
    onError: (error) => {
      toast({
        title: "Dashboard Error",
        description: error.message,
        variant: "destructive",
      });
    },
    onDataUpdate: (data) => {
      // Check for critical alerts
      if (data.health?.alerts && data.health.alerts.length > 0) {
        toast({
          title: "Critical Alert",
          description: data.health.alerts[0],
          variant: "destructive",
        });
      }
    },
  });

  const handleExportMetrics = async () => {
    if (!dashboard.exportMetrics) return;

    setIsExporting(true);
    try {
      const result = await dashboard.exportMetrics(exportFormat);

      // Download the exported data
      const blob = new Blob([
        exportFormat === 'json' ? JSON.stringify(result.data, null, 2) : result.data
      ], {
        type: exportFormat === 'json' ? 'application/json' : 'text/plain'
      });

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `notification-metrics-${new Date().toISOString().split('T')[0]}.${exportFormat}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: "Export Successful",
        description: `Metrics exported as ${exportFormat.toUpperCase()}`,
      });
    } catch (error) {
      toast({
        title: "Export Failed",
        description: error instanceof Error ? error.message : "Failed to export metrics",
        variant: "destructive",
      });
    } finally {
      setIsExporting(false);
    }
  };

  const handleTestNotifications = async () => {
    if (!dashboard.testNotifications) return;

    try {
      const result = await dashboard.testNotifications();

      const passedCount = result.summary?.passed || 0;
      const failedCount = result.summary?.failed || 0;

      if (failedCount === 0) {
        toast({
          title: "All Tests Passed",
          description: `${passedCount} notification channels tested successfully`,
        });
      } else {
        toast({
          title: "Some Tests Failed",
          description: `${passedCount} passed, ${failedCount} failed`,
          variant: "destructive",
        });
      }
    } catch (error) {
      toast({
        title: "Test Failed",
        description: error instanceof Error ? error.message : "Failed to run tests",
        variant: "destructive",
      });
    }
  };

  // System status indicator
  const getSystemStatus = () => {
    if (dashboard.loading) return { status: 'loading', color: 'gray' };
    if (!dashboard.isConnected) return { status: 'disconnected', color: 'red' };
    if (dashboard.hasAlerts) return { status: 'critical', color: 'red' };
    if (dashboard.hasWarnings) return { status: 'warning', color: 'yellow' };
    return { status: 'healthy', color: 'green' };
  };

  const systemStatus = getSystemStatus();

  return (
    <>
      <title>Notification Dashboard - CoachIQ</title>
      <meta name="description" content="Real-time monitoring and management of the notification system" />

      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <div className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center py-4">
              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2">
                  <Activity className="h-8 w-8 text-blue-600" />
                  <div>
                    <h1 className="text-2xl font-bold text-gray-900">
                      Notification Dashboard
                    </h1>
                    <p className="text-sm text-gray-500">
                      Real-time system monitoring and management
                    </p>
                  </div>
                </div>

                <Badge
                  variant={systemStatus.color === 'green' ? 'default' : 'destructive'}
                  className="ml-4"
                >
                  <div className={`w-2 h-2 rounded-full mr-2 ${
                    systemStatus.color === 'green' ? 'bg-green-500' :
                    systemStatus.color === 'yellow' ? 'bg-yellow-500' : 'bg-red-500'
                  }`} />
                  {systemStatus.status.charAt(0).toUpperCase() + systemStatus.status.slice(1)}
                </Badge>
              </div>

              <div className="flex items-center space-x-3">
                {/* Connection Status */}
                <div className="flex items-center space-x-2 text-sm">
                  <div className={`w-2 h-2 rounded-full ${
                    dashboard.isConnected ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <span className="text-gray-600">
                    {dashboard.isConnected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>

                {/* Last Update */}
                {dashboard.lastUpdate && (
                  <div className="text-sm text-gray-500">
                    Last update: {dashboard.lastUpdate.toLocaleTimeString()}
                  </div>
                )}

                {/* Export Button */}
                <select
                  value={exportFormat}
                  onChange={(e) => setExportFormat(e.target.value as 'json' | 'csv' | 'prometheus')}
                  className="text-sm border rounded px-2 py-1"
                >
                  <option value="json">JSON</option>
                  <option value="csv">CSV</option>
                  <option value="prometheus">Prometheus</option>
                </select>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportMetrics}
                  disabled={isExporting}
                >
                  <Download className="h-4 w-4 mr-2" />
                  {isExporting ? 'Exporting...' : 'Export'}
                </Button>

                {/* Test Button */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleTestNotifications}
                >
                  <Zap className="h-4 w-4 mr-2" />
                  Test
                </Button>

                {/* Refresh Button */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={dashboard.refresh}
                  disabled={dashboard.loading}
                >
                  <RefreshCw className={`h-4 w-4 mr-2 ${dashboard.loading ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* System Overview Cards */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {/* Critical Alerts */}
          {dashboard.error && (
            <Alert variant="destructive" className="mb-6">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>System Error</AlertTitle>
              <AlertDescription>{dashboard.error}</AlertDescription>
            </Alert>
          )}

          {/* Quick Stats */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Queue Depth</CardTitle>
                <Activity className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {dashboard.queueDepth?.toLocaleString() || '0'}
                </div>
                <p className="text-xs text-muted-foreground">
                  notifications pending
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
                <Shield className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {dashboard.successRate?.toFixed(1) || '0'}%
                </div>
                <p className="text-xs text-muted-foreground">
                  delivery success rate
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">System Health</CardTitle>
                <Activity className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {dashboard.isHealthy ? 'Healthy' : 'Issues'}
                </div>
                <p className="text-xs text-muted-foreground">
                  overall system status
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Active Alerts</CardTitle>
                <AlertCircle className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {(dashboard.health?.alerts?.length || 0) + (dashboard.health?.warnings?.length || 0)}
                </div>
                <p className="text-xs text-muted-foreground">
                  alerts and warnings
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Main Dashboard */}
          <NotificationDashboard />
        </div>

        {/* Footer */}
        <div className="bg-white border-t">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex justify-between items-center text-sm text-gray-500">
              <div>
                CoachIQ Notification System Dashboard
              </div>
              <div className="flex items-center space-x-4">
                <span>Auto-refresh: {dashboard.autoRefresh ? 'Enabled' : 'Disabled'}</span>
                <span>WebSocket: {dashboard.enableWebSocket ? 'Enabled' : 'Disabled'}</span>
                <span>Time Range: {dashboard.timeRange}h</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default NotificationDashboardPage;
