/**
 * PIN Management Hooks
 *
 * React hooks for managing PIN authentication, validation, and security state.
 * Provides clean state management and error handling for RV safety operations.
 */

import { useState, useEffect, useCallback } from 'react';
import { useToast } from '@/hooks/use-toast';
import {
  validatePIN,
  getUserPINInfo,
  getSecurityStatus,
  getActivePINSessions,
  createPIN,
  changePIN,
  terminatePINSession,
  unlockPIN,
  rotatePINs,
  getPINSessionStatus,
  type PINType,
  type PINValidationRequest,
  type PINValidationResponse,
  type PINInfo,
  type SecurityStatus,
  type PINSession,
  type CreatePINRequest,
  type ChangePINRequest,
  type SessionStatusResponse
} from '@/api/pin-auth';

// Hook for PIN validation with session management
export function usePINValidation() {
  const [isValidating, setIsValidating] = useState(false);
  const [activeSession, setActiveSession] = useState<{
    sessionId: string;
    pinType: PINType;
    expiresAt: string;
  } | null>(null);
  const { toast } = useToast();

  const validatePINCode = useCallback(async (request: PINValidationRequest): Promise<PINValidationResponse | null> => {
    setIsValidating(true);
    try {
      const response = await validatePIN(request);

      if (response.valid && response.session_id && response.expires_at) {
        setActiveSession({
          sessionId: response.session_id,
          pinType: request.pin_type,
          expiresAt: response.expires_at
        });

        toast({
          title: 'PIN Validated',
          description: `${request.pin_type.toUpperCase()} PIN session active`,
        });
      }

      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'PIN validation failed';
      toast({
        title: 'Validation Error',
        description: message,
        variant: 'destructive'
      });
      return null;
    } finally {
      setIsValidating(false);
    }
  }, [toast]);

  const terminateSession = useCallback(async () => {
    if (!activeSession) return;

    try {
      await terminatePINSession(activeSession.sessionId);
      setActiveSession(null);
      toast({
        title: 'Session Terminated',
        description: 'PIN session has been terminated',
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to terminate session',
        variant: 'destructive'
      });
    }
  }, [activeSession, toast]);

  const checkSessionStatus = useCallback(async (): Promise<SessionStatusResponse | null> => {
    if (!activeSession) return null;

    try {
      const status = await getPINSessionStatus(activeSession.sessionId);

      if (!status.is_valid) {
        setActiveSession(null);
        toast({
          title: 'Session Expired',
          description: 'PIN session has expired',
          variant: 'destructive'
        });
      }

      return status;
    } catch (error) {
      setActiveSession(null);
      return null;
    }
  }, [activeSession, toast]);

  // Auto-check session status
  useEffect(() => {
    if (!activeSession) return;

    const interval = setInterval(checkSessionStatus, 30000); // Check every 30 seconds
    return () => clearInterval(interval);
  }, [activeSession, checkSessionStatus]);

  return {
    isValidating,
    activeSession,
    validatePIN: validatePINCode,
    terminateSession,
    checkSessionStatus
  };
}

