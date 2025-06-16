import React, { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { useHealthContext } from '@/contexts/health-context';
import { IconServer, IconSearch, IconFilter } from '@tabler/icons-react';
import { CheckCircleIcon, AlertTriangleIcon, XCircleIcon, ChevronRight, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ComponentStatus } from '@/types/health';

/**
 * Application Health Summary Card - Level 2 of the Information Pyramid
 * Shows a high-level summary with drill-down capability via side panel.
 */
export function ApplicationHealthSummaryCard() {
  const { componentStatuses, systemHealth } = useHealthContext();
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'critical' | 'warning' | 'healthy'>('all');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['critical', 'warning']));

  // Calculate summary statistics
  const stats = useMemo(() => {
    const components = Object.entries(componentStatuses);
    const total = components.length;
    const healthy = components.filter(([_, status]) => status === 'ok').length;
    const warning = components.filter(([_, status]) => status === 'warning').length;
    const critical = components.filter(([_, status]) => status === 'critical').length;

    return { total, healthy, warning, critical };
  }, [componentStatuses]);

  // Group components by category
  const groupedComponents = useMemo(() => {
    const groups: Record<string, { name: string; status: ComponentStatus }[]> = {
      'Core Services': [],
      'Protocol Systems': [],
      'Safety Systems': [],
      'API Systems': [],
      'Other': [],
    };

    Object.entries(componentStatuses).forEach(([name, status]) => {
      // Apply search filter
      if (searchQuery && !name.toLowerCase().includes(searchQuery.toLowerCase())) {
        return;
      }

      // Apply status filter
      if (statusFilter !== 'all') {
        if (statusFilter === 'critical' && status !== 'critical') return;
        if (statusFilter === 'warning' && status !== 'warning') return;
        if (statusFilter === 'healthy' && status !== 'ok') return;
      }

      // Categorize components
      let category: keyof typeof groups = 'Other';
      if (name.includes('core') || name.includes('entity') || name.includes('app_state')) {
        category = 'Core Services';
      } else if (name.includes('protocol') || name.includes('rvc') || name.includes('can')) {
        category = 'Protocol Systems';
      } else if (name.includes('safety') || name.includes('brake') || name.includes('auth')) {
        category = 'Safety Systems';
      } else if (name.includes('api') || name.includes('websocket')) {
        category = 'API Systems';
      }

      const group = groups[category];
      if (group) {
        group.push({ name, status });
      }
    });

    // Remove empty groups
    Object.keys(groups).forEach(key => {
      const typedKey = key;
      if (groups[typedKey] && groups[typedKey].length === 0) {
        delete groups[typedKey];
      }
    });

    return groups;
  }, [componentStatuses, searchQuery, statusFilter]);

  const getStatusIcon = (status: ComponentStatus) => {
    switch (status) {
      case 'critical':
        return <XCircleIcon className="h-4 w-4 text-destructive" />;
      case 'warning':
        return <AlertTriangleIcon className="h-4 w-4 text-yellow-600" />;
      case 'ok':
        return <CheckCircleIcon className="h-4 w-4 text-green-600" />;
      default:
        return null;
    }
  };

  const toggleGroup = (group: string) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(group)) {
      newExpanded.delete(group);
    } else {
      newExpanded.add(group);
    }
    setExpandedGroups(newExpanded);
  };

  return (
    <>
      <Card
        className="cursor-pointer hover:shadow-md transition-shadow"
        onClick={() => setIsPanelOpen(true)}
      >
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IconServer className="h-5 w-5" />
              <span>Application Health</span>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="text-2xl font-bold">
              {stats.healthy}/{stats.total}
            </div>
            <div className="text-sm text-muted-foreground">
              Services Healthy
            </div>
          </div>
          {(stats.critical > 0 || stats.warning > 0) && (
            <div className="mt-3 flex gap-2">
              {stats.critical > 0 && (
                <Badge variant="destructive">
                  {stats.critical} Critical
                </Badge>
              )}
              {stats.warning > 0 && (
                <Badge variant="secondary">
                  {stats.warning} Warning
                </Badge>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Sheet open={isPanelOpen} onOpenChange={setIsPanelOpen}>
        <SheetContent className="w-[500px] sm:w-[600px] sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>Application Health Details</SheetTitle>
            <SheetDescription>
              Detailed health status for all system components
            </SheetDescription>
          </SheetHeader>

          <div className="mt-6 space-y-4">
            {/* Search and Filter Controls */}
            <div className="space-y-3">
              <div className="relative">
                <IconSearch className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search components..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>

              <div className="flex gap-2">
                <Button
                  variant={statusFilter === 'all' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setStatusFilter('all')}
                >
                  All ({stats.total})
                </Button>
                <Button
                  variant={statusFilter === 'critical' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setStatusFilter('critical')}
                >
                  Critical ({stats.critical})
                </Button>
                <Button
                  variant={statusFilter === 'warning' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setStatusFilter('warning')}
                >
                  Warning ({stats.warning})
                </Button>
                <Button
                  variant={statusFilter === 'healthy' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setStatusFilter('healthy')}
                >
                  Healthy ({stats.healthy})
                </Button>
              </div>
            </div>

            <Separator />

            {/* Grouped Component List */}
            <ScrollArea className="h-[calc(100vh-16rem)]">
              <div className="space-y-4 pr-4">
                {Object.entries(groupedComponents).map(([group, components]) => {
                  const isExpanded = expandedGroups.has(group);
                  const hasIssues = components.some(c => c.status !== 'ok');

                  return (
                    <div key={group} className="space-y-2">
                      <button
                        onClick={() => toggleGroup(group)}
                        className="flex w-full items-center justify-between rounded-md px-2 py-1 hover:bg-muted/50"
                      >
                        <div className="flex items-center gap-2">
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                          <span className="font-medium">{group}</span>
                          <span className="text-sm text-muted-foreground">
                            ({components.length})
                          </span>
                          {hasIssues && (
                            <Badge variant="outline" className="ml-2 h-5 px-1.5 text-xs">
                              Issues
                            </Badge>
                          )}
                        </div>
                      </button>

                      {isExpanded && (
                        <div className="ml-6 space-y-1">
                          {components.map(({ name, status }) => (
                            <div
                              key={name}
                              className={cn(
                                'flex items-center justify-between rounded-md px-3 py-2',
                                status === 'critical' && 'bg-destructive/10',
                                status === 'warning' && 'bg-yellow-50 dark:bg-yellow-900/20',
                                status === 'ok' && 'bg-muted/30'
                              )}
                            >
                              <div className="flex items-center gap-2">
                                {getStatusIcon(status)}
                                <span className="text-sm font-medium">
                                  {name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                                </span>
                              </div>
                              <Badge
                                variant={
                                  status === 'critical' ? 'destructive' :
                                  status === 'warning' ? 'secondary' : 'default'
                                }
                                className="text-xs"
                              >
                                {status === 'ok' ? 'Healthy' : status.charAt(0).toUpperCase() + status.slice(1)}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
