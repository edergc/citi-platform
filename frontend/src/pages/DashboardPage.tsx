import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, GitBranch, HelpCircle, Search, XCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { CardGridSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { SystemFormDialog } from '@/components/SystemFormDialog'
import { HexagonStat, HexagonLegend } from '@/components/ui/hexagon-stat'
import { StatusChip } from '@/components/ui/status-chip'
import type { RecentIncident, Service, ServiceStatus, System, SystemCriticality, SystemStatus } from '@/types'
import { timeAgo } from '@/lib/format'

const incidentSeverityTone: Record<string, 'info' | 'warning' | 'critical'> = {
  info: 'info',
  warning: 'warning',
  critical: 'critical',
}

type HealthStatus = 'operational' | 'degraded' | 'down' | 'unknown'

const criticalityVariant: Record<SystemCriticality, 'default' | 'info' | 'warning' | 'danger'> = {
  low: 'default',
  medium: 'info',
  high: 'warning',
  critical: 'danger',
}

const criticalityLabel: Record<SystemCriticality, string> = {
  low: 'Baja',
  medium: 'Media',
  high: 'Alta',
  critical: 'Crítica',
}

const statusTone: Record<SystemStatus, 'ok' | 'warning' | 'neutral'> = {
  active: 'ok',
  maintenance: 'warning',
  retired: 'neutral',
}

const statusLabel: Record<SystemStatus, string> = {
  active: 'Activo',
  maintenance: 'Mantenimiento',
  retired: 'Retirado',
}

const statusHexColor: Record<SystemStatus, string> = {
  active: '#34d399',
  maintenance: '#a78bfa',
  retired: '#64748b',
}

const healthMeta: Record<HealthStatus, { label: string; tone: 'ok' | 'warning' | 'critical' | 'neutral'; icon: typeof CheckCircle2 }> = {
  operational: { label: 'Operativo', tone: 'ok', icon: CheckCircle2 },
  degraded: { label: 'Degradado', tone: 'warning', icon: AlertTriangle },
  down: { label: 'Caído', tone: 'critical', icon: XCircle },
  unknown: { label: 'Sin datos', tone: 'neutral', icon: HelpCircle },
}

function computeHealth(statuses: ServiceStatus[]): HealthStatus {
  if (statuses.length === 0) return 'unknown'
  if (statuses.every((s) => s === 'stopped')) return 'down'
  if (statuses.some((s) => s === 'stopped' || s === 'degraded')) return 'degraded'
  return 'operational'
}

export function DashboardPage() {
  const [search, setSearch] = useState('')
  const [criticalityFilter, setCriticalityFilter] = useState<SystemCriticality | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<SystemStatus | 'all'>('all')

  const { data: systems, isLoading, isError } = useQuery({
    queryKey: ['systems'],
    queryFn: async () => (await api.get<System[]>('/systems')).data,
  })

  const { data: services } = useQuery({
    queryKey: ['services'],
    queryFn: async () => (await api.get<Service[]>('/services')).data,
  })

  const { data: incidents } = useQuery({
    queryKey: ['systems', 'recent-incidents'],
    queryFn: async () => (await api.get<RecentIncident[]>('/systems/recent-incidents', { params: { limit: 8 } })).data,
    refetchInterval: 30000,
  })

  const servicesBySystem = useMemo(() => {
    const map = new Map<string, Service[]>()
    for (const service of services ?? []) {
      const list = map.get(service.system_id) ?? []
      list.push(service)
      map.set(service.system_id, list)
    }
    return map
  }, [services])

  const filteredSystems = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (systems ?? []).filter((system) => {
      if (criticalityFilter !== 'all' && system.criticality !== criticalityFilter) return false
      if (statusFilter !== 'all' && system.status !== statusFilter) return false
      if (
        term &&
        !system.name.toLowerCase().includes(term) &&
        !(system.description ?? '').toLowerCase().includes(term) &&
        !(system.category ?? '').toLowerCase().includes(term)
      ) {
        return false
      }
      return true
    })
  }, [systems, search, criticalityFilter, statusFilter])

  const stats = useMemo(() => {
    const all = systems ?? []
    return {
      total: all.length,
      active: all.filter((s) => s.status === 'active').length,
      maintenance: all.filter((s) => s.status === 'maintenance').length,
      retired: all.filter((s) => s.status === 'retired').length,
      critical: all.filter((s) => s.criticality === 'critical').length,
    }
  }, [systems])

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-base font-medium text-slate-200">Centro de Aplicaciones</h2>
          <p className="text-sm text-slate-500">Sistemas institucionales administrados por CITI Platform.</p>
        </div>
        <SystemFormDialog trigger={<Button size="sm">+ Nuevo sistema</Button>} />
      </div>

      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-center gap-6 py-5">
          <HexagonStat
            segments={[
              { value: stats.maintenance, color: statusHexColor.maintenance, label: 'Mantenimiento' },
              { value: stats.retired, color: statusHexColor.retired, label: 'Retirados' },
              { value: stats.active, color: statusHexColor.active, label: 'Activos' },
            ]}
          />
          <HexagonLegend
            segments={[
              { value: stats.maintenance, color: statusHexColor.maintenance, label: 'Mantenimiento' },
              { value: stats.retired, color: statusHexColor.retired, label: 'Retirados' },
              { value: stats.active, color: statusHexColor.active, label: 'Activos' },
            ]}
          />
          <div className="ml-auto text-right">
            <p className="text-3xl font-semibold text-red-400">{stats.critical}</p>
            <p className="text-xs uppercase tracking-wide text-slate-500">sistemas críticos</p>
          </div>
        </CardContent>
      </Card>

      {incidents && incidents.length > 0 && (
        <Card className="mb-6">
          <CardContent className="py-4">
            <h3 className="mb-3 text-sm font-medium text-slate-200">Incidentes recientes</h3>
            <div className="flex flex-col divide-y divide-slate-800">
              {incidents.map((incident) => (
                <div key={incident.id} className="flex items-start justify-between gap-4 py-2">
                  <div>
                    <p className="text-sm text-slate-200">{incident.title}</p>
                    <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{incident.message}</p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <StatusChip tone={incidentSeverityTone[incident.severity] ?? 'neutral'}>{incident.severity.toUpperCase()}</StatusChip>
                    <span className="text-xs text-slate-500">{timeAgo(incident.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            placeholder="Buscar por nombre, categoría o descripción…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={criticalityFilter} onValueChange={(v) => setCriticalityFilter(v as SystemCriticality | 'all')}>
          <SelectTrigger className="sm:w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toda criticidad</SelectItem>
            <SelectItem value="low">Baja</SelectItem>
            <SelectItem value="medium">Media</SelectItem>
            <SelectItem value="high">Alta</SelectItem>
            <SelectItem value="critical">Crítica</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as SystemStatus | 'all')}>
          <SelectTrigger className="sm:w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todo estado</SelectItem>
            <SelectItem value="active">Activo</SelectItem>
            <SelectItem value="maintenance">Mantenimiento</SelectItem>
            <SelectItem value="retired">Retirado</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading && <CardGridSkeleton count={6} />}
      {isError && <ErrorMessage>No se pudo cargar la lista de sistemas.</ErrorMessage>}
      {systems && systems.length === 0 && (
        <p className="text-sm text-slate-400">Todavía no hay sistemas registrados.</p>
      )}
      {systems && systems.length > 0 && filteredSystems.length === 0 && (
        <p className="text-sm text-slate-500">Ningún sistema coincide con los filtros aplicados.</p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filteredSystems.map((system) => {
          const systemServices = servicesBySystem.get(system.id) ?? []
          const health = computeHealth(systemServices.map((s) => s.status))
          const HealthIcon = healthMeta[health].icon

          return (
            <Link key={system.id} to={`/systems/${system.id}`}>
              <Card className="flex h-full flex-col transition-colors hover:border-slate-700">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle>{system.name}</CardTitle>
                    <StatusChip tone={statusTone[system.status]}>{statusLabel[system.status].toUpperCase()}</StatusChip>
                  </div>
                  <CardDescription className="line-clamp-2">
                    {system.description ?? 'Sin descripción'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="mt-auto flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <Badge variant={criticalityVariant[system.criticality]}>
                      {criticalityLabel[system.criticality]}
                    </Badge>
                    {system.category && <span className="text-xs text-slate-500">{system.category}</span>}
                  </div>
                  <div className="flex items-center justify-between border-t border-slate-800 pt-3 text-xs">
                    <span className="flex items-center gap-1.5">
                      <StatusChip tone={healthMeta[health].tone} className="gap-1">
                        <HealthIcon className="h-3 w-3" />
                        {healthMeta[health].label.toUpperCase()}
                      </StatusChip>
                      <span className="text-slate-500">
                        ({systemServices.length} {systemServices.length === 1 ? 'servicio' : 'servicios'})
                      </span>
                    </span>
                    {system.repo_url && (
                      <span className="flex items-center gap-1 text-slate-500">
                        <GitBranch className="h-3.5 w-3.5" />
                        {system.default_branch}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