// Hook for PIN management operations
export function usePINManagement(userId?: string) {
  const [pinInfo, setPinInfo] = useState<PINInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const loadPINInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const pins = await getUserPINInfo(userId);
      setPinInfo(pins);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load PIN information';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  const createPINCode = useCallback(async (request: CreatePINRequest): Promise<boolean> => {
    try {
      await createPIN(request, userId);
      await loadPINInfo();
      toast({
        title: 'PIN Created',
        description: `${request.pin_type.toUpperCase()} PIN created successfully`,
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create PIN';
      toast({
        title: 'Creation Error',
        description: message,
        variant: 'destructive'
      });
      return false;
    }
  }, [userId, loadPINInfo, toast]);

  const changePINCode = useCallback(async (request: ChangePINRequest): Promise<boolean> => {
    try {
      await changePIN(request);
      await loadPINInfo();
      toast({
        title: 'PIN Changed',
        description: `${request.pin_type.toUpperCase()} PIN updated successfully`,
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to change PIN';
      toast({
        title: 'Change Error',
        description: message,
        variant: 'destructive'
      });
      return false;
    }
  }, [loadPINInfo, toast]);

  const unlockPINType = useCallback(async (pinType: PINType): Promise<boolean> => {
    if (!userId) return false;

    try {
      await unlockPIN(userId, pinType);
      await loadPINInfo();
      toast({
        title: 'PIN Unlocked',
        description: `${pinType.toUpperCase()} PIN has been unlocked`,
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to unlock PIN';
      toast({
        title: 'Unlock Error',
        description: message,
        variant: 'destructive'
      });
      return false;
    }
  }, [userId, loadPINInfo, toast]);

  const rotatePINs_ = useCallback(async (): Promise<boolean> => {
    if (!userId) return false;

    try {
      const result = await rotatePINs(userId);
      await loadPINInfo();
      toast({
        title: 'PINs Rotated',
        description: `Rotated ${result.rotated_pins.length} PIN(s)`,
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to rotate PINs';
      toast({
        title: 'Rotation Error',
        description: message,
        variant: 'destructive'
      });
      return false;
    }
  }, [userId, loadPINInfo, toast]);

  // Get PIN info for specific type
  const getPINInfo = useCallback((pinType: PINType) => {
    return pinInfo.find(pin => pin.pin_type === pinType);
  }, [pinInfo]);

  // Check if PIN type is configured
  const isPINConfigured = useCallback((pinType: PINType) => {
    return pinInfo.some(pin => pin.pin_type === pinType);
  }, [pinInfo]);

  useEffect(() => {
    loadPINInfo();
  }, [loadPINInfo]);

  return {
    pinInfo,
    loading,
    error,
    loadPINInfo,
    createPIN: createPINCode,
    changePIN: changePINCode,
    unlockPIN: unlockPINType,
    rotatePINs: rotatePINs_,
    getPINInfo,
    isPINConfigured
  };
}

// Hook for security status monitoring
export function useSecurityStatus(autoRefresh = true, refreshInterval = 30000) {
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadSecurityStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await getSecurityStatus();
      setSecurityStatus(status);
      setLastUpdated(new Date());
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load security status';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  // Check for security alerts
  const getSecurityAlerts = useCallback(() => {
    if (!securityStatus) return [];

    const alerts: { type: 'error' | 'warning'; message: string }[] = [];

    // Check for lockouts
    const lockouts = Object.entries(securityStatus.lockout_status)
      .filter(([_, status]) => status.is_locked_out);

    if (lockouts.length > 0) {
      alerts.push({
        type: 'error',
        message: `${lockouts.length} PIN type(s) locked out`
      });
    }

    // Check security level
    if (securityStatus.security_level === 'low') {
      alerts.push({
        type: 'warning',
        message: 'Security level is LOW'
      });
    }

    return alerts;
  }, [securityStatus]);

  useEffect(() => {
    loadSecurityStatus();
  }, [loadSecurityStatus]);

  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(loadSecurityStatus, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, loadSecurityStatus]);

  return {
    securityStatus,
    loading,
    error,
    lastUpdated,
    loadSecurityStatus,
    getSecurityAlerts
  };
}

// Hook for active session management (admin view)
export function useActiveSessions() {
  const [activeSessions, setActiveSessions] = useState<PINSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const loadActiveSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const sessions = await getActivePINSessions();
      setActiveSessions(sessions);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load active sessions';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, []);

  const terminateSession = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      await terminatePINSession(sessionId);
      await loadActiveSessions();
      toast({
        title: 'Session Terminated',
        description: 'PIN session terminated successfully',
      });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to terminate session';
      toast({
        title: 'Termination Error',
        description: message,
        variant: 'destructive'
      });
      return false;
    }
  }, [loadActiveSessions, toast]);

  useEffect(() => {
    loadActiveSessions();
  }, [loadActiveSessions]);

  return {
    activeSessions,
    loading,
    error,
    loadActiveSessions,
    terminateSession
  };
}
