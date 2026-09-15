const TOKEN_KEY = 'itsKnowledgeAuthToken'
const USER_KEY = 'itsKnowledgeAuthUser'

let verifiedToken = ''
let verificationPromise = null

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
  verifiedToken = token
}

export const clearAuthSession = () => {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
  verifiedToken = ''
  verificationPromise = null
}

export const login = async (username, password) => {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || '登录失败，请稍后重试')
  setAuthSession(data.access_token, data.user)
  return data.user
}

export const register = async (username, password) => {
  const response = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || '注册失败，请稍后重试')
  setAuthSession(data.access_token, data.user)
  return data.user
}

export const verifyAuthSession = async () => {
  const token = getAuthToken()
  if (!token) return null
  if (token === verifiedToken) return getAuthUser()
  if (verificationPromise) return verificationPromise

  verificationPromise = fetch('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` }
  })
    .then(async response => {
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || '登录状态已失效')
      setAuthSession(token, data.user)
      return data.user
    })
    .catch(error => {
      clearAuthSession()
      throw error
    })
    .finally(() => {
      verificationPromise = null
    })

  return verificationPromise
}
