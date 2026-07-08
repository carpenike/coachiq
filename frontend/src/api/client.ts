/**
 * API Client Configuration and Base Utilities
 *
 * This module provides the base configuration for API communication,
 * including error handling, response parsing, and common utilities.
 *
 * Environment Configuration:
 * - VITE_API_URL: Backend API base URL (e.g., http://localhost:8000 in dev, /api in prod)
 * - VITE_WS_URL: WebSocket base URL (e.g., ws://localhost:8000 in dev, auto-detected in prod)
 *
 * Development: Uses Vite proxy to forward /api and /ws to backend
 * Production: Uses relative paths assuming reverse proxy configuration
 */

import { tokenStorage } from '@/lib/token-storage';

import type { APIError } from './types';

/**
 * Base URL for API requests
 * Uses VITE_API_URL environment variable or defaults to empty string
 * (endpoints already include /api prefix)
 */
export const API_BASE = (() => {
  const apiUrl = import.meta.env.VITE_API_URL;

  if (apiUrl?.trim()) {
    return apiUrl;
  }

  // Default to empty string in production so endpoints use full paths
  // (endpoints already include /api prefix)
  return '';
})();

/**
 * WebSocket base URL for real-time connections
 *
 * Connection priority:
 *   1. VITE_BACKEND_WS_URL (preferred, set in .env[.development])
 *   2. VITE_WS_URL (legacy, fallback)
 *   3. In dev: ws://localhost:8000 (direct to backend, not via Vite proxy)
 *   4. In prod: auto-detect based on current page protocol/host for reverse proxy
 *
 * Example .env.development:
 *   VITE_BACKEND_WS_URL=ws://localhost:8000
 */
export const WS_BASE = (() => {
  const backendWsUrl = import.meta.env.VITE_BACKEND_WS_URL;
  if (backendWsUrl?.trim()) {
    return backendWsUrl;
  }
  const wsUrl = import.meta.env.VITE_WS_URL;
  if (wsUrl?.trim()) {
    return wsUrl;
  }

  // Development fallback
  if (import.meta.env.DEV) {
    console.warn('WebSocket URL not configured in development. Using default ws://localhost:8000');
    return 'ws://localhost:8000';
  }

  // Production fallback: use relative path for reverse proxy
  // This constructs the WebSocket URL based on the current page's protocol and host
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsBaseUrl = `${protocol}//${window.location.host}`;
  console.info(`Using auto-detected WebSocket URL for reverse proxy: ${wsBaseUrl}`);
  return wsBaseUrl;
})();

/**
 * Gets authorization header with JWT token
 */
function getAuthHeader(): Record<string, string> {
  const token = tokenStorage.getAccessToken();
  return token ? { 'Authorization': `Bearer ${token}` } : {};
}

/**
 * Refresh a soon-to-expire (or already expired) access token *before* a
 * request goes out.
 *
 * The only other refresh trigger is a `setTimeout` scheduled at login
 * (token-storage.scheduleTokenRefresh). On a tablet/phone panel that timer is
 * throttled or skipped while the tab is backgrounded or the device sleeps, so
 * the access token silently expires and the next request carries a dead token
 * → 401 → AuthGuard bounces the user to /login. Doing a request-time refresh
 * closes that gap. Only refresh when we actually hold a valid refresh token;
 * otherwise fall through and let the request proceed (auth-disabled coaches
 * have no token data and must not block here).
 */
async function ensureFreshAccessToken(): Promise<void> {
  if (!tokenStorage.needsRefresh()) return;
  if (!tokenStorage.isRefreshTokenValid()) return;
  try {
    await tokenStorage.attemptTokenRefresh();
  } catch {
    // Refresh failure is handled by token-storage's callbacks; don't block the
    // request — it will surface its own 401 if the token really is dead.
  }
}

/** Common fetch options for all API requests */
const defaultOptions: RequestInit = {
  headers: {
    'Content-Type': 'application/json',
  },
};

/**
 * Custom error class for API-related errors
 */
export class APIClientError extends Error {
  statusCode: number;
  status: number; // Alias for backward compatibility
  originalError: Error | undefined;
  constructor(
    message: string,
    statusCode: number,
    originalError?: Error
  ) {
    super(message);
    this.name = 'APIClientError';
    this.statusCode = statusCode;
    this.status = statusCode; // Alias for backward compatibility
    this.originalError = originalError;
  }
}

