import React, { useState } from 'react';
import { useHealthContext } from '@/contexts/health-context';
import { cn } from '@/lib/utils';
import { CheckCircleIcon, AlertTriangleIcon, XCircleIcon, Loader2, AlertCircle, ArrowRight as ArrowRightIcon } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import type { ComponentStatus } from '@/types/health';

/**
 * Sidebar-integrated system status indicator with progressive disclosure.
 * Always visible, shows detailed health information in a sheet when clicked.
 */
export function SystemStatusIndicator() {
  const { status, componentStatuses, isConnected, systemHealth } = useHealthContext();
  const [isOpen, setIsOpen] = useState(false);

  // Determine overall status and styling
  const getStatusConfig = () => {
    if (!isConnected) {
      return {
        icon: XCircleIcon,
        label: 'Disconnected',
        className: 'text-destructive',
        bgClassName: 'bg-destructive/10 hover:bg-destructive/20',
        description: 'Unable to connect to backend services',
      };
    }

    switch (status) {
      case 'critical':
        return {
          icon: XCircleIcon,
          label: 'Critical Issues',
          className: 'text-destructive',
          bgClassName: 'bg-destructive/10 hover:bg-destructive/20',
          description: 'Critical systems require attention',
        };
      case 'warning':
        return {
          icon: AlertTriangleIcon,
          label: 'Warnings',
          className: 'text-yellow-600 dark:text-yellow-500',
          bgClassName: 'bg-yellow-50 hover:bg-yellow-100 dark:bg-yellow-900/20 dark:hover:bg-yellow-900/30',
          description: 'Non-critical issues detected',
        };
      case 'healthy':
        return {
          icon: CheckCircleIcon,
          label: 'All Systems Operational',
          className: 'text-green-600 dark:text-green-500',
          bgClassName: 'bg-green-50 hover:bg-green-100 dark:bg-green-900/20 dark:hover:bg-green-900/30',
          description: 'All systems functioning normally',
        };
      default:
        return {
          icon: Loader2,
          label: 'Loading...',
          className: 'text-muted-foreground',
          bgClassName: 'bg-muted/10 hover:bg-muted/20',
          description: 'Checking system status',
          isLoading: true,
        };
    }
  };

  const statusConfig = getStatusConfig();
  const Icon = statusConfig.icon;

  // Format component name for display
  const formatComponentName = (name: string): string => {
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Get component status details
  const getComponentStatusConfig = (status: ComponentStatus) => {
    switch (status) {
      case 'critical':
        return {
          icon: XCircleIcon,
          className: 'text-destructive',
          badge: 'destructive' as const,
        };
      case 'warning':
        return {
          icon: AlertTriangleIcon,
          className: 'text-yellow-600',
          badge: 'secondary' as const,
        };
      case 'ok':
        return {
          icon: CheckCircleIcon,
          className: 'text-green-600',
          badge: 'default' as const,
        };
      default:
        return {
          icon: AlertCircle,
          className: 'text-muted-foreground',
          badge: 'outline' as const,
        };
    }
  };

  // Group components by status
  const groupedComponents = React.useMemo(() => {
    const groups: Record<ComponentStatus, { name: string; status: ComponentStatus }[]> = {
      critical: [],
      warning: [],
      ok: [],
      unknown: [],
    };

    Object.entries(componentStatuses).forEach(([name, status]) => {
      groups[status].push({ name, status });
    });

    return groups;
  }, [componentStatuses]);

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <button
          className={cn(
            'flex items-center gap-2 w-full px-3 py-2 rounded-md transition-colors',
            statusConfig.bgClassName
          )}
          aria-label="System status"
        >
          <Icon
            className={cn(
              'h-4 w-4',
              statusConfig.className,
              statusConfig.isLoading && 'animate-spin'
            )}
          />
          <span className="text-sm font-medium">System Status</span>
          {(groupedComponents.critical.length > 0 || groupedComponents.warning.length > 0) && (
            <Badge variant="outline" className="ml-auto text-xs">
              {groupedComponents.critical.length + groupedComponents.warning.length}
            </Badge>
          )}
        </button>
      </SheetTrigger>
      <SheetContent className="w-[400px] sm:w-[540px]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Icon className={cn('h-5 w-5', statusConfig.className)} />
            {statusConfig.label}
          </SheetTitle>
          <SheetDescription>{statusConfig.description}</SheetDescription>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-10rem)] mt-2">
          <div className="space-y-6 px-4 pb-4">
            {/* Service Information */}
            {systemHealth && (
              <div>
                <h3 className="font-semibold mb-3">Service Information</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Service:</span>
                    <span>{systemHealth.service?.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Version:</span>
                    <span>{systemHealth.service?.version}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Environment:</span>
                    <span>{systemHealth.service?.environment}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Response Time:</span>
                    <span>{systemHealth.response_time_ms}ms</span>
                  </div>
                </div>
              </div>
            )}

            <Separator />

            {/* Component Status */}
            <div>
              <h3 className="font-semibold mb-3">Component Status</h3>
              <div className="space-y-4">
                {/* Critical Components */}
                {groupedComponents.critical.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-destructive mb-2">Critical Issues</h4>
                    <div className="space-y-2">
                      {groupedComponents.critical.map(({ name }) => {
                        const config = getComponentStatusConfig('critical');
                        return (
                          <div key={name} className="flex items-center gap-2 p-2 rounded-md bg-destructive/10">
                            <config.icon className={cn('h-4 w-4', config.className)} />
                            <span className="text-sm font-medium">{formatComponentName(name)}</span>
                            <Badge variant={config.badge} className="ml-auto text-xs">
                              Critical
                            </Badge>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Warning Components */}
                {groupedComponents.warning.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-yellow-600 mb-2">Warnings</h4>
                    <div className="space-y-2">
                      {groupedComponents.warning.map(({ name }) => {
                        const config = getComponentStatusConfig('warning');
                        return (
                          <div key={name} className="flex items-center gap-2 p-2 rounded-md bg-yellow-50 dark:bg-yellow-900/20">
                            <config.icon className={cn('h-4 w-4', config.className)} />
                            <span className="text-sm font-medium">{formatComponentName(name)}</span>
                            <Badge variant={config.badge} className="ml-auto text-xs">
                              Warning
                            </Badge>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Healthy Components */}
                {groupedComponents.ok.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-green-600 mb-2">Operational</h4>
                    <div className="space-y-2">
                      {groupedComponents.ok.map(({ name }) => {
                        const config = getComponentStatusConfig('ok');
                        return (
                          <div key={name} className="flex items-center gap-2 p-2 rounded-md bg-muted/10">
                            <config.icon className={cn('h-4 w-4', config.className)} />
                            <span className="text-sm">{formatComponentName(name)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Additional Details */}
            {systemHealth?.issues && (
              <>
                <Separator />
                <div>
                  <h3 className="font-semibold mb-3">Issue Summary</h3>
                  <div className="space-y-2 text-sm">
                    {systemHealth.issues.critical && (
                      <div className="p-3 rounded-md bg-destructive/10">
                        <p className="font-medium text-destructive">Critical Systems</p>
                        <p className="text-muted-foreground mt-1">
                          {systemHealth.issues.critical.failed?.length || 0} failed,{' '}
                          {systemHealth.issues.critical.degraded?.length || 0} degraded
                        </p>
                      </div>
                    )}
                    {systemHealth.issues.warning && (
                      <div className="p-3 rounded-md bg-yellow-50 dark:bg-yellow-900/20">
                        <p className="font-medium text-yellow-600">Warning Systems</p>
                        <p className="text-muted-foreground mt-1">
                          {systemHealth.issues.warning.failed?.length || 0} failed,{' '}
                          {systemHealth.issues.warning.degraded?.length || 0} degraded
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            <Separator />

            {/* Link to Full Dashboard */}
            <div className="mt-4">
              <a
                href="/system-status"
                className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm font-medium rounded-md bg-muted hover:bg-muted/80 transition-colors"
              >
                View Full Operations Dashboard
                <ArrowRightIcon className="h-4 w-4" />
              </a>
            </div>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
