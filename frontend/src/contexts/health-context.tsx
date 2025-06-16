import React, { createContext, useContext, useEffect, useRef, type ReactNode } from 'react';
import { useSystemHealthStatus, useReadinessCheck } from '@/hooks/useHealthStatus';
import { useToast } from '@/hooks/use-toast';
import type { SystemHealth } from '@/types/health';

interface HealthContextValue {
  systemHealth: SystemHealth | undefined;
  isHealthy: boolean;
  isLoading: boolean;
  isError: boolean;
  connectionStatus: 'connected' | 'disconnected' | 'unknown';
  status: 'healthy' | 'warning' | 'critical' | 'loading';
  componentStatuses: Record<string, 'ok' | 'warning' | 'critical' | 'unknown'>;
  isConnected: boolean;
}

const HealthContext = createContext<HealthContextValue | null>(null);

interface HealthProviderProps {
  children: ReactNode;
}

/**
 * Plays an alert sound for critical system failures.
 * Only plays if user has interacted with page (browser requirement).
 */
const playAlertSound = (severity: 'critical' | 'warning') => {
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

export const HealthProvider: React.FC<HealthProviderProps> = ({ children }) => {
  const { data: systemHealth, isLoading, isError } = useSystemHealthStatus();
  const { data: readiness } = useReadinessCheck();
  const previousHealth = useRef<SystemHealth | undefined>(undefined);
  const { toast } = useToast();

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
    if (curr.issues?.critical?.failed && prev?.issues?.critical?.failed) {
      const newCriticals = curr.issues.critical.failed.filter(
        (f: string) => !prev.issues!.critical.failed.includes(f)
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

    // Check for new warnings
    if (curr.issues?.warning?.failed && prev?.issues?.warning?.failed) {
      const newWarnings = curr.issues.warning.failed.filter(
        (f: string) => !prev.issues!.warning.failed.includes(f)
      );

      if (newWarnings.length > 0) {
        toast({
          title: "System Warning",
          description: `${newWarnings.join(', ')} system(s) have warnings`,
        });
      }
    }

    previousHealth.current = systemHealth;
  }, [systemHealth, toast]);

  // Calculate overall status
  const status = (() => {
    if (isLoading) return 'loading';
    if (!systemHealth || isError) return 'critical';
    if (systemHealth.issues?.critical?.failed?.length || systemHealth.issues?.critical?.degraded?.length) {
      return 'critical';
    }
    if (systemHealth.issues?.warning?.failed?.length || systemHealth.issues?.warning?.degraded?.length) {
      return 'warning';
    }
    return 'healthy';
  })();

  // Calculate component statuses
  const componentStatuses: Record<string, 'ok' | 'warning' | 'critical' | 'unknown'> = {};
  if (systemHealth?.checks) {
    Object.entries(systemHealth.checks).forEach(([name, check]) => {
      const isCritical = systemHealth.issues?.critical?.failed?.includes(name) ||
                        systemHealth.issues?.critical?.degraded?.includes(name);
      const isWarning = systemHealth.issues?.warning?.failed?.includes(name) ||
                       systemHealth.issues?.warning?.degraded?.includes(name);

      componentStatuses[name] = isCritical ? 'critical' :
                               isWarning ? 'warning' :
                               check.status === 'pass' ? 'ok' : 'unknown';
    });
  }

  const value: HealthContextValue = {
    systemHealth,
    isHealthy: readiness?.ready ?? false,
    isLoading,
    isError,
    connectionStatus,
    status,
    componentStatuses,
    isConnected: connectionStatus === 'connected',
  };

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
};

export const useHealth = () => {
  const context = useContext(HealthContext);
  if (!context) throw new Error('useHealth must be used within HealthProvider');
  return context;
};

// Alias for consistency with component naming
export const useHealthContext = useHealth;
