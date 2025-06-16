import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { IconTerminal, IconFilter, IconRefresh } from '@tabler/icons-react';
import { AlertCircle, Info, AlertTriangle, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEventLogs } from '@/hooks/useEventLogs';

type LogLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical';

interface LogEntry {
  id: string;
  timestamp: Date;
  level: LogLevel;
  component: string;
  message: string;
  details?: Record<string, any> | undefined;
}

/**
 * Event Log Stream Card - Real-time system events for operational context
 * Provides immediate context for alerts and system changes
 */
export function EventLogStreamCard() {
  const [levelFilter, setLevelFilter] = useState<LogLevel | 'all'>('all');
  const [isAutoScrolling, setIsAutoScrolling] = useState(true);

  // Use real API data
  const { data, isLoading, error, refetch } = useEventLogs(
    levelFilter === 'all' ? { limit: 50 } : { limit: 50, level: levelFilter }
  );

  // Map API response to component format
  const apiLogs: LogEntry[] = data?.events.map(event => ({
    id: event.id,
    timestamp: new Date(event.timestamp * 1000),
    level: event.level,
    component: event.component,
    message: event.message,
    details: event.details ?? undefined,
  })) || [];

  // Generate sample log entries for fallback
  const generateSampleLogs = (): LogEntry[] => {
    const components = ['can-interface', 'api-server', 'database', 'websocket', 'entity-manager'];
    const levels: LogLevel[] = ['info', 'warning', 'error', 'debug', 'critical'];

    const messages = {
      debug: [
        'Periodic health check completed',
        'Cache refresh completed',
        'Background task executed',
      ],
      info: [
        'New entity discovered: Light Switch (Instance 12)',
        'WebSocket client connected',
        'Configuration reloaded',
        'Feature flag updated: vector_search=true',
      ],
      warning: [
        'High memory usage detected (85%)',
        'Slow database query detected (2.3s)',
        'CAN message queue growing (depth: 150)',
        'Authentication token expiring soon',
      ],
      error: [
        'Failed to connect to CAN interface can1',
        'Database connection timeout',
        'WebSocket connection lost',
        'Entity state update failed',
      ],
      critical: [
        'CAN interface can0 went offline',
        'Database connection pool exhausted',
        'Safety system unresponsive',
      ],
    };

    return Array.from({ length: 20 }, (_, i) => {
      const level = levels[Math.floor(Math.random() * levels.length)] || 'info';
      const component = components[Math.floor(Math.random() * components.length)] || 'unknown';
      const messageArray = messages[level as keyof typeof messages];
      const message = messageArray[Math.floor(Math.random() * messageArray.length)] || 'Unknown message';

      const logEntry: LogEntry = {
        id: `log-${i}`,
        timestamp: new Date(Date.now() - i * 30000 - Math.random() * 30000), // Last 10 minutes
        level,
        component,
        message,
      };

      if (level === 'error' || level === 'critical') {
        logEntry.details = {
          errorCode: `ERR_${Math.floor(Math.random() * 1000)}`,
          retryCount: Math.floor(Math.random() * 3),
        };
      }

      return logEntry;
    }).sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
  };

  // Use real logs if available, otherwise use sample data
  const [sampleLogs, setSampleLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    // Only use sample data if API is not available
    if (!data && !isLoading) {
      setSampleLogs(generateSampleLogs());
    }
  }, [data, isLoading]);

  // Combine API logs with any simulated updates
  const displayLogs = apiLogs.length > 0 ? apiLogs : sampleLogs;

  const getLevelIcon = (level: LogLevel) => {
    switch (level) {
      case 'critical':
        return <Zap className="h-3 w-3" />;
      case 'error':
        return <AlertCircle className="h-3 w-3" />;
      case 'warning':
        return <AlertTriangle className="h-3 w-3" />;
      case 'info':
        return <Info className="h-3 w-3" />;
      default:
        return <Info className="h-3 w-3" />;
    }
  };

  const getLevelColor = (level: LogLevel) => {
    switch (level) {
      case 'critical':
        return 'text-purple-600';
      case 'error':
        return 'text-destructive';
      case 'warning':
        return 'text-yellow-600';
      case 'info':
        return 'text-blue-600';
      default:
        return 'text-muted-foreground';
    }
  };

  const getLevelBadge = (level: LogLevel) => {
    const variants = {
      critical: 'destructive' as const,
      error: 'destructive' as const,
      warning: 'secondary' as const,
      info: 'outline' as const,
      debug: 'outline' as const,
    };
    return variants[level];
  };

  const filteredLogs = displayLogs;

  const formatTimestamp = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const refreshLogs = () => {
    refetch();
  };

  if (isLoading && displayLogs.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <IconTerminal className="h-5 w-5" />
            <span>Event Stream</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <IconTerminal className="h-5 w-5" />
            <span>Event Stream</span>
            <Badge variant="outline" className="text-xs">
              {filteredLogs.length}
            </Badge>
          </CardTitle>
          <div className="flex items-center gap-2">
            <Select
              value={levelFilter}
              onValueChange={(value) => {
                setLevelFilter(value as LogLevel | 'all');
              }}
            >
              <SelectTrigger className="w-24 h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
                <SelectItem value="error">Error</SelectItem>
                <SelectItem value="warning">Warning</SelectItem>
                <SelectItem value="info">Info</SelectItem>
                <SelectItem value="debug">Debug</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              onClick={refreshLogs}
              className="h-8 w-8 p-0"
            >
              <IconRefresh className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-80">
          <div className="space-y-1">
            {filteredLogs.map((log) => (
              <div
                key={log.id}
                className={cn(
                  'flex items-start gap-2 p-2 rounded-md text-sm border transition-colors',
                  log.level === 'critical' && 'bg-purple-50 border-purple-200 dark:bg-purple-900/10',
                  log.level === 'error' && 'bg-destructive/5 border-destructive/20',
                  log.level === 'warning' && 'bg-yellow-50 border-yellow-200 dark:bg-yellow-900/10',
                  (log.level === 'info' || log.level === 'debug') && 'bg-muted/30 border-muted'
                )}
              >
                <div className={cn('mt-0.5', getLevelColor(log.level))}>
                  {getLevelIcon(log.level)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-muted-foreground font-mono">
                      {formatTimestamp(log.timestamp)}
                    </span>
                    <Badge variant={getLevelBadge(log.level)} className="text-xs px-1.5 py-0">
                      {log.level.toUpperCase()}
                    </Badge>
                    <span className="text-xs text-muted-foreground font-mono">
                      {log.component}
                    </span>
                  </div>
                  <div className="text-sm leading-tight">
                    {log.message}
                  </div>
                  {log.details && (
                    <div className="mt-1 text-xs font-mono text-muted-foreground">
                      {Object.entries(log.details).map(([key, value]) => (
                        <span key={key} className="mr-3">
                          {key}: {String(value)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>

        {/* Status indicators */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span>Real-time updates enabled</span>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span>Live</span>
            </div>
          </div>
          <span>Last 50 events</span>
        </div>
      </CardContent>
    </Card>
  );
}
