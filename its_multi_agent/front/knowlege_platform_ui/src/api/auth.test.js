import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearAuthSession,
  getAuthToken,
  getAuthUser,
  login,
  verifyAuthSession
} from './auth'

describe('authentication session', () => {
  beforeEach(() => {
    clearAuthSession()
    vi.restoreAllMocks()
  })

  it('stores a successful login for the current browser tab', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: 'signed-token',
        user: { username: 'admin', role: 'admin' }
      })
    }))

    await login('admin', 'password123')

    expect(getAuthToken()).toBe('signed-token')
    expect(getAuthUser()).toEqual({ username: 'admin', role: 'admin' })
  })

  it('clears an invalid persisted session', async () => {
    sessionStorage.setItem('itsKnowledgeAuthToken', 'expired-token')
    sessionStorage.setItem('itsKnowledgeAuthUser', JSON.stringify({ username: 'admin', role: 'admin' }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: '登录状态已失效' })
    }))

    await expect(verifyAuthSession()).rejects.toThrow('登录状态已失效')
    expect(getAuthToken()).toBe('')
    expect(getAuthUser()).toBeNull()
  })
})
