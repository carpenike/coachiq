/**
 * PIN Management Card Component
 *
 * Displays PIN configuration, status, and management controls for RV safety operations.
 * Includes PIN creation, changing, and security status monitoring.
 */

import React, { useState, useEffect } from 'react';
import { Shield, Key, Clock, AlertTriangle, Settings, RotateCcw, Unlock, Plus } from 'lucide-react';
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
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/hooks/use-toast';
import {
  getUserPINInfo,
  getSecurityStatus,
  unlockPIN,
  rotatePINs,
  type PINInfo,
  type SecurityStatus,
  type PINType
} from '@/api/pin-auth';
import { PINCreationDialog } from './PINCreationDialog';
import { PINChangeDialog } from './PINChangeDialog';

interface PINManagementCardProps {
  userId?: string; // Optional - if provided, shows admin view for specific user
  isAdminView?: boolean;
  onPINAction?: (action: string, pinType: PINType) => void;
}

const PIN_TYPE_LABELS: Record<PINType, string> = {
  emergency: 'Emergency PIN',
  override: 'Override PIN',
  maintenance: 'Maintenance PIN'
};

const PIN_TYPE_DESCRIPTIONS: Record<PINType, string> = {
  emergency: 'Critical safety operations',
  override: 'Safety system overrides',
  maintenance: 'System maintenance'
};

const PIN_TYPE_COLORS: Record<PINType, 'destructive' | 'default' | 'secondary'> = {
  emergency: 'destructive',
  override: 'default',
  maintenance: 'secondary'
};

