const TOKEN_KEY = 'itsAuthToken'
const USER_KEY = 'itsAuthUser'

export const getAuthToken = () => sessionStorage.getItem(TOKEN_KEY) || ''

export const getAuthUser = () => {
  try {
    return JSON.parse(sessionStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export const setAuthSession = (token, user) => {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}

export const clearAuthSession = () => {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem('currentUserId')
}

export const authFetch = async (url, options = {}) => {
  const headers = new Headers(options.headers || {})
  const token = getAuthToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(url, { ...options, headers })
  if (response.status === 401 && token === getAuthToken()) {
    clearAuthSession()
    window.dispatchEvent(new CustomEvent('auth:unauthorized'))
  }
  return response
}

export const readJsonResponse = async (response) => {
  const text = await response.text()
  if (!text.trim()) return {}
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`服务返回了无效数据（HTTP ${response.status}）`)
  }
}

export const readErrorMessage = async (response, fallback = '请求失败，请稍后重试') => {
  const data = await readJsonResponse(response)
  if (typeof data.detail === 'string' && data.detail.trim()) return data.detail
  if (typeof data.message === 'string' && data.message.trim()) return data.message
  return `${fallback}（HTTP ${response.status}）`
}

export const register = async (username, password) => {
  const response = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await readJsonResponse(response)
  if (!response.ok) throw new Error(data.detail || '注册失败，请稍后重试')
  setAuthSession(data.access_token, data.user)
  return data.user
}
