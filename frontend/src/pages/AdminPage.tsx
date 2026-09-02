import { useMemo, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { api } from '@/lib/api'
import type { AdminUser, AlertRule, AuditLogEntry, Role, Server, Site } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { StatusChip } from '@/components/ui/status-chip'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton, TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth'
import { UserFormDialog } from '@/components/UserFormDialog'
import { RoleFormDialog } from '@/components/RoleFormDialog'
import { SiteFormDialog } from '@/components/SiteFormDialog'
import { SetUserPasswordDialog } from '@/components/SetUserPasswordDialog'
import { AlertRuleFormDialog } from '@/components/AlertRuleFormDialog'
import { actionLabel, entityLabel, formatDetails } from '@/lib/auditLabels'

type Tab = 'users' | 'roles' | 'sites' | 'alerts' | 'audit'

const ALL = '__all__'

function errorDetail(err: unknown, fallback: string): string {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
}

function UsersTab() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const { data: users, isLoading, isError } = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.get<AdminUser[]>('/users')).data,
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => api.delete(`/users/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
    onError: (err: unknown) => window.alert(errorDetail(err, 'No se pudo eliminar el usuario.')),
  })

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return users ?? []
    return (users ?? []).filter((u) =>
      [u.full_name, u.dni, u.email ?? '', u.site_names.join(' '), u.role_name ?? '']
        .join(' ')
        .toLowerCase()
        .includes(term),
    )
  }, [users, search])

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Usuarios del sistema</h3>
        <UserFormDialog trigger={<Button size="sm">+ Nuevo usuario</Button>} />
      </div>

      {isLoading && <TableSkeleton rows={5} cols={7} />}
      {isError && <ErrorMessage>No se pudo cargar la lista de usuarios.</ErrorMessage>}
      {users && users.length === 0 && <p className="text-sm text-slate-500">Todavía no hay usuarios registrados.</p>}

      {users && users.length > 0 && (
        <>
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <Input
              placeholder="Buscar por nombre, DNI, correo, sede o perfil…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="max-w-sm pl-9"
            />
          </div>
          {filteredUsers.length === 0 && <p className="text-sm text-slate-500">Ningún usuario coincide con la búsqueda.</p>}
        </>
      )}

      {filteredUsers.length > 0 && (
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Nombre</th>
              <th className="px-4 py-2 font-medium">DNI</th>
              <th className="px-4 py-2 font-medium">Correo</th>
              <th className="px-4 py-2 font-medium">Sede</th>
              <th className="px-4 py-2 font-medium">Perfil</th>
              <th className="px-4 py-2 font-medium">Estado</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {filteredUsers.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-2 text-slate-100">
                  {u.full_name}
                  {u.is_superuser && (
                    <Badge className="ml-2" variant="info">
                      Administrador
                    </Badge>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-400">{u.dni}</td>
                <td className="px-4 py-2 text-slate-400">{u.email ?? <span className="italic text-slate-600">sin correo</span>}</td>
                <td className="px-4 py-2 text-slate-400">{u.site_names.length > 0 ? u.site_names.join(', ') : '—'}</td>
                <td className="px-4 py-2 text-slate-400">{u.role_name ?? '—'}</td>
                <td className="px-4 py-2">
                  <StatusChip tone={u.is_active ? 'ok' : 'critical'}>{u.is_active ? 'ACTIVO' : 'INACTIVO'}</StatusChip>
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right">
                  <UserFormDialog user={u} trigger={<Button variant="ghost" size="sm">Editar</Button>} />
                  <SetUserPasswordDialog
                    user={u}
                    trigger={
                      <Button variant="ghost" size="sm">
                        Contraseña
                      </Button>
                    }
                  />
                  {u.id !== currentUser?.id && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (confirm(`¿Eliminar al usuario "${u.full_name}"?`)) deleteMutation.mutate(u.id)
                      }}
                    >
                      Eliminar
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}

function RolesTab() {
  const queryClient = useQueryClient()
  const { data: roles, isLoading, isError } = useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await api.get<Role[]>('/roles')).data,
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => api.delete(`/roles/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['roles'] }),
    onError: (err: unknown) => window.alert(errorDetail(err, 'No se pudo eliminar el perfil.')),
  })

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Perfiles y privilegios</h3>
        <RoleFormDialog trigger={<Button size="sm">+ Nuevo perfil</Button>} />
      </div>

      {isLoading && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-20 w-full rounded-md" />
          <Skeleton className="h-20 w-full rounded-md" />
          <Skeleton className="h-20 w-full rounded-md" />
        </div>
      )}
      {isError && <ErrorMessage>No se pudo cargar la lista de perfiles.</ErrorMessage>}
      {roles && roles.length === 0 && <p className="text-sm text-slate-500">Todavía no hay perfiles registrados.</p>}

      <div className="flex flex-col gap-3">
        {roles?.map((role) => (
          <div key={role.id} className="rounded-md border border-slate-800 p-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm font-medium text-slate-100">{role.name}</span>
                {role.is_system_role && (
                  <Badge className="ml-2" variant="info">
                    Sistema
                  </Badge>
                )}
                {role.description && <p className="mt-0.5 text-xs text-slate-400">{role.description}</p>}
              </div>
              <div className="flex items-center gap-1">
                <RoleFormDialog role={role} trigger={<Button variant="ghost" size="sm">Editar</Button>} />
                {!role.is_system_role && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (confirm(`¿Eliminar el perfil "${role.name}"?`)) deleteMutation.mutate(role.id)
                    }}
                  >
                    Eliminar
                  </Button>
                )}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {role.permission_codes.length === 0 ? (
                <span className="text-xs text-slate-500">Sin privilegios de administración (solo lectura)</span>
              ) : (
                role.permission_codes.map((code) => (
                  <Badge key={code} variant="default">
                    {code}
                  </Badge>
                ))
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SitesTab() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const { data: sites, isLoading, isError } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => api.delete(`/sites/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sites'] }),
    onError: (err: unknown) => window.alert(errorDetail(err, 'No se pudo eliminar la sede.')),
  })

  const filteredSites = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return sites ?? []
    return (sites ?? []).filter((s) =>
      [s.name, s.code, s.address ?? ''].join(' ').toLowerCase().includes(term),
    )
  }, [sites, search])

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Sedes</h3>
        <SiteFormDialog trigger={<Button size="sm">+ Nueva sede</Button>} />
      </div>

      {isLoading && <TableSkeleton rows={4} cols={5} />}
      {isError && <ErrorMessage>No se pudo cargar la lista de sedes.</ErrorMessage>}
      {sites && sites.length === 0 && <p className="text-sm text-slate-500">Todavía no hay sedes registradas.</p>}

      {sites && sites.length > 0 && (
        <>
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <Input
              placeholder="Buscar por nombre, código o dirección…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="max-w-sm pl-9"
            />
          </div>
          {filteredSites.length === 0 && <p className="text-sm text-slate-500">Ninguna sede coincide con la búsqueda.</p>}
        </>
      )}

      {filteredSites.length > 0 && (
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Nombre</th>
              <th className="px-4 py-2 font-medium">Código</th>
              <th className="px-4 py-2 font-medium">Dirección</th>
              <th className="px-4 py-2 font-medium">Zona horaria</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {filteredSites.map((site) => (
              <tr key={site.id}>
                <td className="px-4 py-2 text-slate-100">{site.name}</td>
                <td className="px-4 py-2 text-slate-400">{site.code}</td>
                <td className="px-4 py-2 text-slate-400">{site.address ?? '—'}</td>
                <td className="px-4 py-2 text-slate-400">{site.timezone}</td>
                <td className="whitespace-nowrap px-4 py-2 text-right">
                  <Button variant="ghost" size="sm" onClick={() => navigate(`/servers?site=${site.id}&view=lista`)}>
                    Ver servidores
                  </Button>
                  <SiteFormDialog site={site} trigger={<Button variant="ghost" size="sm">Editar</Button>} />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (confirm(`¿Eliminar la sede "${site.name}"?`)) deleteMutation.mutate(site.id)
                    }}
                  >
                    Eliminar
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}

const metricLabel: Record<string, string> = {
  ram_percent: 'RAM',
  cpu_percent: 'CPU',
  disk_percent_used: 'Disco',
}

const conditionSymbol: Record<string, string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
  eq: '=',
}

const severityTone: Record<string, 'info' | 'warning' | 'critical'> = {
  info: 'info',
  warning: 'warning',
  critical: 'critical',
}

const severityLabel: Record<string, string> = {
  info: 'Informativo',
  warning: 'Advertencia',
  critical: 'Crítico',
}

function AlertsTab() {
  const queryClient = useQueryClient()
  const { data: rules, isLoading, isError } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: async () => (await api.get<AlertRule[]>('/alert-rules')).data,
  })
  const { data: servers } = useQuery({
    queryKey: ['servers'],
    queryFn: async () => (await api.get<Server[]>('/servers')).data,
  })
  const hostnameById = new Map((servers ?? []).map((s) => [s.id, s.hostname]))

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => api.delete(`/alert-rules/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-rules'] }),
    onError: (err: unknown) => window.alert(errorDetail(err, 'No se pudo eliminar la regla.')),
  })

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-slate-300">Reglas de alerta</h3>
          <p className="text-xs text-slate-500">Umbrales de CPU/RAM/disco que disparan notificaciones a los responsables de cada sede.</p>
        </div>
        <AlertRuleFormDialog trigger={<Button size="sm">+ Nueva regla</Button>} />
      </div>

      {isLoading && <TableSkeleton rows={4} cols={8} />}
      {isError && <ErrorMessage>No se pudo cargar la lista de reglas.</ErrorMessage>}
      {rules && rules.length === 0 && <p className="text-sm text-slate-500">Todavía no hay reglas de alerta configuradas.</p>}

      {rules && rules.length > 0 && (
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Nombre</th>
              <th className="px-4 py-2 font-medium">Alcance</th>
              <th className="px-4 py-2 font-medium">Métrica</th>
              <th className="px-4 py-2 font-medium">Condición</th>
              <th className="px-4 py-2 font-medium">Severidad</th>
              <th className="px-4 py-2 font-medium">Espera</th>
              <th className="px-4 py-2 font-medium">Estado</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td className="px-4 py-2 text-slate-100">{rule.name}</td>
                <td className="px-4 py-2 text-slate-400">
                  {rule.scope_id ? hostnameById.get(rule.scope_id) ?? '—' : 'Todos los servidores'}
                </td>
                <td className="px-4 py-2 text-slate-400">
                  {metricLabel[rule.metric] ?? rule.metric}
                  {rule.metric_target && <span className="text-slate-500"> ({rule.metric_target})</span>}
                </td>
                <td className="px-4 py-2 text-slate-400">
                  {conditionSymbol[rule.condition] ?? rule.condition} {rule.threshold}%
                </td>
                <td className="px-4 py-2">
                  <StatusChip tone={severityTone[rule.severity] ?? 'neutral'}>
                    {(severityLabel[rule.severity] ?? rule.severity).toUpperCase()}
                  </StatusChip>
                </td>
                <td className="px-4 py-2 text-slate-400">{rule.cooldown_minutes} min</td>
                <td className="px-4 py-2">
                  <StatusChip tone={rule.enabled ? 'ok' : 'neutral'}>{rule.enabled ? 'ACTIVA' : 'INACTIVA'}</StatusChip>
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-right">
                  <AlertRuleFormDialog rule={rule} trigger={<Button variant="ghost" size="sm">Editar</Button>} />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (confirm(`¿Eliminar la regla "${rule.name}"?`)) deleteMutation.mutate(rule.id)
                    }}
                  >
                    Eliminar
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}