export function PINManagementCard({ userId, isAdminView = false, onPINAction }: PINManagementCardProps) {
  const [pinInfo, setPINInfo] = useState<PINInfo[]>([]);
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showChangeDialog, setShowChangeDialog] = useState(false);
  const [selectedPINType, setSelectedPINType] = useState<PINType>('emergency');
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const { toast } = useToast();

  // Load PIN information and security status
  const loadPINData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [pins, security] = await Promise.all([
        getUserPINInfo(userId),
        getSecurityStatus()
      ]);

      setPINInfo(pins);
      setSecurityStatus(security);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load PIN data';
      setError(errorMessage);
      toast({
        title: 'Error',
        description: errorMessage,
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPINData();
  }, [userId]);

  // Handle PIN unlock (admin only)
  const handleUnlockPIN = async (pinType: PINType) => {
    if (!userId || !isAdminView) return;

    setActionLoading(`unlock-${pinType}`);
    try {
      await unlockPIN(userId, pinType);
      toast({
        title: 'PIN Unlocked',
        description: `${PIN_TYPE_LABELS[pinType]} has been unlocked`,
      });
      await loadPINData();
      onPINAction?.('unlock', pinType);
    } catch (err) {
      toast({
        title: 'Unlock Failed',
        description: err instanceof Error ? err.message : 'Failed to unlock PIN',
        variant: 'destructive'
      });
    } finally {
      setActionLoading(null);
    }
  };

  // Handle PIN rotation (admin only)
  const handleRotatePINs = async () => {
    if (!userId || !isAdminView) return;

    setActionLoading('rotate');
    try {
      const result = await rotatePINs(userId);
      toast({
        title: 'PINs Rotated',
        description: `Rotated ${result.rotated_pins.length} PIN(s): ${result.rotated_pins.join(', ')}`,
      });
      await loadPINData();
      onPINAction?.('rotate', 'emergency'); // Use emergency as default for callback
    } catch (err) {
      toast({
        title: 'Rotation Failed',
        description: err instanceof Error ? err.message : 'Failed to rotate PINs',
        variant: 'destructive'
      });
    } finally {
      setActionLoading(null);
    }
  };

  // Handle successful PIN creation
  const handlePINCreated = async () => {
    await loadPINData();
    setShowCreateDialog(false);
    toast({
      title: 'PIN Created',
      description: `${PIN_TYPE_LABELS[selectedPINType]} has been created successfully`,
    });
    onPINAction?.('create', selectedPINType);
  };

  // Handle successful PIN change
  const handlePINChanged = async () => {
    await loadPINData();
    setShowChangeDialog(false);
    toast({
      title: 'PIN Changed',
      description: `${PIN_TYPE_LABELS[selectedPINType]} has been updated successfully`,
    });
    onPINAction?.('change', selectedPINType);
  };

  // Check if PIN type is configured
  const isPINConfigured = (pinType: PINType) => {
    return pinInfo.some(pin => pin.pin_type === pinType);
  };

  // Get lockout status for PIN type
  const getLockoutStatus = (pinType: PINType) => {
    return securityStatus?.lockout_status[pinType];
  };

  // Format expiration date
  const formatExpiration = (expiresAt?: string) => {
    if (!expiresAt) return 'Never';
    const date = new Date(expiresAt);
    const now = new Date();
    const diffMs = date.getTime() - now.getTime();
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays < 0) return 'Expired';
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Tomorrow';
    return `${diffDays} days`;
  };

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            PIN Management
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
            PIN Management
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <Button onClick={loadPINData} className="mt-4" variant="outline">
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            PIN Management
            {isAdminView && userId && (
              <Badge variant="outline" className="ml-auto">Admin View</Badge>
            )}
          </CardTitle>
          <CardDescription>
            Configure PINs for safety-critical RV operations
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Security Status Overview */}
          {securityStatus && (
            <div className="space-y-3">
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
                <Badge variant="outline">{securityStatus.active_sessions}</Badge>
              </div>

              <Separator />
            </div>
          )}

          {/* PIN Types Configuration */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium">PIN Configuration</h4>
              {isAdminView && (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setSelectedPINType('emergency');
                      setShowCreateDialog(true);
                    }}
                    disabled={actionLoading !== null}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Add PIN
                  </Button>
                  {userId && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleRotatePINs}
                      disabled={actionLoading !== null}
                    >
                      {actionLoading === 'rotate' ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-current mr-1" />
                      ) : (
                        <RotateCcw className="h-4 w-4 mr-1" />
                      )}
                      Rotate All
                    </Button>
                  )}
                </div>
              )}
            </div>

            {(['emergency', 'override', 'maintenance'] as PINType[]).map(pinType => {
              const pin = pinInfo.find(p => p.pin_type === pinType);
              const lockout = getLockoutStatus(pinType);
              const isConfigured = isPINConfigured(pinType);

              return (
                <div key={pinType} className="border rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant={PIN_TYPE_COLORS[pinType]}>
                        {pinType.toUpperCase()}
                      </Badge>
                      <span className="font-medium">{PIN_TYPE_LABELS[pinType]}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {isConfigured ? (
                        <Badge variant="outline" className="text-green-600">
                          <Key className="h-3 w-3 mr-1" />
                          Configured
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-muted-foreground">
                          Not Set
                        </Badge>
                      )}
                    </div>
                  </div>

                  <p className="text-sm text-muted-foreground">
                    {PIN_TYPE_DESCRIPTIONS[pinType]}
                  </p>

                  {pin && (
                    <div className="space-y-2">
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">Expires:</span>
                          <span className="ml-2">{formatExpiration(pin.expires_at)}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Uses:</span>
                          <span className="ml-2">
                            {pin.use_count}{pin.max_uses ? `/${pin.max_uses}` : ''}
                          </span>
                        </div>
                      </div>

                      {pin.max_uses && (
                        <Progress value={(pin.use_count / pin.max_uses) * 100} className="h-2" />
                      )}
                    </div>
                  )}

                  {/* Lockout Status */}
                  {lockout?.is_locked_out && (
                    <Alert variant="destructive">
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription className="flex items-center justify-between">
                        <span>Locked out ({lockout.failed_attempts} failed attempts)</span>
                        {isAdminView && userId && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleUnlockPIN(pinType)}
                            disabled={actionLoading !== null}
                          >
                            {actionLoading === `unlock-${pinType}` ? (
                              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-current mr-1" />
                            ) : (
                              <Unlock className="h-3 w-3 mr-1" />
                            )}
                            Unlock
                          </Button>
                        )}
                      </AlertDescription>
                    </Alert>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2">
                    {!isConfigured ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSelectedPINType(pinType);
                          setShowCreateDialog(true);
                        }}
                        disabled={actionLoading !== null}
                      >
                        <Plus className="h-4 w-4 mr-1" />
                        Create PIN
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSelectedPINType(pinType);
                          setShowChangeDialog(true);
                        }}
                        disabled={actionLoading !== null || lockout?.is_locked_out}
                      >
                        <Settings className="h-4 w-4 mr-1" />
                        Change PIN
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Security Notice */}
          <Alert>
            <Shield className="h-4 w-4" />
            <AlertDescription className="text-sm">
              <strong>Security Notice:</strong> PINs are required for safety-critical operations.
              Failed attempts will result in temporary lockouts. Contact your administrator if you
              experience issues.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>

      {/* PIN Creation Dialog */}
      <PINCreationDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        pinType={selectedPINType}
        userId={userId}
        onSuccess={handlePINCreated}
      />

      {/* PIN Change Dialog */}
      <PINChangeDialog
        open={showChangeDialog}
        onOpenChange={setShowChangeDialog}
        pinType={selectedPINType}
        onSuccess={handlePINChanged}
      />
    </>
  );
}
