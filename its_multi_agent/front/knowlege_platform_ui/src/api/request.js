import axios from 'axios'
import { clearAuthSession, getAuthToken } from './auth'

const service = axios.create({
  baseURL: '/api',
  timeout: 50000
})

service.interceptors.request.use(config => {
  const token = getAuthToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

service.interceptors.response.use(
  response => response.data,
  error => {
    if (error.response?.status === 401) {
      clearAuthSession()
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    }
    return Promise.reject(error)
  }
)

export default service