/**
 * Handles API responses with proper error handling and type safety
 *
 * @param response - The fetch Response object
 * @returns Promise resolving to the parsed JSON data
 * @throws APIClientError for HTTP errors or parsing failures
 */
export async function handleApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `API Error: ${response.status}`;
    let errorDetails: APIError | undefined;

    try {
      errorDetails = await response.json() as APIError;
      errorMessage = errorDetails.detail || errorMessage;
    } catch (parseError) {
      // If we can't parse the error response, use the default message
      console.warn('Failed to parse error response:', parseError);
    }

    throw new APIClientError(errorMessage, response.status);
  }

  try {
    return await response.json() as T;
  } catch (parseError) {
    throw new APIClientError(
      'Failed to parse response JSON',
      response.status,
      parseError as Error
    );
  }
}

/**
 * Creates a fetch request with default options and error handling
 *
 * @param url - The URL to fetch
 * @param options - Additional fetch options
 * @returns Promise resolving to the parsed response data
 */
export async function apiRequest<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const fullUrl = url.startsWith('/') ? url : `${API_BASE}/${url}`;

  // Build the request each time so a retry picks up the freshly-refreshed token
  // via getAuthHeader() rather than reusing the dead one.
  const buildInit = (): RequestInit => ({
    ...defaultOptions,
    ...options,
    headers: {
      ...defaultOptions.headers,
      ...getAuthHeader(),
      ...options.headers,
    },
  });

  await ensureFreshAccessToken();

  const response = await fetch(fullUrl, buildInit());

  // A 401 means the access token was already dead when the request left: the
  // proactive refresh above only fires inside the pre-expiry buffer, and a
  // backgrounded tablet/phone can wake with an expired token (its refresh timer
  // was throttled while asleep). Refresh once and retry before surfacing the
  // failure, so a transient expiry doesn't blank the query and strand the UI on
  // stale/empty data. Mirrors the SSE client's 401 handling.
  //
  // Auth endpoints are excluded: /api/auth/refresh is how we refresh, so
  // retrying it here would re-enter attemptTokenRefresh and deadlock on its own
  // coalesced in-flight promise.
  if (
    response.status === 401 &&
    !isAuthEndpoint(url) &&
    tokenStorage.isRefreshTokenValid()
  ) {
    const refreshed = await tokenStorage.attemptTokenRefresh().catch(() => false);
    if (refreshed) {
      return handleApiResponse<T>(await fetch(fullUrl, buildInit()));
    }
  }

  return handleApiResponse<T>(response);
}

/**
 * Token-management endpoints must not trigger the request-time 401 refresh:
 * they either manage the token lifecycle themselves or would recurse into the
 * in-flight refresh they are part of.
 */
function isAuthEndpoint(url: string): boolean {
  return url.includes('/api/auth/');
}

/**
 * Creates a GET request
 */
export async function apiGet<T>(url: string): Promise<T> {
  return apiRequest<T>(url, { method: 'GET' });
}

/**
 * Fetches a binary/file endpoint with auth headers and returns the Blob.
 *
 * File downloads can't use a plain `<a href>` because the API authenticates
 * with a Bearer header (not a cookie), so the browser's own navigation
 * request would arrive unauthenticated and 401.
 */
export async function apiGetBlob(
  url: string
): Promise<{ blob: Blob; filename: string | null }> {
  const fullUrl = url.startsWith('/') ? url : `${API_BASE}/${url}`;

  await ensureFreshAccessToken();

  const response = await fetch(fullUrl, { headers: getAuthHeader() });
  if (!response.ok) {
    let errorMessage = `API Error: ${response.status}`;
    try {
      errorMessage = ((await response.json()) as APIError).detail || errorMessage;
    } catch {
      // Non-JSON error body; keep the default message.
    }
    throw new APIClientError(errorMessage, response.status);
  }

  const disposition = response.headers.get('content-disposition');
  const filenameMatch = disposition?.match(/filename="?([^";]+)"?/i);
  return { blob: await response.blob(), filename: filenameMatch?.[1] ?? null };
}

/**
 * Creates a POST request
 */
export async function apiPost<T>(url: string, data?: unknown): Promise<T> {
  const options: RequestInit = { method: 'POST' };
  if (data) {
    options.body = JSON.stringify(data);
  }
  return apiRequest<T>(url, options);
}

