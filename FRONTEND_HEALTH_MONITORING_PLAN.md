# Frontend Health Monitoring Implementation Plan

## Overview

This plan outlines the frontend improvements to leverage our comprehensive health endpoint architecture for the RV-C vehicle control system. The focus is on creating a clear, hierarchical status visualization that supports both operators and technicians while maintaining safety-critical system requirements.

## Core Principles

1. **Progressive Disclosure**: Immediate status → Subsystem details → Diagnostics → Performance metrics
2. **Safety First**: Critical failures always visible, unambiguous indicators
3. **Role-Based Views**: Different interfaces for operators vs technicians
4. **Alert Fatigue Prevention**: Only notify on state changes, not persistent conditions
5. **Clear Status Differentiation**: "System Unhealthy" vs "Status Unavailable"

## Architecture Overview

### Health Status Hierarchy

```
Level 1: Overall System Status (Binary: Operational/Not Operational)
  ├── Source: /readyz endpoint (200 = operational, 503 = not operational)
  └── Display: Global status banner

Level 2: Subsystem Status
  ├── Source: /api/v2/system/status with IETF format
  └── Display: Dashboard grid with component cards

Level 3: Diagnostic Details
  ├── Source: Detailed component data from status endpoint
  └── Display: Expandable cards or modal dialogs

Level 4: Performance Metrics
  ├── Source: /health/monitoring endpoint
  └── Display: Technician-only performance dashboard
```

## Implementation Phases

### Phase 1: Core Health Status Infrastructure

#### 1.1 Type Definitions

Create comprehensive TypeScript types for health data:

```typescript
// src/types/health.ts
export type HealthStatus = 'pass' | 'warn' | 'fail';
export type ComponentStatus = 'ok' | 'warning' | 'critical' | 'unknown';
export type SafetyClassification = 'critical' | 'safety_related' | 'position_critical' | 'operational' | 'maintenance';

export interface HealthCheck {
  status: HealthStatus;
}

export interface SystemHealthComponent {
  name: string;
  status: ComponentStatus;
  safetyclassification: SafetyClassification;
  message: string;
  lastCheck: string;
  details?: Record<string, any>;
}

export interface SystemHealth {
  status: HealthStatus;
  version: string;
  releaseId: string;
  serviceId: string;
  description: string;
  timestamp: string;
  checks: Record<string, HealthCheck>;
  issues?: {
    critical: {
      failed: string[];
      degraded: string[];
    };
    warning: {
      failed: string[];
      degraded: string[];
    };
  };
  service: {
    name: string;
    version: string;
    environment: string;
    hostname: string;
    platform: string;
  };
  response_time_ms: number;
}

export interface HealthMonitoringData {
  endpoints: Record<string, {
    total_requests: number;
    success_rate: number;
    avg_response_time_ms: number;
    consecutive_failures: number;
    health_status: ComponentStatus;
  }>;
  overall_health: ComponentStatus;
  total_requests: number;
  global_success_rate: number;
  alerts: string[];
}
```

#### 1.2 React Query Hooks

Implement data fetching hooks with proper error handling:

```typescript
// src/hooks/useSystemHealth.ts
import { useQuery } from '@tanstack/react-query';
import { SystemHealth } from '@/types/health';

export const useSystemHealth = () => {
  return useQuery({
    queryKey: ['systemHealth'],
    queryFn: async () => {
      const response = await fetch('/api/v2/system/status?format=ietf');
      if (!response.ok) {
        if (response.status === 503) {
          // System not ready - parse the response for details
          const data = await response.json();
          return data as SystemHealth;
        }
        throw new Error('Failed to fetch system health');
      }
      return response.json() as Promise<SystemHealth>;
    },
    refetchInterval: 5000, // Poll every 5 seconds
    staleTime: 4000,
    retry: (failureCount, error) => {
      // Always retry on network errors, limited retries on server errors
      return failureCount < 3;
    },
  });
};

export const useHealthMonitoring = (enabled: boolean = false) => {
  return useQuery({
    queryKey: ['healthMonitoring'],
    queryFn: async () => {
      const response = await fetch('/health/monitoring');
      if (!response.ok) throw new Error('Failed to fetch monitoring data');
      return response.json();
    },
    refetchInterval: enabled ? 10000 : false, // Poll every 10s when enabled
    enabled, // Only fetch in technician mode
  });
};

export const useReadinessCheck = () => {
  return useQuery({
    queryKey: ['readiness'],
    queryFn: async () => {
      const response = await fetch('/readyz');
      return {
        ready: response.ok,
        status: response.status,
        data: await response.json(),
      };
    },
    refetchInterval: 10000, // Less frequent for top-level check
    staleTime: 8000,
  });
};
```

#### 1.3 Health Context Provider

Create a context for global health state:

