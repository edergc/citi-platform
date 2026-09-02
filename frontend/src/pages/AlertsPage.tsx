import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '@/lib/api'
import type { AlertEvent, AlertEventStatus, AlertMetric, AlertSeverityLevel, Site } from '@/types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TableSkeleton } from '@/components/ui/skeleton'
import { ErrorMessage } from '@/components/ui/error-message'
import { HexagonStat, HexagonLegend } from '@/components/ui/hexagon-stat'
import { StatusChip } from '@/components/ui/status-chip'
import { cn } from '@/lib/utils'
import { timeAgo } from '@/lib/format'

const ALL = '__all__'
const PAGE_SIZE = 30

const severityTone: Record<AlertSeverityLevel, 'info' | 'warning' | 'critical'> = {
  info: 'info',
  warning: 'warning',
  critical: 'critical',
}
const severityColor: Record<AlertSeverityLevel, string> = {
  info: '#38bdf8',
  warning: '#fbbf24',
  critical: '#f87171',
}
const severityLabel: Record<AlertSeverityLevel, string> = {
  info: 'Informativo',
  warning: 'Advertencia',
  critical: 'Crítico',
}
const severityBorder: Record<AlertSeverityLevel, string> = {
  info: 'border-l-sky-400',
  warning: 'border-l-amber-400',
  critical: 'border-l-red-400',
}
const metricLabel: Record<AlertMetric, string> = {
  ram_percent: 'RAM',
  cpu_percent: 'CPU',
  disk_percent_used: 'Disco',
  network_reachable: 'Red: sin respuesta',
  network_latency_ms: 'Red: latencia',
  network_loss_percent: 'Red: pérdida',
}
const statusLabel: Record<AlertEventStatus, string> = {
  open: 'Abierta',
  resolved: 'Resuelta',
}

const VALID_SEVERITIES = ['critical', 'warning', 'info'] as const