const AUDIT_PAGE_SIZE = 20

function dayLabel(date: Date): string {
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  if (date.toDateString() === today.toDateString()) return 'Hoy'
  if (date.toDateString() === yesterday.toDateString()) return 'Ayer'
  return date.toLocaleDateString('es-PE', {
    day: 'numeric',
    month: 'long',
    year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined,
  })
}

// Groups an already-sorted (newest-first) page of logs into same-day buckets, each
// rendered as its own section — turns one long undifferentiated table into scannable
// chunks ("Hoy", "Ayer", "3 de septiembre"...) instead of one continuous scrollbar.
function groupLogsByDay(logs: AuditLogEntry[]): { key: string; label: string; items: AuditLogEntry[] }[] {
  const order: string[] = []
  const map = new Map<string, AuditLogEntry[]>()
  for (const log of logs) {
    const key = new Date(log.created_at).toDateString()
    if (!map.has(key)) {
      map.set(key, [])
      order.push(key)
    }
    map.get(key)!.push(log)
  }
  return order.map((key) => ({ key, label: dayLabel(new Date(key)), items: map.get(key)! }))
}

function AuditTab() {
  const [entityType, setEntityType] = useState(ALL)
  const [action, setAction] = useState(ALL)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const { data: actions } = useQuery({
    queryKey: ['audit-actions'],
    queryFn: async () => (await api.get<string[]>('/audit-logs/actions')).data,
  })

  const { data: entityTypes } = useQuery({
    queryKey: ['audit-entity-types'],
    queryFn: async () => (await api.get<string[]>('/audit-logs/entity-types')).data,
  })

  const { data: logs, isLoading, isError } = useQuery({
    queryKey: ['audit-logs', entityType, action],
    queryFn: async () =>
      (
        await api.get<AuditLogEntry[]>('/audit-logs', {
          params: {
            entity_type: entityType === ALL ? undefined : entityType,
            action: action === ALL ? undefined : action,
            limit: 300,
          },
        })
      ).data,
  })

  const filteredLogs = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return logs ?? []
    return (logs ?? []).filter((log) => {
      const haystack = [
        log.user_full_name ?? 'anónimo',
        actionLabel(log.action),
        entityLabel(log.entity_type),
        log.ip_address ?? '',
        formatDetails(log.details),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(term)
    })
  }, [logs, search])

  const totalPages = Math.max(1, Math.ceil(filteredLogs.length / AUDIT_PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageLogs = filteredLogs.slice((currentPage - 1) * AUDIT_PAGE_SIZE, currentPage * AUDIT_PAGE_SIZE)
  const groups = groupLogsByDay(pageLogs)

  function updateFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-sm font-medium text-slate-300">Auditoría</h3>
        <p className="text-sm text-slate-500">Registro de quién hizo qué en la plataforma.</p>
      </div>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            placeholder="Buscar por usuario, acción, elemento, IP…"
            value={search}
            onChange={(e) => updateFilter(setSearch)(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={entityType} onValueChange={updateFilter(setEntityType)}>
          <SelectTrigger className="sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todos los tipos de registro</SelectItem>
            {(entityTypes ?? []).map((t) => (
              <SelectItem key={t} value={t}>
                {entityLabel(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={action} onValueChange={updateFilter(setAction)}>
          <SelectTrigger className="sm:w-72">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todas las acciones</SelectItem>
            {(actions ?? []).map((a) => (
              <SelectItem key={a} value={a}>
                {actionLabel(a)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <TableSkeleton rows={6} cols={6} />}
      {isError && <ErrorMessage>No se pudo cargar el registro de auditoría.</ErrorMessage>}
      {logs && logs.length === 0 && <p className="text-sm text-slate-500">No hay eventos registrados.</p>}
      {logs && logs.length > 0 && filteredLogs.length === 0 && (
        <p className="text-sm text-slate-500">Ningún evento coincide con la búsqueda.</p>
      )}

      {pageLogs.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900/60 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Hora</th>
                <th className="px-4 py-2 font-medium">Usuario</th>
                <th className="px-4 py-2 font-medium" title="Qué se hizo">
                  Acción realizada
                </th>
                <th className="px-4 py-2 font-medium" title="Sobre qué elemento del sistema">
                  Sobre
                </th>
                <th className="px-4 py-2 font-medium" title="Información adicional del evento">
                  Detalles
                </th>
                <th className="px-4 py-2 font-medium" title="Dirección de red desde donde se realizó la acción">
                  IP de origen
                </th>
              </tr>
            </thead>
            {groups.map((group) => (
              <tbody key={group.key} className="divide-y divide-slate-800">
                <tr>
                  <td colSpan={6} className="bg-slate-900/80 px-4 py-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
                    {group.label} <span className="normal-case text-slate-500">· {group.items.length} evento{group.items.length !== 1 ? 's' : ''}</span>
                  </td>
                </tr>
                {group.items.map((log) => (
                  <tr key={log.id}>
                    <td className="whitespace-nowrap px-4 py-2 text-slate-400">
                      {new Date(log.created_at).toLocaleTimeString('es-PE')}
                    </td>
                    <td className="px-4 py-2 text-slate-100">{log.user_full_name ?? 'Anónimo'}</td>
                    <td className="px-4 py-2">
                      <Badge variant="default">{actionLabel(log.action)}</Badge>
                    </td>
                    <td className="px-4 py-2 text-slate-400">{entityLabel(log.entity_type)}</td>
                    <td className="max-w-md px-4 py-2 text-xs text-slate-500">{formatDetails(log.details)}</td>
                    <td className="px-4 py-2 text-slate-500">{log.ip_address ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}

      {filteredLogs.length > 0 && (
        <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
          <p className="text-xs text-slate-500">
            Mostrando {(currentPage - 1) * AUDIT_PAGE_SIZE + 1}–{Math.min(currentPage * AUDIT_PAGE_SIZE, filteredLogs.length)} de{' '}
            {filteredLogs.length} {filteredLogs.length === 1 ? 'evento' : 'eventos'}
          </p>
          <Pagination page={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </div>
      )}
    </div>
  )
}

const tabs: { key: Tab; label: string }[] = [
  { key: 'users', label: 'Usuarios' },
  { key: 'roles', label: 'Perfiles' },
  { key: 'sites', label: 'Sedes' },
  { key: 'alerts', label: 'Alertas' },
  { key: 'audit', label: 'Auditoría' },
]

export function AdminPage() {
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('users')

  if (!user?.is_superuser) {
    return <Navigate to="/" replace />
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-base font-medium text-slate-200">Administración</h2>
        <p className="text-sm text-slate-500">Control de usuarios, perfiles de acceso y sedes institucionales.</p>
      </div>

      <div className="mb-6 flex gap-1 border-b border-slate-800">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'px-4 py-2 text-sm transition-colors',
              tab === t.key
                ? 'border-b-2 border-amber-500 text-slate-100'
                : 'text-slate-400 hover:text-slate-200',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'users' && <UsersTab />}
      {tab === 'roles' && <RolesTab />}
      {tab === 'sites' && <SitesTab />}
      {tab === 'alerts' && <AlertsTab />}
      {tab === 'audit' && <AuditTab />}
    </div>
  )
}