```typescript
// src/contexts/health-context.tsx
import React, { createContext, useContext, useEffect, useRef } from 'react';
import { useSystemHealth, useReadinessCheck } from '@/hooks/useSystemHealth';
import { toast } from '@/components/ui/use-toast';
import { SystemHealth } from '@/types/health';

interface HealthContextValue {
  systemHealth?: SystemHealth;
  isHealthy: boolean;
  isLoading: boolean;
  isError: boolean;
  connectionStatus: 'connected' | 'disconnected' | 'unknown';
}

const HealthContext = createContext<HealthContextValue | null>(null);

export const HealthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { data: systemHealth, isLoading, isError } = useSystemHealth();
  const { data: readiness } = useReadinessCheck();
  const previousHealth = useRef<SystemHealth>();

  // Determine connection status
  const connectionStatus = isError ? 'disconnected' :
                          systemHealth ? 'connected' : 'unknown';

  // Check for critical state changes
  useEffect(() => {
    if (!systemHealth || !previousHealth.current) {
      previousHealth.current = systemHealth;
      return;
    }

    const prev = previousHealth.current;
    const curr = systemHealth;

    // Check for new critical failures
    if (curr.issues?.critical?.failed && prev.issues?.critical?.failed) {
      const newCriticals = curr.issues.critical.failed.filter(
        f => !prev.issues.critical.failed.includes(f)
      );

      if (newCriticals.length > 0) {
        toast({
          variant: "destructive",
          title: "Critical System Failure",
          description: `${newCriticals.join(', ')} system(s) have failed`,
        });

        // Play alert sound for critical failures
        playAlertSound('critical');
      }
    }

    previousHealth.current = systemHealth;
  }, [systemHealth]);

  const value: HealthContextValue = {
    systemHealth,
    isHealthy: readiness?.ready ?? false,
    isLoading,
    isError,
    connectionStatus,
  };

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
};

export const useHealth = () => {
  const context = useContext(HealthContext);
  if (!context) throw new Error('useHealth must be used within HealthProvider');
  return context;
};
```

### Phase 2: UI Components

#### 2.1 Global Status Banner

Create an always-visible status indicator:

```typescript
// src/components/system-status-banner.tsx
import { useHealth } from '@/contexts/health-context';
import { cn } from '@/lib/utils';
import { AlertCircle, CheckCircle, XCircle, WifiOff } from 'lucide-react';

export const SystemStatusBanner = () => {
  const { isHealthy, connectionStatus, systemHealth } = useHealth();

  if (connectionStatus === 'disconnected') {
    return (
      <div className="bg-gray-600 text-white px-4 py-2 flex items-center justify-center animate-pulse">
        <WifiOff className="w-5 h-5 mr-2" />
        <span className="font-medium">Status Unknown: Connection to vehicle lost</span>
      </div>
    );
  }

  if (connectionStatus === 'unknown') {
    return (
      <div className="bg-blue-600 text-white px-4 py-2 flex items-center justify-center">
        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
        <span className="font-medium">Connecting to vehicle systems...</span>
      </div>
    );
  }

  const hasCritical = (systemHealth?.issues?.critical?.failed?.length ?? 0) > 0;
  const hasWarning = (systemHealth?.issues?.warning?.failed?.length ?? 0) > 0 ||
                     (systemHealth?.issues?.warning?.degraded?.length ?? 0) > 0;

  if (!isHealthy && hasCritical) {
    return (
      <div className="bg-red-600 text-white px-4 py-2 flex items-center justify-center">
        <XCircle className="w-5 h-5 mr-2" />
        <span className="font-medium">
          Critical Failure: {systemHealth?.description || 'System not operational'}
        </span>
      </div>
    );
  }

  if (hasWarning) {
    return (
      <div className="bg-yellow-500 text-black px-4 py-2 flex items-center justify-center animate-pulse">
        <AlertCircle className="w-5 h-5 mr-2" />
        <span className="font-medium">
          System Degraded: {systemHealth?.description || 'Reduced functionality'}
        </span>
      </div>
    );
  }

  return (
    <div className="bg-green-600 text-white px-4 py-2 flex items-center justify-center">
      <CheckCircle className="w-5 h-5 mr-2" />
      <span className="font-medium">All Systems Operational</span>
    </div>
  );
};
```

#### 2.2 Health Dashboard

Main dashboard showing all subsystems:

```typescript
// src/pages/health-dashboard.tsx
import { useState } from 'react';
import { useSystemHealth, useHealthMonitoring } from '@/hooks/useSystemHealth';
import { Card } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { HealthComponentCard } from '@/components/health-component-card';
import { HealthPerformanceChart } from '@/components/health-performance-chart';

export const HealthDashboard = () => {
  const [technicianMode, setTechnicianMode] = useState(false);
  const { data: health } = useSystemHealth();
  const { data: monitoring } = useHealthMonitoring(technicianMode);

  // Transform health checks into components array
  const components = Object.entries(health?.checks || {}).map(([name, check]) => {
    const isCritical = health?.issues?.critical?.failed?.includes(name) ||
                      health?.issues?.critical?.degraded?.includes(name);
    const isWarning = health?.issues?.warning?.failed?.includes(name) ||
                     health?.issues?.warning?.degraded?.includes(name);

    return {
      name,
      status: check.status === 'fail' ? 'critical' :
              check.status === 'warn' ? 'warning' : 'ok',
      isCritical,
      message: getComponentMessage(name, check.status),
      details: technicianMode ? getComponentDetails(name) : undefined,
    };
  });

  // Sort: critical first, then warnings, then ok
  const sortedComponents = components.sort((a, b) => {
    const statusOrder = { critical: 0, warning: 1, ok: 2 };
    return statusOrder[a.status] - statusOrder[b.status];
  });

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">System Health Dashboard</h1>
        <div className="flex items-center gap-2">
          <label htmlFor="technician-mode" className="text-sm font-medium">
            Technician Mode
          </label>
          <Switch
            id="technician-mode"
            checked={technicianMode}
            onCheckedChange={setTechnicianMode}
          />
        </div>
      </div>

      <Tabs defaultValue="status" className="w-full">
        <TabsList>
          <TabsTrigger value="status">System Status</TabsTrigger>
          {technicianMode && (
            <>
              <TabsTrigger value="performance">Performance Metrics</TabsTrigger>
              <TabsTrigger value="diagnostics">Diagnostics</TabsTrigger>
            </>
          )}
        </TabsList>

        <TabsContent value="status" className="mt-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {sortedComponents.map((component) => (
              <HealthComponentCard
                key={component.name}
                component={component}
                showDetails={technicianMode}
              />
            ))}
          </div>
        </TabsContent>

        {technicianMode && (
          <>
            <TabsContent value="performance" className="mt-6">
              <HealthPerformanceChart data={monitoring} />
            </TabsContent>

            <TabsContent value="diagnostics" className="mt-6">
              <DiagnosticsPanel health={health} />
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
};
```

#### 2.3 Component Status Card

Individual component visualization:

```typescript
// src/components/health-component-card.tsx
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import { useState } from 'react';

interface HealthComponentCardProps {
  component: {
    name: string;
    status: 'ok' | 'warning' | 'critical';
    isCritical: boolean;
    message: string;
    details?: any;
  };
  showDetails: boolean;
}

export const HealthComponentCard = ({ component, showDetails }: HealthComponentCardProps) => {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const statusConfig = {
    ok: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-100' },
    warning: { icon: AlertTriangle, color: 'text-yellow-600', bg: 'bg-yellow-100' },
    critical: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-100' },
  };

  const config = statusConfig[component.status];
  const Icon = config.icon;

  return (
    <>
      <Card className={cn(
        "transition-all",
        component.status === 'critical' && "ring-2 ring-red-500",
        component.status === 'warning' && "ring-1 ring-yellow-500"
      )}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <Icon className={cn("w-5 h-5", config.color)} />
              {formatComponentName(component.name)}
            </CardTitle>
            {component.isCritical && (
              <Badge variant="destructive" className="text-xs">
                Safety Critical
              </Badge>
            )}
          </div>
          <CardDescription>{component.message}</CardDescription>
        </CardHeader>
        {showDetails && component.details && (
          <CardContent>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDetailsOpen(true)}
            >
              View Details
            </Button>
          </CardContent>
        )}
      </Card>

      <Dialog open={detailsOpen} onOpenChange={setDetailsOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{formatComponentName(component.name)} - Diagnostic Details</DialogTitle>
          </DialogHeader>
          <pre className="bg-gray-100 p-4 rounded overflow-auto max-h-96 text-xs">
            {JSON.stringify(component.details, null, 2)}
          </pre>
        </DialogContent>
      </Dialog>
    </>
  );
};
```

### Phase 3: Performance Monitoring

#### 3.1 Performance Visualization

Show health probe performance metrics:

```typescript
// src/components/health-performance-chart.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export const HealthPerformanceChart = ({ data }: { data: HealthMonitoringData }) => {
  if (!data) return null;

  const chartData = Object.entries(data.endpoints).map(([endpoint, metrics]) => ({
    endpoint,
    responseTime: metrics.avg_response_time_ms,
    successRate: metrics.success_rate * 100,
  }));

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Average Response Time (ms)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <XAxis dataKey="endpoint" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="responseTime" stroke="#8884d8" />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Success Rate (%)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <XAxis dataKey="endpoint" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Line type="monotone" dataKey="successRate" stroke="#82ca9d" />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
};
```

### Phase 4: Alert System

#### 4.1 Alert Sound Manager

Implement audio alerts for critical changes:

