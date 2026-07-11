/**
 * Secure Token Storage Utility
 *
 * Provides secure storage and management of authentication tokens with automatic
 * refresh functionality and secure cleanup.
 */

import { refreshToken as refreshTokenAPI, revokeRefreshToken } from '@/api/endpoints'
import type { AuthStatus, RefreshTokenResponse } from '@/api/types'

// Storage keys
const ACCESS_TOKEN_KEY = 'auth_token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const TOKEN_EXPIRY_KEY = 'token_expiry'
const REFRESH_TOKEN_EXPIRY_KEY = 'refresh_token_expiry'

// Token refresh timing
const REFRESH_BUFFER_MS = 60000 // Refresh 1 minute before expiry
const REFRESH_RETRY_DELAY_MS = 5000 // Retry failed refresh after 5 seconds
// Cap transient-failure retries so a permanently-broken refresh (e.g. the
// backend was restarted and the server-side session is gone) lands the user on
// /login instead of looping "Token refresh failed" every 5s until the refresh
// token's multi-day expiry.
const MAX_REFRESH_RETRIES = 3

/**
 * Interface for token data
 */
export interface TokenData {
  accessToken: string
  refreshToken: string
  expiresAt: number
  refreshExpiresAt: number
}

/**
 * Interface for token refresh callback
 */
export interface TokenRefreshCallbacks {
  onRefreshSuccess?: (tokens: TokenData) => void
  onRefreshFailure?: (error: Error) => void
  onTokenExpired?: () => void
}

class TokenStorageManager {
  private refreshTimeout: NodeJS.Timeout | null = null
  private refreshCallbacks: TokenRefreshCallbacks = {}
  private refreshPromise: Promise<boolean> | null = null
  private authEnabled: boolean | null = null
  private refreshRetryCount = 0

  /**
   * Store authentication tokens securely
   */
  storeTokens(tokens: {
    access_token: string
    refresh_token: string
    expires_in: number
    refresh_expires_in: number
  }): TokenData {
    const now = Date.now()
    const expiresAt = now + (tokens.expires_in * 1000)
    const refreshExpiresAt = now + (tokens.refresh_expires_in * 1000)

    // Store in localStorage (consider upgrading to secure storage in the future)
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
    localStorage.setItem(TOKEN_EXPIRY_KEY, expiresAt.toString())
    localStorage.setItem(REFRESH_TOKEN_EXPIRY_KEY, refreshExpiresAt.toString())

    const tokenData: TokenData = {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      expiresAt,
      refreshExpiresAt,
    }

    // Schedule automatic refresh
    this.scheduleTokenRefresh(tokenData)

    return tokenData
  }

