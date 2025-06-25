/**
 * Secure Token Storage Utility
 *
 * Provides secure storage and management of authentication tokens with automatic
 * refresh functionality and secure cleanup.
 */

import { refreshToken as refreshTokenAPI, revokeRefreshToken, getAuthStatus } from '@/api/endpoints'
import type { RefreshTokenResponse } from '@/api/types'

// Storage keys
const ACCESS_TOKEN_KEY = 'auth_token'
const REFRESH_TOKEN_KEY = 'refresh_token'
const TOKEN_EXPIRY_KEY = 'token_expiry'
const REFRESH_TOKEN_EXPIRY_KEY = 'refresh_token_expiry'

// Token refresh timing
const REFRESH_BUFFER_MS = 60000 // Refresh 1 minute before expiry
const REFRESH_RETRY_DELAY_MS = 5000 // Retry failed refresh after 5 seconds

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
  private isRefreshing = false
  private authEnabled: boolean | null = null

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
   * Attempt to refresh the access token
   */
  async attemptTokenRefresh(): Promise<boolean> {
    if (this.isRefreshing) {
      return false // Already refreshing
    }

    // Skip refresh if auth is disabled
    if (this.authEnabled === false) {
      return false
    }

    const tokenData = this.getTokenData()
    if (!tokenData || !this.isRefreshTokenValid()) {
      this.refreshCallbacks.onTokenExpired?.()
      return false
    }

    this.isRefreshing = true

    try {
      const response: RefreshTokenResponse = await refreshTokenAPI(tokenData.refreshToken)

      // Store new tokens
      const newTokenData = this.storeTokens(response)

      this.refreshCallbacks.onRefreshSuccess?.(newTokenData)
      return true
    } catch (error) {
      // Check if error is due to auth being disabled
      if (error instanceof Error && error.message.includes('Authentication is disabled')) {
        console.info('Token refresh skipped: Authentication is disabled by server configuration')
        this.authEnabled = false
        return false
      }
      console.error('Token refresh failed:', error)

      // Schedule retry if refresh token is still valid
      if (this.isRefreshTokenValid()) {
        setTimeout(() => {
          this.isRefreshing = false
          void this.attemptTokenRefresh()
        }, REFRESH_RETRY_DELAY_MS)
      } else {
        this.refreshCallbacks.onTokenExpired?.()
      }

      this.refreshCallbacks.onRefreshFailure?.(error as Error)
      return false
    } finally {
      this.isRefreshing = false
    }
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

    this.isRefreshing = false
  }

  /**
   * Initialize token manager (call on app startup)
   */
  async initialize(): Promise<void> {
    // Check auth status first
    try {
      const authStatus = await getAuthStatus()
      this.authEnabled = authStatus.enabled

      // If auth is disabled, skip token initialization
      if (!authStatus.enabled || authStatus.mode === 'none') {
        console.info('Token initialization skipped: Authentication is disabled')
        return
      }
    } catch (error) {
      // If we can't get auth status, assume auth is enabled
      console.warn('Failed to get auth status, assuming authentication is enabled:', error)
      this.authEnabled = true
    }

    const tokenData = this.getTokenData()
    if (tokenData) {
      // Check if tokens are still valid
      if (this.isRefreshTokenValid()) {
        if (this.needsRefresh()) {
          // Immediately refresh if needed
          void this.attemptTokenRefresh()
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
