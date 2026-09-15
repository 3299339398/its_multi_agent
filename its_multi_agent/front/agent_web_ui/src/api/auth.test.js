import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearAuthSession,
  authFetch,
  getAuthToken,
  readErrorMessage,
  readJsonResponse,
  setAuthSession,
} from './auth'

describe('auth session storage', () => {
  beforeEach(() => clearAuthSession())
  afterEach(() => vi.unstubAllGlobals())

  it('does not invalidate a new login when an old token receives a late 401', async () => {
    let respond
    vi.stubGlobal('fetch', () => new Promise(resolve => { respond = resolve }))
    setAuthSession('old-token', { username: 'alice' })
    const request = authFetch('/api/user_sessions')
    setAuthSession('new-token', { username: 'bob' })
    respond(new Response('', { status: 401 }))
    await request
    expect(getAuthToken()).toBe('new-token')
  })

  it('invalidates the current login when its token receives a 401', async () => {
    vi.stubGlobal('fetch', async () => new Response('', { status: 401 }))
    setAuthSession('expired-token', { username: 'alice' })
    await authFetch('/api/user_sessions')
    expect(getAuthToken()).toBe('')
  })

  it('keeps credentials in the current tab session', () => {
    setAuthSession('signed-token', { username: 'user' })

    expect(getAuthToken()).toBe('signed-token')
    expect(localStorage.getItem('itsAuthToken')).toBeNull()
  })

  it('removes legacy persistent credentials when clearing a session', () => {
    localStorage.setItem('itsAuthToken', 'legacy-token')

    clearAuthSession()

    expect(getAuthToken()).toBe('')
    expect(localStorage.getItem('itsAuthToken')).toBeNull()
  })

  it('handles an empty proxy response without a JSON parsing error', async () => {
    const response = new Response('', { status: 502 })

    await expect(readJsonResponse(response)).resolves.toEqual({})
  })

  it('reports invalid non-empty JSON clearly', async () => {
    const response = new Response('upstream failed', { status: 502 })

    await expect(readJsonResponse(response)).rejects.toThrow('服务返回了无效数据')
  })

  it('uses the backend Chinese error detail', async () => {
    const response = new Response('{"detail":"用户名或密码错误"}', {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })

    await expect(readErrorMessage(response, '登录失败')).resolves.toBe('用户名或密码错误')
  })

  it('uses a localized fallback for an empty error response', async () => {
    const response = new Response('', { status: 502 })

    await expect(readErrorMessage(response)).resolves.toBe('请求失败，请稍后重试（HTTP 502）')
  })
})
