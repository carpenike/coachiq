/**
 * Security Status Card Component
 *
 * Displays real-time security status for RV safety systems.
 * Includes active sessions, lockout status, and security alerts.
 */

import React, { useState, useEffect } from 'react';
import { Shield, AlertTriangle, Clock, Eye, Users, Activity, RefreshCw } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/hooks/use-toast';
import {
  getSecurityStatus,
  getActivePINSessions,
  terminatePINSession,
  type SecurityStatus,
  type PINSession,
  type PINType
} from '@/api/pin-auth';

interface SecurityStatusCardProps {
  autoRefresh?: boolean;
  refreshInterval?: number;
  isAdminView?: boolean;
  onSessionAction?: (action: string, sessionId: string) => void;
}

const PIN_TYPE_LABELS: Record<PINType, string> = {
  emergency: 'Emergency',
  override: 'Override',
  maintenance: 'Maintenance'
};

const PIN_TYPE_COLORS: Record<PINType, 'destructive' | 'default' | 'secondary'> = {
  emergency: 'destructive',
  override: 'default',
  maintenance: 'secondary'
};

export function SecurityStatusCard({
  autoRefresh = true,
  refreshInterval = 30000, // 30 seconds
  isAdminView = false,
  onSessionAction
}: SecurityStatusCardProps) {
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [activeSessions, setActiveSessions] = useState<PINSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const { toast } = useToast();

  // Load security data
  const loadSecurityData = async () => {
    try {
      setError(null);

      const promises: Promise<any>[] = [getSecurityStatus()];
      if (isAdminView) {
        promises.push(getActivePINSessions());
      }

      const results = await Promise.all(promises);
      setSecurityStatus(results[0]);

      if (isAdminView && results[1]) {
        setActiveSessions(results[1]);
      }

      setLastUpdated(new Date());
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load security status';
      setError(errorMessage);
      console.error('Security status error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    loadSecurityData();
  }, [isAdminView]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(loadSecurityData, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval]);

  // Handle session termination (admin only)
  const handleTerminateSession = async (sessionId: string) => {
    if (!isAdminView) return;

    setActionLoading(sessionId);
    try {
      await terminatePINSession(sessionId);
      toast({
        title: 'Session Terminated',
        description: 'PIN session has been terminated successfully',
      });
      await loadSecurityData();
      onSessionAction?.('terminate', sessionId);
    } catch (err) {
      toast({
        title: 'Termination Failed',
        description: err instanceof Error ? err.message : 'Failed to terminate session',
        variant: 'destructive'
      });
    } finally {
      setActionLoading(null);
    }
  };

  // Format time remaining
  const formatTimeRemaining = (expiresAt: string) => {
    const now = new Date().getTime();
    const expiry = new Date(expiresAt).getTime();
    const diffMs = expiry - now;

    if (diffMs <= 0) return 'Expired';

    const minutes = Math.floor(diffMs / (1000 * 60));
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    }
    return `${minutes}m`;
  };

  // Check for security alerts
  const getSecurityAlerts = () => {
    const alerts: { type: 'error' | 'warning'; message: string }[] = [];

    if (!securityStatus) return alerts;

    // Check for lockouts
    const lockouts = Object.entries(securityStatus.lockout_status)
      .filter(([_, status]) => status.is_locked_out);

    if (lockouts.length > 0) {
      alerts.push({
        type: 'error',
        message: `${lockouts.length} PIN type(s) locked out: ${lockouts.map(([type]) => type).join(', ')}`
      });
    }

    // Check security level
    if (securityStatus.security_level === 'low') {
      alerts.push({
        type: 'warning',
        message: 'Security level is LOW - consider reviewing PIN configurations'
      });
    }

    // Check for excessive active sessions
    if (securityStatus.active_sessions > 5) {
      alerts.push({
        type: 'warning',
        message: `High number of active sessions (${securityStatus.active_sessions})`
      });
    }

    return alerts;
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Security Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-3">
            <div className="h-4 bg-muted rounded w-3/4" />
            <div className="h-4 bg-muted rounded w-1/2" />
            <div className="h-4 bg-muted rounded w-2/3" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Security Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <Button onClick={loadSecurityData} className="mt-4" variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const alerts = getSecurityAlerts();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Security Status
          <div className="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={loadSecurityData}
              disabled={actionLoading !== null}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardTitle>
        <CardDescription className="flex items-center gap-2">
          Real-time security monitoring for RV safety systems
          {lastUpdated && (
            <span className="text-xs text-muted-foreground">
              • Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Security Alerts */}
        {alerts.length > 0 && (
          <div className="space-y-2">
            {alerts.map((alert, index) => (
              <Alert key={index} variant={alert.type === 'error' ? 'destructive' : 'default'}>
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{alert.message}</AlertDescription>
              </Alert>
            ))}
          </div>
        )}

        {/* Security Overview */}
        {securityStatus && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Security Level</span>
                  <Badge variant={
                    securityStatus.security_level === 'high' ? 'default' :
                    securityStatus.security_level === 'medium' ? 'secondary' : 'destructive'
                  }>
                    {securityStatus.security_level.toUpperCase()}
                  </Badge>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Active Sessions</span>
                  <Badge variant="outline" className="flex items-center gap-1">
                    <Activity className="h-3 w-3" />
                    {securityStatus.active_sessions}
                  </Badge>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Configured PINs</span>
                  <Badge variant="outline" className="flex items-center gap-1">
                    <Eye className="h-3 w-3" />
                    {securityStatus.pin_types_configured.length}/3
                  </Badge>
                </div>
              </div>
            </div>

            <Separator />

            {/* PIN Type Status */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium">PIN Status</h4>

              {(['emergency', 'override', 'maintenance'] as PINType[]).map(pinType => {
                const isConfigured = securityStatus.pin_types_configured.includes(pinType);
                const lockout = securityStatus.lockout_status[pinType];

                return (
                  <div key={pinType} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center gap-2">
                      <Badge variant={PIN_TYPE_COLORS[pinType]} className="text-xs">
                        {pinType.toUpperCase()}
                      </Badge>
                      <span className="text-sm">{PIN_TYPE_LABELS[pinType]} PIN</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {isConfigured ? (
                        <Badge variant="outline" className="text-green-600">Configured</Badge>
                      ) : (
                        <Badge variant="outline" className="text-muted-foreground">Not Set</Badge>
                      )}

                      {lockout?.is_locked_out && (
                        <Badge variant="destructive" className="text-xs">
                          <AlertTriangle className="h-3 w-3 mr-1" />
                          Locked
                        </Badge>
                      )}

                      {lockout && lockout.failed_attempts > 0 && !lockout.is_locked_out && (
                        <Badge variant="secondary" className="text-xs">
                          {lockout.failed_attempts} fails
                        </Badge>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Active Sessions (Admin View) */}
        {isAdminView && activeSessions.length > 0 && (
          <>
            <Separator />
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium">Active PIN Sessions</h4>
                <Badge variant="outline" className="flex items-center gap-1">
                  <Users className="h-3 w-3" />
                  {activeSessions.length}
                </Badge>
              </div>

              <div className="space-y-2 max-h-40 overflow-y-auto">
                {activeSessions.map(session => (
                  <div key={session.session_id} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={PIN_TYPE_COLORS[session.pin_type]} className="text-xs">
                          {session.pin_type.toUpperCase()}
                        </Badge>
                        <span className="text-sm font-medium">
                          {session.session_id.substring(0, 8)}...
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatTimeRemaining(session.expires_at)}
                        </span>
                        {session.max_operations && (
                          <span>
                            {session.operation_count}/{session.max_operations} ops
                          </span>
                        )}
                        {session.ip_address && (
                          <span>{session.ip_address}</span>
                        )}
                      </div>
                    </div>

                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleTerminateSession(session.session_id)}
                      disabled={actionLoading !== null}
                    >
                      {actionLoading === session.session_id ? (
                        <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-current" />
                      ) : (
                        'Terminate'
                      )}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