export function AlertsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()

  // Lets links (e.g. the critical-alert banner) land here pre-filtered — read once at
  // mount, same "deep-linkable" spirit as ServersPage's ?site= filter, but this one
  // doesn't need to stay in sync with the URL afterward since it's just a starting point.
  const initialSeverity = searchParams.get('severity')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<AlertEventStatus | typeof ALL>('open')
  const [severityFilter, setSeverityFilter] = useState<AlertSeverityLevel | typeof ALL>(
    (VALID_SEVERITIES as readonly string[]).includes(initialSeverity ?? '') ? (initialSeverity as AlertSeverityLevel) : ALL,
  )
  const [siteFilter, setSiteFilter] = useState(ALL)
  const [limit, setLimit] = useState(PAGE_SIZE)

  const { data: sites } = useQuery({
    queryKey: ['sites'],
    queryFn: async () => (await api.get<Site[]>('/sites')).data,
  })

  // Separate from the filtered/paginated list below so the stat cards always reflect the
  // true open-alert counts, not just whatever page of filtered results happens to be
  // loaded — 300 is the backend's max page size and comfortably covers this fleet's size.
  const { data: openEvents } = useQuery({
    queryKey: ['alert-rules', 'events', 'open-counts'],
    queryFn: async () =>
      (await api.get<AlertEvent[]>('/alert-rules/events', { params: { status_filter: 'open', limit: 300 } })).data,
    refetchInterval: 30000,
  })

  const severityCounts: Record<AlertSeverityLevel, number> = { critical: 0, warning: 0, info: 0 }
  for (const e of openEvents ?? []) severityCounts[e.severity]++

  const {
    data: events,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['alert-rules', 'events', 'browse', { search, statusFilter, severityFilter, siteFilter, limit }],
    queryFn: async () =>
      (
        await api.get<AlertEvent[]>('/alert-rules/events', {
          params: {
            limit,
            ...(search.trim() ? { search: search.trim() } : {}),
            ...(statusFilter !== ALL ? { status_filter: statusFilter } : {}),
            ...(severityFilter !== ALL ? { severity_filter: severityFilter } : {}),
            ...(siteFilter !== ALL ? { site_id_filter: siteFilter } : {}),
          },
        })
      ).data,
    refetchInterval: 30000,
  })

  const acknowledgeEvent = useMutation({
    mutationFn: async (eventId: string) => api.post<AlertEvent>(`/alert-rules/events/${eventId}/acknowledge`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules', 'events'] })
    },
  })

  // Fires one acknowledge call per event (reusing the same per-event permission check the
  // single-item button already relies on) rather than a dedicated bulk endpoint — simplest
  // correct option at this scale, and it can't silently skip an event the caller isn't
  // actually allowed to acknowledge.
  const acknowledgeAll = useMutation({
    mutationFn: async (eventIds: string[]) =>
      Promise.all(eventIds.map((id) => api.post<AlertEvent>(`/alert-rules/events/${id}/acknowledge`))),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules', 'events'] })
    },
  })

  const unacknowledgedVisible = (events ?? []).filter((e) => e.status === 'open' && !e.acknowledged_at)

  function updateFilter<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value)
      setLimit(PAGE_SIZE)
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-slate-100">Alertas</h2>
        <p className="mt-1 text-sm text-slate-400">
          Historial de alertas disparadas por las reglas de umbral configuradas, con reconocimiento por usuario.
        </p>
      </div>

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-6 py-5">
          <HexagonStat
            segments={[
              { value: severityCounts.critical, color: severityColor.critical, label: 'Críticas abiertas' },
              { value: severityCounts.warning, color: severityColor.warning, label: 'Advertencias abiertas' },
              { value: severityCounts.info, color: severityColor.info, label: 'Informativas abiertas' },
            ]}
          />
          <HexagonLegend
            segments={[
              { value: severityCounts.critical, color: severityColor.critical, label: 'Críticas abiertas' },
              { value: severityCounts.warning, color: severityColor.warning, label: 'Advertencias abiertas' },
              { value: severityCounts.info, color: severityColor.info, label: 'Informativas abiertas' },
            ]}
          />
        </CardContent>
      </Card>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            placeholder="Buscar por regla o hostname…"
            value={search}
            onChange={(e) => updateFilter(setSearch)(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={statusFilter} onValueChange={updateFilter((v: string) => setStatusFilter(v as typeof statusFilter))}>
          <SelectTrigger className="sm:w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todo estado</SelectItem>
            <SelectItem value="open">Abiertas</SelectItem>
            <SelectItem value="resolved">Resueltas</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={severityFilter}
          onValueChange={updateFilter((v: string) => setSeverityFilter(v as typeof severityFilter))}
        >
          <SelectTrigger className="sm:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Toda severidad</SelectItem>
            <SelectItem value="critical">Crítico</SelectItem>
            <SelectItem value="warning">Advertencia</SelectItem>
            <SelectItem value="info">Informativo</SelectItem>
          </SelectContent>
        </Select>
        <Select value={siteFilter} onValueChange={updateFilter(setSiteFilter)}>
          <SelectTrigger className="sm:w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todas las sedes</SelectItem>
            {sites?.map((site) => (
              <SelectItem key={site.id} value={site.id}>
                {site.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading && <TableSkeleton rows={8} cols={7} />}
      {isError && <ErrorMessage>No se pudo cargar el historial de alertas.</ErrorMessage>}
      {events && events.length === 0 && (
        <p className="text-sm text-slate-500">Ninguna alerta coincide con los filtros aplicados.</p>
      )}

      {unacknowledgedVisible.length > 1 && (
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs text-slate-500">
            {unacknowledgedVisible.length} sin reconocer en esta vista
          </p>
          <Button
            size="sm"
            variant="outline"
            disabled={acknowledgeAll.isPending}
            onClick={() => acknowledgeAll.mutate(unacknowledgedVisible.map((e) => e.id))}
          >
            {acknowledgeAll.isPending ? 'Reconociendo…' : 'Reconocer todas'}
          </Button>
        </div>
      )}

      {events && events.length > 0 && (
        <div className="flex flex-col gap-2">
          {events.map((event) => (
            <div
              key={event.id}
              className={cn(
                'flex flex-col gap-2 rounded-lg border border-l-4 border-slate-800 bg-slate-900/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between',
                severityBorder[event.severity],
                event.status === 'resolved' && 'opacity-60',
              )}
            >
              <div
                className={cn('flex min-w-0 flex-1 flex-col gap-1', event.server_id && 'cursor-pointer')}
                onClick={() => event.server_id && navigate(`/servers/${event.server_id}`)}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusChip tone={severityTone[event.severity]}>{severityLabel[event.severity].toUpperCase()}</StatusChip>
                  <StatusChip tone={event.status === 'open' ? 'warning' : 'ok'}>{statusLabel[event.status].toUpperCase()}</StatusChip>
                  {event.during_maintenance && <Badge variant="maintenance">Mantenimiento</Badge>}
                  <span className="text-sm font-medium text-slate-100">{event.rule_name}</span>
                </div>
                <p className="text-xs text-slate-500">
                  {metricLabel[event.metric]}
                  {event.metric_target ? ` (${event.metric_target})` : ''}
                  {event.value != null && ` · ${event.value.toFixed(1)}%`}
                  {event.hostname && (
                    <>
                      {' · '}
                      <span className="text-slate-400">{event.hostname}</span>
                    </>
                  )}
                  {event.site_name && ` · ${event.site_name}`}
                  {!event.server_id && ' · Regla global'}
                </p>
              </div>

              <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end" onClick={(e) => e.stopPropagation()}>
                <span className="text-xs text-slate-500">
                  Disparada {timeAgo(event.triggered_at)}
                  {event.resolved_at && ` · Resuelta ${timeAgo(event.resolved_at)}`}
                </span>
                {event.acknowledged_at ? (
                  <span className="text-xs text-slate-500">
                    Reconocida por {event.acknowledged_by_name ?? 'alguien'} · {timeAgo(event.acknowledged_at)}
                  </span>
                ) : event.status === 'open' ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={acknowledgeEvent.isPending}
                    onClick={() => acknowledgeEvent.mutate(event.id)}
                  >
                    Reconocer
                  </Button>
                ) : null}
              </div>
            </div>
          ))}

          {events.length === limit && (
            <Button variant="outline" size="sm" className="self-center" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
              Cargar más
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