```typescript
// src/utils/alert-sounds.ts
export const playAlertSound = (severity: 'critical' | 'warning') => {
  // Only play sounds if user has interacted with page (browser requirement)
  if (!document.hidden && window.AudioContext) {
    const audio = new Audio(
      severity === 'critical' ? '/sounds/critical-alert.mp3' : '/sounds/warning-alert.mp3'
    );
    audio.volume = 0.5;
    audio.play().catch(() => {
      // Ignore errors if autoplay is blocked
    });
  }
};
```

#### 4.2 Notification Preferences

Allow users to configure alerts:

```typescript
// src/components/notification-preferences.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useLocalStorage } from '@/hooks/use-local-storage';

export const NotificationPreferences = () => {
  const [prefs, setPrefs] = useLocalStorage('health-notifications', {
    criticalAlerts: true,
    warningAlerts: false,
    soundEnabled: true,
    desktopNotifications: false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Notification Preferences</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <Label htmlFor="critical-alerts">Critical System Alerts</Label>
          <Switch
            id="critical-alerts"
            checked={prefs.criticalAlerts}
            onCheckedChange={(checked) =>
              setPrefs({ ...prefs, criticalAlerts: checked })
            }
          />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="warning-alerts">Warning Alerts</Label>
          <Switch
            id="warning-alerts"
            checked={prefs.warningAlerts}
            onCheckedChange={(checked) =>
              setPrefs({ ...prefs, warningAlerts: checked })
            }
          />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="sound-enabled">Sound Alerts</Label>
          <Switch
            id="sound-enabled"
            checked={prefs.soundEnabled}
            onCheckedChange={(checked) =>
              setPrefs({ ...prefs, soundEnabled: checked })
            }
          />
        </div>
      </CardContent>
    </Card>
  );
};
```

## Integration Steps

1. **Install Dependencies**:
   ```bash
   cd frontend
   npm install recharts
   ```

2. **Update App Layout**:
   - Wrap app with `HealthProvider`
   - Add `SystemStatusBanner` to main layout
   - Add navigation to health dashboard

3. **Configure React Query**:
   - Set up proper error boundaries
   - Configure retry logic for safety-critical context

4. **Add Sound Assets**:
   - Add alert sound files to `public/sounds/`
   - Test browser autoplay policies

## Testing Strategy

### Unit Tests
- Test health status transformations
- Test alert triggering logic
- Test connection vs health status differentiation

### Integration Tests
- Test polling behavior with mock endpoints
- Test state change notifications
- Test technician mode toggle

### E2E Tests
- Test critical failure scenarios
- Test degraded state handling
- Test connection loss scenarios

## Performance Considerations

1. **Polling Optimization**:
   - Use different intervals for different endpoints
   - Implement exponential backoff on errors
   - Pause polling when tab is not visible

2. **Render Optimization**:
   - Memoize component transformations
   - Use React.memo for static components
   - Virtualize long lists of components

3. **Network Optimization**:
   - Implement request deduplication
   - Use stale-while-revalidate pattern
   - Compress monitoring data responses

## Security Considerations

1. **Role-Based Access**:
   - Technician mode should require authentication
   - Sensitive diagnostic data should be filtered
   - Audit trail for technician mode access

2. **Data Validation**:
   - Validate all health data shapes
   - Sanitize component details before display
   - Prevent XSS in dynamic content

## Success Metrics

1. **User Experience**:
   - Time to first meaningful status < 2 seconds
   - Alert response time < 100ms from state change
   - Zero false positive critical alerts

2. **Technical Performance**:
   - Health dashboard renders < 16ms (60fps)
   - Network overhead < 5% of bandwidth
   - Memory usage stable over 24 hours

3. **Operational Impact**:
   - Reduced time to diagnose issues by 50%
   - Increased operator confidence in system status
   - Fewer unnecessary system restarts

## Future Enhancements

1. **Historical Trending**:
   - Store health metrics in time-series DB
   - Show component health over time
   - Predictive failure analysis

2. **Mobile Support**:
   - Responsive design for tablets
   - Touch-optimized interactions
   - Offline capability with service workers

3. **Advanced Diagnostics**:
   - Component dependency visualization
   - Failure correlation analysis
   - Suggested remediation actions

4. **Integration Features**:
   - Export health reports
   - SNMP trap generation
   - Webhook notifications

## Timeline

- **Week 1**: Core infrastructure (types, hooks, context)
- **Week 2**: UI components (banner, dashboard, cards)
- **Week 3**: Performance monitoring and technician mode
- **Week 4**: Alert system and notification preferences
- **Week 5**: Testing and optimization
- **Week 6**: Documentation and deployment

This plan provides a comprehensive approach to building a production-ready health monitoring interface that balances the needs of operators and technicians while maintaining the safety-critical requirements of the RV-C vehicle control system.
