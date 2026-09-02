import axios, { type InternalAxiosRequestConfig } from 'axios'
import { ACCESS_TOKEN_KEY, recordActivity, redirectToLogin, REFRESH_TOKEN_KEY } from './session'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!refreshToken) return null
  try {
    // Plain axios (not the `api` instance) so this call never re-enters these interceptors.
    const { data } = await axios.post(`${import.meta.env.VITE_API_URL}/auth/refresh`, {
      refresh_token: refreshToken,
    })
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
    return data.access_token as string
  } catch {
    return null
  }
}

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

api.interceptors.response.use(
  (response) => {
    recordActivity()
    return response
  },
  async (error) => {
    const config = error.config as RetryableConfig | undefined
    const isLoginRequest = config?.url === '/auth/login'

    if (error.response?.status === 401 && config && !config._retried && !isLoginRequest) {
      config._retried = true
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null
      })
      const newToken = await refreshPromise
      if (newToken) {
        recordActivity()
        config.headers.Authorization = `Bearer ${newToken}`
        return api(config)
      }
      redirectToLogin('expired')
      return Promise.reject(error)
    }

    return Promise.reject(error)
  },
)
