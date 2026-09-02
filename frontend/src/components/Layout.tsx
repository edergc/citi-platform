import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  FileText,
  HelpCircle,
  Inbox,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  Network,
  Radar,
  Scale,
  Server,
  Settings,
  Siren,
  UserRound,
  Wifi,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ChangePasswordDialog } from '@/components/ChangePasswordDialog'
import { NotificationBell } from '@/components/NotificationBell'
import { CriticalAlertBanner } from '@/components/CriticalAlertBanner'
import { CriticalAlertModal } from '@/components/CriticalAlertModal'
import { InstitutionalHeaderBackdrop } from '@/components/InstitutionalHeaderBackdrop'

function RailLink({ to, end, icon: Icon, label }: { to: string; end?: boolean; icon: LucideIcon; label: string }) {
  return (
    <NavLink to={to} end={end} title={label} aria-label={label} className="group relative flex h-11 w-11 items-center justify-center">
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute left-0 h-5 w-0.5 rounded-r bg-amber-400" />}
          <span
            className={cn(
              'flex h-9 w-9 items-center justify-center rounded-lg transition-colors',
              isActive ? 'bg-amber-500/15 text-amber-400' : 'text-slate-500 group-hover:bg-slate-800/70 group-hover:text-slate-200',
            )}
          >
            <Icon className="h-[18px] w-[18px]" />
          </span>
        </>
      )}
    </NavLink>
  )
}

export function Layout() {
  const { user, logout, hasPermission } = useAuth()
  const navigate = useNavigate()
  const [changingPassword, setChangingPassword] = useState(false)

  const navItems: { to: string; end?: boolean; icon: LucideIcon; label: string; show?: boolean }[] = [
    { to: '/', end: true, icon: LayoutGrid, label: 'Sistemas', show: hasPermission('systems.manage') },
    { to: '/servers', icon: Server, label: 'Servidores' },
    { to: '/connectivity', icon: Wifi, label: 'Conectividad' },
    { to: '/network', icon: Network, label: 'Diagnóstico de red' },
    { to: '/problemas', icon: AlertTriangle, label: 'Problemas' },
    { to: '/alerts', icon: Siren, label: 'Alertas' },
    { to: '/mantenimiento', icon: Wrench, label: 'Mantenimiento' },
    { to: '/sinteticos', icon: Radar, label: 'Sintéticos' },
    { to: '/reports/weekly', icon: FileText, label: 'Reporte semanal' },
    { to: '/notifications', icon: Inbox, label: 'Notificaciones', show: hasPermission('notifications.manage') },
    { to: '/dashboards', icon: LayoutDashboard, label: 'Dashboards', show: user?.is_superuser },
    { to: '/admin', icon: Settings, label: 'Administración', show: user?.is_superuser },
  ]

  const initials = user?.full_name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')

  return (
    <div className="flex min-h-screen bg-[#0b0e14]">
      <aside className="flex w-16 shrink-0 flex-col items-center border-r border-slate-800/80 bg-[#0d1117] py-3">
        <NavLink
          to="/"
          title="CITI Platform"
          aria-label="CITI Platform"
          className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-red-950 text-amber-400"
        >
          <Scale className="h-5 w-5" />
        </NavLink>

        <nav className="flex flex-1 flex-col items-center gap-0.5 overflow-y-auto">
          {navItems
            .filter((item) => item.show !== false)
            .map((item) => (
              <RailLink key={item.to} to={item.to} end={item.end} icon={item.icon} label={item.label} />
            ))}
        </nav>

        <div className="flex flex-col items-center gap-0.5 pt-2">
          <NotificationBell />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                title={user?.full_name}
                className="flex h-9 w-9 items-center justify-center rounded-full bg-red-900/60 text-xs font-semibold text-amber-400 transition-colors hover:bg-red-900"
              >
                {initials}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="right" align="end">
              <DropdownMenuLabel>{user?.username}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => navigate('/profile')}>
                <UserRound className="h-4 w-4" />
                Mi perfil
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setChangingPassword(true)}>
                <KeyRound className="h-4 w-4" />
                Cambiar contraseña
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => window.open('/docs/guia-tecnicos.html', '_blank', 'noopener')}>
                <HelpCircle className="h-4 w-4" />
                Guía de uso
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-red-400 data-[highlighted]:text-red-300" onSelect={logout}>
                <LogOut className="h-4 w-4" />
                Cerrar sesión
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      <div className="flex min-h-screen flex-1 flex-col">
        <header className="relative flex h-12 shrink-0 items-center overflow-hidden border-b border-amber-500/20 px-5">
          <InstitutionalHeaderBackdrop />
          <div className="relative z-10 flex items-baseline gap-2">
            <h1 className="text-sm font-semibold text-slate-100">CITI Platform</h1>
            <p className="text-xs text-slate-400">Centro de Operaciones Tecnológicas</p>
          </div>
        </header>

        <CriticalAlertBanner />

        <main className="mx-auto w-full max-w-[1600px] flex-1 px-5 py-5">
          <Outlet />
        </main>
      </div>

      <ChangePasswordDialog open={changingPassword} onOpenChange={setChangingPassword} />
      <CriticalAlertModal />
    </div>
  )
}
