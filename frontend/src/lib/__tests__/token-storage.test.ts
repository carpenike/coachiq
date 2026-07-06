/**
 * Tests for the token refresh lifecycle: coalescing of concurrent refreshes
 * and survival of the server's refresh-token rotation race.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RefreshTokenResponse } from '@/api/types'

const refreshTokenAPI = vi.fn<(token: string) => Promise<RefreshTokenResponse>>()

vi.mock('@/api/endpoints', () => ({
  refreshToken: (token: string) => refreshTokenAPI(token),
  revokeRefreshToken: vi.fn().mockResolvedValue(undefined),
  getAuthStatus: vi.fn().mockResolvedValue({ enabled: true, mode: 'multi' }),
}))

// Import AFTER the mock so the module under test binds to the mocked API.
const { tokenStorage } = await import('@/lib/token-storage')

function seedTokens({
  accessExpired = true,
  refreshToken = 'refresh-original',
}: { accessExpired?: boolean; refreshToken?: string } = {}) {
  const now = Date.now()
  localStorage.setItem('auth_token', 'access-original')
  localStorage.setItem('refresh_token', refreshToken)
  localStorage.setItem('token_expiry', String(accessExpired ? now - 1_000 : now + 600_000))
  localStorage.setItem('refresh_token_expiry', String(now + 7 * 24 * 3_600_000))
}

function refreshResponse(suffix: string): RefreshTokenResponse {
  return {
    access_token: `access-${suffix}`,
    refresh_token: `refresh-${suffix}`,
    token_type: 'bearer',
    expires_in: 900,
    refresh_expires_in: 30 * 24 * 3600,
  } as RefreshTokenResponse
}

describe('tokenStorage.attemptTokenRefresh', () => {
  beforeEach(() => {
    localStorage.clear()
    refreshTokenAPI.mockReset()
    tokenStorage.setRefreshCallbacks({})
  })

  afterEach(() => {
    localStorage.clear()
    tokenStorage.cleanup()
  })

  it('coalesces concurrent callers onto a single refresh request', async () => {
    seedTokens()
    let resolveRefresh!: (value: RefreshTokenResponse) => void
    refreshTokenAPI.mockImplementation(
      () => new Promise((resolve) => { resolveRefresh = resolve })
    )

    // Simulates page load: request-time refresh, boot init, and the SSE 401
    // handler all firing together.
    const first = tokenStorage.attemptTokenRefresh()
    const second = tokenStorage.attemptTokenRefresh()
    const third = tokenStorage.attemptTokenRefresh()

    resolveRefresh(refreshResponse('rotated'))
    const results = await Promise.all([first, second, third])

    expect(results).toEqual([true, true, true])
    expect(refreshTokenAPI).toHaveBeenCalledTimes(1)
    expect(tokenStorage.getAccessToken()).toBe('access-rotated')
  })

  it('starts a new refresh after the previous one settles', async () => {
    seedTokens()
    refreshTokenAPI.mockResolvedValue(refreshResponse('one'))
    await tokenStorage.attemptTokenRefresh()

    // Force the freshly stored access token to look stale again.
    localStorage.setItem('token_expiry', String(Date.now() - 1_000))
    refreshTokenAPI.mockResolvedValue(refreshResponse('two'))
    await tokenStorage.attemptTokenRefresh()

    expect(refreshTokenAPI).toHaveBeenCalledTimes(2)
    expect(tokenStorage.getAccessToken()).toBe('access-two')
  })

  it('adopts tokens rotated by another tab instead of killing the session', async () => {
    seedTokens()
    const onTokenExpired = vi.fn()
    tokenStorage.setRefreshCallbacks({ onTokenExpired })

    refreshTokenAPI.mockImplementation(() => {
      // While our request is in flight, "another tab" wins the rotation race:
      // it stores the rotated pair, and the server rejects our now-revoked
      // token with a 4xx.
      const now = Date.now()
      localStorage.setItem('auth_token', 'access-winner')
      localStorage.setItem('refresh_token', 'refresh-winner')
      localStorage.setItem('token_expiry', String(now + 600_000))
      localStorage.setItem('refresh_token_expiry', String(now + 7 * 24 * 3_600_000))
      const error = new Error('Refresh token has been revoked') as Error & { status: number }
      error.status = 401
      return Promise.reject(error)
    })

    const result = await tokenStorage.attemptTokenRefresh()

    expect(result).toBe(true)
    expect(onTokenExpired).not.toHaveBeenCalled()
    expect(tokenStorage.getAccessToken()).toBe('access-winner')
    expect(tokenStorage.getRefreshToken()).toBe('refresh-winner')
  })

  it('signals expiry when the refresh token is genuinely dead', async () => {
    seedTokens()
    const onTokenExpired = vi.fn()
    tokenStorage.setRefreshCallbacks({ onTokenExpired })

    const error = new Error('Refresh token has been revoked') as Error & { status: number }
    error.status = 401
    refreshTokenAPI.mockRejectedValue(error)

    const result = await tokenStorage.attemptTokenRefresh()

    expect(result).toBe(false)
    expect(onTokenExpired).toHaveBeenCalled()
  })
})
