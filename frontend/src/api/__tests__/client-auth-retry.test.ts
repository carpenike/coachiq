/**
 * Regression tests for the request-time 401 refresh-and-retry in `apiRequest`.
 *
 * A request can leave with an access token that is already dead server-side —
 * the proactive refresh only fires inside the pre-expiry buffer, and a
 * backgrounded tablet wakes with an expired token whose refresh timer was
 * throttled. Without a response-side retry the request 401s, the query errors,
 * and entity collections blank out (only entities still receiving live SSE
 * updates keep any data). These tests pin the fix: one 401 triggers a single
 * token refresh + retry; auth endpoints are excluded to avoid recursing into
 * the refresh they are part of.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RefreshTokenResponse } from '@/api/types'

const refreshTokenAPI = vi.fn<(token: string) => Promise<RefreshTokenResponse>>()

vi.mock('@/api/endpoints', () => ({
  refreshToken: (token: string) => refreshTokenAPI(token),
  revokeRefreshToken: vi.fn().mockResolvedValue(undefined),
  getAuthStatus: vi.fn().mockResolvedValue({ enabled: true, mode: 'multi' }),
}))

// Import AFTER the mock so the modules under test bind to the mocked endpoints.
const { apiGet } = await import('@/api/client')
const { tokenStorage } = await import('@/lib/token-storage')

/** A live (not near-expiry) access token so the proactive refresh stays a no-op. */
function seedLiveTokens(accessToken = 'access-original') {
  const now = Date.now()
  localStorage.setItem('auth_token', accessToken)
  localStorage.setItem('refresh_token', 'refresh-original')
  localStorage.setItem('token_expiry', String(now + 600_000))
  localStorage.setItem('refresh_token_expiry', String(now + 7 * 24 * 3_600_000))
}

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response
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

function authHeaderOf(call: Parameters<typeof fetch> | undefined): string | undefined {
  const init = call?.[1]
  const headers = init?.headers as Record<string, string> | undefined
  return headers?.Authorization
}

const fetchMock = vi.fn<typeof fetch>()

describe('apiRequest 401 refresh-and-retry', () => {
  beforeEach(() => {
    localStorage.clear()
    refreshTokenAPI.mockReset()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    tokenStorage.setRefreshCallbacks({})
  })

  afterEach(() => {
    localStorage.clear()
    tokenStorage.cleanup()
    vi.unstubAllGlobals()
  })

  it('refreshes once and retries with the new token after a 401', async () => {
    seedLiveTokens()
    refreshTokenAPI.mockResolvedValue(refreshResponse('fresh'))
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))

    const result = await apiGet<{ ok: boolean }>('/api/v1/entities')

    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(refreshTokenAPI).toHaveBeenCalledTimes(1)
    // The first attempt carried the dead token; the retry carries the fresh one.
    expect(authHeaderOf(fetchMock.mock.calls[0])).toBe('Bearer access-original')
    expect(authHeaderOf(fetchMock.mock.calls[1])).toBe('Bearer access-fresh')
  })

  it('surfaces the 401 when the retry still fails', async () => {
    seedLiveTokens()
    refreshTokenAPI.mockResolvedValue(refreshResponse('fresh'))
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'still dead' }))

    await expect(apiGet('/api/v1/entities')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(refreshTokenAPI).toHaveBeenCalledTimes(1)
  })

  it('does not refresh-and-retry auth endpoints (avoids recursing into the refresh)', async () => {
    seedLiveTokens()
    refreshTokenAPI.mockResolvedValue(refreshResponse('fresh'))
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: 'bad refresh token' }))

    await expect(apiGet('/api/auth/refresh')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(refreshTokenAPI).not.toHaveBeenCalled()
  })

  it('does not retry when no valid refresh token is available', async () => {
    // Live access token but an expired refresh token: nothing to refresh with.
    const now = Date.now()
    localStorage.setItem('auth_token', 'access-original')
    localStorage.setItem('refresh_token', 'refresh-original')
    localStorage.setItem('token_expiry', String(now + 600_000))
    localStorage.setItem('refresh_token_expiry', String(now - 1_000))
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))

    await expect(apiGet('/api/v1/entities')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(refreshTokenAPI).not.toHaveBeenCalled()
  })
})
