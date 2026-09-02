import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/lib/auth'

export function RequirePermission({ code, redirectTo = '/servers' }: { code: string; redirectTo?: string }) {
  const { hasPermission } = useAuth()
  return hasPermission(code) ? <Outlet /> : <Navigate to={redirectTo} replace />
}
