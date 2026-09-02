import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'
import {
  ACCESS_TOKEN_KEY,
  clearSession,
  getLastActivity,
  INACTIVITY_LIMIT_MS,
  recordActivity,
  REFRESH_TOKEN_KEY,
} from './session'
import type { AdminUser } from '@/types'

export type CurrentUser = AdminUser

interface AuthContextValue {
  user: CurrentUser | null
  isAuthenticated: boolean
  loading: boolean
  login: (dni: string, password: string) => Promise<void>
  logout: () => void
  hasPermission: (code: string) => boolean
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const ACTIVITY_EVENTS = ['mousedown', 'keydown', 'scroll', 'touchstart'] as const
const INACTIVITY_CHECK_INTERVAL_MS = 60 * 1000

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    api
      .get<CurrentUser>('/auth/me')
      .then((res) => setUser(res.data))
      .catch(() => clearSession())
      .finally(() => setLoading(false))
  }, [])

  // Closes the session after INACTIVITY_LIMIT_MS with zero user activity, independent of
  // whether the underlying tokens are still technically valid (silent refresh in api.ts
  // would otherwise keep a completely idle tab logged in indefinitely).
  useEffect(() => {
    if (!user) return

    const onActivity = () => recordActivity()
    ACTIVITY_EVENTS.forEach((event) => window.addEventListener(event, onActivity, { passive: true }))

    const interval = window.setInterval(() => {
      if (Date.now() - getLastActivity() > INACTIVITY_LIMIT_MS) {
        clearSession()
        setUser(null)
        navigate('/login?reason=inactivity', { replace: true })
      }
    }, INACTIVITY_CHECK_INTERVAL_MS)

    return () => {
      ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, onActivity))
      window.clearInterval(interval)
    }
  }, [user, navigate])

  async function login(dni: string, password: string) {
    setLoading(true)
    try {
      const { data } = await api.post('/auth/login', { dni, password })
      localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
      localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
      recordActivity()
      const me = await api.get<CurrentUser>('/auth/me')
      setUser(me.data)
    } finally {
      setLoading(false)
    }
  }

  function logout() {
    clearSession()
    setUser(null)
  }

  function hasPermission(code: string) {
    return !!user && (user.is_superuser || user.permission_codes.includes(code))
  }

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, loading, login, logout, hasPermission }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
