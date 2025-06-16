import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { IconShield, IconServer, IconDatabase, IconWifi, IconCpu, IconSettings } from '@tabler/icons-react';
import { CheckCircleIcon, AlertTriangleIcon, XCircleIcon, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useComponentHealth } from '@/hooks/useComponentHealth';

type ComponentStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

interface Component {
  id: string;
  name: string;
  status: ComponentStatus;
  message?: string | undefined;
  category: 'core' | 'network' | 'storage' | 'external';
  lastChecked?: Date | undefined;
}

/**
 * Component Health Grid - Shows individual service health status
 * Provides immediate visibility into which components are healthy/unhealthy
 */
export function ComponentHealthGrid() {
  const { data, isLoading, error } = useComponentHealth();

  // Map API response to component format
  const components: Component[] = data?.components.map(comp => ({
    id: comp.id,
    name: comp.name,
    status: comp.status as ComponentStatus,
    message: comp.message ?? undefined,
    category: comp.category,
    lastChecked: comp.last_checked ? new Date(comp.last_checked * 1000) : undefined,
  })) || [];

  // Fallback data for when API is unavailable
  const fallbackComponents: Component[] = [
    {
      id: 'api-server',
      name: 'API Server',
      status: 'healthy',
      message: 'All endpoints responsive',
      category: 'core',
      lastChecked: new Date(Date.now() - 30000), // 30 seconds ago
    },
    {
      id: 'database',
      name: 'Database',
      status: 'degraded',
      message: 'High query latency',
      category: 'storage',
      lastChecked: new Date(Date.now() - 45000),
    },
    {
      id: 'websocket-service',
      name: 'WebSocket Service',
      status: 'healthy',
      message: 'Active connections: 24',
      category: 'network',
      lastChecked: new Date(Date.now() - 15000),
    },
    {
      id: 'can-interface',
      name: 'CAN Interface',
      status: 'unhealthy',
      message: 'Interface can0 offline',
      category: 'external',
      lastChecked: new Date(Date.now() - 120000), // 2 minutes ago
    },
    {
      id: 'entity-manager',
      name: 'Entity Manager',
      status: 'healthy',
      message: '47 entities active',
      category: 'core',
      lastChecked: new Date(Date.now() - 20000),
    },
    {
      id: 'auth-service',
      name: 'Authentication',
      status: 'healthy',
      message: 'JWT validation active',
      category: 'core',
      lastChecked: new Date(Date.now() - 35000),
    },
    {
      id: 'feature-manager',
      name: 'Feature Manager',
      status: 'healthy',
      message: '12 features enabled',
      category: 'core',
      lastChecked: new Date(Date.now() - 25000),
    },
  ];

  // Use real data if available, otherwise use fallback
  const displayComponents = components.length > 0 ? components : (error ? [] : fallbackComponents);

  const getStatusIcon = (status: ComponentStatus) => {
    switch (status) {
      case 'healthy':
        return <CheckCircleIcon className="h-4 w-4 text-green-600" />;
      case 'degraded':
        return <AlertTriangleIcon className="h-4 w-4 text-yellow-600" />;
      case 'unhealthy':
        return <XCircleIcon className="h-4 w-4 text-destructive" />;
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getStatusBadge = (status: ComponentStatus) => {
    switch (status) {
      case 'healthy':
        return <Badge variant="default" className="bg-green-100 text-green-800 text-xs">Healthy</Badge>;
      case 'degraded':
        return <Badge variant="secondary" className="bg-yellow-100 text-yellow-800 text-xs">Degraded</Badge>;
      case 'unhealthy':
        return <Badge variant="destructive" className="text-xs">Unhealthy</Badge>;
      default:
        return <Badge variant="outline" className="text-xs">Unknown</Badge>;
    }
  };

  const getCategoryIcon = (category: Component['category']) => {
    switch (category) {
      case 'core':
        return <IconServer className="h-4 w-4" />;
      case 'network':
        return <IconWifi className="h-4 w-4" />;
      case 'storage':
        return <IconDatabase className="h-4 w-4" />;
      case 'external':
        return <IconCpu className="h-4 w-4" />;
      default:
        return <IconSettings className="h-4 w-4" />;
    }
  };

  const formatLastChecked = (date: Date) => {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <IconShield className="h-5 w-5" />
            <span>Component Health</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Group by category and sort by status (unhealthy first)
  const groupedComponents = displayComponents.reduce((acc, component) => {
    if (!acc[component.category]) acc[component.category] = [];
    acc[component.category]!.push(component);
    return acc;
  }, {} as Record<string, Component[]>);

  // Sort each group by status priority
  const statusPriority = { unhealthy: 0, degraded: 1, healthy: 2, unknown: 3 };
  Object.values(groupedComponents).forEach(group => {
    group.sort((a, b) => statusPriority[a.status] - statusPriority[b.status]);
  });

  // Count status types
  const statusCounts = displayComponents.reduce((acc, comp) => {
    acc[comp.status] = (acc[comp.status] || 0) + 1;
    return acc;
  }, {} as Record<ComponentStatus, number>);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <IconShield className="h-5 w-5" />
            <span>Component Health</span>
          </CardTitle>
          <div className="flex gap-1">
            {statusCounts.unhealthy > 0 && (
              <Badge variant="destructive" className="text-xs">
                {statusCounts.unhealthy}
              </Badge>
            )}
            {statusCounts.degraded > 0 && (
              <Badge variant="secondary" className="bg-yellow-100 text-yellow-800 text-xs">
                {statusCounts.degraded}
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-80">
          <div className="space-y-4">
            {Object.entries(groupedComponents).map(([category, categoryComponents]) => (
              <div key={category} className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  {getCategoryIcon(category as Component['category'])}
                  <span className="capitalize">{category}</span>
                </div>
                <div className="space-y-1 ml-6">
                  {categoryComponents.map((component) => (
                    <div
                      key={component.id}
                      className={cn(
                        'flex items-center justify-between p-2 rounded-md border transition-colors',
                        component.status === 'unhealthy' && 'bg-destructive/5 border-destructive/20',
                        component.status === 'degraded' && 'bg-yellow-50 border-yellow-200 dark:bg-yellow-900/10',
                        component.status === 'healthy' && 'bg-green-50/50 border-green-200/50 dark:bg-green-900/5'
                      )}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {getStatusIcon(component.status)}
                        <div className="min-w-0">
                          <div className="font-medium text-sm">{component.name}</div>
                          {component.message && (
                            <div className="text-xs text-muted-foreground truncate">
                              {component.message}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        {getStatusBadge(component.status)}
                        {component.lastChecked && (
                          <div className="text-xs text-muted-foreground">
                            {formatLastChecked(component.lastChecked)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