/**
 * Creates a PUT request
 */
export async function apiPut<T>(url: string, data?: unknown): Promise<T> {
  const options: RequestInit = { method: 'PUT' };
  if (data) {
    options.body = JSON.stringify(data);
  }
  return apiRequest<T>(url, options);
}

/**
 * Creates a DELETE request
 */
export async function apiDelete<T>(url: string): Promise<T> {
  return apiRequest<T>(url, { method: 'DELETE' });
}

/**
 * Builds query string from parameters object
 *
 * @param params - Object of query parameters
 * @returns Query string (without leading ?)
 */
export function buildQueryString(params: Record<string, unknown> | Record<string, string | number | boolean | undefined>): string {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      searchParams.append(key, String(value));
    }
  });

  return searchParams.toString();
}

/**
 * Creates a URL with query parameters
 *
 * @param baseUrl - The base URL
 * @param params - Query parameters object
 * @returns Full URL with query string
 */
export function createUrlWithParams(
  baseUrl: string,
  params: Record<string, unknown> = {}
): string {
  const queryString = buildQueryString(params);
  return queryString ? `${baseUrl}?${queryString}` : baseUrl;
}

/**
 * Retry configuration for API requests
 */
export interface RetryConfig {
  maxRetries: number;
  baseDelay: number;
  maxDelay: number;
  backoffMultiplier: number;
}

const defaultRetryConfig: RetryConfig = {
  maxRetries: 3,
  baseDelay: 1000,
  maxDelay: 10000,
  backoffMultiplier: 2,
};

/**
 * Makes an API request with exponential backoff retry logic
 *
 * @param requestFn - Function that makes the API request
 * @param config - Retry configuration
 * @returns Promise resolving to the response data
 */
export async function withRetry<T>(
  requestFn: () => Promise<T>,
  config: Partial<RetryConfig> = {}
): Promise<T> {
  const { maxRetries, baseDelay, maxDelay, backoffMultiplier } = {
    ...defaultRetryConfig,
    ...config,
  };

  let lastError: Error | undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await requestFn();
    } catch (error) {
      lastError = error as Error;

      // Don't retry on final attempt or for non-retryable errors
      if (attempt === maxRetries || !shouldRetry(error as APIClientError)) {
        break;
      }

      // Calculate delay with exponential backoff
      const delay = Math.min(
        baseDelay * Math.pow(backoffMultiplier, attempt),
        maxDelay
      );

      console.warn(
        `API request failed (attempt ${attempt + 1}/${maxRetries + 1}), retrying in ${delay}ms:`,
        error
      );

      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  throw new Error(lastError?.message || 'Request failed after retries');
}

/**
 * Determines if an error should trigger a retry
 *
 * @param error - The error to check
 * @returns True if the request should be retried
 */
function shouldRetry(error: APIClientError): boolean {
  // Retry on network errors and 5xx server errors
  if (!error.statusCode) return true; // Network error
  if (error.statusCode >= 500) return true; // Server error

  // Don't retry on 4xx client errors (except 408 timeout and 429 rate limit)
  if (error.statusCode >= 400 && error.statusCode < 500) {
    return error.statusCode === 408 || error.statusCode === 429;
  }

  return false;
}

/**
 * Environment detection utilities
 */
export const env = {
  isDevelopment: import.meta.env.MODE === 'development',
  isProduction: import.meta.env.MODE === 'production',
  isTest: import.meta.env.MODE === 'test',
  apiUrl: API_BASE,
  wsUrl: WS_BASE,
  // Export environment variables for debugging
  viteApiUrl: import.meta.env.VITE_API_URL,
  viteWsUrl: import.meta.env.VITE_WS_URL,
};

/**
 * Logging utility for API requests (only in development)
 */
export function logApiRequest(method: string, url: string, data?: unknown): void {
  if (env.isDevelopment) {
    console.group(`🌐 API ${method.toUpperCase()} ${url}`);
    if (data) {
      console.debug('📤 Request data:', data);
    }
    console.groupEnd();
  }
}

/**
 * Logging utility for API responses (only in development)
 */
export function logApiResponse<T>(url: string, data: T): void {
  if (env.isDevelopment) {
    console.group(`✅ API Response ${url}`);
    console.debug('📥 Response data:', data);
    console.groupEnd();
  }
}