  /**
   * Get current access token
   */
  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY)
  }

  /**
   * Get current refresh token
   */
  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  }

  /**
   * Get all token data
   */
  getTokenData(): TokenData | null {
    const accessToken = this.getAccessToken()
    const refreshToken = this.getRefreshToken()
    const expiresAt = localStorage.getItem(TOKEN_EXPIRY_KEY)
    const refreshExpiresAt = localStorage.getItem(REFRESH_TOKEN_EXPIRY_KEY)

    if (!accessToken || !refreshToken || !expiresAt || !refreshExpiresAt) {
      return null
    }

    return {
      accessToken,
      refreshToken,
      expiresAt: parseInt(expiresAt, 10),
      refreshExpiresAt: parseInt(refreshExpiresAt, 10),
    }
  }

  /**
   * Check if access token is valid (not expired)
   */
  isAccessTokenValid(): boolean {
    const tokenData = this.getTokenData()
    if (!tokenData) return false

    return Date.now() < tokenData.expiresAt
  }

  /**
   * Check if refresh token is valid (not expired)
   */
  isRefreshTokenValid(): boolean {
    const tokenData = this.getTokenData()
    if (!tokenData) return false

    return Date.now() < tokenData.refreshExpiresAt
  }

  /**
   * Check if tokens need refresh (within buffer time)
   */
  needsRefresh(): boolean {
    const tokenData = this.getTokenData()
    if (!tokenData) return false

    return Date.now() > (tokenData.expiresAt - REFRESH_BUFFER_MS)
  }

  /**
   * Set callback functions for token refresh events
   */
  setRefreshCallbacks(callbacks: TokenRefreshCallbacks): void {
    this.refreshCallbacks = callbacks
  }

  /**
   * Schedule automatic token refresh
   */
  private scheduleTokenRefresh(tokenData: TokenData): void {
    // Skip scheduling if auth is disabled
    if (this.authEnabled === false) {
      return
    }

    // Clear existing timeout
    if (this.refreshTimeout) {
      clearTimeout(this.refreshTimeout)
    }

    // Calculate when to refresh (before expiry)
    const refreshAt = tokenData.expiresAt - REFRESH_BUFFER_MS
    const delay = Math.max(0, refreshAt - Date.now())

    this.refreshTimeout = setTimeout(() => {
      void this.attemptTokenRefresh()
    }, delay)
  }

  /**
   * Attempt to refresh the access token.
   *
   * Coalesces concurrent callers onto one in-flight refresh: the request-time
   * refresh (client.ts), the scheduled timer, the SSE client's 401 handler,
   * and app boot can all fire together on page load. The old implementation
   * returned false to whoever lost that race, so their request went out with
   * the stale token, got a 401, and AuthGuard bounced the user to /login on
   * nearly every visit. Awaiting the shared promise means every caller
   * proceeds only once the fresh token is actually stored.
   */
  async attemptTokenRefresh(): Promise<boolean> {
    this.refreshPromise ??= this.performTokenRefresh().finally(() => {
      this.refreshPromise = null
    })
    return this.refreshPromise
  }

  private async performTokenRefresh(): Promise<boolean> {
    // Skip refresh if auth is disabled
    if (this.authEnabled === false) {
      return false
    }

    const tokenData = this.getTokenData()
    if (!tokenData || !this.isRefreshTokenValid()) {
      this.refreshCallbacks.onTokenExpired?.()
      return false
    }

    try {
      const response: RefreshTokenResponse = await refreshTokenAPI(tokenData.refreshToken)

      // Store new tokens
      const newTokenData = this.storeTokens(response)

      this.refreshRetryCount = 0
      this.refreshCallbacks.onRefreshSuccess?.(newTokenData)
      return true
    } catch (error) {
      // Check if error is due to auth being disabled
      if (error instanceof Error && error.message.includes('Authentication is disabled')) {
        console.info('Token refresh skipped: Authentication is disabled by server configuration')
        this.authEnabled = false
        return false
      }
      // Rotation race: the server rotates AND revokes the refresh token on
      // every use, so if another tab (or PWA window) refreshed first, the
      // token this call sent is already revoked — a 4xx here does NOT mean
      // the session is dead. If localStorage now holds a different, live
      // token pair (stored by the winner), adopt it instead of wiping the
      // session and forcing a re-login.
      const storedRefreshToken = this.getRefreshToken()
      if (
        storedRefreshToken &&
        storedRefreshToken !== tokenData.refreshToken &&
        this.isAccessTokenValid()
      ) {
        console.warn('Token refresh superseded by another tab; adopting its tokens')
        this.refreshRetryCount = 0
        return true
      }
      console.error('Token refresh failed:', error)
      this.handleRefreshFailure(error as Error)
      return false
    }
  }

  /**
   * Decide whether a failed refresh is worth retrying, or whether the session
   * is dead and the user should be routed to /login.
   *
   * A 4xx means the server rejected the refresh token itself (invalid, revoked,
   * or its server-side session no longer exists — e.g. after a backend
   * restart). Retrying can never succeed, so give up immediately. Only
   * genuinely transient failures (network drops, 5xx) get a bounded retry;
   * without a cap a permanently-broken refresh loops every few seconds until
   * the refresh token's multi-day expiry.
   */
  private handleRefreshFailure(error: Error): void {
    const status = (error as { statusCode?: number; status?: number }).statusCode
      ?? (error as { status?: number }).status
    const isUnrecoverable = typeof status === 'number' && status >= 400 && status < 500
    const canRetry =
      !isUnrecoverable &&
      this.isRefreshTokenValid() &&
      this.refreshRetryCount < MAX_REFRESH_RETRIES

    if (canRetry) {
      this.refreshRetryCount += 1
      // By the time this fires, the failed attempt's shared promise has been
      // cleared, so this starts a fresh coalesced refresh.
      setTimeout(() => {
        void this.attemptTokenRefresh()
      }, REFRESH_RETRY_DELAY_MS)
    } else {
      // Unrecoverable or out of retries: clear the dead session and signal
      // expiry so the auth layer routes the user to /login instead of looping.
      this.refreshRetryCount = 0
      if (this.refreshTimeout) {
        clearTimeout(this.refreshTimeout)
        this.refreshTimeout = null
      }
      this.refreshCallbacks.onTokenExpired?.()
    }

    this.refreshCallbacks.onRefreshFailure?.(error)
  }

  /**
   * Manually refresh tokens
   */
  async refreshTokens(): Promise<TokenData | null> {
    const success = await this.attemptTokenRefresh()
    return success ? this.getTokenData() : null
  }

  /**
   * Clear all stored tokens
   */
  async clearTokens(): Promise<void> {
    // Revoke refresh token on the server if available
    const refreshToken = this.getRefreshToken()
    if (refreshToken) {
      try {
        await revokeRefreshToken(refreshToken)
      } catch (error) {
        console.warn('Failed to revoke refresh token:', error)
        // Continue with local cleanup even if server revocation fails
      }
    }

    // Clear from localStorage
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(TOKEN_EXPIRY_KEY)
    localStorage.removeItem(REFRESH_TOKEN_EXPIRY_KEY)

    // Clear refresh timeout
    if (this.refreshTimeout) {
      clearTimeout(this.refreshTimeout)
      this.refreshTimeout = null
    }
  }

  /**
   * Initialize token manager (call on app startup)
   */
  async initialize(authStatus: AuthStatus): Promise<void> {
    this.authEnabled = authStatus.enabled

    if (!authStatus.enabled || authStatus.mode === 'none') {
      console.info('Token initialization skipped: Authentication is disabled')
      return
    }

    const tokenData = this.getTokenData()
    if (tokenData) {
      // Check if tokens are still valid
      if (this.isRefreshTokenValid()) {
        if (this.needsRefresh()) {
          // Refresh now and make callers (the auth provider's session-restore
          // gate) wait for it, so AuthGuard can't bounce to /login while the
          // stored session is still being revived.
          await this.attemptTokenRefresh()
        } else {
          // Schedule refresh for later
          this.scheduleTokenRefresh(tokenData)
        }
      } else {
        // Tokens expired, clear them
        void this.clearTokens()
      }
    }
  }

  /**
   * Cleanup when app is closing
   */
  cleanup(): void {
    if (this.refreshTimeout) {
      clearTimeout(this.refreshTimeout)
      this.refreshTimeout = null
    }
  }
}

// Export singleton instance
export const tokenStorage = new TokenStorageManager()

// Export utility functions with proper binding
export const storeTokens = tokenStorage.storeTokens.bind(tokenStorage)
export const getAccessToken = tokenStorage.getAccessToken.bind(tokenStorage)
export const getRefreshToken = tokenStorage.getRefreshToken.bind(tokenStorage)
export const getTokenData = tokenStorage.getTokenData.bind(tokenStorage)
export const isAccessTokenValid = tokenStorage.isAccessTokenValid.bind(tokenStorage)
export const isRefreshTokenValid = tokenStorage.isRefreshTokenValid.bind(tokenStorage)
export const needsRefresh = tokenStorage.needsRefresh.bind(tokenStorage)
export const setRefreshCallbacks = tokenStorage.setRefreshCallbacks.bind(tokenStorage)
export const refreshTokens = tokenStorage.refreshTokens.bind(tokenStorage)
export const clearTokens = tokenStorage.clearTokens.bind(tokenStorage)
export const initializeTokenStorage = tokenStorage.initialize.bind(tokenStorage)
export const cleanupTokenStorage = tokenStorage.cleanup.bind(tokenStorage)
