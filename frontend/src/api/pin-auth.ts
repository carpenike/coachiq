/**
 * PIN Authentication API client for RV safety operations
 *
 * Provides typed API functions for PIN validation, management, and session handling
 * for safety-critical operations in RV-C environments.
 */

import { apiPost, apiGet, logApiRequest, logApiResponse } from './client';

// PIN Types for RV safety operations
export type PINType = 'emergency' | 'override' | 'maintenance';

// PIN validation request and response
export interface PINValidationRequest {
  pin: string;
  pin_type: PINType;
  operation_context?: string;
  session_duration_minutes?: number;
}

export interface PINValidationResponse {
  valid: boolean;
  session_id: string | null;
  expires_at: string | null;
  remaining_attempts?: number;
  lockout_until?: string | null;
  message: string;
}

// PIN management interfaces
export interface PINInfo {
  pin_type: PINType;
  description?: string;
  expires_at?: string;
  is_active: boolean;
  max_uses?: number;
  use_count: number;
  lockout_after_failures: number;
  lockout_duration_minutes: number;
  last_used_at?: string;
}

export interface ChangePINRequest {
  pin_type: PINType;
  old_pin: string;
  new_pin: string;
  description?: string | undefined;
  expires_after_days?: number | undefined;
  max_uses?: number | undefined;
}

export interface CreatePINRequest {
  pin_type: PINType;
  pin: string;
  description?: string | undefined;
  expires_after_days?: number | undefined;
  max_uses?: number | undefined;
  lockout_after_failures?: number | undefined;
  lockout_duration_minutes?: number | undefined;
}

// Session management interfaces
export interface PINSession {
  session_id: string;
  pin_type: PINType;
  created_at: string;
  expires_at: string;
  max_operations?: number;
  operation_count: number;
  is_active: boolean;
  ip_address?: string;
}

export interface SessionStatusResponse {
  session_id: string;
  is_valid: boolean;
  expires_at: string | null;
  operations_remaining?: number;
  time_remaining_minutes: number;
}

// Security status interfaces
export interface SecurityStatus {
  pin_types_configured: PINType[];
  lockout_status: Record<PINType, {
    is_locked_out: boolean;
    lockout_until?: string;
    failed_attempts: number;
  }>;
  active_sessions: number;
  security_level: 'high' | 'medium' | 'low';
}

/**
 * Validate a PIN for safety operations
 *
 * @param request - PIN validation request
 * @returns Promise resolving to validation response with session info
 */
export async function validatePIN(request: PINValidationRequest): Promise<PINValidationResponse> {
  const url = '/api/pin-auth/validate';

  logApiRequest('POST', url, { ...request, pin: '[REDACTED]' });
  const result = await apiPost<PINValidationResponse>(url, request);
  logApiResponse(url, { ...result, session_id: result.session_id ? '[REDACTED]' : null });

  return result;
}

/**
 * Get current PIN session status
 *
 * @param sessionId - PIN session identifier
 * @returns Promise resolving to session status
 */
export async function getPINSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
  const url = `/api/pin-auth/session/${sessionId}/status`;

  logApiRequest('GET', url);
  const result = await apiGet<SessionStatusResponse>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Terminate a PIN session
 *
 * @param sessionId - PIN session identifier
 * @returns Promise resolving to termination confirmation
 */
export async function terminatePINSession(sessionId: string): Promise<{ message: string }> {
  const url = `/api/pin-auth/session/${sessionId}/terminate`;

  logApiRequest('POST', url);
  const result = await apiPost<{ message: string }>(url, {});
  logApiResponse(url, result);

  return result;
}

/**
 * Get user's PIN information (admin only)
 *
 * @param userId - User identifier (optional, defaults to current user)
 * @returns Promise resolving to array of PIN info
 */
export async function getUserPINInfo(userId?: string): Promise<PINInfo[]> {
  const url = userId ? `/api/pin-auth/admin/users/${userId}/pins` : '/api/pin-auth/pins';

  logApiRequest('GET', url);
  const result = await apiGet<PINInfo[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Create a new PIN for a user (admin only)
 *
 * @param request - PIN creation request
 * @param userId - User identifier (optional, defaults to current user)
 * @returns Promise resolving to creation confirmation
 */
export async function createPIN(request: CreatePINRequest, userId?: string): Promise<{ message: string; pin_type: PINType }> {
  const url = userId ? `/api/pin-auth/admin/users/${userId}/pins` : '/api/pin-auth/pins';

  logApiRequest('POST', url, { ...request, pin: '[REDACTED]' });
  const result = await apiPost<{ message: string; pin_type: PINType }>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Change an existing PIN
 *
 * @param request - PIN change request
 * @returns Promise resolving to change confirmation
 */
export async function changePIN(request: ChangePINRequest): Promise<{ message: string; pin_type: PINType }> {
  const url = '/api/pin-auth/change-pin';

  logApiRequest('POST', url, { ...request, old_pin: '[REDACTED]', new_pin: '[REDACTED]' });
  const result = await apiPost<{ message: string; pin_type: PINType }>(url, request);
  logApiResponse(url, result);

  return result;
}

/**
 * Rotate all PINs for a user (admin only)
 *
 * @param userId - User identifier
 * @returns Promise resolving to rotation confirmation
 */
export async function rotatePINs(userId: string): Promise<{ message: string; rotated_pins: PINType[] }> {
  const url = `/api/pin-auth/admin/users/${userId}/rotate-pins`;

  logApiRequest('POST', url);
  const result = await apiPost<{ message: string; rotated_pins: PINType[] }>(url, {});
  logApiResponse(url, result);

  return result;
}

/**
 * Get system security status
 *
 * @returns Promise resolving to security status
 */
export async function getSecurityStatus(): Promise<SecurityStatus> {
  const url = '/api/pin-auth/security-status';

  logApiRequest('GET', url);
  const result = await apiGet<SecurityStatus>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Get active PIN sessions (admin only)
 *
 * @returns Promise resolving to array of active sessions
 */
export async function getActivePINSessions(): Promise<PINSession[]> {
  const url = '/api/pin-auth/admin/active-sessions';

  logApiRequest('GET', url);
  const result = await apiGet<PINSession[]>(url);
  logApiResponse(url, result);

  return result;
}

/**
 * Manually unlock a PIN type for a user (admin only)
 *
 * @param userId - User identifier
 * @param pinType - PIN type to unlock
 * @returns Promise resolving to unlock confirmation
 */
export async function unlockPIN(userId: string, pinType: PINType): Promise<{ message: string }> {
  const url = `/api/pin-auth/admin/users/${userId}/unlock/${pinType}`;

  logApiRequest('POST', url);
  const result = await apiPost<{ message: string }>(url, {});
  logApiResponse(url, result);

  return result;
}
