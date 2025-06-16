/**
 * PIN Validation Dialog Component
 *
 * Provides a secure dialog for PIN entry and validation for safety-critical RV operations.
 * Includes visual feedback, attempt tracking, and lockout protection.
 */

import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Shield, AlertTriangle, Clock, CheckCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { validatePIN, type PINType, type PINValidationRequest, type PINValidationResponse } from '@/api/pin-auth';

interface PINValidationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pinType: PINType;
  operationContext: string;
  onValidationSuccess: (response: PINValidationResponse) => void;
  onValidationError?: (error: string) => void;
  sessionDurationMinutes?: number;
}

const PIN_TYPE_LABELS: Record<PINType, string> = {
  emergency: 'Emergency PIN',
  override: 'Override PIN',
  maintenance: 'Maintenance PIN'
};

const PIN_TYPE_DESCRIPTIONS: Record<PINType, string> = {
  emergency: 'Required for emergency safety operations and system shutdown',
  override: 'Required for overriding safety interlocks and automated systems',
  maintenance: 'Required for maintenance operations and diagnostic procedures'
};

const PIN_TYPE_COLORS: Record<PINType, 'destructive' | 'default' | 'secondary'> = {
  emergency: 'destructive',
  override: 'default',
  maintenance: 'secondary'
};

export function PINValidationDialog({
  open,
  onOpenChange,
  pinType,
  operationContext,
  onValidationSuccess,
  onValidationError,
  sessionDurationMinutes = 60
}: PINValidationDialogProps) {
  const [pin, setPIN] = useState('');
  const [showPIN, setShowPIN] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remainingAttempts, setRemainingAttempts] = useState<number | undefined>(undefined);
  const [lockoutUntil, setLockoutUntil] = useState<string | undefined>(undefined);
  const [timeRemaining, setTimeRemaining] = useState<number>(0);

  // Reset state when dialog opens/closes
  useEffect(() => {
    if (open) {
      setPIN('');
      setError(null);
      setRemainingAttempts(undefined);
      setLockoutUntil(undefined);
      setTimeRemaining(0);
    }
  }, [open]);

  // Lockout countdown timer
  useEffect(() => {
    if (!lockoutUntil) return;

    const interval = setInterval(() => {
      const now = new Date().getTime();
      const lockoutTime = new Date(lockoutUntil).getTime();
      const remaining = Math.max(0, lockoutTime - now);

      setTimeRemaining(Math.ceil(remaining / 1000));

      if (remaining <= 0) {
        setLockoutUntil(undefined);
        setError(null);
        setRemainingAttempts(undefined);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [lockoutUntil]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!pin.trim()) {
      setError('PIN is required');
      return;
    }

    if (lockoutUntil && new Date(lockoutUntil) > new Date()) {
      setError('Account is locked out. Please wait before trying again.');
      return;
    }

    setIsValidating(true);
    setError(null);

    try {
      const request: PINValidationRequest = {
        pin: pin.trim(),
        pin_type: pinType,
        operation_context: operationContext,
        session_duration_minutes: sessionDurationMinutes
      };

      const response = await validatePIN(request);

      if (response.valid && response.session_id) {
        onValidationSuccess(response);
        onOpenChange(false);
      } else {
        setError(response.message);
        setRemainingAttempts(response.remaining_attempts);

        if (response.lockout_until) {
          setLockoutUntil(response.lockout_until);
        }

        // Clear PIN on failed attempt
        setPIN('');
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'PIN validation failed';
      setError(errorMessage);
      onValidationError?.(errorMessage);
      setPIN('');
    } finally {
      setIsValidating(false);
    }
  };

  const formatTimeRemaining = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const isLockedOut = Boolean(lockoutUntil && new Date(lockoutUntil) > new Date());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            {PIN_TYPE_LABELS[pinType]} Required
          </DialogTitle>
          <DialogDescription>
            {PIN_TYPE_DESCRIPTIONS[pinType]}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Operation Context */}
          <div className="rounded-lg bg-muted p-3">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant={PIN_TYPE_COLORS[pinType]} className="text-xs">
                {pinType.toUpperCase()}
              </Badge>
              <span className="text-sm font-medium">Operation</span>
            </div>
            <p className="text-sm text-muted-foreground">{operationContext}</p>
          </div>

          {/* Lockout Warning */}
          {isLockedOut && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="flex items-center justify-between">
                <span>Account locked. Try again in:</span>
                <Badge variant="destructive" className="font-mono">
                  <Clock className="h-3 w-3 mr-1" />
                  {formatTimeRemaining(timeRemaining)}
                </Badge>
              </AlertDescription>
            </Alert>
          )}

          {/* Error Alert */}
          {error && !isLockedOut && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                {error}
                {remainingAttempts !== undefined && (
                  <div className="mt-2">
                    <span className="text-sm">
                      Attempts remaining: {remainingAttempts}
                    </span>
                    <Progress
                      value={(remainingAttempts / 5) * 100}
                      className="h-2 mt-1"
                    />
                  </div>
                )}
              </AlertDescription>
            </Alert>
          )}

          {/* PIN Entry Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="pin">Enter {PIN_TYPE_LABELS[pinType]}</Label>
              <div className="relative">
                <Input
                  id="pin"
                  type={showPIN ? 'text' : 'password'}
                  value={pin}
                  onChange={(e) => setPIN(e.target.value)}
                  placeholder="Enter PIN"
                  disabled={isValidating || isLockedOut}
                  className="pr-10"
                  autoFocus
                  autoComplete="off"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                  onClick={() => setShowPIN(!showPIN)}
                  disabled={isValidating || isLockedOut}
                >
                  {showPIN ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            {/* Session Duration Info */}
            <div className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Session duration: {sessionDurationMinutes} minutes
            </div>

            {/* Submit Button */}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isValidating}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={isValidating || !pin.trim() || isLockedOut}
                className="flex-1"
              >
                {isValidating ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                    Validating...
                  </>
                ) : (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Validate
                  </>
                )}
              </Button>
            </div>
          </form>

          {/* Security Notice */}
          <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
            <strong>Security Notice:</strong> PIN attempts are logged and monitored.
            Multiple failed attempts will result in temporary lockout.
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
